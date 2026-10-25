import numpy as np
import pandas as pd

from fakealpha.pipeline import FAMILY_ORDER, summarise


def _rows(family: str, n: int = 20, audit_suspicion: float = 0.5) -> list[dict]:
    rng = np.random.default_rng(3)
    rows = []
    for i in range(n):
        suspicion_audit = 0.0 if family == "honest" else (
            0.99 if i < 4 else audit_suspicion
        )
        difference = 0.2 + rng.normal(0.0, 0.02)
        rows.append(
            {
                "replicate": i,
                "family": family,
                "sr": 0.8 + difference,
                "sr_honest": 0.8,
                "sr_difference": difference,
                "publishable_dsr": False,
                "publishable_reality_check": False,
                "suspicion_dsr": 0.2,
                "suspicion_pbo": 0.3,
                "suspicion_reality_check": 0.05,
                "suspicion_split": rng.normal(0.0, 0.1),
                "suspicion_audit": suspicion_audit,
            }
        )
    return rows


def test_summarise_audit_uses_a_five_percent_level():
    rows = _rows("honest", audit_suspicion=0.0)
    for family in FAMILY_ORDER:
        if family != "honest":
            rows.extend(_rows(family))
    summary = summarise(pd.DataFrame(rows)).set_index("family")
    assert summary.loc["same_bar_fill", "threshold_audit"] == 0.95
    assert summary.loc["same_bar_fill", "tpr_audit"] == 0.2
    assert (summary["fpr_audit"] == 0.0).all()


def test_summarise_reports_inflation_interval():
    rows = _rows("honest", audit_suspicion=0.0)
    for family in FAMILY_ORDER:
        if family != "honest":
            rows.extend(_rows(family))
    summary = summarise(pd.DataFrame(rows)).set_index("family")
    estimate = summary.loc["same_bar_fill", "sr_inflation"]
    assert abs(estimate - 0.2) < 0.01
    assert summary.loc["same_bar_fill", "sr_inflation_ci_low"] < estimate
    assert summary.loc["same_bar_fill", "sr_inflation_ci_high"] > estimate
