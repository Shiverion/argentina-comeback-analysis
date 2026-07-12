"""Bridge the opportunity panels to Notebook 1's match-state outcome estimand."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, sha256_file, write_json_atomic
from research_etl.transform import write_csv_atomic


LABELS = ["DRAW", "TEAM_LOSS", "TEAM_WIN"]
STATE_FEATURES = [
    "time_bin_start_minute",
    "goal_diff_pre",
    "red_cards_for_pre",
    "red_cards_against_pre",
    "home_indicator",
]
SPATIAL_FEATURES = [
    "box_entries_prev_5m",
    "box_receipts_prev_5m",
    "non_penalty_xg_prev_5m",
    "final_third_entries_prev_5m",
]
POSSESSION_FEATURES = ["possession_sequences_prev_5m"]
DISCIPLINE_FEATURES = [
    "fouls_committed_prev_5m",
    "fouls_suffered_prev_5m",
    "yellow_cards_prev_5m",
]
OPPONENT_FEATURES = ["opponent_box_entries_prev_5m", "opponent_non_penalty_xg_prev_5m"]
BRIDGE_FEATURE_SETS = {
    "state_only": STATE_FEATURES,
    "spatial_augmented": STATE_FEATURES + SPATIAL_FEATURES,
    "possession_augmented": STATE_FEATURES + SPATIAL_FEATURES + POSSESSION_FEATURES,
    "opportunity_augmented": STATE_FEATURES + SPATIAL_FEATURES + POSSESSION_FEATURES + DISCIPLINE_FEATURES + OPPONENT_FEATURES,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _aligned_probabilities(model: Any, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    raw = model.predict_proba(frame[features])
    aligned = np.zeros((len(frame), len(LABELS)), dtype=float)
    for index, label in enumerate(model.classes_):
        aligned[:, LABELS.index(label)] = raw[:, index]
    row_sums = aligned.sum(axis=1, keepdims=True)
    return np.divide(aligned, row_sums, out=np.zeros_like(aligned), where=row_sums > 0)


def _metrics(outcomes: pd.Series, probabilities: np.ndarray) -> dict[str, Any]:
    values = outcomes.to_numpy()
    truth = np.column_stack([values == label for label in LABELS]).astype(float)
    clipped = np.clip(probabilities, 1e-7, 1 - 1e-7)
    clipped = clipped / clipped.sum(axis=1, keepdims=True)
    return {
        "rows": int(len(values)),
        "log_loss": float(log_loss(values, clipped, labels=LABELS)),
        "multiclass_brier": float(np.mean(np.sum((clipped - truth) ** 2, axis=1))),
        "accuracy": float(np.mean(np.asarray(LABELS)[clipped.argmax(axis=1)] == values)),
    }


def _prepare_temporal_frame(paths: ProjectPaths, path: Path) -> pd.DataFrame:
    temporal = pd.read_csv(path)
    score_columns = {"regulation_home_score", "regulation_away_score"}
    if score_columns.issubset(temporal.columns):
        frame = temporal.copy()
    else:
        audit = pd.read_csv(paths.processed_dir / "statsbomb_history_match_audit.csv")
        required_audit = {
            "match_id", "home_team", "away_team", "regulation_home_score", "regulation_away_score",
        }
        if missing := sorted(required_audit - set(audit.columns)):
            raise SourceError(f"Bridge analysis audit is missing columns: {', '.join(missing)}")
        audit = audit[list(required_audit)].drop_duplicates("match_id")
        frame = temporal.merge(audit, on="match_id", how="inner", validate="many_to_one")
    frame["home_indicator"] = frame["home_or_away"].eq("home").astype(int)
    frame["team_final_score"] = np.where(
        frame["home_or_away"].eq("home"), frame["regulation_home_score"], frame["regulation_away_score"]
    )
    frame["opponent_final_score"] = np.where(
        frame["home_or_away"].eq("home"), frame["regulation_away_score"], frame["regulation_home_score"]
    )
    frame["regulation_result"] = np.select(
        [frame["team_final_score"] > frame["opponent_final_score"], frame["team_final_score"] == frame["opponent_final_score"]],
        ["TEAM_WIN", "DRAW"],
        default="TEAM_LOSS",
    )
    required = sorted(set(sum(BRIDGE_FEATURE_SETS.values(), [])) | {"match_id", "regulation_result"})
    frame = frame.dropna(subset=required).reset_index(drop=True)
    if frame["match_id"].nunique() < 50 or len(frame) < 500:
        raise SourceError("Bridge analysis requires at least 50 matches and 500 complete temporal rows.")
    return frame


def _fit_bridge_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    groups = frame["match_id"].astype(str)
    splitter = GroupKFold(n_splits=min(5, groups.nunique()))
    splits = list(splitter.split(frame, frame["regulation_result"], groups))
    result = frame[[
        "match_id", "team_name", "opponent_team_name", "time_bin_start_minute", "goal_diff_pre", "regulation_result",
    ]].copy()
    metadata: list[dict[str, Any]] = []
    full_predictions = None
    for variant, features in BRIDGE_FEATURE_SETS.items():
        probabilities = np.zeros((len(frame), len(LABELS)), dtype=float)
        for train_index, test_index in splits:
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.5, max_iter=500, solver="lbfgs"),
            )
            model.fit(frame.iloc[train_index][features], frame.iloc[train_index]["regulation_result"])
            probabilities[test_index] = _aligned_probabilities(model, frame.iloc[test_index], features)
        for index, label in enumerate(LABELS):
            result[f"p_{variant}_{label.lower()}"] = probabilities[:, index]
        metrics = _metrics(frame["regulation_result"], probabilities)
        metadata.append({
            "variant": variant,
            "features": features,
            "folds": len(splits),
            **metrics,
        })
        if variant == "opportunity_augmented":
            full_predictions = probabilities

    if full_predictions is None:
        raise SourceError("Bridge opportunity-augmented predictions were not generated.")

    cf_for = frame.copy()
    cf_against = frame.copy()
    cf_for["goal_diff_pre"] = cf_for["goal_diff_pre"] + 1
    cf_against["goal_diff_pre"] = cf_against["goal_diff_pre"] - 1
    counterfactual_for = np.zeros((len(frame), len(LABELS)), dtype=float)
    counterfactual_against = np.zeros((len(frame), len(LABELS)), dtype=float)
    features = BRIDGE_FEATURE_SETS["opportunity_augmented"]
    for train_index, test_index in splits:
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=500, solver="lbfgs"),
        )
        model.fit(frame.iloc[train_index][features], frame.iloc[train_index]["regulation_result"])
        counterfactual_for[test_index] = _aligned_probabilities(model, cf_for.iloc[test_index], features)
        counterfactual_against[test_index] = _aligned_probabilities(model, cf_against.iloc[test_index], features)
    result["p_team_win_observed"] = full_predictions[:, LABELS.index("TEAM_WIN")]
    result["p_team_win_scored_penalty"] = counterfactual_for[:, LABELS.index("TEAM_WIN")]
    result["p_team_win_opponent_scored_penalty"] = counterfactual_against[:, LABELS.index("TEAM_WIN")]
    result["delta_win_probability_for_scored_penalty"] = result["p_team_win_scored_penalty"] - result["p_team_win_observed"]
    result["delta_win_probability_against_scored_penalty"] = result["p_team_win_opponent_scored_penalty"] - result["p_team_win_observed"]
    return result, metadata


def _impact_summary(predictions: pd.DataFrame, *, panel: str, tier: str) -> pd.DataFrame:
    frame = predictions.copy()
    frame["time_band"] = pd.cut(
        frame["time_bin_start_minute"], bins=[-1, 60, 70, 80, 90, 200], labels=["0-60", "60-70", "70-80", "80-90", "90+"],
    ).astype(str)
    frame["score_bucket"] = np.select(
        [frame["goal_diff_pre"] <= -2, frame["goal_diff_pre"] == -1, frame["goal_diff_pre"] == 0],
        ["two_or_more_down", "one_down", "level"],
        default="ahead",
    )
    cohorts = {
        "all": np.ones(len(frame), dtype=bool),
        "trailing": frame["goal_diff_pre"] < 0,
        "two_or_more_down": frame["goal_diff_pre"] <= -2,
        "late_trailing": (frame["goal_diff_pre"] < 0) & (frame["time_bin_start_minute"] >= 60),
        "late_two_or_more_down": (frame["goal_diff_pre"] <= -2) & (frame["time_bin_start_minute"] >= 60),
    }
    rows: list[dict[str, Any]] = []
    for cohort, mask in cohorts.items():
        for time_band in ["all", "60-70", "70-80", "80-90"]:
            selected = frame.loc[mask & (frame["time_band"].eq(time_band) if time_band != "all" else True)]
            if len(selected) < 20:
                continue
            rows.append({
                "panel": panel,
                "tier": tier,
                "cohort": cohort,
                "time_band": time_band,
                "rows": int(len(selected)),
                "mean_win_probability_observed": float(selected["p_team_win_observed"].mean()),
                "mean_win_probability_if_penalty_scored_for": float(selected["p_team_win_scored_penalty"].mean()),
                "mean_win_probability_if_penalty_scored_against": float(selected["p_team_win_opponent_scored_penalty"].mean()),
                "mean_delta_for": float(selected["delta_win_probability_for_scored_penalty"].mean()),
                "mean_delta_against": float(selected["delta_win_probability_against_scored_penalty"].mean()),
            })
    return pd.DataFrame(rows)


def _write_skill_chart(path: Path, skill_rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame(skill_rows)
    pivot = frame.pivot(index="tier", columns="variant", values="log_loss")
    ax = pivot.plot(kind="bar", figsize=(9, 5), color=["#9aa9b8", "#6f8f58", "#2f6f8f", "#d65a4a"])
    ax.set_title("Out-of-fold log loss: state model versus opportunity extensions")
    ax.set_xlabel("Competition tier")
    ax.set_ylabel("Multiclass log loss (lower is better)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(title="Model variant", frameon=False, fontsize=8)
    ax.figure.tight_layout()
    ax.figure.savefig(path, dpi=180)
    plt.close(ax.figure)


def _write_impact_chart(path: Path, impact: pd.DataFrame) -> None:
    selected = impact.loc[(impact["cohort"] == "late_two_or_more_down") & (impact["time_band"] == "all")]
    if selected.empty:
        return
    chart = selected.set_index("tier")[["mean_delta_for", "mean_delta_against"]]
    ax = chart.plot(kind="bar", figsize=(8, 5), color=["#6f8f58", "#d65a4a"])
    ax.axhline(0, color="#25344a", linewidth=0.8)
    ax.set_title("Modelled win-probability shift from an immediate penalty goal")
    ax.set_xlabel("Competition tier")
    ax.set_ylabel("Change in win probability")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(["Penalty scored for team", "Penalty scored against team"], frameon=False)
    ax.figure.tight_layout()
    ax.figure.savefig(path, dpi=180)
    plt.close(ax.figure)


def run_bridge_analysis(paths: ProjectPaths) -> dict[str, Any]:
    """Run the linked state, opportunity, counterfactual, and robustness lane."""

    panel_paths: list[tuple[str, str, Path]] = []
    world_path = paths.processed_dir / "statsbomb_world_cup_temporal_features.csv"
    history_path = paths.processed_dir / "statsbomb_history_temporal_features.csv"
    if world_path.exists():
        panel_paths.append(("statsbomb_world_cup", "world_cup", world_path))
    if history_path.exists():
        history = pd.read_csv(history_path, usecols=["competition_tier"]).drop_duplicates()
        for tier in sorted(history["competition_tier"].dropna().unique()):
            panel_paths.append(("statsbomb_history", str(tier), history_path))
    if not panel_paths:
        raise SourceError("Bridge analysis requires temporal StatsBomb panels.")

    artifacts: list[dict[str, Any]] = []
    skill_rows: list[dict[str, Any]] = []
    impact_frames: list[pd.DataFrame] = []
    model_groups: list[dict[str, Any]] = []
    for panel, tier, path in panel_paths:
        frame = _prepare_temporal_frame(paths, path)
        if panel == "statsbomb_history":
            frame = frame.loc[frame["competition_tier"].eq(tier)].reset_index(drop=True)
        predictions, metrics = _fit_bridge_panel(frame)
        suffix = tier.replace(" ", "_")
        prediction_path = paths.results_dir / f"bridge_statsbomb_{suffix}_oof_predictions.csv"
        write_csv_atomic(predictions, prediction_path)
        artifacts.append({"path": str(prediction_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(predictions)), "sha256": sha256_file(prediction_path)})
        for item in metrics:
            skill_rows.append({"panel": panel, "tier": tier, **item})
        model_groups.append({"panel": panel, "tier": tier, "models": metrics})
        impact_frames.append(_impact_summary(predictions, panel=panel, tier=tier))

    impact = pd.concat(impact_frames, ignore_index=True)
    impact_path = paths.results_dir / "bridge_penalty_win_impact.csv"
    write_csv_atomic(impact, impact_path)
    artifacts.append({"path": str(impact_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(impact)), "sha256": sha256_file(impact_path)})
    skill_path = paths.results_dir / "bridge_model_skill.csv"
    skill_frame = pd.DataFrame(skill_rows)
    write_csv_atomic(skill_frame, skill_path)
    artifacts.append({"path": str(skill_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(skill_frame)), "sha256": sha256_file(skill_path)})

    assets = paths.results_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    skill_chart = assets / "12_bridge_model_skill.png"
    impact_chart = assets / "13_penalty_win_impact.png"
    _write_skill_chart(skill_chart, skill_rows)
    _write_impact_chart(impact_chart, impact)
    artifacts.extend([
        {"path": str(skill_chart.relative_to(paths.root)).replace("\\", "/"), "sha256": sha256_file(skill_chart)},
        {"path": str(impact_chart.relative_to(paths.root)).replace("\\", "/"), "sha256": sha256_file(impact_chart) if impact_chart.exists() else None},
    ])

    manifest = {
        "pipeline": "research_etl.bridge_analysis",
        "created_at": _utc_now(),
        "status": "ready",
        "interpretation": (
            "The bridge model predicts final regulation result from a pre-window state. Opportunity variants are robustness checks; "
            "the penalty scenarios change only goal_diff_pre by one goal and therefore estimate immediate score-state sensitivity, "
            "not the full tactical or psychological effect of a penalty."
        ),
        "non_pooling_rule": "World Cup, selected club, and selected non-World-Cup international panels remain separate.",
        "primary_variant": "opportunity_augmented",
        "models": model_groups,
        "artifacts": artifacts,
    }
    write_json_atomic(manifest, paths.results_dir / "bridge_analysis_manifest.json")
    return manifest
