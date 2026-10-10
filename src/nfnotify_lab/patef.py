from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from .consensus import consensus_attack_support
from .temporal import add_temporal_features


EXPERT_FEATURES: dict[str, tuple[str, ...]] = {
    "state": (
        "delta_nrf_ausf",
        "delta_route",
        "state_conflict",
        "state_conflict_persist",
        "state_pair_available_count",
        "conflict_source_count",
        "single_source_conflict",
        "dual_source_conflict",
        "single_source_conflict_persist",
        "dual_source_conflict_persist",
        "conflict_source_count_mean_6",
        "single_source_conflict_mean_6",
        "dual_source_conflict_mean_6",
        "route_conflict_persist",
        "cache_conflict_persist",
        "delta_nrf_ausf_mean_3",
        "delta_nrf_ausf_mean_6",
        "delta_route_mean_3",
        "delta_route_mean_6",
        "state_conflict_mean_3",
        "state_conflict_mean_6",
        "state_conflict_max_12",
        "prov_nrf_ausf",
        "prov_route",
        "obs_fraction",
        "m_nrf",
        "m_ausf",
        "m_route",
    ),
    "notify": (
        "delta_notify",
        "bad_notify_seen",
        "recent_bad_notify_seen_6",
        "recent_notify_seen_6",
        "recent_trusted_notify_seen_6",
        "notify_seen",
        "notify_subscription_valid",
        "notify_sender_trusted",
        "since_notify",
        "prov_notify",
        "m_notify",
        "delta_notify_mean_3",
        "delta_notify_max_6",
    ),
    "temporal": (
        "delta_time",
        "cache_changed",
        "since_nrf_update",
        "since_nrf_endpoint_change",
        "nrf_endpoint_changed",
        "recent_nrf_update_seen_6",
        "recent_nrf_update_seen_12",
        "recent_nrf_endpoint_changed_12",
        "state_conflict_persist",
        "single_source_conflict_persist",
        "dual_source_conflict_persist",
        "conflict_source_count_mean_6",
        "single_source_conflict_mean_6",
        "dual_source_conflict_mean_6",
        "unexplained_conflict",
        "trusted_transition",
        "delta_time_mean_3",
        "delta_time_max_6",
        "recovery_active",
        "recovery_active_mean_6",
        "state_conflict_mean_6",
        "state_conflict_mean_12",
        "obs_fraction",
        "evidence_coverage",
    ),
    "context": (
        "recovery_active",
        "recovery_active_mean_3",
        "recovery_active_mean_6",
        "recent_nrf_update_seen_6",
        "recent_nrf_update_seen_12",
        "nrf_endpoint_changed",
        "recent_nrf_endpoint_changed_12",
        "recent_trusted_notify_seen_6",
        "obs_fraction",
        "evidence_coverage",
    ),
}

PA_TEF_SINGLE_SOURCE_PERSISTENCE_STEPS = 7
PA_TEF_DUAL_SOURCE_PERSISTENCE_STEPS = 1
PA_TEF_NEUTRAL_SCORE = 0.5


META_FEATURES = (
    "p_state",
    "p_notify",
    "p_temporal",
    "p_context",
    "avail_state",
    "avail_notify",
    "avail_temporal",
    "avail_context",
    "obs_fraction",
    "recovery_active",
    "transition_context",
    "state_conflict_persist_norm",
    "single_source_conflict_persist_norm",
    "dual_source_conflict_persist_norm",
    "conflict_source_fraction",
    "recent_bad_notify",
    "unexplained_conflict",
    "consensus_support",
)


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def _expert_model(random_state: int) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.07,
                    max_iter=120,
                    max_leaf_nodes=15,
                    l2_regularization=1.2,
                    random_state=random_state,
                ),
            ),
        ]
    )


def semantic_attack_support(x: pd.DataFrame) -> pd.Series:
    """Deterministic domain-semantic evidence for a suspicious post-effect.

    This function is intentionally public so the exact same semantic guard can
    be evaluated as a standalone baseline. PA-TEF must beat that baseline to
    claim an empirical contribution from learned evidence fusion.
    """
    bad_notify = x["recent_bad_notify_seen_6"].fillna(0.0).clip(0.0, 1.0)
    recovery = x["recovery_active"].fillna(0.0).clip(0.0, 1.0)
    observed_transition = pd.concat(
        [
            x["recent_nrf_update_seen_12"].fillna(0.0),
            x["recent_nrf_endpoint_changed_12"].fillna(0.0),
        ],
        axis=1,
    ).max(axis=1)
    transition_block = np.maximum(recovery, observed_transition)
    persistence = (
        (x["state_conflict_persist"].fillna(0.0) - 1.0) / 3.0
    ).clip(0.0, 1.0)
    coverage = x["evidence_coverage"].fillna(0.0).clip(0.0, 1.0)

    unexplained = x["state_conflict"].fillna(0.0) * (1.0 - transition_block)
    state_support = unexplained * persistence * coverage
    temporal_support = (
        x["delta_time"].fillna(0.0) * (1.0 - transition_block) * coverage
    )

    support = pd.concat(
        [bad_notify, state_support, temporal_support],
        axis=1,
    ).max(axis=1)
    return support.clip(0.0, 1.0)


def provenance_normalized_attack_gate(
    x: pd.DataFrame,
    *,
    single_source_steps: int = PA_TEF_SINGLE_SOURCE_PERSISTENCE_STEPS,
    dual_source_steps: int = PA_TEF_DUAL_SOURCE_PERSISTENCE_STEPS,
) -> pd.Series:
    """Source-symmetric gate that separates evidence eligibility from coverage.

    Persistence parameters are explicit so development-only sweeps can test
    whether a more permissive semantic eligibility envelope gives learned
    fusion room to add value. Production/default behavior remains 7/1.
    """
    if single_source_steps < 1 or dual_source_steps < 1:
        raise ValueError("persistence steps must be >= 1")

    bad_notify = x["recent_bad_notify_seen_6"].fillna(0.0).clip(0.0, 1.0)
    recovery = x["recovery_active"].fillna(0.0).clip(0.0, 1.0)
    observed_transition = pd.concat(
        [
            x["recent_nrf_update_seen_12"].fillna(0.0),
            x["recent_nrf_endpoint_changed_12"].fillna(0.0),
        ],
        axis=1,
    ).max(axis=1)
    transition_block = np.maximum(recovery, observed_transition)

    dual_ready = (
        x["dual_source_conflict_persist"].fillna(0.0) >= dual_source_steps
    ).astype(float)
    single_ready = (
        x["single_source_conflict_persist"].fillna(0.0) >= single_source_steps
    ).astype(float)
    full_state_support = np.maximum(dual_ready, single_ready) * (
        1.0 - transition_block
    )

    partial_state_view = x["state_pair_available_count"].fillna(0.0).eq(1.0)
    persistent_partial_conflict = (
        partial_state_view
        & x["state_conflict"].fillna(0.0).gt(0.0)
        & x["state_conflict_persist"].fillna(0.0).ge(single_source_steps)
    ).astype(float)
    partial_support = persistent_partial_conflict * (1.0 - transition_block)

    return pd.concat(
        [bad_notify, full_state_support, partial_support],
        axis=1,
    ).max(axis=1).clip(0.0, 1.0)


class ProvenanceAwareTemporalEvidenceFusion:
    """Specialized NFStatusNotify post-effect detector.

    PA-TEF trains independent evidence experts and fuses only out-of-fold
    expert probabilities. Source masks gate unavailable experts to a neutral
    probability instead of treating missing observations as benign evidence.

    The final risk is gated by provenance-normalized semantic evidence.  The
    gate suppresses transient single-observer skew using source-consensus
    persistence, but unlike the original PA-TEF it does not multiply risk by
    observation coverage.  This prevents partial telemetry from making a
    calibrated threshold mathematically unreachable.
    """

    requires_full_frame = True
    is_probability_score = False

    def __init__(
        self,
        random_state: int = 0,
        stack_folds: int = 4,
        *,
        use_decision_gate: bool = True,
        include_consensus_meta: bool = True,
        gate_single_source_steps: int = PA_TEF_SINGLE_SOURCE_PERSISTENCE_STEPS,
        gate_dual_source_steps: int = PA_TEF_DUAL_SOURCE_PERSISTENCE_STEPS,
    ) -> None:
        self.random_state = random_state
        self.stack_folds = stack_folds
        self.use_decision_gate = use_decision_gate
        self.include_consensus_meta = include_consensus_meta
        self.gate_single_source_steps = gate_single_source_steps
        self.gate_dual_source_steps = gate_dual_source_steps
        self.meta_features = (
            META_FEATURES
            if include_consensus_meta
            else tuple(
                feature
                for feature in META_FEATURES
                if feature != "consensus_support"
            )
        )
        self.experts: dict[str, Pipeline] = {}
        self.fusion: LogisticRegression | None = None
        self.calibrator: LogisticRegression | None = None

    @staticmethod
    def _ensure_temporal(x: pd.DataFrame) -> pd.DataFrame:
        if "state_conflict_persist" in x.columns:
            return x.copy()
        return add_temporal_features(x)

    @staticmethod
    def _availability(x: pd.DataFrame) -> pd.DataFrame:
        state = pd.concat(
            [x["prov_nrf_ausf"].fillna(0.0), x["prov_route"].fillna(0.0)],
            axis=1,
        ).max(axis=1)
        transition_context = pd.concat(
            [
                x["recovery_active"].fillna(0.0),
                x["recent_nrf_update_seen_12"].fillna(0.0),
                x["recent_nrf_endpoint_changed_12"].fillna(0.0),
                x["recent_trusted_notify_seen_6"].fillna(0.0),
            ],
            axis=1,
        ).max(axis=1)
        return pd.DataFrame(
            {
                "avail_state": state.astype(float),
                "avail_notify": x["m_notify"].fillna(0.0).astype(float),
                "avail_temporal": (
                    x["m_nrf"].fillna(0.0).astype(float)
                    + x["m_ausf"].fillna(0.0).astype(float)
                )
                / 2.0,
                "avail_context": np.ones(len(x), dtype=float),
                "obs_fraction": x["obs_fraction"].fillna(0.0).astype(float),
                "recovery_active": x["recovery_active"].fillna(0.0).astype(float),
                "transition_context": transition_context.astype(float),
                "state_conflict_persist_norm": x["state_conflict_persist"]
                .fillna(0.0)
                .clip(0, 12)
                .astype(float)
                / 12.0,
                "single_source_conflict_persist_norm": x[
                    "single_source_conflict_persist"
                ]
                .fillna(0.0)
                .clip(0, 12)
                .astype(float)
                / 12.0,
                "dual_source_conflict_persist_norm": x[
                    "dual_source_conflict_persist"
                ]
                .fillna(0.0)
                .clip(0, 12)
                .astype(float)
                / 12.0,
                "conflict_source_fraction": (
                    x["conflict_source_count"].fillna(0.0)
                    / x["state_pair_available_count"].replace(0.0, np.nan)
                )
                .fillna(0.0)
                .clip(0.0, 1.0),
                "recent_bad_notify": x["recent_bad_notify_seen_6"]
                .fillna(0.0)
                .astype(float),
                "unexplained_conflict": x["unexplained_conflict"]
                .fillna(0.0)
                .astype(float),
                "consensus_support": consensus_attack_support(x)
                .fillna(0.0)
                .astype(float),
            },
            index=x.index,
        )

    def _expert_probabilities(
        self, x: pd.DataFrame, models: dict[str, Pipeline] | None = None
    ) -> pd.DataFrame:
        frame = self._ensure_temporal(x)
        models = models or self.experts
        availability = self._availability(frame)
        out = pd.DataFrame(index=frame.index)

        for name, columns in EXPERT_FEATURES.items():
            probability = models[name].predict_proba(frame[list(columns)])[:, 1]
            available = availability[f"avail_{name}"].to_numpy()
            out[f"p_{name}"] = np.where(available > 0.0, probability, 0.5)

        return out

    def _meta_frame(
        self, x: pd.DataFrame, models: dict[str, Pipeline] | None = None
    ) -> pd.DataFrame:
        frame = self._ensure_temporal(x)
        expert = self._expert_probabilities(frame, models=models)
        meta = pd.concat([expert, self._availability(frame)], axis=1)
        return meta[list(self.meta_features)].astype(float)

    def fit(
        self, x: pd.DataFrame, y: pd.Series
    ) -> ProvenanceAwareTemporalEvidenceFusion:
        frame = self._ensure_temporal(x)
        target = pd.Series(np.asarray(y, dtype=int), index=frame.index)
        groups = frame["run_id"].astype(str).to_numpy()
        unique_groups = np.unique(groups)

        if len(unique_groups) < 2:
            raise ValueError("PA-TEF requires at least two independent run_id groups")

        folds = min(self.stack_folds, len(unique_groups))
        splitter = GroupKFold(n_splits=folds)
        oof = pd.DataFrame(index=frame.index, columns=self.meta_features, dtype=float)

        for fold, (train_idx, valid_idx) in enumerate(
            splitter.split(frame, target, groups=groups)
        ):
            fold_models: dict[str, Pipeline] = {}
            for expert_index, (name, columns) in enumerate(EXPERT_FEATURES.items()):
                model = _expert_model(self.random_state + 10 * fold + expert_index)
                model.fit(frame.iloc[train_idx][list(columns)], target.iloc[train_idx])
                fold_models[name] = model

            fold_meta = self._meta_frame(frame.iloc[valid_idx], models=fold_models)
            oof.loc[fold_meta.index, list(self.meta_features)] = fold_meta.to_numpy()

        self.fusion = LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=0.7,
            random_state=self.random_state,
        )
        self.fusion.fit(oof.astype(float), target)

        self.experts = {}
        for expert_index, (name, columns) in enumerate(EXPERT_FEATURES.items()):
            model = _expert_model(self.random_state + 100 + expert_index)
            model.fit(frame[list(columns)], target)
            self.experts[name] = model

        self.calibrator = None
        return self

    def _raw_scores(self, x: pd.DataFrame) -> np.ndarray:
        if self.fusion is None or not self.experts:
            raise RuntimeError("PA-TEF must be fitted before scoring")
        return self.fusion.predict_proba(self._meta_frame(x))[:, 1]

    def calibrate(
        self, x: pd.DataFrame, y: pd.Series
    ) -> ProvenanceAwareTemporalEvidenceFusion:
        target = np.asarray(y, dtype=int)
        raw = self._raw_scores(x)
        if len(np.unique(target)) < 2 or len(np.unique(raw)) < 2:
            self.calibrator = None
            return self

        self.calibrator = LogisticRegression(max_iter=500, C=1.0)
        self.calibrator.fit(_logit(raw).reshape(-1, 1), target)
        return self

    def _calibrated_scores(self, x: pd.DataFrame) -> np.ndarray:
        raw = self._raw_scores(x)
        if self.calibrator is None:
            return raw
        return self.calibrator.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]

    def learned_scores(self, x: pd.DataFrame) -> np.ndarray:
        """Return calibrated learned-fusion scores before semantic gating."""
        return self._calibrated_scores(x)

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        frame = self._ensure_temporal(x)
        calibrated = self._calibrated_scores(frame)
        if not self.use_decision_gate:
            return calibrated

        gate = provenance_normalized_attack_gate(
            frame,
            single_source_steps=self.gate_single_source_steps,
            dual_source_steps=self.gate_dual_source_steps,
        ).to_numpy(dtype=float)

        # Gate-off rows are semantically ineligible, but assigning zero would
        # make the low-FPR threshold collapse to the smallest positive float
        # and remove the learned fusion from the decision. A neutral score
        # preserves a meaningful threshold: an alert requires both semantic
        # eligibility and calibrated learned evidence above the neutral prior.
        return np.where(gate > 0.0, calibrated, PA_TEF_NEUTRAL_SCORE)

    def risk_report(self, x: pd.DataFrame) -> pd.DataFrame:
        frame = self._ensure_temporal(x)
        expert = self._expert_probabilities(frame)
        availability = self._availability(frame)
        support = semantic_attack_support(frame)
        gate = provenance_normalized_attack_gate(
            frame,
            single_source_steps=self.gate_single_source_steps,
            dual_source_steps=self.gate_dual_source_steps,
        )
        risk = self.score_samples(frame)

        confidence = (
            0.40 * availability["avail_state"]
            + 0.25 * availability["avail_notify"]
            + 0.20 * availability["avail_temporal"]
            + 0.15 * availability["obs_fraction"]
        ).clip(0.0, 1.0)

        evidence: list[str] = []
        for _, row in frame.iterrows():
            if row.get("recent_bad_notify_seen_6", 0.0) > 0:
                evidence.append("untrusted_or_unbound_nfstatusnotify")
            elif row.get("recovery_active", 0.0) > 0:
                evidence.append("legitimate_recovery_context")
            elif (
                row.get("recent_nrf_update_seen_12", 0.0) > 0
                or row.get("recent_nrf_endpoint_changed_12", 0.0) > 0
            ):
                evidence.append("legitimate_nrf_transition_context")
            elif (
                row.get("state_conflict_persist", 0.0) >= 2
                and row.get("unexplained_conflict", 0.0) > 0
            ):
                evidence.append("persistent_unexplained_state_divergence")
            elif row.get("delta_time", 0.0) > 0:
                evidence.append("cache_change_without_recent_nrf_update")
            else:
                evidence.append("weak_or_partial_evidence")

        report = pd.DataFrame(index=frame.index)
        report["risk_score"] = risk
        report["confidence"] = confidence.to_numpy()
        report["semantic_support"] = support.to_numpy()
        report["decision_gate"] = gate.to_numpy()
        report["dominant_evidence"] = evidence
        for column in expert.columns:
            report[column] = expert[column].to_numpy()
        return report
