"""Classify late two-goal comebacks by their penalty path.

This module is deliberately separate from the World Cup rarity calculation.
StatsBomb event data can identify penalty-shot events, but it is not a complete
historical adjudication ledger.  The output therefore reports an availability
sample and keeps the focal 2026 match as an explicit, non-denominator case.

The primary cutoff is 79:00.  A state is evaluated strictly before the cutoff
(``elapsed_seconds < cutoff``), while penalty events are counted from the
cutoff onward (``elapsed_seconds >= cutoff``).  This prevents an event exactly
at the boundary from being counted in both halves of the definition.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_etl.counterfactual import wilson_interval
from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, load_config, sha256_file, write_json_atomic
from research_etl.statsbomb_history import _canonical_team_name, extract_match_timeline
from research_etl.transform import write_csv_atomic


PRIMARY_CUTOFF_MINUTE = 79
DEFAULT_CUTOFFS = [75, 78, 79, 80]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _elapsed_seconds(event: dict[str, Any]) -> int | None:
    if event.get("period") not in (1, 2) or event.get("minute") is None:
        return None
    return int(event["minute"]) * 60 + int(event.get("second") or 0)


def _is_penalty_shot(event: dict[str, Any]) -> bool:
    return (
        event.get("period") in (1, 2)
        and (event.get("type") or {}).get("name") == "Shot"
        and (event.get("shot") or {}).get("type", {}).get("name") == "Penalty"
    )


def _is_penalty_goal(event: dict[str, Any]) -> bool:
    return _is_penalty_shot(event) and (event.get("shot") or {}).get("outcome", {}).get("name") == "Goal"


def _is_goal_event(event: dict[str, Any]) -> bool:
    return (
        ((event.get("type") or {}).get("name") == "Shot" and (event.get("shot") or {}).get("outcome", {}).get("name") == "Goal")
        or (event.get("type") or {}).get("name") == "Own Goal For"
    )


def _score_before(timeline: list[dict[str, Any]], cutoff_seconds: int) -> tuple[int, int]:
    prior = [row for row in timeline if int(row["elapsed_seconds"]) < cutoff_seconds]
    if not prior:
        return 0, 0
    latest = prior[-1]
    return int(latest["home_score"]), int(latest["away_score"])


def _final_score(timeline: list[dict[str, Any]]) -> tuple[int, int]:
    if not timeline:
        return 0, 0
    latest = timeline[-1]
    return int(latest["home_score"]), int(latest["away_score"])


def _team_penalty_counts(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    cutoff_seconds: int,
) -> dict[str, dict[str, int]]:
    home = match_meta["home_team"]["home_team_name"]
    away = match_meta["away_team"]["away_team_name"]
    counts = {
        home: {"penalty_shots": 0, "penalty_goals": 0},
        away: {"penalty_shots": 0, "penalty_goals": 0},
    }
    for event in events:
        elapsed = _elapsed_seconds(event)
        if elapsed is None or elapsed < cutoff_seconds or not _is_penalty_shot(event):
            continue
        team = _canonical_team_name(match_meta, event)
        if team is None:
            raise SourceError(
                f"Could not map penalty event {event.get('id')} in match {match_meta.get('match_id')} "
                f"to {home} or {away}."
            )
        counts[team]["penalty_shots"] += 1
        if _is_penalty_goal(event):
            counts[team]["penalty_goals"] += 1
    return counts


def _recovery_features(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    focal_team: str,
    home_before: int,
    away_before: int,
    cutoff_seconds: int,
) -> dict[str, Any]:
    """Track whether later goals reduce, equalize, or reverse the deficit.

    This is an outcome-independent mechanism lane: a team can equalize without
    winning the match, and a penalty can reduce a two-goal deficit without ever
    producing an equalizer.
    """

    home = match_meta["home_team"]["home_team_name"]
    away = match_meta["away_team"]["away_team_name"]
    goal_events: list[tuple[int, str, str, bool]] = []
    for event in events:
        elapsed = _elapsed_seconds(event)
        if elapsed is None or elapsed < cutoff_seconds or not _is_goal_event(event):
            continue
        team = _canonical_team_name(match_meta, event)
        if team is None:
            raise SourceError(
                f"Could not map goal event {event.get('id')} in match {match_meta.get('match_id')} "
                f"to {home} or {away}."
            )
        goal_events.append((elapsed, str(event.get("id", "")), team, _is_penalty_goal(event)))
    goal_events.sort(key=lambda item: (item[0], item[1]))

    current_home = int(home_before)
    current_away = int(away_before)
    features: dict[str, Any] = {
        "own_penalty_goal_after_cutoff": False,
        "own_penalty_goal_while_two_down": False,
        "own_penalty_goal_while_two_or_more_down": False,
        "own_penalty_goal_as_equalizer": False,
        "own_penalty_goal_as_go_ahead": False,
        "reached_level_after_cutoff": False,
        "equalized_by_own_penalty": False,
        "equalized_by_open_play": False,
        "first_equalizer_method": None,
        "reached_lead_after_cutoff": False,
        "first_own_goal_after_cutoff_was_penalty": False,
        "own_penalty_goal_count_after_cutoff": 0,
        "two_own_penalty_shots_within_10m": False,
        "two_own_penalty_goals_within_10m": False,
        "minimum_gap_between_own_penalty_shots_seconds": None,
    }
    own_penalty_shot_times = sorted(
        int(elapsed)
        for event in events
        for elapsed in [_elapsed_seconds(event)]
        if elapsed is not None and elapsed >= cutoff_seconds and _is_penalty_shot(event)
        and _canonical_team_name(match_meta, event) == focal_team
    )
    own_penalty_goal_times = sorted(
        int(elapsed)
        for event in events
        for elapsed in [_elapsed_seconds(event)]
        if elapsed is not None and elapsed >= cutoff_seconds and _is_penalty_goal(event)
        and _canonical_team_name(match_meta, event) == focal_team
    )
    if len(own_penalty_shot_times) >= 2:
        gaps = [right - left for left, right in zip(own_penalty_shot_times, own_penalty_shot_times[1:])]
        features["minimum_gap_between_own_penalty_shots_seconds"] = min(gaps)
        features["two_own_penalty_shots_within_10m"] = min(gaps) <= 600
    if len(own_penalty_goal_times) >= 2:
        features["two_own_penalty_goals_within_10m"] = any(
            right - left <= 600 for left, right in zip(own_penalty_goal_times, own_penalty_goal_times[1:])
        )
    first_own_goal_seen = False
    for _, _, team, penalty_goal in goal_events:
        before_diff = current_home - current_away if focal_team == home else current_away - current_home
        is_own_goal = team == focal_team
        if is_own_goal:
            if not first_own_goal_seen:
                features["first_own_goal_after_cutoff_was_penalty"] = bool(penalty_goal)
                first_own_goal_seen = True
            if penalty_goal:
                features["own_penalty_goal_after_cutoff"] = True
                features["own_penalty_goal_count_after_cutoff"] += 1
                features["own_penalty_goal_while_two_down"] |= before_diff == -2
                features["own_penalty_goal_while_two_or_more_down"] |= before_diff <= -2
                features["own_penalty_goal_as_equalizer"] |= before_diff == -1
                features["own_penalty_goal_as_go_ahead"] |= before_diff == 0
            if team == home:
                current_home += 1
            elif team == away:
                current_away += 1
            after_diff = current_home - current_away if focal_team == home else current_away - current_home
            if before_diff == -1 and after_diff == 0:
                features["reached_level_after_cutoff"] = True
                if features["first_equalizer_method"] is None:
                    if penalty_goal:
                        features["equalized_by_own_penalty"] = True
                        features["first_equalizer_method"] = "penalty"
                    else:
                        features["equalized_by_open_play"] = True
                        features["first_equalizer_method"] = "open_play"
            if after_diff > 0:
                features["reached_lead_after_cutoff"] = True
        else:
            if team == home:
                current_home += 1
            elif team == away:
                current_away += 1
    return features


def _penalty_sequence_row(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    tournament: str,
    tier: str,
    source_version: str,
) -> dict[str, Any]:
    """Summarize same-team penalty-event pairs across the full regulation match."""

    home = match_meta["home_team"]["home_team_name"]
    away = match_meta["away_team"]["away_team_name"]
    shot_times = {home: [], away: []}
    goal_times = {home: [], away: []}
    for event in events:
        elapsed = _elapsed_seconds(event)
        if elapsed is None or not _is_penalty_shot(event):
            continue
        team = _canonical_team_name(match_meta, event)
        if team is None:
            raise SourceError(
                f"Could not map penalty event {event.get('id')} in match {match_meta.get('match_id')} "
                f"to {home} or {away}."
            )
        shot_times[team].append(int(elapsed))
        if _is_penalty_goal(event):
            goal_times[team].append(int(elapsed))

    def sequence_stats(times: list[int]) -> tuple[bool, int | None]:
        ordered = sorted(times)
        if len(ordered) < 2:
            return False, None
        gaps = [right - left for left, right in zip(ordered, ordered[1:])]
        minimum = min(gaps)
        return minimum <= 600, minimum

    home_shot_pair, home_shot_gap = sequence_stats(shot_times[home])
    away_shot_pair, away_shot_gap = sequence_stats(shot_times[away])
    home_goal_pair, home_goal_gap = sequence_stats(goal_times[home])
    away_goal_pair, away_goal_gap = sequence_stats(goal_times[away])
    shot_gaps = [gap for gap in (home_shot_gap, away_shot_gap) if gap is not None]
    goal_gaps = [gap for gap in (home_goal_gap, away_goal_gap) if gap is not None]
    return {
        "match_id": str(match_meta["match_id"]),
        "tournament": tournament,
        "year": int(str(match_meta["match_date"])[:4]),
        "competition_tier": tier,
        "home_team": home,
        "away_team": away,
        "home_penalty_shot_count": len(shot_times[home]),
        "away_penalty_shot_count": len(shot_times[away]),
        "home_penalty_goal_count": len(goal_times[home]),
        "away_penalty_goal_count": len(goal_times[away]),
        "any_team_two_penalty_shots_within_10m": bool(home_shot_pair or away_shot_pair),
        "any_team_two_penalty_goals_within_10m": bool(home_goal_pair or away_goal_pair),
        "minimum_same_team_penalty_shot_gap_seconds": min(shot_gaps) if shot_gaps else None,
        "minimum_same_team_penalty_goal_gap_seconds": min(goal_gaps) if goal_gaps else None,
        "source_name": "StatsBomb Open Data",
        "source_version": source_version,
    }


def classify_match_cutoff(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    cutoff_minute: int,
    tournament: str,
    tier: str,
    source_version: str,
) -> list[dict[str, Any]]:
    """Return one row for each team two or more goals down before a cutoff."""

    home = match_meta["home_team"]["home_team_name"]
    away = match_meta["away_team"]["away_team_name"]
    timeline = extract_match_timeline(
        {**match_meta, "_tournament": tournament, "_year": int(str(match_meta["match_date"])[:4]), "_tier": tier},
        events,
        tournament=tournament,
        tier=tier,
        source_version=source_version,
    )
    home_before, away_before = _score_before(timeline, cutoff_minute * 60)
    home_final, away_final = _final_score(timeline)
    penalty_counts = _team_penalty_counts(match_meta, events, cutoff_seconds=cutoff_minute * 60)

    rows: list[dict[str, Any]] = []
    for focal, opponent, focal_before, opponent_before, focal_final, opponent_final in (
        (home, away, home_before, away_before, home_final, away_final),
        (away, home, away_before, home_before, away_final, home_final),
    ):
        goal_difference = focal_before - opponent_before
        if goal_difference > -2:
            continue
        own = penalty_counts[focal]
        against = penalty_counts[opponent]
        own_shots = int(own["penalty_shots"])
        own_goals = int(own["penalty_goals"])
        against_shots = int(against["penalty_shots"])
        against_goals = int(against["penalty_goals"])
        recovery = _recovery_features(
            match_meta,
            events,
            focal_team=focal,
            home_before=home_before,
            away_before=away_before,
            cutoff_seconds=cutoff_minute * 60,
        )
        comeback = focal_final > opponent_final
        if not comeback:
            primary_path = "no_comeback"
        elif own_shots == 0 and against_shots == 0:
            primary_path = "clean_strict"
        elif own_goals > 0:
            primary_path = "own_penalty_goal_assisted"
        elif own_shots > 0:
            primary_path = "own_penalty_attempt_no_goal"
        else:
            primary_path = "opponent_penalty_context"
        rows.append(
            {
                "dataset_role": "historical_benchmark",
                "match_id": str(match_meta["match_id"]),
                "tournament": tournament,
                "year": int(str(match_meta["match_date"])[:4]),
                "competition_tier": tier,
                "home_team": home,
                "away_team": away,
                "focal_team": focal,
                "opponent_team": opponent,
                "cutoff_minute": int(cutoff_minute),
                "pre_cutoff_focal_score": int(focal_before),
                "pre_cutoff_opponent_score": int(opponent_before),
                "pre_cutoff_goal_difference": int(goal_difference),
                "final_focal_score": int(focal_final),
                "final_opponent_score": int(opponent_final),
                "comeback": bool(comeback),
                "own_penalty_shots_after_cutoff": own_shots,
                "own_penalty_goals_after_cutoff": own_goals,
                "opponent_penalty_shots_after_cutoff": against_shots,
                "opponent_penalty_goals_after_cutoff": against_goals,
                "total_penalty_shots_after_cutoff": own_shots + against_shots,
                "total_penalty_goals_after_cutoff": own_goals + against_goals,
                "clean_strict": bool(comeback and own_shots == 0 and against_shots == 0),
                "clean_outcome": bool(comeback and own_goals == 0 and against_goals == 0),
                "penalty_assisted_by_own_shot": bool(comeback and own_shots > 0),
                "penalty_assisted_by_own_goal": bool(comeback and own_goals > 0),
                **recovery,
                "primary_path": primary_path,
                "source_name": "StatsBomb Open Data",
                "source_version": source_version,
            }
        )
    return rows


def _iter_history_matches(paths: ProjectPaths):
    config = load_config(paths)
    source = config["statsbomb_history"]
    raw_dir = paths.root / source["raw_target_dir"]
    for pair in source["pairs"]:
        matches_path = raw_dir / "matches" / str(pair["competition_id"]) / f"{pair['season_id']}.json"
        if not matches_path.exists():
            raise SourceError(f"Missing StatsBomb history metadata: {matches_path}")
        for match_meta in json.loads(matches_path.read_text(encoding="utf-8")):
            event_path = raw_dir / "events" / f"{match_meta['match_id']}.json"
            if not event_path.exists():
                raise SourceError(f"Missing StatsBomb event stream: {event_path}")
            yield (
                match_meta,
                json.loads(event_path.read_text(encoding="utf-8")),
                f"{pair['competition_name']} {pair['season_name']}",
                str(pair["tier"]),
                str(source["pinned_commit"]),
            )


def focal_case_rows(paths: ProjectPaths, *, cutoffs: list[int]) -> pd.DataFrame:
    """Represent the focal match separately so it never changes the benchmark denominator."""

    path = paths.processed_dir / "focal_events.csv"
    if not path.exists():
        raise SourceError(f"Missing focal event file: {path}")
    frame = pd.read_csv(path)
    frame = frame.sort_values(["elapsed_seconds", "event_id"], kind="stable")
    goal_rows = frame.loc[frame["event_type"].eq("goal")]
    final_argentina = int(goal_rows["score_argentina"].iloc[-1]) if not goal_rows.empty else 0
    final_egypt = int(goal_rows["score_egypt"].iloc[-1]) if not goal_rows.empty else 0
    rows = []
    for cutoff in cutoffs:
        prior = frame.loc[frame["elapsed_seconds"] < cutoff * 60]
        pre_argentina = int(prior["score_argentina"].iloc[-1]) if not prior.empty else 0
        pre_egypt = int(prior["score_egypt"].iloc[-1]) if not prior.empty else 0
        after = frame.loc[frame["elapsed_seconds"] >= cutoff * 60]
        penalty_after = after["event_type"].astype(str).str.startswith("PENALTY_")
        own_after = int((after["team"].eq("Argentina") & penalty_after).sum())
        own_goals_after = int((after["team"].eq("Argentina") & after["event_type"].eq("PENALTY_GOAL")).sum())
        opponent_after = int((after["team"].eq("Egypt") & penalty_after).sum())
        opponent_goals_after = int((after["team"].eq("Egypt") & after["event_type"].eq("PENALTY_GOAL")).sum())
        equalizer_events = after.loc[
            after["team"].eq("Argentina")
            & after["event_type"].eq("goal")
            & after["score_argentina"].eq(after["score_egypt"])
        ]
        lead_events = after.loc[
            after["team"].eq("Argentina")
            & after["event_type"].eq("goal")
            & after["score_argentina"].gt(after["score_egypt"])
        ]
        rows.append(
            {
                "dataset_role": "focal_case",
                "match_id": "M95",
                "tournament": "FIFA World Cup 2026 Round of 16",
                "year": 2026,
                "competition_tier": "world_cup_focal",
                "home_team": "Argentina",
                "away_team": "Egypt",
                "focal_team": "Argentina",
                "opponent_team": "Egypt",
                "cutoff_minute": cutoff,
                "pre_cutoff_focal_score": pre_argentina,
                "pre_cutoff_opponent_score": pre_egypt,
                "pre_cutoff_goal_difference": pre_argentina - pre_egypt,
                "final_focal_score": final_argentina,
                "final_opponent_score": final_egypt,
                "comeback": bool(final_argentina > final_egypt),
                "own_penalty_shots_after_cutoff": own_after,
                "own_penalty_goals_after_cutoff": own_goals_after,
                "opponent_penalty_shots_after_cutoff": opponent_after,
                "opponent_penalty_goals_after_cutoff": opponent_goals_after,
                "total_penalty_shots_after_cutoff": own_after + opponent_after,
                "total_penalty_goals_after_cutoff": own_goals_after + opponent_goals_after,
                "clean_strict": bool(final_argentina > final_egypt and own_after == 0 and opponent_after == 0),
                "clean_outcome": bool(final_argentina > final_egypt and own_goals_after == 0 and opponent_goals_after == 0),
                "penalty_assisted_by_own_shot": bool(final_argentina > final_egypt and own_after > 0),
                "penalty_assisted_by_own_goal": bool(final_argentina > final_egypt and own_goals_after > 0),
                "own_penalty_goal_after_cutoff": bool(own_goals_after > 0),
                "own_penalty_goal_while_two_down": False,
                "own_penalty_goal_while_two_or_more_down": False,
                "own_penalty_goal_as_equalizer": False,
                "own_penalty_goal_as_go_ahead": False,
                "reached_level_after_cutoff": bool(not equalizer_events.empty),
                "equalized_by_own_penalty": False,
                "equalized_by_open_play": bool(not equalizer_events.empty),
                "first_equalizer_method": "open_play" if not equalizer_events.empty else None,
                "reached_lead_after_cutoff": bool(not lead_events.empty),
                "first_own_goal_after_cutoff_was_penalty": False,
                "own_penalty_goal_count_after_cutoff": own_goals_after,
                "two_own_penalty_shots_within_10m": False,
                "two_own_penalty_goals_within_10m": False,
                "minimum_gap_between_own_penalty_shots_seconds": None,
                "primary_path": "clean_strict" if final_argentina > final_egypt and own_after == 0 and opponent_after == 0 else "other",
                "source_name": "FIFA Performance Summary Report M95",
                "source_version": "official_2026_m95",
            }
        )
    return pd.DataFrame(rows)


def _summary_rows(cases: pd.DataFrame) -> pd.DataFrame:
    historical = cases.loc[cases["dataset_role"].eq("historical_benchmark")].copy()
    rows: list[dict[str, Any]] = []
    for (tier, cutoff), group in historical.groupby(["competition_tier", "cutoff_minute"], sort=True):
        eligible = len(group)
        comebacks = int(group["comeback"].sum())
        clean_strict = int(group["clean_strict"].sum())
        clean_outcome = int(group["clean_outcome"].sum())
        own_shot = int(group["penalty_assisted_by_own_shot"].sum())
        own_goal = int(group["penalty_assisted_by_own_goal"].sum())
        three_plus = int((group["comeback"] & group["own_penalty_shots_after_cutoff"].ge(3)).sum())
        metrics = {
            "comebacks": comebacks,
            "clean_strict_comebacks": clean_strict,
            "clean_outcome_comebacks": clean_outcome,
            "own_penalty_shot_assisted_comebacks": own_shot,
            "own_penalty_goal_assisted_comebacks": own_goal,
            "three_plus_own_penalty_shot_comebacks": three_plus,
            "team_states_with_own_penalty_goal_after_cutoff": int(group["own_penalty_goal_after_cutoff"].sum()),
            "team_states_with_own_penalty_goal_while_two_down": int(group["own_penalty_goal_while_two_down"].sum()),
            "team_states_with_own_penalty_goal_while_two_or_more_down": int(group["own_penalty_goal_while_two_or_more_down"].sum()),
            "team_states_equalizing_by_own_penalty": int(group["equalized_by_own_penalty"].sum()),
            "team_states_equalizing_by_open_play": int(group["equalized_by_open_play"].sum()),
            "team_states_reaching_level_after_cutoff": int(group["reached_level_after_cutoff"].sum()),
            "team_states_reaching_lead_after_cutoff": int(group["reached_lead_after_cutoff"].sum()),
            "team_states_with_two_own_penalty_shots_within_10m": int(group["two_own_penalty_shots_within_10m"].sum()),
            "team_states_with_two_own_penalty_goals_within_10m": int(group["two_own_penalty_goals_within_10m"].sum()),
        }
        for metric, successes in metrics.items():
            lower, upper = wilson_interval(int(successes), eligible)
            rows.append(
                {
                    "dataset_role": "historical_benchmark",
                    "competition_tier": tier,
                    "cutoff_minute": int(cutoff),
                    "metric": metric,
                    "successes": int(successes),
                    "denominator": int(eligible),
                    "eligible_team_states": int(eligible),
                    "unique_matches": int(group["match_id"].nunique()),
                    "rate": float(successes / eligible) if eligible else np.nan,
                    "wilson_lower": lower,
                    "wilson_upper": upper,
                }
            )
    return pd.DataFrame(rows)


def run_comeback_path_analysis(paths: ProjectPaths, *, cutoffs: list[int] | None = None) -> dict[str, Any]:
    """Build reproducible clean/penalty-assisted comeback outputs."""

    config = load_config(paths)
    configured_cutoffs = config["statsbomb_history"].get(
        "comeback_path_cutoff_minutes",
        config["statsbomb_history"].get("threshold_minutes", DEFAULT_CUTOFFS),
    )
    cutoffs = sorted(set(cutoffs or configured_cutoffs) | {PRIMARY_CUTOFF_MINUTE})
    rows: list[dict[str, Any]] = []
    sequence_rows: list[dict[str, Any]] = []
    match_count = 0
    for match_meta, events, tournament, tier, source_version in _iter_history_matches(paths):
        match_count += 1
        sequence_rows.append(
            _penalty_sequence_row(
                match_meta,
                events,
                tournament=tournament,
                tier=tier,
                source_version=source_version,
            )
        )
        for cutoff in cutoffs:
            rows.extend(
                classify_match_cutoff(
                    match_meta,
                    events,
                    cutoff_minute=int(cutoff),
                    tournament=tournament,
                    tier=tier,
                    source_version=source_version,
                )
            )
    historical = pd.DataFrame(rows)
    focal = focal_case_rows(paths, cutoffs=cutoffs)
    cases = pd.concat([historical, focal], ignore_index=True)
    cases_path = paths.results_dir / "comeback_path_cases.csv"
    summary_path = paths.results_dir / "comeback_path_summary.csv"
    sequence_path = paths.results_dir / "penalty_sequence_cases.csv"
    sequence_summary_path = paths.results_dir / "penalty_sequence_summary.csv"
    write_csv_atomic(cases, cases_path)
    summary_frame = _summary_rows(cases)
    write_csv_atomic(summary_frame, summary_path)
    sequence_frame = pd.DataFrame(sequence_rows)
    write_csv_atomic(sequence_frame, sequence_path)
    sequence_summary = (
        sequence_frame.groupby("competition_tier", sort=True)
        .agg(
            matches_scanned=("match_id", "nunique"),
            matches_with_two_penalty_shots_within_10m=("any_team_two_penalty_shots_within_10m", "sum"),
            matches_with_two_penalty_goals_within_10m=("any_team_two_penalty_goals_within_10m", "sum"),
        )
        .reset_index()
    )
    sequence_summary["shot_pair_rate"] = sequence_summary["matches_with_two_penalty_shots_within_10m"] / sequence_summary["matches_scanned"]
    sequence_summary["goal_pair_rate"] = sequence_summary["matches_with_two_penalty_goals_within_10m"] / sequence_summary["matches_scanned"]
    write_csv_atomic(sequence_summary, sequence_summary_path)

    manifest = {
        "pipeline": "research_etl.comeback_paths",
        "created_at": _utc_now(),
        "status": "ready",
        "primary_cutoff_minute": PRIMARY_CUTOFF_MINUTE,
        "cutoffs": cutoffs,
        "historical_matches_scanned": match_count,
        "historical_team_state_rows": int(len(historical)),
        "focal_case_is_excluded_from_denominators": True,
        "definitions": {
            "eligible": "A team is two or more goals down strictly before the cutoff.",
            "clean_strict": "A comeback with no penalty-shot event by either team from the cutoff onward.",
            "clean_outcome": "A comeback with no penalty-goal event by either team from the cutoff onward.",
            "penalty_assisted_by_own_shot": "A comeback where the focal team attempted at least one penalty after the cutoff.",
            "penalty_assisted_by_own_goal": "A comeback where the focal team scored at least one penalty after the cutoff.",
            "three_plus": "A comeback where the focal team attempted at least three penalties after the cutoff.",
            "team_states_with_own_penalty_goal_while_two_down": "All eligible states where the trailing team scored a penalty while the live deficit was exactly two goals; final comeback is not required.",
            "team_states_equalizing_by_own_penalty": "All eligible states where a trailing team's penalty goal changed the live state from one goal down to level; final comeback is not required.",
            "team_states_equalizing_by_open_play": "All eligible states that reached level after the cutoff without the equalizing goal being a penalty.",
            "team_states_with_two_own_penalty_shots_within_10m": "All eligible states where the trailing team had two or more penalty-shot events within a rolling 10-minute interval after the cutoff.",
            "team_states_with_two_own_penalty_goals_within_10m": "All eligible states where the trailing team scored two penalty goals within a rolling 10-minute interval after the cutoff.",
            "full_match_sequence": "A separate scan of all regulation-time events in all 2,379 selected matches; it is not conditioned on a two-goal deficit.",
        },
        "limitations": [
            "StatsBomb event coverage is an explicit availability sample, not all football history.",
            "Penalty-shot events are an event-feed proxy and do not adjudicate whether an award was correct.",
            "The focal match is kept as a labeled case because it is not part of the historical benchmark source.",
            "At 79:00 Argentina was already 1-2 after Romero's 78th-minute goal; the 79-minute benchmark is not a claim that the focal state was still 0-2.",
        ],
        "artifacts": [
            {"path": str(cases_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(cases)), "sha256": sha256_file(cases_path)},
            {"path": str(summary_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(summary_frame)), "sha256": sha256_file(summary_path)},
            {"path": str(sequence_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(sequence_frame)), "sha256": sha256_file(sequence_path)},
            {"path": str(sequence_summary_path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(sequence_summary)), "sha256": sha256_file(sequence_summary_path)},
        ],
    }
    manifest_path = paths.results_dir / "comeback_path_manifest.json"
    write_json_atomic(manifest, manifest_path)
    return manifest
