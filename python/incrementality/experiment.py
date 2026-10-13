"""Experiment health checks: before trusting any lift number, check the randomisation worked.

1. Sample ratio mismatch (SRM): did the treated share come out at the designed split?
   A mismatch usually means users were lost or misassigned somewhere, and then the groups aren't comparable.
2. Covariate balance: do treated and control users look alike on their features before any ad?
   Measured as standardised mean differences (SMD); |SMD| under 0.1 is the usual "balanced" line.
3. Classifier test: can a model tell treated from control using only the features?
   If assignment was random it can't beat a coin flip, so AUC should sit at 0.5 within noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

FEATURES = [f"f{i}" for i in range(12)]


@dataclass(frozen=True)
class SRMResult:
    n_total: int
    n_treated: int
    expected_share: float
    observed_share: float
    chi2: float
    p_value: float

    @property
    def mismatch(self) -> bool:
        """Industry convention: flag SRM only at p < 0.001, because big tests run this check often."""
        return self.p_value < 0.001


def srm(n_treated: int, n_total: int, expected_share: float) -> SRMResult:
    """Chi-square goodness-of-fit test of the treated/control counts against the designed split."""
    observed = np.array([n_treated, n_total - n_treated])
    expected = np.array([expected_share, 1 - expected_share]) * n_total
    chi2, p = stats.chisquare(observed, expected)
    return SRMResult(n_total, n_treated, expected_share, n_treated / n_total, float(chi2), float(p))


def balance(con: duckdb.DuckDBPyConnection, source: str, features: list[str] = FEATURES) -> pd.DataFrame:
    """Mean of each feature by group and the standardised mean difference, computed inside DuckDB.

    `source` is anything DuckDB can select from: a table name or a quoted Parquet path.
    """
    parts = ", ".join(
        f"avg({f}) FILTER (WHERE treatment = 1) AS {f}_mt, avg({f}) FILTER (WHERE treatment = 0) AS {f}_mc, "
        f"var_samp({f}) FILTER (WHERE treatment = 1) AS {f}_vt, var_samp({f}) FILTER (WHERE treatment = 0) AS {f}_vc"
        for f in features)
    row = con.execute(f"SELECT {parts} FROM {source}").df().iloc[0]
    out = pd.DataFrame({
        "feature": features,
        "mean_treated": [row[f"{f}_mt"] for f in features],
        "mean_control": [row[f"{f}_mc"] for f in features],
        "sd_pooled": [np.sqrt((row[f"{f}_vt"] + row[f"{f}_vc"]) / 2) for f in features],
    })
    out["smd"] = (out["mean_treated"] - out["mean_control"]) / out["sd_pooled"]
    return out


@dataclass(frozen=True)
class ClassifierResult:
    auc: float
    fold_aucs: tuple[float, ...]
    null_se: float  # standard error of AUC if the features carry no information about treatment

    @property
    def z(self) -> float:
        return (self.auc - 0.5) / self.null_se


def classifier_test(X: pd.DataFrame, treatment: pd.Series, folds: int = 5, seed: int = 0) -> ClassifierResult:
    """Out-of-fold AUC of a gradient-boosted model predicting treatment from the features."""
    y = treatment.to_numpy()
    scores = np.empty(len(y))
    fold_aucs = []
    for train, test in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, y):
        model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=seed)
        model.fit(X.iloc[train], y[train])
        scores[test] = model.predict_proba(X.iloc[test])[:, 1]
        fold_aucs.append(roc_auc_score(y[test], scores[test]))
    n1, n0 = int(y.sum()), int(len(y) - y.sum())
    null_se = float(np.sqrt((n1 + n0 + 1) / (12 * n1 * n0)))  # Mann-Whitney null variance of the AUC
    return ClassifierResult(float(roc_auc_score(y, scores)), tuple(fold_aucs), null_se)
