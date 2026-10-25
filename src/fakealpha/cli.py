"""Command line interface for the FakeAlpha benchmark."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import pandas as pd
import yaml

from .data import (
    fetch_universe,
    load_panel,
    load_processed,
    panel_report,
    write_processed,
)
from .pipeline import run_experiment
from .report import report_from_saved, write_outputs


def _load_config(path: Path) -> tuple[dict, Path]:
    config = yaml.safe_load(path.read_text())
    root = path.resolve().parent.parent
    return config, root


def _fetch(config: dict, root: Path, force: bool) -> pd.DataFrame:
    fetch_universe(config, root, force=force)
    panel = load_panel(config, root)
    write_processed(panel, config, root)
    report = panel_report(panel)
    print(
        f"[data] panel {report['rows']} rows x {len(report['columns'])} assets "
        f"{report['first_date']}..{report['last_date']}"
    )
    return panel


def _panel(config: dict, root: Path) -> pd.DataFrame:
    processed = root / config["paths"]["data_processed"] / "prices.csv"
    if processed.exists():
        return load_processed(config, root)
    return load_panel(config, root)


def _run(config: dict, root: Path, panel: pd.DataFrame) -> None:
    rows, metadata = run_experiment(config, panel)
    summary = write_outputs(rows, metadata, config, root)
    columns = [
        "family",
        "mean_sr",
        "sr_inflation",
        "tpr_dsr",
        "tpr_pbo",
        "tpr_reality_check",
        "tpr_split_half",
        "tpr_combined",
        "tpr_audit",
        "publishable_dsr",
    ]
    display = summary[[c for c in columns if c in summary.columns]].copy()
    for column in display.columns:
        if display[column].dtype.kind == "f":
            display[column] = display[column].round(3)
    print("\n" + display.to_string(index=False))
    print(f"\n[results] tables: {root / config['paths']['tables']}")
    print(f"[results] figures: {root / config['paths']['figures']}")
    print(f"[results] manifest: {root / config['paths']['results'] / 'run_manifest.json'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fakealpha", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="download and validate live market data")
    fetch.add_argument("--config", default="config/experiment.yaml")
    fetch.add_argument("--force", action="store_true", help="ignore cached raw responses")

    run = subparsers.add_parser("run", help="run the benchmark on cached data")
    run.add_argument("--config", default="config/experiment.yaml")
    run.add_argument("--quick", action="store_true", help="small smoke-test configuration")

    reproduce = subparsers.add_parser(
        "reproduce", help="fetch (cached), run, and write all artifacts"
    )
    reproduce.add_argument("--config", default="config/experiment.yaml")
    reproduce.add_argument("--force", action="store_true")
    reproduce.add_argument("--quick", action="store_true")

    report = subparsers.add_parser("report", help="regenerate tables and figures")
    report.add_argument("--config", default="config/experiment.yaml")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config, root = _load_config(Path(args.config))
    if getattr(args, "quick", False):
        config = copy.deepcopy(config)
        config["experiment"]["n_replicates"] = 3
        config["experiment"]["n_candidates"] = 12
        config["experiment"]["bootstrap_samples"] = 150
        print("[config] quick mode: 3 replicates, 12 candidates")

    if args.command == "fetch":
        _fetch(config, root, force=args.force)
    elif args.command == "run":
        panel = _panel(config, root)
        _run(config, root, panel)
    elif args.command == "reproduce":
        processed = root / config["paths"]["data_processed"] / "prices.csv"
        if args.force or not processed.exists():
            panel = _fetch(config, root, force=args.force)
        else:
            panel = load_processed(config, root)
            print("[data] using committed processed panel")
        _run(config, root, panel)
    elif args.command == "report":
        summary = report_from_saved(config, root)
        print(summary.to_string(index=False))
    return 0
