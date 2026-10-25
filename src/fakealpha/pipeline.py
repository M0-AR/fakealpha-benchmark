"""Paired honest/contaminated experiment pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .features import compute_features
from .stats import (
    audit_p_value,
    deflated_sharpe,
    pbo,
    sharpe,
    sidak_reality_check,
    split_half_z,
    wilson_interval,
)
from .strategies import (
    Candidate,
    candidate_pool,
    full_sample_signals,
    honest_signals,
    rebalance_dates,
    returns_matrix,
    survivorship_universe,
    target_feature_signals,
)

RETURN_FAMILIES = {
    "same_bar_fill",
    "target_feature",
    "full_sample_target_encoding",
    "survivorship",
}
SELECTION_FAMILIES = {"p_hacked_selection", "shuffled_cv"}
FAMILY_ORDER = [
    "same_bar_fill",
    "target_feature",
    "full_sample_target_encoding",
    "shuffled_cv",
    "survivorship",
    "p_hacked_selection",
]
ALL_FAMILIES = ["honest", *FAMILY_ORDER]
AUDIT_ALPHA = 0.05


@dataclass
class FamilyResult:
    replicate: int
    family: str
    selected: str
    reported: pd.Series
    matrix_test: pd.DataFrame
    honest_reported: pd.Series
    sr: float
    sr_honest: float
    gates: dict = field(default_factory=dict)

    def row(self) -> dict:
        row = {
            "replicate": self.replicate,
            "family": self.family,
            "selected": self.selected,
            "sr": self.sr,
            "sr_honest": self.sr_honest,
            "sr_difference": self.sr - self.sr_honest,
        }
        row.update(self.gates)
        return row


def _test_slice(matrix: pd.DataFrame, config: dict) -> pd.DataFrame:
    start = f"{config['experiment']['test_start']}-01-01"
    end = f"{config['experiment']['test_end']}-12-31"
    return matrix.loc[start:end]


def build_family_matrices(
    prices: pd.DataFrame, features: dict[str, pd.DataFrame], config: dict
) -> dict[str, pd.DataFrame]:
    experiment = config["experiment"]
    rebalance = rebalance_dates(prices.index, experiment.get("rebalance_freq", "W-FRI"))
    cost_bps = float(experiment["cost_bps"])
    pool = candidate_pool()
    volatility = features["vol20"]

    base = honest_signals(features)
    matrices = {
        "honest": returns_matrix(
            prices, base, volatility, pool, cost_bps, 1, None, rebalance
        ),
        "same_bar_fill": returns_matrix(
            prices, base, volatility, pool, cost_bps, 0, None, rebalance
        ),
        "target_feature": returns_matrix(
            prices,
            target_feature_signals(features, float(experiment["target_feature_lambda"])),
            volatility,
            pool,
            cost_bps,
            1,
            None,
            rebalance,
        ),
        "full_sample_target_encoding": returns_matrix(
            prices,
            full_sample_signals(features),
            volatility,
            pool,
            cost_bps,
            1,
            None,
            rebalance,
        ),
        "survivorship": returns_matrix(
            prices,
            base,
            volatility,
            pool,
            cost_bps,
            1,
            survivorship_universe(features),
            rebalance,
        ),
    }
    matrices["p_hacked_selection"] = matrices["honest"]
    matrices["shuffled_cv"] = matrices["honest"]
    return matrices


def walk_forward_select(
    matrix: pd.DataFrame, config: dict
) -> tuple[pd.Series, dict[int, str]]:
    experiment = config["experiment"]
    years = range(int(experiment["test_start"]), int(experiment["test_end"]) + 1)
    embargo = int(experiment.get("embargo_days", 0))
    parts = []
    selections: dict[int, str] = {}
    for year in years:
        train_end = pd.Timestamp(f"{year - 1}-12-31") - pd.Timedelta(days=embargo)
        train = matrix.loc[:train_end]
        scores = {}
        for column in matrix.columns:
            values = train[column].dropna()
            scores[column] = (
                sharpe(values, annualize=False) if len(values) >= 126 else -np.inf
            )
        finite = {k: v for k, v in scores.items() if np.isfinite(v)}
        if finite:
            best = max(finite, key=finite.get)
        else:
            best = max(matrix.columns, key=lambda c: matrix[c].notna().sum())
        selections[year] = best
        parts.append(matrix[best].loc[f"{year}-01-01":f"{year}-12-31"])
    reported = pd.concat(parts).sort_index().rename("return")
    return reported.dropna(), selections


def select_test_max(matrix: pd.DataFrame, config: dict) -> tuple[pd.Series, str]:
    test = _test_slice(matrix, config)
    scores = {c: sharpe(test[c], annualize=False) for c in test.columns}
    finite = {k: v for k, v in scores.items() if np.isfinite(v)}
    best = max(finite, key=finite.get) if finite else test.columns[0]
    return test[best].dropna().rename("return"), best


def select_oracle_annual(matrix: pd.DataFrame, config: dict) -> tuple[pd.Series, str]:
    """Annual ex-post selection: the clearest form of test-set p-hacking."""
    test = _test_slice(matrix, config)
    parts = []
    for year in sorted(set(test.index.year)):
        block = test[test.index.year == year]
        scores = {c: sharpe(block[c], annualize=False) for c in block.columns}
        finite = {k: v for k, v in scores.items() if np.isfinite(v)}
        best = max(finite, key=finite.get) if finite else block.columns[0]
        parts.append(block[best])
    return pd.concat(parts).sort_index().rename("return"), "oracle_annual"


def select_shuffled_cv(
    matrix: pd.DataFrame, config: dict, seed: int, folds: int = 5
) -> tuple[pd.Series, str]:
    """Shuffled CV on the evaluation window: a realistic cross-validation leak."""
    test = _test_slice(matrix, config)
    rng = np.random.default_rng(seed)
    assignment = rng.integers(0, folds, size=len(test))
    scores = {}
    for column in test.columns:
        values = test[column]
        fold_scores = []
        for fold in range(folds):
            subset = values.iloc[assignment == fold].dropna()
            fold_scores.append(
                sharpe(subset, annualize=False) if len(subset) >= 30 else -np.inf
            )
        scores[column] = float(np.mean(fold_scores))
    finite = {k: v for k, v in scores.items() if np.isfinite(v)}
    best = max(finite, key=finite.get) if finite else test.columns[0]
    return test[best].dropna().rename("return"), best


def compute_gates(
    reported: pd.Series, matrix_test: pd.DataFrame, audit: float
) -> dict:
    dsr_info = deflated_sharpe(reported, matrix_test)
    dsr = dsr_info["dsr"]
    pbo_value = pbo(matrix_test)
    rc_value = sidak_reality_check(reported, matrix_test.shape[1])
    split_value = split_half_z(reported)
    gates = {
        "dsr": dsr,
        "sr0": dsr_info.get("sr0", float("nan")),
        "pbo": pbo_value,
        "reality_check_p": rc_value,
        "split_half_z": split_value,
        "audit_p": audit,
    }
    gates["suspicion_dsr"] = 1.0 - dsr if np.isfinite(dsr) else 0.5
    gates["suspicion_pbo"] = pbo_value if np.isfinite(pbo_value) else 0.5
    gates["suspicion_reality_check"] = (
        1.0 - rc_value if np.isfinite(rc_value) else 0.0
    )
    gates["suspicion_split"] = split_value if np.isfinite(split_value) else 0.0
    gates["suspicion_audit"] = 1.0 - audit
    gates["publishable_dsr"] = bool(np.isfinite(dsr) and dsr >= 0.95)
    gates["publishable_reality_check"] = bool(np.isfinite(rc_value) and rc_value <= 0.05)
    return gates


def run_replicate(
    matrices: dict[str, pd.DataFrame],
    candidates: list[Candidate],
    config: dict,
    replicate: int,
    seed: int,
) -> list[FamilyResult]:
    ids = [candidate.id for candidate in candidates]
    honest_matrix = matrices["honest"][ids]
    honest_reported, _ = walk_forward_select(honest_matrix, config)
    sr_honest = sharpe(honest_reported)
    results: list[FamilyResult] = []

    for family in ALL_FAMILIES:
        if family == "honest":
            matrix = honest_matrix
            reported = honest_reported
            selected = "walk_forward"
        elif family == "p_hacked_selection":
            matrix = honest_matrix
            reported, selected = select_oracle_annual(honest_matrix, config)
        elif family == "shuffled_cv":
            matrix = honest_matrix
            reported, selected = select_shuffled_cv(
                honest_matrix, config, seed=seed + 17
            )
        else:
            matrix = matrices[family][ids]
            reported, selections = walk_forward_select(matrix, config)
            selected = selections[max(selections)]

        matrix_test = _test_slice(
            matrix if family in RETURN_FAMILIES else honest_matrix, config
        )
        audit = audit_p_value(
            reported,
            honest_reported,
            n_boot=int(config["experiment"].get("bootstrap_samples", 500)),
            block=int(config["experiment"].get("bootstrap_block", 20)),
            seed=seed + 101,
        )
        gates = compute_gates(reported, matrix_test, audit)
        results.append(
            FamilyResult(
                replicate=replicate,
                family=family,
                selected=selected,
                reported=reported,
                matrix_test=matrix_test,
                honest_reported=honest_reported,
                sr=sharpe(reported),
                sr_honest=sr_honest,
                gates=gates,
            )
        )
    return results


def run_experiment(config: dict, prices: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    features = compute_features(prices)
    matrices = build_family_matrices(prices, features, config)
    pool = candidate_pool()
    experiment = config["experiment"]
    n_replicates = int(experiment["n_replicates"])
    n_candidates = min(int(experiment["n_candidates"]), len(pool))
    rng = np.random.default_rng(int(experiment["random_seed"]))

    rows = []
    selections = {}
    for replicate in range(n_replicates):
        indices = sorted(rng.choice(len(pool), size=n_candidates, replace=False))
        candidates = [pool[i] for i in indices]
        seed = int(experiment["random_seed"]) + replicate * 1009
        results = run_replicate(matrices, candidates, config, replicate, seed)
        rows.extend(result.row() for result in results)
        selections[replicate] = [c.id for c in candidates]
        print(
            f"[run] replicate {replicate + 1}/{n_replicates}: "
            f"honest SR={results[0].sr:.3f} "
            f"target SR={next(r.sr for r in results if r.family == 'target_feature'):.3f} "
            f"phack SR={next(r.sr for r in results if r.family == 'p_hacked_selection'):.3f}"
        )

    metadata = {
        "n_days": int(len(prices)),
        "n_assets": int(prices.shape[1]),
        "n_pool": len(pool),
        "n_candidates": n_candidates,
        "n_replicates": n_replicates,
        "selections": selections,
    }
    return pd.DataFrame(rows), metadata


def summarise(rows: pd.DataFrame) -> pd.DataFrame:
    gates = [
        "suspicion_dsr",
        "suspicion_pbo",
        "suspicion_reality_check",
        "suspicion_split",
        "suspicion_audit",
    ]
    labels = {
        "suspicion_dsr": "dsr",
        "suspicion_pbo": "pbo",
        "suspicion_reality_check": "reality_check",
        "suspicion_split": "split_half",
        "suspicion_audit": "audit",
    }
    honest = rows[rows["family"] == "honest"]
    returns_gates = [
        "suspicion_pbo",
        "suspicion_reality_check",
        "suspicion_split",
    ]
    thresholds = {
        gate: float(np.nanquantile(honest[gate], 0.95, method="higher"))
        for gate in gates
    }
    scale = {
        gate: max(
            float(np.nanquantile(honest[gate], 0.75) - np.nanquantile(honest[gate], 0.25)),
            1e-6,
        )
        for gate in gates
    }
    honest_combined = np.nanmax(
        np.column_stack(
            [(honest[gate] - thresholds[gate]) / scale[gate] for gate in returns_gates]
        ),
        axis=1,
    )
    combined_threshold = float(np.nanquantile(honest_combined, 0.95, method="higher"))

    def combined_score(frame: pd.DataFrame) -> np.ndarray:
        return np.nanmax(
            np.column_stack(
                [(frame[gate] - thresholds[gate]) / scale[gate] for gate in returns_gates]
            ),
            axis=1,
        )

    output = []
    for family in FAMILY_ORDER:
        subset = rows[rows["family"] == family]
        honest_subset = honest
        record = {
            "family": family,
            "n": int(len(subset)),
            "mean_sr": float(subset["sr"].mean()),
            "mean_sr_se": float(subset["sr"].std(ddof=1) / np.sqrt(len(subset))),
            "median_sr": float(subset["sr"].median()),
            "mean_sr_honest": float(subset["sr_honest"].mean()),
            "sr_inflation": float(subset["sr_difference"].mean()),
            "sr_inflation_se": float(subset["sr_difference"].std(ddof=1) / np.sqrt(len(subset))),
            "publishable_dsr": float(subset["publishable_dsr"].mean()),
            "publishable_reality_check": float(subset["publishable_reality_check"].mean()),
        }
        record["mean_sr_ci_low"] = record["mean_sr"] - 1.96 * record["mean_sr_se"]
        record["mean_sr_ci_high"] = record["mean_sr"] + 1.96 * record["mean_sr_se"]
        record["sr_inflation_ci_low"] = (
            record["sr_inflation"] - 1.96 * record["sr_inflation_se"]
        )
        record["sr_inflation_ci_high"] = (
            record["sr_inflation"] + 1.96 * record["sr_inflation_se"]
        )
        for gate in gates:
            if gate == "suspicion_audit":
                cutoff = 1.0 - AUDIT_ALPHA
                flagged = subset[gate] >= cutoff
                honest_flagged = honest_subset[gate] >= cutoff
            else:
                cutoff = thresholds[gate]
                flagged = subset[gate] > cutoff
                honest_flagged = honest_subset[gate] > cutoff
            record[f"tpr_{labels[gate]}"] = float(flagged.mean())
            record[f"fpr_{labels[gate]}"] = float(honest_flagged.mean())
            record[f"threshold_{labels[gate]}"] = cutoff
            successes = int(flagged.sum())
            low, high = wilson_interval(successes, len(flagged))
            record[f"tpr_{labels[gate]}_ci_low"] = low
            record[f"tpr_{labels[gate]}_ci_high"] = high
            try:
                from sklearn.metrics import roc_auc_score

                y = np.r_[np.zeros(len(honest_subset)), np.ones(len(subset))]
                scores = np.r_[honest_subset[gate].to_numpy(), subset[gate].to_numpy()]
                record[f"auc_{labels[gate]}"] = float(roc_auc_score(y, scores))
            except ValueError:
                record[f"auc_{labels[gate]}"] = float("nan")
        combined = combined_score(subset)
        combined_flags = combined > combined_threshold
        record["tpr_combined"] = float(combined_flags.mean())
        record["fpr_combined"] = float(
            (combined_score(honest_subset) > combined_threshold).mean()
        )
        low, high = wilson_interval(int(combined_flags.sum()), len(combined_flags))
        record["tpr_combined_ci_low"] = low
        record["tpr_combined_ci_high"] = high
        record["threshold_combined"] = combined_threshold
        output.append(record)
    return pd.DataFrame(output)
