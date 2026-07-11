"""Notebook-independent analytical outputs built from validated processed artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from research_etl.counterfactual import continuation_probability, scenario_timing_sensitivity, wilson_interval
from research_etl.discipline import percentile_rank, team_tournament_discipline
from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, load_config, sha256_file, write_json_atomic
from research_etl.transform import write_csv_atomic

FOCAL_CHECKPOINTS = [(14, -1), (66, -2), (70, -2), (75, -2), (78, -1), (80, -1), (82, 0), (91, 1)]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_scenario_only_analysis(paths: ProjectPaths) -> dict[str, Any]:
    """Execute configured conditional scenarios without assessing decision correctness."""

    config = load_config(paths)
    events_path = paths.processed_dir / "historical_match_events.csv"
    snapshots_path = paths.processed_dir / "historical_snapshots.csv"
    if not events_path.exists() or not snapshots_path.exists():
        raise SourceError("Scenario analysis requires historical_match_events.csv and historical_snapshots.csv.")
    events = pd.read_csv(events_path)
    snapshots = pd.read_csv(snapshots_path)

    frames = []
    for scenario in config.get("scenario_only", []):
        if scenario.get("decision_correctness_status") != "not_assessed":
            raise SourceError("Scenario-only analysis must keep decision_correctness_status=not_assessed.")
        observed = scenario["observed_score"]
        alternate = scenario["alternate_score"]
        frame = scenario_timing_sensitivity(
            events,
            snapshots,
            scenario_id=scenario["scenario_id"],
            elapsed_seconds_candidates=[int(value) * 60 for value in scenario["timing_minutes"]],
            observed_focal_score=int(observed["Argentina"]),
            observed_opponent_score=int(observed["Egypt"]),
            alternate_focal_score=int(alternate["Argentina"]),
            alternate_opponent_score=int(alternate["Egypt"]),
            evidence_status=scenario["evidence_status"],
        )
        frame.insert(1, "incident_id", scenario["incident_id"])
        frame["impact_percentage_points"] = frame["impact_probability_points"] * 100
        frame["bootstrap_lower_percentage_points"] = frame["bootstrap_lower"] * 100
        frame["bootstrap_upper_percentage_points"] = frame["bootstrap_upper"] * 100
        frame["assumption"] = scenario["assumption"]
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output_path = paths.results_dir / "scenario_only_counterfactual.csv"
    write_csv_atomic(result, output_path)
    manifest = {
        "pipeline": "research_etl.analysis.scenario_only",
        "created_at": _utc_now(),
        "status": "ready" if not result.empty else "no_scenarios_configured",
        "decision_correctness_status": "not_assessed",
        "rows": int(len(result)),
        "output": str(output_path.relative_to(paths.root)).replace("\\", "/"),
        "sha256": sha256_file(output_path),
    }
    write_json_atomic(manifest, paths.results_dir / "scenario_only_manifest.json")
    return manifest


def run_descriptive_sensitivity(paths: ProjectPaths) -> dict[str, Any]:
    """Write era-specific rarity and tie-aware Argentina discipline summaries."""

    config = load_config(paths)
    snapshots_path = paths.processed_dir / "historical_snapshots.csv"
    if not snapshots_path.exists():
        raise SourceError("Descriptive sensitivity requires historical_snapshots.csv.")
    snapshots = pd.read_csv(snapshots_path)
    rarity_rows = []
    for start_year in config["era_sensitivity_start_years"]:
        for threshold in config["threshold_minutes"]:
            eligible = snapshots.loc[
                snapshots["year"].ge(int(start_year))
                & snapshots["threshold_minute"].eq(int(threshold))
                & snapshots["goal_difference"].le(-2)
            ].drop_duplicates("match_id")
            wins = int(eligible["regulation_result"].eq("TRAILING_TEAM_WIN").sum())
            total = int(len(eligible))
            lower, upper = wilson_interval(wins, total)
            rarity_rows.append(
                {
                    "start_year": int(start_year),
                    "threshold_minute": int(threshold),
                    "eligible_matches": total,
                    "comeback_wins": wins,
                    "empirical_probability": wins / total if total else None,
                    "wilson_lower": lower,
                    "wilson_upper": upper,
                }
            )
    rarity = pd.DataFrame(rarity_rows)
    rarity_path = paths.results_dir / "rarity_era_sensitivity.csv"
    write_csv_atomic(rarity, rarity_path)

    raw_dir = paths.raw_dir / "fjelstul"
    discipline = team_tournament_discipline(
        pd.read_csv(raw_dir / "matches.csv"),
        pd.read_csv(raw_dir / "goals.csv"),
        pd.read_csv(raw_dir / "bookings.csv"),
    )
    argentina = discipline.loc[discipline["team_name"].eq("Argentina")].copy()
    percentile_rows = []
    for row in argentina.itertuples(index=False):
        metrics = ["penalty_goals_scored_per_match"]
        if row.year >= 1970:
            metrics.extend(["yellow_cards_per_match", "red_cards_per_match"])
        for metric in metrics:
            result = percentile_rank(discipline, row.tournament_name, "Argentina", metric)
            percentile_rows.append(
                {
                    "year": int(row.year),
                    "tournament_name": row.tournament_name,
                    "metric": metric,
                    "value": result["value"],
                    "percentile": result["percentile"],
                    "tie_count": result["tie_count"],
                    "field_size": result["field_size"],
                }
            )
    discipline_path = paths.results_dir / "argentina_discipline_percentiles.csv"
    write_csv_atomic(pd.DataFrame(percentile_rows), discipline_path)

    manifest = {
        "pipeline": "research_etl.analysis.descriptive_sensitivity",
        "created_at": _utc_now(),
        "status": "ready",
        "artifacts": [
            {
                "path": str(rarity_path.relative_to(paths.root)).replace("\\", "/"),
                "rows": int(len(rarity)),
                "sha256": sha256_file(rarity_path),
            },
            {
                "path": str(discipline_path.relative_to(paths.root)).replace("\\", "/"),
                "rows": int(len(percentile_rows)),
                "sha256": sha256_file(discipline_path),
            },
        ],
        "blocked_extensions": {
            "broad_international_timeline_baseline": "See run_broader_baseline_sensitivity() / results/broader_baseline_rarity.csv for the club and non-World-Cup international cross-check (StatsBomb open data), reported as separate tiers rather than pooled into this World-Cup-only table.",
            "exposure_adjusted_discipline": "Penalty-area entries, challenges, fouls, and referee assignments are not integrated.",
            "club_discipline_check": "Club-competition discipline stats are not computed -- club competitions are not FIFA-officiated and are not relevant to the Argentina/FIFA bias question this section addresses.",
        },
    }
    write_json_atomic(manifest, paths.results_dir / "descriptive_sensitivity_manifest.json")
    return manifest


def run_broader_baseline_sensitivity(paths: ProjectPaths) -> dict[str, Any]:
    """Cross-check the World-Cup-only rarity/continuation results against club and
    non-World-Cup international competitions (StatsBomb open data, Project.md S6.3).

    Each `competition_tier` ("club", "intl") is reported strictly separately from
    each other and from the World Cup baseline -- never pooled into one figure
    (Project.md S5.5's anti-pooling principle applies here too: club and
    international matches differ in squad-selection context and stakes).
    """

    events_path = paths.processed_dir / "statsbomb_historical_match_events.csv"
    snapshots_path = paths.processed_dir / "statsbomb_historical_snapshots.csv"
    if not events_path.exists() or not snapshots_path.exists():
        raise SourceError(
            "Broader-baseline sensitivity requires statsbomb_historical_match_events.csv "
            "and statsbomb_historical_snapshots.csv."
        )
    events = pd.read_csv(events_path, dtype={"match_id": str})
    snapshots = pd.read_csv(snapshots_path, dtype={"match_id": str})

    rarity_rows = []
    continuation_rows = []
    for tier in sorted(snapshots["competition_tier"].unique()):
        tier_snapshots = snapshots.loc[snapshots["competition_tier"].eq(tier)]
        tier_events = events.loc[events["competition_tier"].eq(tier)]
        tier_matches = int(tier_snapshots.drop_duplicates("match_id").shape[0])

        for threshold in (70, 75, 78, 80):
            eligible = tier_snapshots.loc[
                tier_snapshots["threshold_minute"].eq(threshold) & tier_snapshots["goal_difference"].le(-2)
            ].drop_duplicates("match_id")
            wins = int(eligible["regulation_result"].eq("TRAILING_TEAM_WIN").sum())
            total = int(len(eligible))
            lower, upper = wilson_interval(wins, total)
            rarity_rows.append(
                {
                    "competition_tier": tier,
                    "total_matches_in_tier": tier_matches,
                    "threshold_minute": threshold,
                    "eligible_matches": total,
                    "comeback_wins": wins,
                    "empirical_probability": wins / total if total else None,
                    "wilson_lower": lower,
                    "wilson_upper": upper,
                }
            )

        for minute, goal_difference in FOCAL_CHECKPOINTS:
            estimate = continuation_probability(
                tier_events, tier_snapshots, elapsed_seconds=minute * 60, goal_difference=goal_difference
            )
            continuation_rows.append(
                {
                    "competition_tier": tier,
                    "minute": minute,
                    "argentina_goal_difference": goal_difference,
                    "eligible_matches": estimate.eligible_matches,
                    "eligible_team_states": estimate.eligible_team_states,
                    "p_win": estimate.p_win,
                    "interval_lower": estimate.interval_lower,
                    "interval_upper": estimate.interval_upper,
                    "interval_method": estimate.interval_method,
                }
            )

    rarity_path = paths.results_dir / "broader_baseline_rarity.csv"
    continuation_path = paths.results_dir / "broader_baseline_continuation.csv"
    write_csv_atomic(pd.DataFrame(rarity_rows), rarity_path)
    write_csv_atomic(pd.DataFrame(continuation_rows), continuation_path)

    manifest = {
        "pipeline": "research_etl.analysis.broader_baseline_sensitivity",
        "created_at": _utc_now(),
        "status": "ready",
        "non_pooling_rule": "club and intl tiers are reported separately from each other and from the "
        "World-Cup-only baseline in every row above -- never combined into one figure.",
        "artifacts": [
            {
                "path": str(rarity_path.relative_to(paths.root)).replace("\\", "/"),
                "rows": int(len(rarity_rows)),
                "sha256": sha256_file(rarity_path),
            },
            {
                "path": str(continuation_path.relative_to(paths.root)).replace("\\", "/"),
                "rows": int(len(continuation_rows)),
                "sha256": sha256_file(continuation_path),
            },
        ],
    }
    write_json_atomic(manifest, paths.results_dir / "broader_baseline_manifest.json")
    return manifest
