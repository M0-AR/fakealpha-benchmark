"""Descriptive statistics used in the paper. Run after `fakealpha fetch`."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from fakealpha.data import load_panel
from fakealpha.features import compute_features
from fakealpha.pipeline import build_family_matrices
from fakealpha.stats import sharpe


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    config = yaml.safe_load((root / "config/experiment.yaml").read_text())
    prices = load_panel(config, root)
    returns = prices.pct_change(fill_method=None)
    test = returns.loc["2012-01-01":"2025-12-31"]

    equal_weight = test.mean(axis=1)
    sixty_forty = 0.6 * test["SPY"] + 0.4 * test["TLT"]
    features = compute_features(prices)
    matrices = build_family_matrices(prices, features, config)
    honest = matrices["honest"].loc["2012-01-01":"2025-12-31"].dropna(how="any")
    corr = honest.corr().to_numpy()
    eigenvalues = np.linalg.eigvalsh(corr)
    participation = float(eigenvalues.sum() ** 2 / (eigenvalues**2).sum())
    cumulative = np.cumsum(np.sort(eigenvalues)[::-1]) / eigenvalues.sum()
    pcs_90 = int(np.searchsorted(cumulative, 0.90) + 1)
    pairwise = float((corr.sum() - len(corr)) / (len(corr) * (len(corr) - 1)))

    per_replicate = pd.read_csv(root / "results/tables/per_replicate.csv")
    honest_rows = per_replicate[per_replicate["family"] == "honest"]
    audit = {
        family: {
            "p05": float(group["audit_p"].quantile(0.05)),
            "median": float(group["audit_p"].median()),
            "flag_rate": float((group["audit_p"] <= 0.05).mean()),
        }
        for family, group in per_replicate.groupby("family")
    }

    manifest = json.loads((root / "data/raw/manifest.json").read_text())
    rows = {
        symbol: {
            "rows": value["rows"],
            "first": value["first_date"],
            "last": value["last_date"],
            "sha256": value["sha256"][:16],
            "status": value["validation"]["status"],
            "coverage_missing": value["validation"]["missing_business_day_fraction"],
        }
        for symbol, value in manifest["symbols"].items()
    }

    output = {
        "panel": {
            "rows": int(len(prices)),
            "assets": int(prices.shape[1]),
            "first": str(prices.index.min().date()),
            "last": str(prices.index.max().date()),
            "test_rows": int(len(test)),
        },
        "benchmarks": {
            "spy_sr": sharpe(test["SPY"]),
            "equal_weight_sr": sharpe(equal_weight),
            "sixty_forty_sr": sharpe(sixty_forty),
            "spy_vol": float(test["SPY"].std(ddof=1) * np.sqrt(252)),
            "equal_weight_vol": float(equal_weight.std(ddof=1) * np.sqrt(252)),
        },
        "honest": {
            "mean_sr": float(honest_rows["sr"].mean()),
            "median_sr": float(honest_rows["sr"].median()),
            "sd_sr": float(honest_rows["sr"].std(ddof=1)),
            "min_sr": float(honest_rows["sr"].min()),
            "max_sr": float(honest_rows["sr"].max()),
        },
        "candidate_correlation": {
            "n_candidates": int(honest.shape[1]),
            "mean_pairwise": pairwise,
            "participation_ratio": participation,
            "pcs_for_90pct": pcs_90,
        },
        "audit": audit,
        "data": rows,
    }
    (root / "results/tables/descriptives.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
