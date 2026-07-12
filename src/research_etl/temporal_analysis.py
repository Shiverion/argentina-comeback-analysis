"""Grouped out-of-fold hazard summaries for the temporal opportunity panel."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, sha256_file, write_json_atomic
from research_etl.transform import write_csv_atomic


HAZARD_FEATURES = [
    "time_bin_start_minute",
    "goal_diff_pre",
    "red_cards_for_pre",
    "red_cards_against_pre",
    "box_entries_prev_5m",
    "box_receipts_prev_5m",
    "non_penalty_xg_prev_5m",
    "final_third_entries_prev_5m",
    "fouls_committed_prev_5m",
    "fouls_suffered_prev_5m",
    "yellow_cards_prev_5m",
    "possession_sequences_prev_5m",
    "opponent_box_entries_prev_5m",
    "opponent_non_penalty_xg_prev_5m",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fit_oof_hazard_model(
    frame: pd.DataFrame,
    *,
    outcome: str = "penalty_event_next_5m",
    features: list[str] | None = None,
    folds: int = 5,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """Fit a match-grouped logistic hazard model and compare it with a null rate."""

    features = features or HAZARD_FEATURES
    required = ["match_id", outcome, *features]
    model_frame = frame.dropna(subset=required).copy()
    model_frame[outcome] = pd.to_numeric(model_frame[outcome], errors="coerce").astype(int)
    model_frame = model_frame.loc[model_frame[outcome].isin([0, 1])].reset_index(drop=True)
    groups = model_frame["match_id"].astype(str)
    positives = int(model_frame[outcome].sum())
    if len(model_frame) < 500 or groups.nunique() < 50 or positives < 20:
        raise SourceError(
            f"Temporal hazard model needs at least 500 rows, 50 matches, and 20 positive windows; "
            f"received rows={len(model_frame)}, matches={groups.nunique()}, positives={positives}."
        )

    splits = min(folds, groups.nunique())
    splitter = GroupKFold(n_splits=splits)
    predictions = np.zeros(len(model_frame), dtype=float)
    for train_index, test_index in splitter.split(model_frame[features], model_frame[outcome], groups):
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=500, solver="liblinear"),
        )
        model.fit(model_frame.iloc[train_index][features], model_frame.iloc[train_index][outcome])
        predictions[test_index] = model.predict_proba(model_frame.iloc[test_index][features])[:, 1]

    null_rate = float(model_frame[outcome].mean())
    null_predictions = np.repeat(null_rate, len(model_frame))
    predictions = np.clip(predictions, 1e-7, 1 - 1e-7)
    metrics = {
        "outcome": outcome,
        "features": features,
        "rows": int(len(model_frame)),
        "matches": int(groups.nunique()),
        "positive_windows": positives,
        "positive_events": int(frame["penalty_shots_next_5m"].sum()),
        "alternate_penalty_foul_windows": int(frame["penalty_foul_event_next_5m"].sum()),
        "alternate_penalty_foul_events": int(frame["penalty_fouls_won_next_5m"].sum()),
        "folds": splits,
        "positive_rate": null_rate,
        "oof_log_loss": float(log_loss(model_frame[outcome], predictions, labels=[0, 1])),
        "null_log_loss": float(log_loss(model_frame[outcome], null_predictions, labels=[0, 1])),
        "oof_brier_score": float(brier_score_loss(model_frame[outcome], predictions)),
        "null_brier_score": float(brier_score_loss(model_frame[outcome], null_predictions)),
    }
    metrics["oof_beats_null"] = bool(metrics["oof_log_loss"] < metrics["null_log_loss"])
    result = model_frame.copy()
    result["hazard_probability_oof"] = predictions
    result["hazard_residual_oof"] = result[outcome] - predictions

    full_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.5, max_iter=500, solver="liblinear"),
    )
    full_model.fit(model_frame[features], model_frame[outcome])
    coefficients = pd.DataFrame(
        {
            "feature": features,
            "standardized_logit_coefficient": full_model[-1].coef_[0],
        }
    ).sort_values("standardized_logit_coefficient", ascending=False, key=lambda values: values.abs(), kind="stable")
    return result, metrics, coefficients.reset_index(drop=True)


def _hazard_chart(path: Path, predictions: pd.DataFrame, *, title: str) -> None:
    import matplotlib.pyplot as plt

    grouped = (
        predictions.groupby("time_bin_start_minute", as_index=False)
        .agg(observed_rate=("penalty_event_next_5m", "mean"), predicted_rate=("hazard_probability_oof", "mean"))
    )
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.plot(grouped["time_bin_start_minute"], grouped["observed_rate"] * 100, marker="o", color="#d65a4a", label="Observed event rate")
    ax.plot(grouped["time_bin_start_minute"], grouped["predicted_rate"] * 100, marker="o", color="#2f6f8f", label="OOF model rate")
    ax.set_title(title)
    ax.set_xlabel("Start of five-minute window (match minute)")
    ax.set_ylabel("Penalty-shot event rate (%)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_temporal_analysis(paths: ProjectPaths) -> dict[str, Any]:
    """Analyze every available non-pooled temporal StatsBomb panel."""

    panels = []
    world_path = paths.processed_dir / "statsbomb_world_cup_temporal_features.csv"
    history_path = paths.processed_dir / "statsbomb_history_temporal_features.csv"
    if world_path.exists():
        panels.append(("statsbomb_world_cup", "world_cup", pd.read_csv(world_path)))
    if history_path.exists():
        history = pd.read_csv(history_path)
        for tier, frame in history.groupby("competition_tier", sort=True):
            panels.append(("statsbomb_history", str(tier), frame.copy()))
    if not panels:
        raise SourceError("Temporal analysis requires a processed StatsBomb temporal feature panel.")

    artifacts: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    chart_source = None
    for panel, tier, frame in panels:
        predictions, metadata, coefficients = fit_oof_hazard_model(frame)
        metadata.update({"panel": panel, "tier": tier})
        suffix = tier.replace(" ", "_")
        prediction_path = paths.results_dir / f"temporal_statsbomb_{suffix}_oof_predictions.csv"
        coefficient_path = paths.results_dir / f"temporal_statsbomb_{suffix}_coefficients.csv"
        write_csv_atomic(predictions, prediction_path)
        write_csv_atomic(coefficients, coefficient_path)
        artifacts.extend(
            [
                {"path": str(prediction_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(predictions)), "sha256": sha256_file(prediction_path)},
                {"path": str(coefficient_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(coefficients)), "sha256": sha256_file(coefficient_path)},
            ]
        )
        models.append(metadata)
        if tier == "club":
            chart_source = predictions

    if chart_source is not None:
        chart_path = paths.results_dir / "assets" / "11_temporal_club_penalty_hazard.png"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        _hazard_chart(chart_path, chart_source, title="Five-minute penalty-shot hazard in the selected club panel")
        artifacts.append({"path": str(chart_path.relative_to(paths.root)).replace("\\", "/"), "sha256": sha256_file(chart_path)})

    manifest = {
        "pipeline": "research_etl.temporal_analysis",
        "created_at": _utc_now(),
        "status": "ready",
        "interpretation": (
            "Grouped out-of-fold association model. Features use only events before each five-minute window; "
            "penalty_shots is a StatsBomb event proxy and is not an adjudication of penalty correctness or intent."
        ),
        "non_pooling_rule": "World Cup, selected club, and selected non-World-Cup international panels remain separate.",
        "models": models,
        "artifacts": artifacts,
    }
    write_json_atomic(manifest, paths.results_dir / "temporal_analysis_manifest.json")
    return manifest
