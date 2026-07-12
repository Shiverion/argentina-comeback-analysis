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


def _render_broader_baseline_charts(
    paths: ProjectPaths,
    rarity: pd.DataFrame,
    continuation: pd.DataFrame,
    historical_events: pd.DataFrame,
    historical_snapshots: pd.DataFrame,
) -> list[Path]:
    """Render the two broader-baseline figures from the same generated tables."""

    import matplotlib.pyplot as plt

    assets = paths.results_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.titleweight": "bold"})

    rarity_path = assets / "07_broader_baseline_rarity.png"
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for tier, color, marker in (("club", "#e34948", "o"), ("intl", "#6fa8d6", "s")):
        subset = rarity.loc[rarity["competition_tier"].eq(tier)].sort_values("threshold_minute")
        lower = (subset["empirical_probability"] - subset["wilson_lower"]).clip(lower=0) * 100
        upper = (subset["wilson_upper"] - subset["empirical_probability"]).clip(lower=0) * 100
        ax.errorbar(
            subset["threshold_minute"], subset["empirical_probability"] * 100,
            yerr=[lower, upper], fmt=f"{marker}-", color=color, linewidth=1.8,
            capsize=3, label=f"{tier.title()} (n={int(subset['total_matches_in_tier'].iloc[0])} matches)",
        )
        if tier == "club":
            for row in subset.itertuples():
                offset = (0, -15) if int(row.threshold_minute) == 80 else (0, 8)
                ax.annotate(
                    f"{int(row.comeback_wins)}/{int(row.eligible_matches)}",
                    (row.threshold_minute, row.empirical_probability * 100),
                    textcoords="offset points", xytext=offset, ha="center", fontsize=7,
                )
    ax.set_xlabel("Threshold minute")
    ax.set_ylabel("Comeback rate (%)")
    ax.set_title("Late two-goal comebacks in the selected broader sample")
    ax.set_ylim(-0.15, 1.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(rarity_path, dpi=180)
    plt.close(fig)

    wc_rows = []
    for minute, goal_difference in FOCAL_CHECKPOINTS:
        estimate = continuation_probability(
            historical_events,
            historical_snapshots,
            elapsed_seconds=minute * 60,
            goal_difference=goal_difference,
        )
        wc_rows.append({"minute": minute, "p_win": estimate.p_win, "lo": estimate.interval_lower, "hi": estimate.interval_upper})
    world_cup = pd.DataFrame(wc_rows)

    continuation_path = assets / "08_broader_baseline_continuation.png"
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for tier, color, marker in (("club", "#e34948", "o"), ("intl", "#6fa8d6", "s")):
        subset = continuation.loc[continuation["competition_tier"].eq(tier)].sort_values("minute")
        ax.plot(subset["minute"], subset["p_win"] * 100, color=color, marker=marker, linewidth=1.8, label=f"{tier.title()} (StatsBomb)")
        ax.fill_between(subset["minute"], subset["interval_lower"] * 100, subset["interval_upper"] * 100, color=color, alpha=0.12)
    ax.plot(world_cup["minute"], world_cup["p_win"] * 100, color="#2a78d6", marker="^", linewidth=1.8, label="World Cup (Fjelstul)")
    ax.fill_between(world_cup["minute"], world_cup["lo"] * 100, world_cup["hi"] * 100, color="#2a78d6", alpha=0.1)
    ax.set_xlabel("Minute")
    ax.set_ylabel("Regulation win probability (%)\n| same score state, broad historical lookup")
    ax.set_title("Continuation probability across disjoint competition samples")
    ax.set_ylim(-5, 105)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(continuation_path, dpi=180)
    plt.close(fig)
    return [rarity_path, continuation_path]


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
    rarity_frame = pd.DataFrame(rarity_rows)
    continuation_frame = pd.DataFrame(continuation_rows)
    write_csv_atomic(rarity_frame, rarity_path)
    write_csv_atomic(continuation_frame, continuation_path)
    chart_paths = _render_broader_baseline_charts(
        paths,
        rarity_frame,
        continuation_frame,
        events,
        snapshots,
    )

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
            *[
                {
                    "path": str(path.relative_to(paths.root)).replace("\\", "/"),
                    "sha256": sha256_file(path),
                }
                for path in chart_paths
            ],
        ],
    }
    write_json_atomic(manifest, paths.results_dir / "broader_baseline_manifest.json")
    return manifest
