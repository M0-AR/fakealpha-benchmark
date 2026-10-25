"""Live market data acquisition, validation, and panel construction.

The Yahoo Finance chart endpoint is fetched with curl because the endpoint
returns HTTP 429 to Python's default TLS fingerprint from some networks while
accepting curl. Raw responses are hashed and retained so every experiment can
be traced to the exact bytes that produced it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits"
    "&includeAdjustedClose=true"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class DataError(RuntimeError):
    """Raised when live market data cannot be obtained or validated."""


def _epoch(value: str | None) -> int:
    if value is None:
        return int(datetime.now(UTC).timestamp())
    return int(pd.Timestamp(value, tz="UTC").timestamp())


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fetch_curl(url: str, destination: Path, timeout: int = 60, retries: int = 6) -> bytes:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    hosts = [url, url.replace("query1.finance.yahoo.com", "query2.finance.yahoo.com")]
    for attempt in range(retries):
        target = hosts[attempt % len(hosts)]
        tmp = destination.with_suffix(".tmp")
        proc = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--compressed",
                "--max-time",
                str(timeout),
                "-A",
                USER_AGENT,
                "-H",
                "Accept: application/json,text/plain,*/*",
                "-H",
                "Accept-Language: en-US,en;q=0.9",
                "-o",
                str(tmp),
                "-w",
                "%{http_code}",
                target,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        code = proc.stdout.strip()
        if code == "200" and tmp.exists():
            payload = tmp.read_bytes()
            tmp.replace(destination)
            return payload
        last_error = f"HTTP {code or '?'} {proc.stderr.strip()}".strip()
        tmp.unlink(missing_ok=True)
        if attempt < retries - 1:
            time.sleep(min(5 * (attempt + 1), 30))
    raise DataError(f"could not fetch {url}: {last_error}")


def _parse_chart(payload: bytes) -> tuple[pd.DataFrame, dict]:
    try:
        doc = json.loads(payload)
        result = doc["chart"]["result"][0]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise DataError(f"unexpected Yahoo payload: {exc}") from exc

    timestamps = result.get("timestamp") or []
    adj = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    close = quote.get("close")
    volume = quote.get("volume")
    if not timestamps or adj is None or close is None:
        raise DataError(f"empty Yahoo series for {result.get('meta', {}).get('symbol')}")

    index = (
        pd.to_datetime(timestamps, unit="s", utc=True)
        .tz_convert("America/New_York")
        .normalize()
        .tz_localize(None)
    )
    frame = pd.DataFrame(
        {
            "date": index,
            "close": pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(),
            "adjclose": pd.to_numeric(pd.Series(adj), errors="coerce").to_numpy(),
            "volume": pd.to_numeric(pd.Series(volume), errors="coerce").to_numpy()
            if volume is not None
            else np.nan,
        }
    )
    frame = (
        frame.dropna(subset=["adjclose"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    frame = frame[frame["adjclose"] > 0]
    if frame.empty:
        raise DataError("Yahoo series has no positive adjusted closes")
    return frame, result.get("meta", {})


def _validate(frame: pd.DataFrame) -> dict:
    dates = pd.DatetimeIndex(frame["date"])
    expected = pd.bdate_range(dates.min(), dates.max())
    gaps = dates.to_series().diff().dt.days.dropna()
    returns = frame["adjclose"].pct_change(fill_method=None)
    ratio = frame["adjclose"] / frame["close"].replace(0, np.nan)
    checks = {
        "monotonic_dates": bool(dates.is_monotonic_increasing),
        "duplicate_dates": int(dates.duplicated().sum()),
        "nonpositive_adjusted": int((frame["adjclose"] <= 0).sum()),
        "missing_business_day_fraction": round(1 - len(dates) / len(expected), 6),
        "max_calendar_gap_days": int(gaps.max()) if len(gaps) else 0,
        "zero_return_fraction": round(float((returns.abs() < 1e-12).mean()), 6),
        "adjustment_ratio_min": round(float(ratio.min()), 6),
        "adjustment_ratio_max": round(float(ratio.max()), 6),
    }
    checks["status"] = (
        "ok"
        if checks["monotonic_dates"]
        and checks["duplicate_dates"] == 0
        and checks["nonpositive_adjusted"] == 0
        and checks["missing_business_day_fraction"] < 0.10
        else "warn"
    )
    return checks


def fetch_universe(config: dict, root: Path, force: bool = False) -> dict:
    """Fetch every symbol, save raw bytes plus a hash manifest."""
    raw_dir = root / config["paths"]["data_raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    start = config["universe"].get("history_start") or config["universe"]["start"]
    end = config["universe"].get("end")
    p1, p2 = _epoch(start), _epoch(end)
    manifest_path = raw_dir / "manifest.json"
    manifest = {"generated_at": datetime.now(UTC).isoformat(), "symbols": {}}
    if manifest_path.exists() and not force:
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            manifest = {"generated_at": None, "symbols": {}}

    for symbol in config["universe"]["symbols"]:
        destination = raw_dir / f"{symbol}.json"
        if destination.exists() and not force and symbol in manifest.get("symbols", {}):
            print(f"[data] cached {symbol}")
            continue
        url = YAHOO_URL.format(symbol=symbol, p1=p1, p2=p2)
        payload = _fetch_curl(url, destination)
        frame, meta = _parse_chart(payload)
        checks = _validate(frame)
        manifest["symbols"][symbol] = {
            "url": url,
            "fetched_at": datetime.now(UTC).isoformat(),
            "sha256": _sha256(payload),
            "bytes": len(payload),
            "rows": int(len(frame)),
            "first_date": str(frame["date"].iloc[0].date()),
            "last_date": str(frame["date"].iloc[-1].date()),
            "last_close": float(frame["close"].iloc[-1]),
            "last_adjusted_close": float(frame["adjclose"].iloc[-1]),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "validation": checks,
        }
        print(
            f"[data] {symbol}: {len(frame)} rows "
            f"{frame['date'].iloc[0].date()}..{frame['date'].iloc[-1].date()} "
            f"({checks['status']})"
        )
        time.sleep(1.0)

    manifest["generated_at"] = datetime.now(UTC).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    bad = [s for s, v in manifest["symbols"].items() if v["validation"]["status"] != "ok"]
    if bad:
        print(f"[data] WARNING: validation warnings for {', '.join(sorted(bad))}")
    return manifest


def load_panel(config: dict, root: Path) -> pd.DataFrame:
    """Build a common adjusted-close panel from cached raw responses."""
    raw_dir = root / config["paths"]["data_raw"]
    symbols = config["universe"]["symbols"]
    frames = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}.json"
        if not path.exists():
            raise DataError(f"missing raw data for {symbol}; run `fakealpha fetch`")
        frame, _ = _parse_chart(path.read_bytes())
        frames[symbol] = frame.set_index("date")["adjclose"].rename(symbol)

    spy = frames.get("SPY")
    if spy is not None:
        calendar = spy.index
    else:
        calendar = pd.concat(frames.values(), axis=1).index
    panel = pd.concat(frames.values(), axis=1).sort_index()
    panel = panel.reindex(pd.DatetimeIndex(calendar).sort_values())
    panel = panel.ffill(limit=3)

    start = pd.Timestamp(config["universe"]["start"])
    end = config["universe"].get("end")
    panel = panel.loc[panel.index >= start]
    if end:
        panel = panel.loc[panel.index <= pd.Timestamp(end)]
    panel = panel.dropna(how="all")
    if len(panel) < 500:
        raise DataError(f"price panel too short: {len(panel)} rows")
    return panel


def load_processed(config: dict, root: Path) -> pd.DataFrame:
    """Load the committed processed panel, used when raw responses are unavailable."""
    path = root / config["paths"]["data_processed"] / "prices.csv"
    if not path.exists():
        raise DataError(f"missing processed panel: {path}; run `fakealpha fetch`")
    panel = pd.read_csv(
        path, parse_dates=["date"], float_precision="round_trip"
    ).set_index("date").sort_index()
    if len(panel) < 500:
        raise DataError(f"price panel too short: {len(panel)} rows")
    return panel


def write_processed(panel: pd.DataFrame, config: dict, root: Path) -> None:
    processed = root / config["paths"]["data_processed"]
    processed.mkdir(parents=True, exist_ok=True)
    panel.to_csv(processed / "prices.csv", index_label="date", float_format="%.17g")
    panel.pct_change(fill_method=None).to_csv(
        processed / "returns.csv", index_label="date", float_format="%.17g"
    )


def panel_report(panel: pd.DataFrame) -> dict:
    returns = panel.pct_change(fill_method=None)
    return {
        "rows": int(len(panel)),
        "columns": list(panel.columns),
        "first_date": str(panel.index.min().date()),
        "last_date": str(panel.index.max().date()),
        "missing_fraction": {c: round(float(panel[c].isna().mean()), 6) for c in panel.columns},
        "zero_return_fraction": {
            c: round(float((returns[c].abs() < 1e-12).mean()), 6) for c in panel.columns
        },
    }
