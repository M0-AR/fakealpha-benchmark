import json

import pandas as pd
import pytest

from fakealpha.data import (
    DataError,
    _parse_chart,
    _validate,
    load_processed,
    write_processed,
)


def _payload(days=5):
    timestamps = [
        int(pd.Timestamp(f"2020-01-{i + 1:02d}", tz="UTC").timestamp()) for i in range(days)
    ]
    closes = [100.0 + i for i in range(days)]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "TEST", "currency": "USD"},
                        "timestamp": timestamps,
                        "indicators": {
                            "adjclose": [{"adjclose": closes}],
                            "quote": [{"close": closes, "volume": [1000] * days}],
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode()


def test_parse_chart_returns_sorted_frame():
    frame, meta = _parse_chart(_payload())
    assert meta["symbol"] == "TEST"
    assert len(frame) == 5
    assert frame["date"].is_monotonic_increasing
    assert (frame["adjclose"] > 0).all()


def test_parse_chart_rejects_empty_payload():
    with pytest.raises(DataError):
        _parse_chart(b'{"chart": {"result": []}}')


def test_validate_flags_duplicate_dates():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-02"]),
            "close": [1.0, 1.0, 1.0],
            "adjclose": [1.0, 1.0, 1.0],
        }
    )
    checks = _validate(frame)
    assert checks["duplicate_dates"] == 1
    assert checks["status"] == "warn"


def test_processed_panel_round_trips_exactly(tmp_path):
    dates = pd.date_range("2020-01-01", periods=600, freq="B")
    values = 100 + pd.Series(range(600), dtype="float64") * 0.123456789012345
    panel = pd.DataFrame({"AAA": values, "BBB": values * 1.7}, index=dates)
    panel.index.name = "date"
    config = {"paths": {"data_processed": "data/processed"}}
    write_processed(panel, config, tmp_path)
    assert load_processed(config, tmp_path).equals(panel)
