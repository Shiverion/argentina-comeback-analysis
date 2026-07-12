"""Descriptive and partial opportunity-adjusted summaries for officiating features.

The outputs are deliberately modest. They measure association between attack
opportunity proxies and penalty-kick outcomes; they do not adjudicate decision
correctness or infer officiating intent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_poisson_deviance
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, sha256_file, write_json_atomic
from research_etl.transform import write_csv_atomic


OPPORTUNITY_FEATURES = ["box_entries", "non_penalty_xg"]
CORRELATION_PERMUTATIONS = 10_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clustered_spearman_interval(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    cluster: str,
    replicates: int = 500,
    random_state: int = 20260712,
) -> dict[str, float | int | None]:
    """Spearman correlation with bootstrap resampling at match level."""

    valid = frame[[cluster, x, y]].dropna().copy()
    if valid.empty or valid[x].nunique() < 2 or valid[y].nunique() < 2:
        return {"correlation": None, "lower": None, "upper": None, "rows": int(len(valid)), "clusters": 0}
    observed = float(valid[x].corr(valid[y], method="spearman"))
    cluster_arrays = [
        group[[x, y]].to_numpy(dtype=float)
        for _, group in valid.groupby(cluster, sort=False)
    ]
    clusters = np.arange(len(cluster_arrays))
    rng = np.random.default_rng(random_state)
    bootstrap = []
    for _ in range(replicates):
        selected = rng.choice(clusters, size=len(clusters), replace=True)
        sample = np.concatenate([cluster_arrays[index] for index in selected], axis=0)
        coefficient = pd.Series(sample[:, 0]).corr(pd.Series(sample[:, 1]), method="spearman")
        if pd.notna(coefficient):
            bootstrap.append(float(coefficient))
    lower, upper = (np.quantile(bootstrap, [0.025, 0.975]).tolist() if bootstrap else [np.nan, np.nan])
    return {
        "correlation": observed,
        "lower": float(lower) if pd.notna(lower) else None,
        "upper": float(upper) if pd.notna(upper) else None,
        "rows": int(len(valid)),
        "clusters": int(len(clusters)),
    }


def clustered_spearman_permutation(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    cluster: str,
    replicates: int = CORRELATION_PERMUTATIONS,
    random_state: int = 20260712,
) -> dict[str, float | int | str | None]:
    """Test Spearman association by permuting whole outcome clusters.

    The permutation preserves the two team rows and their within-match outcome
    structure, while breaking the alignment between exposure clusters and
    outcome clusters. It is an association test, not a causal or bias test.
    """

    valid = frame[[cluster, x, y]].dropna().copy()
    grouped = [group[[x, y]].to_numpy(dtype=float) for _, group in valid.groupby(cluster, sort=False)]
    if len(grouped) < 2 or valid[x].nunique() < 2 or valid[y].nunique() < 2:
        return {
            "permutation_p_value": None,
            "null_lower": None,
            "null_upper": None,
            "replicates": 0,
            "method": "whole_cluster_permutation",
        }

    observed_values = np.concatenate(grouped, axis=0)
    x_rank = rankdata(observed_values[:, 0]).astype(float)
    y_rank = rankdata(observed_values[:, 1]).astype(float)
    x_rank = (x_rank - x_rank.mean()) / x_rank.std()
    y_rank = (y_rank - y_rank.mean()) / y_rank.std()
    y_rank_groups = []
    offset = 0
    for group in grouped:
        next_offset = offset + len(group)
        y_rank_groups.append(y_rank[offset:next_offset])
        offset = next_offset

    rng = np.random.default_rng(random_state)
    null = np.empty(replicates, dtype=float)
    cluster_indices = np.arange(len(y_rank_groups))
    for index in range(replicates):
        shuffled = np.concatenate([y_rank_groups[item] for item in rng.permutation(cluster_indices)])
        null[index] = float(np.mean(x_rank * shuffled))
    observed = float(np.mean(x_rank * y_rank))
    p_value = (int(np.count_nonzero(np.abs(null) >= abs(observed))) + 1) / (replicates + 1)
    return {
        "permutation_p_value": float(p_value),
        "null_lower": float(np.quantile(null, 0.025)),
        "null_upper": float(np.quantile(null, 0.975)),
        "replicates": int(replicates),
        "method": "whole_cluster_permutation",
    }


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Return deterministic Benjamini-Hochberg adjusted p-values."""

    if not p_values:
        return []
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values, kind="stable")
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for rank in range(len(values), 0, -1):
        position = order[rank - 1]
        running = min(running, values[position] * len(values) / rank)
        adjusted[position] = running
    return adjusted.tolist()


def _correlation_test(
    frame: pd.DataFrame,
    *,
    panel: str,
    tier: str | None,
    exposure: str,
    outcome: str,
    cluster: str,
    outcome_definition: str,
    exposure_definition: str,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    interval = clustered_spearman_interval(frame, x=exposure, y=outcome, cluster=cluster)
    permutation = clustered_spearman_permutation(
        frame, x=exposure, y=outcome, cluster=cluster, random_state=seed
    )
    summary = {
        **interval,
        **permutation,
        "exposure": exposure,
        "outcome": outcome,
        "panel": panel,
        "tier": tier,
    }
    row = {
        "panel": panel,
        "tier": tier or "",
        "exposure": exposure,
        "outcome": outcome,
        "exposure_definition": exposure_definition,
        "outcome_definition": outcome_definition,
        "rows": summary["rows"],
        "clusters": summary["clusters"],
        "spearman_correlation": summary["correlation"],
        "bootstrap_lower": summary["lower"],
        "bootstrap_upper": summary["upper"],
        "permutation_p_value": summary["permutation_p_value"],
        "permutation_null_lower": summary["null_lower"],
        "permutation_null_upper": summary["null_upper"],
        "permutation_replicates": summary["replicates"],
        "permutation_method": summary["method"],
    }
    return summary, row


def fit_oof_penalty_model(
    frame: pd.DataFrame,
    *,
    outcome: str,
    cluster: str,
    features: list[str] | None = None,
    folds: int = 5,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit a small, match-grouped out-of-fold Poisson opportunity model.

    This is a partial adjustment only: the feature set intentionally avoids
    post-match cards, fouls, score state, and referee variables until they are
    available at the correct pre-decision time grain.
    """

    features = features or OPPORTUNITY_FEATURES
    required = [cluster, outcome, "team_name", *features]
    model_frame = frame.dropna(subset=required).copy()
    model_frame[outcome] = pd.to_numeric(model_frame[outcome], errors="coerce")
    model_frame = model_frame.loc[model_frame[outcome].ge(0)].copy()
    groups = model_frame[cluster].astype(str)
    nonzero = int(model_frame[outcome].gt(0).sum())
    if len(model_frame) < 40 or groups.nunique() < 10 or nonzero < 10:
        raise SourceError(
            f"Opportunity model needs at least 40 rows, 10 matches, and 10 non-zero {outcome} rows; "
            f"received rows={len(model_frame)}, matches={groups.nunique()}, nonzero={nonzero}."
        )

    splits = min(folds, groups.nunique())
    splitter = GroupKFold(n_splits=splits)
    predictions = np.zeros(len(model_frame), dtype=float)
    for train_index, test_index in splitter.split(model_frame[features], model_frame[outcome], groups):
        model = make_pipeline(StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=1_000))
        model.fit(model_frame.iloc[train_index][features], model_frame.iloc[train_index][outcome])
        predictions[test_index] = model.predict(model_frame.iloc[test_index][features])

    result = model_frame.copy()
    result["expected_penalty_outcome_oof"] = predictions
    result["opportunity_residual_oof"] = result[outcome] - predictions
    null_prediction = np.repeat(float(result[outcome].mean()), len(result))
    metadata = {
        "outcome": outcome,
        "features": features,
        "rows": int(len(result)),
        "matches": int(groups.nunique()),
        "nonzero_outcomes": nonzero,
        "folds": splits,
        "oof_mean_poisson_deviance": float(mean_poisson_deviance(result[outcome], predictions)),
        "null_mean_poisson_deviance": float(mean_poisson_deviance(result[outcome], null_prediction)),
    }
    metadata["oof_beats_null"] = bool(
        metadata["oof_mean_poisson_deviance"] < metadata["null_mean_poisson_deviance"]
    )
    return result, metadata


def _team_residual_summary(predictions: pd.DataFrame, *, outcome: str) -> pd.DataFrame:
    return (
        predictions.groupby("team_name", as_index=False)
        .agg(
            matches=("team_name", "size"),
            observed_penalty_outcome=(outcome, "sum"),
            expected_penalty_outcome=("expected_penalty_outcome_oof", "sum"),
            opportunity_residual=("opportunity_residual_oof", "sum"),
        )
        .sort_values(["opportunity_residual", "team_name"], ascending=[False, True], kind="stable")
        .reset_index(drop=True)
    )


def _chart_penalty_opportunity(path: str, frame: pd.DataFrame, *, x: str, y: str, title: str, xlabel: str, ylabel: str) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    non_argentina = frame.loc[~frame["team_name"].eq("Argentina")]
    argentina = frame.loc[frame["team_name"].eq("Argentina")]
    ax.scatter(non_argentina[x], non_argentina[y], color="#6f8f58", alpha=0.48, s=28, label="Other team-match rows")
    if not argentina.empty:
        ax.scatter(argentina[x], argentina[y], color="#d65a4a", edgecolor="#5f241e", s=52, label="Argentina")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _analyze_statsbomb_panel(frame: pd.DataFrame, *, panel: str, tier: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    selected = frame.copy()
    if tier is not None:
        selected = selected.loc[selected["competition_tier"].eq(tier)].copy()
    selected["penalty_outcome"] = selected["penalty_shots"]
    correlation = clustered_spearman_interval(
        selected, x="box_entries", y="penalty_outcome", cluster="match_id"
    )
    predictions, metadata = fit_oof_penalty_model(selected, outcome="penalty_outcome", cluster="match_id")
    metadata.update({"panel": panel, "tier": tier, "box_entry_spearman": correlation})
    return predictions, _team_residual_summary(predictions, outcome="penalty_outcome"), metadata


def run_opportunity_analysis(paths: ProjectPaths) -> dict[str, Any]:
    """Write analysis tables/charts for every available opportunity panel."""

    assets = paths.results_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    correlation_summaries: list[dict[str, Any]] = []
    correlation_rows: list[dict[str, Any]] = []

    def register_correlation(**kwargs: Any) -> dict[str, Any]:
        summary, row = _correlation_test(**kwargs, seed=20260712 + len(correlation_rows))
        correlation_summaries.append(summary)
        correlation_rows.append(row)
        return summary

    pmsr_path = paths.processed_dir / "pmsr_2026_match_features.csv"
    if pmsr_path.exists():
        pmsr = pd.read_csv(pmsr_path)
        correlation = register_correlation(
            frame=pmsr,
            panel="pmsr_2026",
            tier=None,
            exposure="xg",
            outcome="penalties_awarded",
            cluster="match_number",
            outcome_definition="Official FIFA PMSR penalties awarded",
            exposure_definition="Team-match expected goals from official PMSR report",
        )
        possession_correlation = register_correlation(
            frame=pmsr,
            panel="pmsr_2026",
            tier=None,
            exposure="team_possession_pct",
            outcome="penalties_awarded",
            cluster="match_number",
            outcome_definition="Official FIFA PMSR penalties awarded",
            exposure_definition="Official team controlled-possession percentage; contested possession remains separate",
        )
        summary = (
            pmsr.groupby("team_name", as_index=False)
            .agg(
                matches=("match_number", "size"),
                penalties_awarded=("penalties_awarded", "sum"),
                xg=("xg", "sum"),
                possession_pct=("team_possession_pct", "mean"),
                final_third_receptions=("receptions_final_third", "sum"),
            )
            .sort_values(["penalties_awarded", "team_name"], ascending=[False, True], kind="stable")
        )
        summary["penalties_per_match"] = summary["penalties_awarded"] / summary["matches"]
        summary_path = paths.results_dir / "opportunity_pmsr_2026_team_summary.csv"
        write_csv_atomic(summary, summary_path)
        chart_path = assets / "09_pmsr_2026_penalties_vs_xg.png"
        _chart_penalty_opportunity(
            str(chart_path), pmsr, x="xg", y="penalties_awarded",
            title="Penalty awards and xG in the 2026 FIFA World Cup",
            xlabel="Team-match xG", ylabel="Penalties awarded in the match",
        )
        artifacts.extend(
            [
                {"path": str(summary_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(summary)), "sha256": sha256_file(summary_path)},
                {"path": str(chart_path.relative_to(paths.root)).replace("\\", "/"), "sha256": sha256_file(chart_path)},
            ]
        )
        models.append({
            "panel": "pmsr_2026",
            "model_status": "descriptive_only",
            "xg_spearman": correlation,
            "possession_spearman": possession_correlation,
        })

    world_cup_path = paths.processed_dir / "statsbomb_world_cup_opportunity_features.csv"
    if world_cup_path.exists():
        world_cup = pd.read_csv(world_cup_path)
        correlation = register_correlation(
            frame=world_cup,
            panel="statsbomb_world_cup",
            tier=None,
            exposure="box_entries",
            outcome="penalty_shots",
            cluster="match_id",
            outcome_definition="StatsBomb regulation penalty-shot event proxy",
            exposure_definition="Pass/carry entries into the opponent penalty area",
        )
        possession_correlation = register_correlation(
            frame=world_cup,
            panel="statsbomb_world_cup",
            tier=None,
            exposure="possession_sequence_share",
            outcome="penalty_shots",
            cluster="match_id",
            outcome_definition="StatsBomb regulation penalty-shot event proxy",
            exposure_definition="Event-derived possession-sequence share, not official possession time",
        )
        register_correlation(
            frame=world_cup,
            panel="statsbomb_world_cup",
            tier=None,
            exposure="box_entries",
            outcome="penalty_fouls_won",
            cluster="match_id",
            outcome_definition="StatsBomb Foul Won event flagged as penalty; incomplete award proxy",
            exposure_definition="Pass/carry entries into the opponent penalty area",
        )
        predictions, team_summary, metadata = _analyze_statsbomb_panel(world_cup, panel="statsbomb_world_cup")
        metadata["box_entry_spearman"] = correlation
        metadata["possession_spearman"] = possession_correlation
        predictions_path = paths.results_dir / "opportunity_statsbomb_world_cup_oof_predictions.csv"
        team_path = paths.results_dir / "opportunity_statsbomb_world_cup_team_residuals.csv"
        write_csv_atomic(predictions, predictions_path)
        chart_path = assets / "10_statsbomb_world_cup_box_entries_vs_penalty_shots.png"
        _chart_penalty_opportunity(
            str(chart_path), world_cup, x="box_entries", y="penalty_shots",
            title="Penalty kicks and penalty-area entries in the 2018/2022 World Cup",
            xlabel="Pass/carry entries into the opponent penalty area", ylabel="Penalty kicks in regulation",
        )
        artifacts.extend(
            [
                {"path": str(predictions_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(predictions)), "sha256": sha256_file(predictions_path)},
                {"path": str(chart_path.relative_to(paths.root)).replace("\\", "/"), "sha256": sha256_file(chart_path)},
            ]
        )
        if metadata["oof_beats_null"]:
            write_csv_atomic(team_summary, team_path)
            artifacts.append(
                {"path": str(team_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(team_summary)), "sha256": sha256_file(team_path)}
            )
        else:
            team_path.unlink(missing_ok=True)
        models.append(metadata)

    history_path = paths.processed_dir / "statsbomb_history_opportunity_features.csv"
    if history_path.exists():
        history = pd.read_csv(history_path)
        for tier in sorted(history["competition_tier"].dropna().unique()):
            selected_history = history.loc[history["competition_tier"].eq(tier)].copy()
            correlation = register_correlation(
                frame=selected_history,
                panel="statsbomb_history",
                tier=str(tier),
                exposure="box_entries",
                outcome="penalty_shots",
                cluster="match_id",
                outcome_definition="StatsBomb regulation penalty-shot event proxy",
                exposure_definition="Pass/carry entries into the opponent penalty area",
            )
            possession_correlation = register_correlation(
                frame=selected_history,
                panel="statsbomb_history",
                tier=str(tier),
                exposure="possession_sequence_share",
                outcome="penalty_shots",
                cluster="match_id",
                outcome_definition="StatsBomb regulation penalty-shot event proxy",
                exposure_definition="Event-derived possession-sequence share, not official possession time",
            )
            register_correlation(
                frame=selected_history,
                panel="statsbomb_history",
                tier=str(tier),
                exposure="box_entries",
                outcome="penalty_fouls_won",
                cluster="match_id",
                outcome_definition="StatsBomb Foul Won event flagged as penalty; incomplete award proxy",
                exposure_definition="Pass/carry entries into the opponent penalty area",
            )
            predictions, team_summary, metadata = _analyze_statsbomb_panel(
                history, panel="statsbomb_history", tier=str(tier)
            )
            metadata["box_entry_spearman"] = correlation
            metadata["possession_spearman"] = possession_correlation
            suffix = str(tier).replace(" ", "_")
            predictions_path = paths.results_dir / f"opportunity_statsbomb_{suffix}_oof_predictions.csv"
            team_path = paths.results_dir / f"opportunity_statsbomb_{suffix}_team_residuals.csv"
            write_csv_atomic(predictions, predictions_path)
            artifacts.extend(
                [
                    {"path": str(predictions_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(predictions)), "sha256": sha256_file(predictions_path)},
                ]
            )
            if metadata["oof_beats_null"]:
                write_csv_atomic(team_summary, team_path)
                artifacts.append(
                    {"path": str(team_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(team_summary)), "sha256": sha256_file(team_path)}
                )
            else:
                team_path.unlink(missing_ok=True)
            models.append(metadata)

    if correlation_rows:
        p_values = [float(row["permutation_p_value"]) for row in correlation_rows]
        q_values = _benjamini_hochberg(p_values)
        for row, summary, q_value in zip(correlation_rows, correlation_summaries, q_values):
            row["bh_q_value"] = q_value
            row["significant_bh_05"] = bool(q_value < 0.05)
            summary["bh_q_value"] = q_value
            summary["significant_bh_05"] = bool(q_value < 0.05)
        correlation_path = paths.results_dir / "opportunity_correlation_tests.csv"
        write_csv_atomic(pd.DataFrame(correlation_rows), correlation_path)
        artifacts.append({
            "path": str(correlation_path.relative_to(paths.root)).replace("\\", "/"),
            "rows": int(len(correlation_rows)),
            "sha256": sha256_file(correlation_path),
        })

    if not artifacts:
        raise SourceError("Opportunity analysis requires at least one processed opportunity feature panel.")
    manifest = {
        "pipeline": "research_etl.opportunity_analysis",
        "created_at": _utc_now(),
        "status": "ready",
        "interpretation": (
            "Descriptive association and partial opportunity-adjusted residuals only. The current model excludes "
            "pre-decision score state, strength, and validated decision correctness; it cannot identify bias or intent."
        ),
        "non_pooling_rule": "Models are fit and reported separately for every source population and competition tier.",
        "inference": {
            "correlation_test": "Spearman correlation with 95% match-cluster bootstrap interval and whole-match permutation p-value.",
            "permutation_replicates": CORRELATION_PERMUTATIONS,
            "multiple_testing": "Benjamini-Hochberg false-discovery-rate correction across the registered correlation family.",
            "interpretation": "Significance indicates association under the permutation design; it does not establish causality, decision correctness, or officiating bias.",
        },
        "models": models,
        "artifacts": artifacts,
    }
    write_json_atomic(manifest, paths.results_dir / "opportunity_analysis_manifest.json")
    return manifest
