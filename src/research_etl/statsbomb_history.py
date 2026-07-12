"""Goal/red-card timelines from StatsBomb open-data events (Project.md S6.3 broader baseline).

Separate from the Fjelstul World Cup source. Club competitions (leagues, UCL,
domestic cups) and non-World-Cup international tournaments (Copa America,
UEFA Euro, Africa Cup of Nations) are extracted into the same event-column
shape as historical_match_events.csv, but kept in their own `competition_tier`
("club" / "intl") rather than pooled with each other or with the World Cup --
squad-selection context and stakes differ enough that Project.md's own
anti-pooling principle (S5.5) applies here too. Every downstream rarity or
win-probability table built from this source must report each tier
separately, alongside the World Cup baseline, never merged into one figure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

RED_CARD_NAMES = {"Red Card", "Second Yellow"}
DEFAULT_SOURCE_NAME = "StatsBomb Open Data"


def _same_id(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def _canonical_team_name(match_meta: dict[str, Any], event: dict[str, Any]) -> str | None:
    """Resolve an event team by StatsBomb ID, with name fallback for unit fixtures.

    StatsBomb's match metadata can use a display name such as
    ``Olympique de Marseille`` while the event stream uses ``Marseille``.
    Team IDs are the stable join key; names are only a fallback for fixtures
    that intentionally omit IDs in tests or older exports.
    """

    event_team = event.get("team") or {}
    event_id = event_team.get("id")
    home = match_meta["home_team"]
    away = match_meta["away_team"]
    if _same_id(event_id, home.get("home_team_id")):
        return home["home_team_name"]
    if _same_id(event_id, away.get("away_team_id")):
        return away["away_team_name"]

    event_name = event_team.get("name")
    if event_name == home.get("home_team_name"):
        return home["home_team_name"]
    if event_name == away.get("away_team_name"):
        return away["away_team_name"]
    return None


def extract_match_timeline(
    match_meta: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    tournament: str,
    tier: str,
    source_version: str = "unknown",
) -> list[dict[str, Any]]:
    """One row per goal/red-card event for a single match, in historical-event-table shape."""

    home_team = match_meta["home_team"]["home_team_name"]
    away_team = match_meta["away_team"]["away_team_name"]
    match_id = match_meta["match_id"]
    year = int(str(match_meta["match_date"])[:4])
    stage = match_meta.get("competition_stage") or {}
    stage_name = stage.get("name", "") if isinstance(stage, dict) else ""

    raw_rows: list[dict[str, Any]] = []
    for event in events:
        period = event.get("period")
        if period not in (1, 2):
            continue
        minute = event.get("minute")
        if minute is None:
            continue
        second = event.get("second", 0) or 0
        elapsed_seconds = int(minute) * 60 + int(second)
        event_type = (event.get("type") or {}).get("name")
        if not event_type:
            continue

        is_goal = (
            event_type == "Shot" and (event.get("shot") or {}).get("outcome", {}).get("name") == "Goal"
        ) or event_type == "Own Goal For"
        if is_goal:
            team_name = _canonical_team_name(match_meta, event)
            if team_name is None:
                raise ValueError(
                    f"Could not map relevant event {event.get('id')} in match {match_id} "
                    f"to {home_team} v {away_team} using team ID or canonical name."
                )
            raw_rows.append(
                {
                    "elapsed_seconds": elapsed_seconds,
                    "period": period,
                    "event_team": team_name,
                    "event_type": "GOAL",
                    "order": 0,
                    "event_id": f"{match_id}_{event['id']}",
                }
            )
            continue

        card = None
        if event_type == "Foul Committed":
            card = ((event.get("foul_committed") or {}).get("card") or {}).get("name")
        elif event_type == "Bad Behaviour":
            card = ((event.get("bad_behaviour") or {}).get("card") or {}).get("name")
        if card in RED_CARD_NAMES:
            team_name = _canonical_team_name(match_meta, event)
            if team_name is None:
                raise ValueError(
                    f"Could not map relevant event {event.get('id')} in match {match_id} "
                    f"to {home_team} v {away_team} using team ID or canonical name."
                )
            raw_rows.append(
                {
                    "elapsed_seconds": elapsed_seconds,
                    "period": period,
                    "event_team": team_name,
                    "event_type": "RED_CARD",
                    "order": 1,
                    "event_id": f"{match_id}_{event['id']}",
                }
            )

    raw_rows.sort(key=lambda r: (r["elapsed_seconds"], r["order"], r["event_id"]))

    home_score = away_score = home_red = away_red = 0
    out_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if row["event_type"] == "GOAL":
            if row["event_team"] == home_team:
                home_score += 1
            elif row["event_team"] == away_team:
                away_score += 1
            else:
                continue
        else:
            if row["event_team"] == home_team:
                home_red += 1
            elif row["event_team"] == away_team:
                away_red += 1
            else:
                continue
        out_rows.append(
            {
                "match_id": str(match_id),
                "event_id": row["event_id"],
                "tournament": tournament,
                "year": year,
                "stage": stage_name,
                "period": row["period"],
                "elapsed_seconds": row["elapsed_seconds"],
                "home_team": home_team,
                "away_team": away_team,
                "event_team": row["event_team"],
                "event_type": row["event_type"],
                "outcome": "confirmed",
                "home_score": home_score,
                "away_score": away_score,
                "home_red_cards": home_red,
                "away_red_cards": away_red,
                "is_neutral": tier == "intl",
                "source_name": DEFAULT_SOURCE_NAME,
                "source_version": source_version,
                "competition_tier": tier,
            }
        )
    return out_rows


def _state_at(events: list[dict[str, Any]], elapsed_seconds: int) -> dict[str, int]:
    previous = [e for e in events if e["elapsed_seconds"] <= elapsed_seconds]
    if not previous:
        return {"home_score": 0, "away_score": 0, "home_red_cards": 0, "away_red_cards": 0}
    latest = max(previous, key=lambda e: e["elapsed_seconds"])
    return {
        "home_score": latest["home_score"],
        "away_score": latest["away_score"],
        "home_red_cards": latest["home_red_cards"],
        "away_red_cards": latest["away_red_cards"],
    }


def build_snapshots(
    events_df: pd.DataFrame,
    matches_meta: list[dict[str, Any]],
    *,
    thresholds: list[int],
    source_version: str = "unknown",
) -> pd.DataFrame:
    """One row per (match, threshold) from the trailing team's perspective -- mirrors transform.py."""

    by_match: dict[str, list[dict[str, Any]]] = {}
    for row in events_df.to_dict("records"):
        by_match.setdefault(row["match_id"], []).append(row)

    rows: list[dict[str, Any]] = []
    for meta in matches_meta:
        match_id = str(meta["match_id"])
        match_events = sorted(by_match.get(match_id, []), key=lambda r: r["elapsed_seconds"])
        home_team = meta["home_team"]["home_team_name"]
        away_team = meta["away_team"]["away_team_name"]
        tournament = meta["_tournament"]
        year = meta["_year"]
        tier = meta["_tier"]

        final_home = match_events[-1]["home_score"] if match_events else 0
        final_away = match_events[-1]["away_score"] if match_events else 0

        for threshold in thresholds:
            state = _state_at(match_events, threshold * 60)
            home_score, away_score = state["home_score"], state["away_score"]
            if home_score < away_score:
                trailing_team, leading_team = home_team, away_team
                goal_difference = home_score - away_score
                trailing_red_diff = state["home_red_cards"] - state["away_red_cards"]
                trailing_final, leading_final = final_home, final_away
            elif away_score < home_score:
                trailing_team, leading_team = away_team, home_team
                goal_difference = away_score - home_score
                trailing_red_diff = state["away_red_cards"] - state["home_red_cards"]
                trailing_final, leading_final = final_away, final_home
            else:
                trailing_team, leading_team = pd.NA, pd.NA
                goal_difference = 0
                trailing_red_diff = 0
                trailing_final, leading_final = home_score, away_score

            if pd.isna(trailing_team):
                result = "NOT_TRAILING"
            elif trailing_final > leading_final:
                result = "TRAILING_TEAM_WIN"
            elif trailing_final == leading_final:
                result = "TRAILING_TEAM_DRAW"
            else:
                result = "TRAILING_TEAM_LOSS"

            rows.append(
                {
                    "match_id": match_id,
                    "threshold_minute": threshold,
                    "tournament": tournament,
                    "year": year,
                    "home_team": home_team,
                    "away_team": away_team,
                    "trailing_team": trailing_team,
                    "leading_team": leading_team,
                    "goal_difference": goal_difference,
                    "red_card_difference": trailing_red_diff,
                    "regulation_result": result,
                    "is_neutral": tier == "intl",
                    "competition_tier": tier,
                    "source_name": DEFAULT_SOURCE_NAME,
                    "source_version": source_version,
                }
            )
    return pd.DataFrame(rows)


def build_history_from_raw(
    raw_dir: Path,
    *,
    pairs: list[dict[str, Any]],
    thresholds: list[int],
    source_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build compact StatsBomb artifacts from pinned match and event JSON files.

    The raw directory is intentionally cache-only. Every match is reconstructed
    from its event stream, while the audit table preserves the metadata score
    check and the raw-event coverage needed by the quality gate.
    """

    event_rows: list[dict[str, Any]] = []
    match_meta_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for pair in pairs:
        competition_id = int(pair["competition_id"])
        season_id = int(pair["season_id"])
        tier = str(pair["tier"])
        matches_path = raw_dir / "matches" / str(competition_id) / f"{season_id}.json"
        if not matches_path.exists():
            raise FileNotFoundError(f"Missing StatsBomb match metadata: {matches_path}")
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        tournament = f"{pair['competition_name']} {pair['season_name']}"

        for raw_match in matches:
            match_id = str(raw_match["match_id"])
            event_path = raw_dir / "events" / f"{match_id}.json"
            if not event_path.exists():
                raise FileNotFoundError(f"Missing StatsBomb event stream: {event_path}")
            events = json.loads(event_path.read_text(encoding="utf-8"))
            match_meta = {
                **raw_match,
                "_tournament": tournament,
                "_year": int(str(raw_match["match_date"])[:4]),
                "_tier": tier,
            }
            timeline = extract_match_timeline(
                match_meta,
                events,
                tournament=tournament,
                tier=tier,
                source_version=source_version,
            )
            event_rows.extend(timeline)
            match_meta_rows.append(match_meta)

            regulation_home = timeline[-1]["home_score"] if timeline else 0
            regulation_away = timeline[-1]["away_score"] if timeline else 0
            metadata_home = raw_match.get("home_score")
            metadata_away = raw_match.get("away_score")
            has_extra_periods = any(event.get("period") not in (1, 2) for event in events)
            audit_rows.append(
                {
                    "match_id": match_id,
                    "competition_id": competition_id,
                    "season_id": season_id,
                    "tournament": tournament,
                    "competition_tier": tier,
                    "home_team": raw_match["home_team"]["home_team_name"],
                    "away_team": raw_match["away_team"]["away_team_name"],
                    "metadata_home_score": metadata_home,
                    "metadata_away_score": metadata_away,
                    "regulation_home_score": regulation_home,
                    "regulation_away_score": regulation_away,
                    "has_extra_periods": has_extra_periods,
                    "event_count": len(events),
                    "timeline_event_count": len(timeline),
                    "source_version": source_version,
                }
            )

    event_columns = [
        "match_id", "event_id", "tournament", "year", "stage", "period", "elapsed_seconds",
        "home_team", "away_team", "event_team", "event_type", "outcome", "home_score",
        "away_score", "home_red_cards", "away_red_cards", "is_neutral", "source_name",
        "source_version", "competition_tier",
    ]
    events_frame = pd.DataFrame(event_rows, columns=event_columns)
    snapshots_frame = build_snapshots(
        events_frame,
        match_meta_rows,
        thresholds=thresholds,
        source_version=source_version,
    )
    return events_frame, snapshots_frame, pd.DataFrame(audit_rows)
