"""Compact, opportunity-oriented team-match features from StatsBomb event feeds.

This module deliberately does not label its event-derived possession sequence
share as official possession time. The primary attacking-exposure measures are
spatial event counts: entries, completed receipts, and shots in the opponent's
penalty area.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SOURCE_NAME = "StatsBomb Open Data"
PENALTY_AREA_X = 102.0
PENALTY_AREA_Y_MIN = 18.0
PENALTY_AREA_Y_MAX = 62.0
FINAL_THIRD_X = 80.0

STATSBOMB_OPPORTUNITY_COLUMNS = {
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
    "penalty_fouls_won",
    "penalty_shots",
    "fouls_committed",
    "fouls_suffered",
    "yellow_cards",
    "second_yellows",
    "send_offs",
    "box_entries",
    "box_receipts",
    "shots_in_box",
    "non_penalty_shots_in_box",
    "non_penalty_xg",
    "final_third_entries",
    "possession_sequences",
    "possession_sequence_share",
    "source_name",
    "source_version",
}


def _same_id(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def canonical_team_name(match_meta: dict[str, Any], team: dict[str, Any] | None) -> str | None:
    """Map a StatsBomb team object to a match's canonical display name.

    Stable team IDs are used first. Names are a controlled fallback for older
    fixtures and unit-test inputs that intentionally do not include IDs.
    """

    team = team or {}
    home = match_meta["home_team"]
    away = match_meta["away_team"]
    team_id = team.get("id")
    if _same_id(team_id, home.get("home_team_id")):
        return home["home_team_name"]
    if _same_id(team_id, away.get("away_team_id")):
        return away["away_team_name"]

    team_name = team.get("name")
    if team_name == home.get("home_team_name"):
        return home["home_team_name"]
    if team_name == away.get("away_team_name"):
        return away["away_team_name"]
    return None


def _in_penalty_area(location: Any) -> bool:
    if not isinstance(location, list) or len(location) < 2:
        return False
    try:
        x, y = float(location[0]), float(location[1])
    except (TypeError, ValueError):
        return False
    return x >= PENALTY_AREA_X and PENALTY_AREA_Y_MIN <= y <= PENALTY_AREA_Y_MAX


def _in_final_third(location: Any) -> bool:
    if not isinstance(location, list) or not location:
        return False
    try:
        return float(location[0]) >= FINAL_THIRD_X
    except (TypeError, ValueError):
        return False


def _mapped_team(match_meta: dict[str, Any], event: dict[str, Any], *, field: str = "team") -> str:
    team_name = canonical_team_name(match_meta, event.get(field))
    if team_name is None:
        raise ValueError(
            f"Could not map event {event.get('id')} in match {match_meta.get('match_id')} "
            f"using StatsBomb team ID or canonical name."
        )
    return team_name


def _team_totals() -> dict[str, float | int]:
    return {
        "penalty_fouls_won": 0,
        "penalty_shots": 0,
        "fouls_committed": 0,
        "fouls_suffered": 0,
        "yellow_cards": 0,
        "second_yellows": 0,
        "send_offs": 0,
        "box_entries": 0,
        "box_receipts": 0,
        "shots_in_box": 0,
        "non_penalty_shots_in_box": 0,
        "non_penalty_xg": 0.0,
        "final_third_entries": 0,
    }


def extract_statsbomb_team_match_features(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    tournament: str,
    competition_tier: str,
    source_version: str,
) -> list[dict[str, Any]]:
    """Return two regulation-time, team-match rows from one StatsBomb match.

    `penalty_fouls_won` is the event-feed proxy for a penalty award. It remains
    separate from `penalty_shots`, because a converted, saved, or retaken kick
    is not itself the award decision. Both are retained for reconciliation.
    """

    home = match_meta["home_team"]
    away = match_meta["away_team"]
    home_name = home["home_team_name"]
    away_name = away["away_team_name"]
    totals = {home_name: _team_totals(), away_name: _team_totals()}
    possession_ids: dict[str, set[str]] = {home_name: set(), away_name: set()}

    for event in events:
        if event.get("period") not in (1, 2):
            continue
        event_type = (event.get("type") or {}).get("name")
        if not event_type:
            continue

        if event.get("possession") is not None:
            possession_owner = canonical_team_name(match_meta, event.get("possession_team"))
            if possession_owner is not None:
                possession_ids[possession_owner].add(str(event["possession"]))

        if event_type in {"Foul Committed", "Foul Won", "Bad Behaviour", "Pass", "Carry", "Ball Receipt*", "Shot"}:
            team_name = _mapped_team(match_meta, event)
        else:
            continue

        team = totals[team_name]
        if event_type == "Foul Committed":
            team["fouls_committed"] += 1
            card_name = ((event.get("foul_committed") or {}).get("card") or {}).get("name")
            if card_name == "Yellow Card":
                team["yellow_cards"] += 1
            elif card_name == "Second Yellow":
                team["second_yellows"] += 1
                team["send_offs"] += 1
            elif card_name == "Red Card":
                team["send_offs"] += 1
            continue

        if event_type == "Bad Behaviour":
            card_name = ((event.get("bad_behaviour") or {}).get("card") or {}).get("name")
            if card_name == "Yellow Card":
                team["yellow_cards"] += 1
            elif card_name == "Second Yellow":
                team["second_yellows"] += 1
                team["send_offs"] += 1
            elif card_name == "Red Card":
                team["send_offs"] += 1
            continue

        if event_type == "Foul Won":
            team["fouls_suffered"] += 1
            if bool((event.get("foul_won") or {}).get("penalty")):
                team["penalty_fouls_won"] += 1
            continue

        location = event.get("location")
        if event_type in {"Pass", "Carry"}:
            event_payload = event.get("pass") if event_type == "Pass" else event.get("carry")
            end_location = (event_payload or {}).get("end_location")
            if _in_penalty_area(end_location) and not _in_penalty_area(location):
                team["box_entries"] += 1
            if _in_final_third(end_location) and not _in_final_third(location):
                team["final_third_entries"] += 1
            continue

        if event_type == "Ball Receipt*":
            receipt_complete = not bool((event.get("ball_receipt") or {}).get("outcome"))
            if receipt_complete and _in_penalty_area(location):
                team["box_receipts"] += 1
            continue

        if event_type == "Shot":
            shot = event.get("shot") or {}
            shot_type = (shot.get("type") or {}).get("name")
            if shot_type == "Penalty":
                team["penalty_shots"] += 1
            if _in_penalty_area(location):
                team["shots_in_box"] += 1
                if shot_type != "Penalty":
                    team["non_penalty_shots_in_box"] += 1
            if shot_type != "Penalty":
                team["non_penalty_xg"] += float(shot.get("statsbomb_xg") or 0.0)

    total_sequences = sum(len(values) for values in possession_ids.values())
    referee = match_meta.get("referee") or {}
    stage = match_meta.get("competition_stage") or {}
    stage_name = stage.get("name", "") if isinstance(stage, dict) else ""
    year = int(str(match_meta["match_date"])[:4])
    rows = []
    for team_name, opponent_name, team_meta, opponent_meta, home_or_away in (
        (home_name, away_name, home, away, "home"),
        (away_name, home_name, away, home, "away"),
    ):
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
            "is_neutral": competition_tier == "world_cup" or competition_tier == "intl",
            "referee_id": referee.get("id"),
            "referee_name": referee.get("name"),
            **totals[team_name],
            "possession_sequences": len(possession_ids[team_name]),
            "possession_sequence_share": (
                len(possession_ids[team_name]) / total_sequences if total_sequences else 0.0
            ),
            "source_name": DEFAULT_SOURCE_NAME,
            "source_version": source_version,
        }
        rows.append(row)
    return rows


def build_world_cup_features_from_raw(
    raw_dir: Path,
    *,
    competition_id: int,
    season_ids: list[int],
    source_version: str,
) -> pd.DataFrame:
    """Build a World-Cup-only feature panel from the configured StatsBomb cache."""

    rows: list[dict[str, Any]] = []
    for season_id in season_ids:
        matches_path = raw_dir / "matches" / str(competition_id) / f"{season_id}.json"
        if not matches_path.exists():
            raise FileNotFoundError(f"Missing StatsBomb match metadata: {matches_path}")
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        for match in matches:
            event_path = raw_dir / "events" / f"{match['match_id']}.json"
            if not event_path.exists():
                raise FileNotFoundError(f"Missing StatsBomb event stream: {event_path}")
            events = json.loads(event_path.read_text(encoding="utf-8"))
            competition = match.get("competition") or {}
            season = match.get("season") or {}
            rows.extend(
                extract_statsbomb_team_match_features(
                    match,
                    events,
                    tournament=f"{competition.get('competition_name', 'FIFA World Cup')} {season.get('season_name', season_id)}",
                    competition_tier="world_cup",
                    source_version=source_version,
                )
            )
    return pd.DataFrame(rows).sort_values(["year", "match_id", "home_or_away"], kind="stable").reset_index(drop=True)


def build_history_features_from_raw(
    raw_dir: Path,
    *,
    pairs: list[dict[str, Any]],
    source_version: str,
) -> pd.DataFrame:
    """Build separate club/international feature panels from the selected cache."""

    rows: list[dict[str, Any]] = []
    for pair in pairs:
        competition_id = int(pair["competition_id"])
        season_id = int(pair["season_id"])
        matches_path = raw_dir / "matches" / str(competition_id) / f"{season_id}.json"
        if not matches_path.exists():
            raise FileNotFoundError(f"Missing StatsBomb match metadata: {matches_path}")
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        tournament = f"{pair['competition_name']} {pair['season_name']}"
        for match in matches:
            event_path = raw_dir / "events" / f"{match['match_id']}.json"
            if not event_path.exists():
                raise FileNotFoundError(f"Missing StatsBomb event stream: {event_path}")
            events = json.loads(event_path.read_text(encoding="utf-8"))
            rows.extend(
                extract_statsbomb_team_match_features(
                    match,
                    events,
                    tournament=tournament,
                    competition_tier=str(pair["tier"]),
                    source_version=source_version,
                )
            )
    return pd.DataFrame(rows).sort_values(
        ["competition_tier", "year", "match_id", "home_or_away"], kind="stable"
    ).reset_index(drop=True)
