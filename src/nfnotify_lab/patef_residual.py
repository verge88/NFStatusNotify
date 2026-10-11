"""Experimental PA-TEF learned residual OR the untouched consensus guard.

Does not change the established consensus_guard or PA-TEF default classes.
Small calibration groups MUST ABSTAIN; worst-group empirical thresholds do
not establish a distribution-free FPR guarantee on unseen scenarios.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .consensus import consensus_attack_support
from .patef import META_FEATURES, ProvenanceAwareTemporalEvidenceFusion
from .residual_freshness import FRESHNESS_FEATURES, availability_mask

TARGET_FPR = 0.001
MIN_BENIGN_GROUP = 20
ABSTAIN_THRESHOLD = float(np.nextafter(1.0, np.inf))


class FreshnessAwareFusion(ProvenanceAwareTemporalEvidenceFusion):
    """PA-TEF expert stack; optional *honestly missing* source ages in fusion."""

    def __init__(self, *, use_ages: bool, random_state: int = 42) -> None:
        super().__init__(
            random_state=random_state,
            use_decision_gate=False,
            include_consensus_meta=True,
        )
        self.use_ages = bool(use_ages)
        if self.use_ages:
            self.meta_features = (*META_FEATURES, *FRESHNESS_FEATURES)

    def _meta_frame(
        self, x: pd.DataFrame, models=None,
    ) -> pd.DataFrame:
        frame = self._ensure_temporal(x)
        experts = self._expert_probabilities(frame, models=models)
        meta = pd.concat([experts, self._availability(frame)], axis=1)
        if self.use_ages:
            for col in FRESHNESS_FEATURES:
                # Missing origins are *unknown*, not newly refreshed.
                if col.startswith("age_") and col.endswith("_missing"):
                    meta[col] = (
                        pd.to_numeric(frame[col], errors="coerce").fillna(1.0)
                        if col in frame else 1.0
                    )
                else:
                    meta[col] = (
                        pd.to_numeric(frame[col], errors="coerce")
                        if col in frame else np.nan
                    )
            # Logistic regression requires finite meta values. Unknown ages
            # are represented by missing indicators plus a fixed age cap.
            age_cols = [c for c in FRESHNESS_FEATURES if not c.endswith("_missing")]
            meta[age_cols] = meta[age_cols].fillna(25.0)
        return meta[list(self.meta_features)].astype(float)


def threshold_for_allowed_fps(scores: np.ndarray, count: int) -> float:
    """Smallest strict '>=' threshold with <= count empirical positives.

    Ties are conservatively excluded when a count would be exceeded.
    """
    scores = np.asarray(scores, dtype=float)
    if not np.isfinite(scores).all():
        raise ValueError("non-finite calibration scores")
    if not len(scores):
        return ABSTAIN_THRESHOLD
    if count < 0:
        return ABSTAIN_THRESHOLD
    if count >= len(scores):
        return 0.0
    ordered = np.sort(scores)[::-1]
    return float(np.nextafter(ordered[count], np.inf))


def rolling_residual_scores(frame: pd.DataFrame, scores: np.ndarray) -> np.ndarray:
    """Fixed 3-tick causal max by parent run, never across run boundaries."""
    tmp = frame[["run_id", "t"]].copy()
    tmp["score"] = np.asarray(scores, dtype=float)
    return (
        tmp.groupby("run_id", sort=False)["score"]
        .transform(lambda x: x.rolling(3, min_periods=1).max())
        .to_numpy(float)
    )


class PatefResidualGuard:
    """Guarantee alert set contains EXACT consensus-guard alert set.

    Heterogeneous residual thresholds spend only budget unused by guard on
    held-in *benign* calibration. No residual positives for unknown mask.
    """

    def __init__(
        self, *,
        random_state: int = 42,
        use_ages: bool = True,
        sequential: bool = False,
        target_fpr: float = TARGET_FPR,
    ) -> None:
        self.fusion = FreshnessAwareFusion(
            use_ages=use_ages, random_state=random_state
        )
        self.sequential = bool(sequential)
        self.target_fpr = float(target_fpr)
        self.thresholds: dict[str, float] = {}
        self.mask_reports: list[dict[str, object]] = []

    def fit(self, features: pd.DataFrame) -> PatefResidualGuard:
        self.fusion.fit(features, features["attack_active"])
        return self

    @staticmethod
    def guard_alerts(frame: pd.DataFrame) -> np.ndarray:
        # Exactly the default consensus_guard: positive support means alert.
        return consensus_attack_support(frame).to_numpy(float) > 0.0

    def residual_scores(self, frame: pd.DataFrame) -> np.ndarray:
        scores = np.asarray(self.fusion.learned_scores(frame), dtype=float)
        return (
            rolling_residual_scores(frame, scores)
            if self.sequential else scores
        )

    def calibrate(
        self, pristine: pd.DataFrame, calibration_views: dict[str, pd.DataFrame],
    ) -> PatefResidualGuard:
        if not 0.0 <= self.target_fpr < 1.0:
            raise ValueError("target_fpr must be in [0, 1)")
        self.fusion.calibrate(pristine, pristine["attack_active"])
        pool = []
        for name, frame in calibration_views.items():
            if set(frame["run_id"]) != set(pristine["run_id"]):
                raise ValueError(f"nonmatching calibration parent runs: {name}")
            scores = self.residual_scores(frame)
            pool.append(pd.DataFrame({
                "view": name,
                "scenario": frame["scenario"].to_numpy(),
                "mask": availability_mask(frame),
                "benign": frame["attack_active"].to_numpy(int) == 0,
                "guard": self.guard_alerts(frame),
                "score": scores,
            }))
        all_rows = pd.concat(pool, ignore_index=True)
        benign = all_rows.loc[all_rows["benign"]]
        if benign.empty:
            raise ValueError("no benign calibration points")
        self.thresholds = {}
        self.mask_reports = []
        masks = sorted(benign["mask"].unique())
        for mask in masks:
            subset = benign.loc[benign["mask"] == mask]
            n = len(subset)
            guard_fp = int(subset["guard"].sum())
            threshold = ABSTAIN_THRESHOLD
            reason = "too_few_benign"
            if n >= MIN_BENIGN_GROUP:
                allowed_total = int(np.floor(self.target_fpr * n))
                allowed_residual = allowed_total - guard_fp
                if allowed_residual < 0:
                    reason = "baseline_budget_exhausted"
                else:
                    silent_scores = subset.loc[~subset["guard"], "score"].to_numpy()
                    threshold = threshold_for_allowed_fps(
                        silent_scores, allowed_residual
                    )
                    reason = "calibrated"
                    for _, scen in subset.groupby("scenario", sort=True):
                        if len(scen) < MIN_BENIGN_GROUP:
                            threshold = ABSTAIN_THRESHOLD
                            reason = "too_few_per_scenario"
                            break
                        scen_allowed = (
                            int(np.floor(self.target_fpr * len(scen)))
                            - int(scen["guard"].sum())
                        )
                        if scen_allowed < 0:
                            threshold = ABSTAIN_THRESHOLD
                            reason = "baseline_scenario_budget_exhausted"
                            break
                        scen_scores = scen.loc[~scen["guard"], "score"].to_numpy()
                        threshold = max(
                            threshold, threshold_for_allowed_fps(
                                scen_scores, scen_allowed
                            )
                        )

            self.thresholds[mask] = float(threshold)
            benign_silent = subset.loc[~subset["guard"]]
            residual_fp = int((benign_silent["score"] >= threshold).sum())
            self.mask_reports.append({
                "mask": mask,
                "benign_calibration_points": n,
                "baseline_calibration_fp": guard_fp,
                "residual_calibration_fp": residual_fp,
                "calibration_fpr": (guard_fp + residual_fp) / n,
                "threshold": float(threshold),
                "residual_abstains": bool(threshold >= ABSTAIN_THRESHOLD),
                "reason": reason,
            })
        return self

    def decide(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self.thresholds:
            raise RuntimeError("calibrate before decision")
        guard = self.guard_alerts(frame)
        masks = availability_mask(frame)
        raw = self.residual_scores(frame)
        cutoffs = np.array([
            self.thresholds.get(mask, ABSTAIN_THRESHOLD) for mask in masks
        ])
        residual = (~guard) & (raw >= cutoffs)
        hybrid = guard | residual
        if not np.all(hybrid[guard]):
            raise AssertionError("consensus guard decision was overridden")
        return pd.DataFrame({
            "guard_alert": guard,
            "residual_alert": residual,
            "hybrid_alert": hybrid,
            "residual_score": raw,
            "threshold": cutoffs,
            "mask": masks,
        }, index=frame.index)
