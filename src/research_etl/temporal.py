"""Pre-decision five-minute panels from StatsBomb event streams.

Each row represents one team at the start of a five-minute window. Features
are calculated strictly from events before the window; events inside the
window are used only for the outcome. This makes the panel suitable for a
small hazard model without leaking the decision window into its predictors.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from pathlib import Path
from typing import Any

import pandas as pd

from research_etl.opportunity import canonical_team_name


WINDOW_SECONDS = 5 * 60
REGULATION_SECONDS = 90 * 60

TEMPORAL_COLUMNS = {
    "match_id",
    "team_id",
    "team_name",
    "opponent_team_id",
    "opponent_team_name",
    "home_or_away",
    "tournament",
    "year",
    "stage",
    "competition_tier",
    "is_neutral",
    "referee_id",
    "referee_name",
    "regulation_home_score",
    "regulation_away_score",
    "time_bin_start_minute",
    "time_bin_end_minute",
    "exposure_seconds",
    "goals_for_pre",
    "goals_against_pre",
    "goal_diff_pre",
    "red_cards_for_pre",
    "red_cards_against_pre",
    "box_entries_pre",
    "box_receipts_pre",
    "non_penalty_shots_in_box_pre",
    "non_penalty_xg_pre",
    "final_third_entries_pre",
    "fouls_committed_pre",
    "fouls_suffered_pre",
    "yellow_cards_pre",
    "send_offs_pre",
    "possession_sequences_pre",
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
    "penalty_shots_next_5m",
    "penalty_fouls_won_next_5m",
    "penalty_event_next_5m",
    "penalty_foul_event_next_5m",
    "source_name",
    "source_version",
}

_COUNT_KEYS = (
    "goals",
    "red_cards",
    "box_entries",
    "box_receipts",
    "non_penalty_shots_in_box",
    "final_third_entries",
    "fouls_committed",
    "fouls_suffered",
    "yellow_cards",
    "send_offs",
    "penalty_shots",
    "penalty_fouls_won",
)


def _in_box(location: Any) -> bool:
    if not isinstance(location, list) or len(location) < 2:
        return False
    try:
        x, y = float(location[0]), float(location[1])
    except (TypeError, ValueError):
        return False
    return x >= 102.0 and 18.0 <= y <= 62.0


def _in_final_third(location: Any) -> bool:
    if not isinstance(location, list) or not location:
        return False
    try:
        return float(location[0]) >= 80.0
    except (TypeError, ValueError):
        return False


def _elapsed_seconds(event: dict[str, Any]) -> int | None:
    period = event.get("period")
    minute = event.get("minute")
    if period not in (1, 2) or minute is None:
        return None
    second = event.get("second", 0) or 0
    # StatsBomb resets the event clock at half-time.
    offset = 45 * 60 if period == 2 else 0
    return offset + int(minute) * 60 + int(second)


def _zero_metrics() -> dict[str, float | int]:
    return {key: 0 for key in _COUNT_KEYS} | {"non_penalty_xg": 0.0}


def _event_records(match_meta: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    relevant_types = {"Foul Committed", "Foul Won", "Bad Behaviour", "Pass", "Carry", "Ball Receipt*", "Shot"}
    for order, event in enumerate(events):
        elapsed = _elapsed_seconds(event)
        if elapsed is None:
            continue
        event_type = (event.get("type") or {}).get("name")
        event_team = None
        if event_type in relevant_types or event_type in {"Own Goal For"}:
            event_team = canonical_team_name(match_meta, event.get("team"))
            if event_team is None:
                raise ValueError(
                    f"Could not map relevant event {event.get('id')} in match {match_meta.get('match_id')} "
                    "using StatsBomb team ID or canonical name."
                )

        possession_team = None
        possession_id = event.get("possession")
        if possession_id is not None:
            possession_team = canonical_team_name(match_meta, event.get("possession_team"))
            if possession_team is None:
                raise ValueError(
                    f"Could not map possession owner in event {event.get('id')} in match {match_meta.get('match_id')}."
                )

        metrics = _zero_metrics()
        if event_team is not None:
            if event_type == "Foul Committed":
                metrics["fouls_committed"] = 1
                card_name = ((event.get("foul_committed") or {}).get("card") or {}).get("name")
                if card_name == "Yellow Card":
                    metrics["yellow_cards"] = 1
                elif card_name in {"Second Yellow", "Red Card"}:
                    metrics["send_offs"] = 1
            elif event_type == "Bad Behaviour":
                card_name = ((event.get("bad_behaviour") or {}).get("card") or {}).get("name")
                if card_name == "Yellow Card":
                    metrics["yellow_cards"] = 1
                elif card_name in {"Second Yellow", "Red Card"}:
                    metrics["send_offs"] = 1
            elif event_type == "Foul Won":
                metrics["fouls_suffered"] = 1
                if bool((event.get("foul_won") or {}).get("penalty")):
                    metrics["penalty_fouls_won"] = 1
            elif event_type in {"Pass", "Carry"}:
                payload = event.get("pass") if event_type == "Pass" else event.get("carry")
                end_location = (payload or {}).get("end_location")
                if _in_box(end_location) and not _in_box(event.get("location")):
                    metrics["box_entries"] = 1
                if _in_final_third(end_location) and not _in_final_third(event.get("location")):
                    metrics["final_third_entries"] = 1
            elif event_type == "Ball Receipt*":
                if not bool((event.get("ball_receipt") or {}).get("outcome")) and _in_box(event.get("location")):
                    metrics["box_receipts"] = 1
            elif event_type == "Shot":
                shot = event.get("shot") or {}
                shot_type = (shot.get("type") or {}).get("name")
                if shot_type == "Penalty":
                    metrics["penalty_shots"] = 1
                if _in_box(event.get("location")):
                    if shot_type != "Penalty":
                        metrics["non_penalty_shots_in_box"] = 1
                if shot_type != "Penalty":
                    metrics["non_penalty_xg"] = float(shot.get("statsbomb_xg") or 0.0)
            elif event_type == "Own Goal For":
                metrics["goals"] = 1

            if event_type == "Shot" and (event.get("shot") or {}).get("outcome", {}).get("name") == "Goal":
                metrics["goals"] = 1

        if event_team is None and possession_team is None:
            continue
        records.append(
            {
                "elapsed_seconds": elapsed,
                "order": order,
                "event_team": event_team,
                "possession_team": possession_team,
                "possession_id": str(possession_id) if possession_id is not None else None,
                **metrics,
            }
        )
    return sorted(records, key=lambda row: (row["elapsed_seconds"], row["order"]))


def _sum_records(records: list[dict[str, Any]]) -> dict[str, float | int]:
    result = _zero_metrics()
    for record in records:
        for key in _COUNT_KEYS:
            result[key] += record[key]
        result["non_penalty_xg"] += record["non_penalty_xg"]
    return result


def _prefix_records(records: list[dict[str, Any]]) -> dict[str, list[float | int]]:
    prefix = {key: [0] * (len(records) + 1) for key in (*_COUNT_KEYS, "non_penalty_xg")}
    for index, record in enumerate(records, start=1):
        for key in prefix:
            prefix[key][index] = prefix[key][index - 1] + record[key]
    return prefix


def _prefix_slice(prefix: dict[str, list[float | int]], end_index: int) -> dict[str, float | int]:
    return {key: values[end_index] for key, values in prefix.items()}


def _prefix_range(prefix: dict[str, list[float | int]], left: int, right: int) -> dict[str, float | int]:
    return {key: values[right] - values[left] for key, values in prefix.items()}


def _possession_count(ids: list[str | None], left: int, right: int) -> int:
    return len({value for value in ids[left:right] if value})


def extract_temporal_match_features(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    tournament: str,
    competition_tier: str,
    source_version: str,
) -> list[dict[str, Any]]:
    """Return one strictly pre-decision row per team and five-minute window."""

    home = match_meta["home_team"]
    away = match_meta["away_team"]
    home_name = home["home_team_name"]
    away_name = away["away_team_name"]
    records = _event_records(match_meta, events)
    max_elapsed = max((row["elapsed_seconds"] for row in records), default=REGULATION_SECONDS - 1)
    match_end = max(REGULATION_SECONDS, max_elapsed + 1)
    bin_count = max(1, math.ceil(match_end / WINDOW_SECONDS))
    metric_by_team = {
        home_name: [row for row in records if row["event_team"] == home_name],
        away_name: [row for row in records if row["event_team"] == away_name],
    }
    possession_by_team = {
        home_name: [row for row in records if row["possession_team"] == home_name],
        away_name: [row for row in records if row["possession_team"] == away_name],
    }
    prefix_by_team = {team: _prefix_records(rows) for team, rows in metric_by_team.items()}
    regulation_home_score = int(sum(row["goals"] for row in records if row["event_team"] == home_name))
    regulation_away_score = int(sum(row["goals"] for row in records if row["event_team"] == away_name))
    year = int(str(match_meta["match_date"])[:4])
    stage = match_meta.get("competition_stage") or {}
    stage_name = stage.get("name", "") if isinstance(stage, dict) else ""
    referee = match_meta.get("referee") or {}
    rows: list[dict[str, Any]] = []

    for bin_index in range(bin_count):
        start = bin_index * WINDOW_SECONDS
        end = min((bin_index + 1) * WINDOW_SECONDS, match_end)
        if end <= start:
            continue
        recent_start = max(0, start - WINDOW_SECONDS)
        stats: dict[str, dict[str, Any]] = {}
        outcomes: dict[str, dict[str, Any]] = {}
        for team_name in (home_name, away_name):
            team_records = metric_by_team[team_name]
            times = [row["elapsed_seconds"] for row in team_records]
            pre_index = bisect_left(times, start)
            recent_index = bisect_left(times, recent_start)
            end_index = bisect_left(times, end)
            pre = _prefix_slice(prefix_by_team[team_name], pre_index)
            prefix = prefix_by_team[team_name]
            recent = _prefix_range(prefix, recent_index, pre_index)
            current = _prefix_range(prefix, pre_index, end_index)
            possession_records = possession_by_team[team_name]
            possession_times = [row["elapsed_seconds"] for row in possession_records]
            possession_ids = [row["possession_id"] for row in possession_records]
            possession_pre_index = bisect_left(possession_times, start)
            possession_recent_index = bisect_left(possession_times, recent_start)
            stats[team_name] = {
                **pre,
                "possession_sequences_pre": _possession_count(possession_ids, 0, possession_pre_index),
                "recent": recent,
                "possession_sequences_prev_5m": _possession_count(possession_ids, possession_recent_index, possession_pre_index),
            }
            outcomes[team_name] = current

        for team_name, opponent_name, team_meta, opponent_meta, home_or_away in (
            (home_name, away_name, home, away, "home"),
            (away_name, home_name, away, home, "away"),
        ):
            own = stats[team_name]
            opp = stats[opponent_name]
            own_recent = own["recent"]
            opp_recent = opp["recent"]
            outcome = outcomes[team_name]
            row = {
                "match_id": str(match_meta["match_id"]),
                "team_id": team_meta.get("home_team_id") if home_or_away == "home" else team_meta.get("away_team_id"),
                "team_name": team_name,
                "opponent_team_id": opponent_meta.get("away_team_id") if home_or_away == "home" else opponent_meta.get("home_team_id"),
                "opponent_team_name": opponent_name,
                "home_or_away": home_or_away,
                "tournament": tournament,
                "year": year,
                "stage": stage_name,
                "competition_tier": competition_tier,
                "is_neutral": competition_tier in {"world_cup", "intl"},
                "referee_id": referee.get("id"),
                "referee_name": referee.get("name"),
                "regulation_home_score": regulation_home_score,
                "regulation_away_score": regulation_away_score,
                "time_bin_start_minute": start / 60,
                "time_bin_end_minute": end / 60,
                "exposure_seconds": end - start,
                "goals_for_pre": own["goals"],
                "goals_against_pre": opp["goals"],
                "goal_diff_pre": own["goals"] - opp["goals"],
                "red_cards_for_pre": own["send_offs"],
                "red_cards_against_pre": opp["send_offs"],
                "box_entries_pre": own["box_entries"],
                "box_receipts_pre": own["box_receipts"],
                "non_penalty_shots_in_box_pre": own["non_penalty_shots_in_box"],
                "non_penalty_xg_pre": own["non_penalty_xg"],
                "final_third_entries_pre": own["final_third_entries"],
                "fouls_committed_pre": own["fouls_committed"],
                "fouls_suffered_pre": own["fouls_suffered"],
                "yellow_cards_pre": own["yellow_cards"],
                "send_offs_pre": own["send_offs"],
                "possession_sequences_pre": own["possession_sequences_pre"],
                "box_entries_prev_5m": own_recent["box_entries"],
                "box_receipts_prev_5m": own_recent["box_receipts"],
                "non_penalty_xg_prev_5m": own_recent["non_penalty_xg"],
                "final_third_entries_prev_5m": own_recent["final_third_entries"],
                "fouls_committed_prev_5m": own_recent["fouls_committed"],
                "fouls_suffered_prev_5m": own_recent["fouls_suffered"],
                "yellow_cards_prev_5m": own_recent["yellow_cards"],
                "possession_sequences_prev_5m": own["possession_sequences_prev_5m"],
                "opponent_box_entries_prev_5m": opp_recent["box_entries"],
                "opponent_non_penalty_xg_prev_5m": opp_recent["non_penalty_xg"],
                "penalty_shots_next_5m": outcome["penalty_shots"],
                "penalty_fouls_won_next_5m": outcome["penalty_fouls_won"],
                "penalty_event_next_5m": int(outcome["penalty_shots"] > 0),
                "penalty_foul_event_next_5m": int(outcome["penalty_fouls_won"] > 0),
                "source_name": "StatsBomb Open Data",
                "source_version": source_version,
            }
            rows.append(row)
    return rows


def _build_from_matches(raw_dir: Path, pairs: list[dict[str, Any]], source_version: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        matches_path = raw_dir / "matches" / str(pair["competition_id"]) / (str(pair["season_id"]) + ".json")
        if not matches_path.exists():
            raise FileNotFoundError(f"Missing StatsBomb match metadata: {matches_path}")
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        for match in matches:
            event_path = raw_dir / "events" / (str(match["match_id"]) + ".json")
            if not event_path.exists():
                raise FileNotFoundError(f"Missing StatsBomb event stream: {event_path}")
            events = json.loads(event_path.read_text(encoding="utf-8"))
            tournament = f"{pair['competition_name']} {pair['season_name']}"
            rows.extend(
                extract_temporal_match_features(
                    match,
                    events,
                    tournament=tournament,
                    competition_tier=str(pair["tier"]),
                    source_version=source_version,
                )
            )
    return pd.DataFrame(rows).sort_values(
        ["competition_tier", "year", "match_id", "time_bin_start_minute", "home_or_away"], kind="stable"
    ).reset_index(drop=True)


def build_temporal_history_features_from_raw(raw_dir: Path, *, pairs: list[dict[str, Any]], source_version: str) -> pd.DataFrame:
    return _build_from_matches(raw_dir, pairs, source_version)


def build_temporal_world_cup_features_from_raw(
    raw_dir: Path, *, competition_id: int, season_ids: list[int], source_version: str
) -> pd.DataFrame:
    pairs = [
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "competition_name": "FIFA World Cup",
            "season_name": str(season_id),
            "tier": "world_cup",
        }
        for season_id in season_ids
    ]
    return _build_from_matches(raw_dir, pairs, source_version)
