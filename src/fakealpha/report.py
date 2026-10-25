"""Artifact generation: tables, figures, and a reproducibility manifest."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .pipeline import FAMILY_ORDER, summarise

FAMILY_LABELS = {
    "honest": "Honest",
    "same_bar_fill": "Same-bar fill",
    "target_feature": "Target feature",
    "full_sample_target_encoding": "Full-sample encoding",
    "shuffled_cv": "Shuffled CV",
    "survivorship": "Survivorship",
    "p_hacked_selection": "P-hacked selection",
}
GATES = [
    ("suspicion_dsr", "Deflated Sharpe"),
    ("suspicion_pbo", "PBO"),
    ("suspicion_reality_check", "Reality check"),
    ("suspicion_split", "Split-half"),
    ("suspicion_audit", "Artifact audit"),
]


def _version(package: str) -> str:
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return "unknown"


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def write_tables(rows: pd.DataFrame, summary: pd.DataFrame, root: Path, config: dict) -> None:
    tables = root / config["paths"]["tables"]
    tables.mkdir(parents=True, exist_ok=True)
    rows.to_csv(tables / "per_replicate.csv", index=False)
    summary.to_csv(tables / "summary.csv", index=False)
    honest = rows[rows["family"] == "honest"]
    honest_summary = pd.DataFrame(
        [
            {
                "n": int(len(honest)),
                "mean_sr": float(honest["sr"].mean()),
                "median_sr": float(honest["sr"].median()),
                "sd_sr": float(honest["sr"].std(ddof=1)),
                "publishable_dsr": float(honest["publishable_dsr"].mean()),
                "publishable_reality_check": float(
                    honest["publishable_reality_check"].mean()
                ),
                **{
                    f"mean_{gate}": float(honest[gate].mean())
                    for gate in (
                        "suspicion_dsr",
                        "suspicion_pbo",
                        "suspicion_reality_check",
                        "suspicion_split",
                        "suspicion_audit",
                    )
                },
            }
        ]
    )
    honest_summary.to_csv(tables / "honest_controls.csv", index=False)
    thresholds = {
        row["family"]: {
            key: float(row[key])
            for key in row.index
            if key.startswith("threshold_")
        }
        for _, row in summary.iterrows()
    }
    (tables / "thresholds.json").write_text(json.dumps(thresholds, indent=2) + "\n")


def make_figures(rows: pd.DataFrame, summary: pd.DataFrame, root: Path, config: dict) -> None:
    figures = root / config["paths"]["figures"]
    figures.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    families = list(FAMILY_ORDER)
    order = ["honest", *families]
    data = [rows.loc[rows["family"] == f, "sr"].to_numpy() for f in order]
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    ax.boxplot(data, widths=0.55, showfliers=False, medianprops={"color": "#222"})
    rng = np.random.default_rng(7)
    for i, values in enumerate(data, start=1):
        jitter = rng.uniform(-0.16, 0.16, size=len(values))
        ax.scatter(i + jitter, values, s=12, alpha=0.55, color="#2a6fbb", zorder=3)
    ax.axhline(0, color="#999", linewidth=0.8, linestyle="--")
    ax.set_xticks(range(1, len(order) + 1))
    ax.set_xticklabels([FAMILY_LABELS[f] for f in order], rotation=20, ha="right")
    ax.set_ylabel("Annualized Sharpe ratio")
    ax.set_title("Reported Sharpe ratio by pipeline family")
    fig.tight_layout()
    fig.savefig(figures / "sr_by_family.png")
    plt.close(fig)

    gates_for_plot = [
        ("tpr_dsr", "Deflated Sharpe"),
        ("tpr_pbo", "PBO"),
        ("tpr_reality_check", "Reality check"),
        ("tpr_split_half", "Split-half"),
        ("tpr_combined", "Combined (5% FPR)"),
        ("tpr_audit", "Artifact audit"),
    ]
    x = np.arange(len(families))
    width = 0.13
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    for i, (column, label) in enumerate(gates_for_plot):
        values = summary.set_index("family").loc[families, column].to_numpy(dtype=float)
        ax.bar(x + (i - (len(gates_for_plot) - 1) / 2) * width, values, width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels([FAMILY_LABELS[f] for f in families], rotation=20, ha="right")
    ax.set_ylabel("True-positive rate at 5% FPR")
    ax.set_ylim(0, 1.02)
    ax.set_title("Detection of contaminated backtests")
    ax.legend(ncol=3, fontsize=7.5, frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "detection_tpr.png")
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(8.4, 6.0))
    honest = rows[rows["family"] == "honest"]
    contaminated = rows[rows["family"] != "honest"]
    for ax, (column, label) in zip(axes.ravel(), GATES[:4], strict=False):
        bins = np.linspace(
            min(honest[column].min(), contaminated[column].min()),
            max(honest[column].max(), contaminated[column].max()),
            28,
        )
        ax.hist(
            honest[column],
            bins=bins,
            alpha=0.55,
            label="Honest",
            color="#4c78a8",
            density=True,
        )
        ax.hist(
            contaminated[column],
            bins=bins,
            alpha=0.45,
            label="Contaminated",
            color="#e45756",
            density=True,
        )
        ax.set_title(label)
        ax.set_yticks([])
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle("Suspicion scores: honest controls versus contaminated pipelines")
    fig.tight_layout()
    fig.savefig(figures / "gate_distributions.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    for _, row in summary.iterrows():
        ax.scatter(
            row["sr_inflation"],
            row["tpr_combined"],
            s=55,
            color="#e45756" if row["tpr_combined"] < 0.5 else "#54a24b",
        )
        ax.annotate(
            FAMILY_LABELS.get(row["family"], row["family"]),
            (row["sr_inflation"], row["tpr_combined"]),
            xytext=(6, 5),
            textcoords="offset points",
            fontsize=7.5,
        )
    ax.axhline(0.05, color="#999", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Mean Sharpe inflation relative to honest pipeline")
    ax.set_ylabel("Combined-gate TPR at 5% FPR")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Inflation versus detectability")
    fig.tight_layout()
    fig.savefig(figures / "inflation_vs_detection.png")
    plt.close(fig)



    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    observed = False
    for _, row in summary.iterrows():
        ax.scatter(
            row["sr_inflation"],
            row["tpr_combined"],
            s=55,
            marker="o",
            color="#4c78a8",
            label=None if observed else "Combined screen",
            zorder=3,
        )
        ax.scatter(
            row["sr_inflation"],
            row["tpr_audit"],
            s=55,
            marker="s",
            color="#e45756",
            label=None if observed else "Artifact audit",
            zorder=3,
        )
        ax.annotate(
            FAMILY_LABELS.get(row["family"], row["family"]),
            (row["sr_inflation"], row["tpr_combined"]),
            xytext=(7, 5),
            textcoords="offset points",
            fontsize=7.5,
        )
        observed = True
    ax.set_xscale("symlog", linthresh=0.1)
    ax.axhline(0.05, color="#999", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Mean Sharpe inflation relative to the honest pipeline")
    ax.set_ylabel("TPR at 5% FPR")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Detection power grows with the size of the leak")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(figures / "audit_vs_combined.png")
    plt.close(fig)


def write_manifest(
    rows: pd.DataFrame,
    summary: pd.DataFrame,
    metadata: dict,
    config: dict,
    root: Path,
) -> None:
    results = root / config["paths"]["results"]
    results.mkdir(parents=True, exist_ok=True)
    data_manifest = root / config["paths"]["data_raw"] / "manifest.json"
    processed = root / config["paths"]["data_processed"]
    processed_data = {}
    for name in ("prices.csv", "returns.csv"):
        path = processed / name
        if path.exists():
            processed_data[name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": int(path.stat().st_size),
            }
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            name: _version(name)
            for name in ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "PyYAML")
        },
        "config": config,
        "metadata": metadata,
        "n_rows": int(len(rows)),
        "families": sorted(rows["family"].unique().tolist()),
        "data_manifest": (
            json.loads(data_manifest.read_text()) if data_manifest.exists() else None
        ),
        "processed_data": processed_data,
        "summary": summary.to_dict(orient="records"),
    }
    (results / "run_manifest.json").write_text(
        json.dumps(_json_safe(manifest), indent=2, sort_keys=True) + "\n"
    )


def write_outputs(
    rows: pd.DataFrame, metadata: dict, config: dict, root: Path
) -> pd.DataFrame:
    summary = summarise(rows)
    write_tables(rows, summary, root, config)
    make_figures(rows, summary, root, config)
    write_manifest(rows, summary, metadata, config, root)
    return summary


def report_from_saved(config: dict, root: Path) -> pd.DataFrame:
    tables = root / config["paths"]["tables"]
    rows = pd.read_csv(tables / "per_replicate.csv")
    summary = summarise(rows)
    summary.to_csv(tables / "summary.csv", index=False)
    make_figures(rows, summary, root, config)
    return summary
