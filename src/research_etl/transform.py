from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research_etl.contracts import FOCAL_EVENT_COLUMNS, INCIDENT_COLUMNS, STRENGTH_COLUMNS, missing_columns
from research_etl.paths import ProjectPaths
from research_etl.pmsr import PMSR_EXTRACT_COLUMNS, aggregate_team_penalties, validate_pmsr_extract
from research_etl.sources import SourceError, load_config, sha256_file, write_json_atomic
from research_etl.strength import build_pre_match_strength


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_csv_atomic(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    frame.to_csv(temporary, index=False)
    temporary.replace(destination)


def _as_bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _required_csv(path: Path, required: set[str], label: str) -> pd.DataFrame:
    if not path.exists():
        raise SourceError(f"Missing {label}: {path}. Run `extract` or `init` first.")
    frame = pd.read_csv(path)
    missing = missing_columns(frame.columns, required)
    if missing:
        raise SourceError(f"{label} is missing required columns: {', '.join(missing)}")
    return frame


def minute_to_elapsed_seconds(minute_regulation: Any, minute_stoppage: Any = 0) -> int | None:
    """Map minute-resolution World Cup data to the end of that recorded minute.

    Fjelstul's source records minutes rather than seconds. Placing a goal at the
    last second of its stated minute is conservative for threshold snapshots:
    an event listed in minute 70 is present at 70:00 but not before it.
    """

    minute = pd.to_numeric(pd.Series([minute_regulation]), errors="coerce").iloc[0]
    stoppage = pd.to_numeric(pd.Series([minute_stoppage]), errors="coerce").iloc[0]
    if pd.isna(minute) or minute <= 0:
        return None
    minute = int(minute)
    stoppage = 0 if pd.isna(stoppage) else int(stoppage)
    return max(0, minute * 60 - 1 + stoppage * 60)


def _load_manual_inputs(paths: ProjectPaths) -> tuple[pd.DataFrame, pd.DataFrame]:
    manual_dir = paths.raw_dir / "manual"
    focal = _required_csv(manual_dir / "focal_events_reviewed.csv", FOCAL_EVENT_COLUMNS, "focal event input")
    incidents = _required_csv(manual_dir / "incidents_reviewed.csv", INCIDENT_COLUMNS, "incident input")

    focal = focal.copy()
    focal["elapsed_seconds"] = pd.to_numeric(focal["elapsed_seconds"], errors="raise").astype(int)
    focal["score_argentina"] = pd.to_numeric(focal["score_argentina"], errors="raise").astype(int)
    focal["score_egypt"] = pd.to_numeric(focal["score_egypt"], errors="raise").astype(int)
    focal["verified"] = focal["verified"].map(_as_bool)
    focal = focal.sort_values(["match_id", "elapsed_seconds", "event_id"], kind="stable").reset_index(drop=True)

    incidents = incidents.copy()
    incidents["elapsed_seconds"] = pd.to_numeric(incidents["elapsed_seconds"], errors="coerce").astype("Int64")
    return focal, incidents


def _world_cup_matches(matches: pd.DataFrame) -> pd.DataFrame:
    mask = matches["tournament_name"].astype(str).str.contains(r"FIFA.*World Cup", case=False, na=False, regex=True)
    mask &= ~matches["tournament_name"].astype(str).str.contains("Women", case=False, na=False)
    selected = matches.loc[mask].copy()
    if selected.empty:
        raise SourceError("Fjelstul source did not contain men's FIFA World Cup matches.")
    selected["match_id"] = selected["match_id"].astype(str)
    selected["match_date"] = pd.to_datetime(selected["match_date"], errors="coerce")
    selected["is_knockout"] = selected["knockout_stage"].map(_as_bool)
    return selected


def build_historical_artifacts(
    matches: pd.DataFrame,
    goals: pd.DataFrame,
    bookings: pd.DataFrame,
    *,
    thresholds: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Normalize World Cup goal/card records into regulation-time event and state tables."""

    matches = _world_cup_matches(matches)
    goals = goals.copy()
    bookings = bookings.copy()
    goals["match_id"] = goals["match_id"].astype(str)
    bookings["match_id"] = bookings["match_id"].astype(str)
    valid_match_ids = set(matches["match_id"])
    goals = goals.loc[goals["match_id"].isin(valid_match_ids)].copy()
    bookings = bookings.loc[bookings["match_id"].isin(valid_match_ids)].copy()

    timeline_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    regulation_rows: list[dict[str, Any]] = []

    for match in matches.sort_values("match_id", kind="stable").itertuples(index=False):
        match_id = str(match.match_id)
        home_team = match.home_team_name
        away_team = match.away_team_name
        year = int(match.match_date.year) if pd.notna(match.match_date) else pd.NA

        event_rows: list[dict[str, Any]] = []
        match_goals = goals.loc[goals.match_id.eq(match_id)].copy()
        for goal in match_goals.itertuples(index=False):
            minute = pd.to_numeric(pd.Series([goal.minute_regulation]), errors="coerce").iloc[0]
            if pd.isna(minute) or int(minute) > 90:
                continue
            elapsed_seconds = minute_to_elapsed_seconds(goal.minute_regulation, goal.minute_stoppage)
            if elapsed_seconds is None:
                continue
            event_rows.append(
                {
                    "event_id": f"goal_{goal.goal_id}",
                    "elapsed_seconds": elapsed_seconds,
                    "event_team": goal.team_name,
                    "event_type": "GOAL",
                    "period": 1 if int(minute) <= 45 else 2,
                    "outcome": "confirmed",
                    "order": 0,
                }
            )

        match_bookings = bookings.loc[bookings.match_id.eq(match_id)].copy()
        for booking in match_bookings.itertuples(index=False):
            is_red = _as_bool(booking.red_card) or _as_bool(booking.second_yellow_card) or _as_bool(booking.sending_off)
            if not is_red:
                continue
            minute = pd.to_numeric(pd.Series([booking.minute_regulation]), errors="coerce").iloc[0]
            if pd.isna(minute) or int(minute) > 90:
                continue
            elapsed_seconds = minute_to_elapsed_seconds(booking.minute_regulation, booking.minute_stoppage)
            if elapsed_seconds is None:
                continue
            event_rows.append(
                {
                    "event_id": f"booking_{booking.booking_id}",
                    "elapsed_seconds": elapsed_seconds,
                    "event_team": booking.team_name,
                    "event_type": "RED_CARD",
                    "period": 1 if int(minute) <= 45 else 2,
                    "outcome": "confirmed",
                    "order": 1,
                }
            )

        event_rows.sort(key=lambda item: (item["elapsed_seconds"], item["order"], item["event_id"]))
        home_score = away_score = home_red_cards = away_red_cards = 0
        current_events: list[dict[str, Any]] = []
        for event in event_rows:
            if event["event_type"] == "GOAL":
                if event["event_team"] == home_team:
                    home_score += 1
                elif event["event_team"] == away_team:
                    away_score += 1
                else:
                    raise SourceError(
                        f"Goal {event['event_id']} has team '{event['event_team']}' outside {home_team} v {away_team}."
                    )
            elif event["event_team"] == home_team:
                home_red_cards += 1
            elif event["event_team"] == away_team:
                away_red_cards += 1
            else:
                raise SourceError(
                    f"Booking {event['event_id']} has team '{event['event_team']}' outside {home_team} v {away_team}."
                )

            record = {
                "match_id": match_id,
                "event_id": event["event_id"],
                "tournament": match.tournament_name,
                "year": year,
                "stage": match.stage_name,
                "period": event["period"],
                "elapsed_seconds": event["elapsed_seconds"],
                "home_team": home_team,
                "away_team": away_team,
                "event_team": event["event_team"],
                "event_type": event["event_type"],
                "outcome": event["outcome"],
                "home_score": home_score,
                "away_score": away_score,
                "home_red_cards": home_red_cards,
                "away_red_cards": away_red_cards,
                "is_neutral": True,
                "source_name": "Fjelstul World Cup Database",
                "source_version": "1.2.0",
            }
            current_events.append(record)
            timeline_rows.append(record)

        regulation_rows.append(
            {
                "match_id": match_id,
                "tournament": match.tournament_name,
                "year": year,
                "stage": match.stage_name,
                "home_team": home_team,
                "away_team": away_team,
                "is_knockout": bool(match.is_knockout),
                "is_neutral": True,
                "home_regulation_score": home_score,
                "away_regulation_score": away_score,
            }
        )

        for threshold in thresholds:
            state = _state_at(current_events, threshold * 60)
            current_home_score = state["home_score"]
            current_away_score = state["away_score"]
            if current_home_score < current_away_score:
                trailing_team = home_team
                leading_team = away_team
                goal_difference = current_home_score - current_away_score
                trailing_red_card_difference = state["home_red_cards"] - state["away_red_cards"]
                trailing_final_score = home_score
                leading_final_score = away_score
            elif current_away_score < current_home_score:
                trailing_team = away_team
                leading_team = home_team
                goal_difference = current_away_score - current_home_score
                trailing_red_card_difference = state["away_red_cards"] - state["home_red_cards"]
                trailing_final_score = away_score
                leading_final_score = home_score
            else:
                trailing_team = pd.NA
                leading_team = pd.NA
                goal_difference = 0
                trailing_red_card_difference = 0
                trailing_final_score = current_home_score
                leading_final_score = current_away_score

            if pd.isna(trailing_team):
                result = "NOT_TRAILING"
            elif trailing_final_score > leading_final_score:
                result = "TRAILING_TEAM_WIN"
            elif trailing_final_score == leading_final_score:
                result = "TRAILING_TEAM_DRAW"
            else:
                result = "TRAILING_TEAM_LOSS"

            snapshot_rows.append(
                {
                    "match_id": match_id,
                    "threshold_minute": threshold,
                    "tournament": match.tournament_name,
                    "year": year,
                    "stage": match.stage_name,
                    "home_team": home_team,
                    "away_team": away_team,
                    "trailing_team": trailing_team,
                    "leading_team": leading_team,
                    "home_score": current_home_score,
                    "away_score": current_away_score,
                    "goal_difference": goal_difference,
                    "red_card_difference": trailing_red_card_difference,
                    "regulation_result": result,
                    "is_knockout": bool(match.is_knockout),
                    "is_neutral": True,
                    "source_name": "Fjelstul World Cup Database",
                    "source_version": "1.2.0",
                }
            )

    events = pd.DataFrame(timeline_rows)
    snapshots = pd.DataFrame(snapshot_rows)
    regulation = pd.DataFrame(regulation_rows)
    return events, snapshots, regulation


def _state_at(events: list[dict[str, Any]], elapsed_seconds: int) -> dict[str, int]:
    current = {"home_score": 0, "away_score": 0, "home_red_cards": 0, "away_red_cards": 0}
    for event in events:
        if event["elapsed_seconds"] <= elapsed_seconds:
            current = {
                "home_score": int(event["home_score"]),
                "away_score": int(event["away_score"]),
                "home_red_cards": int(event["home_red_cards"]),
                "away_red_cards": int(event["away_red_cards"]),
            }
        else:
            break
    return current


def build_model_frame(
    regulation: pd.DataFrame,
    historical_events: pd.DataFrame,
    strengths: pd.DataFrame,
    *,
    start_minute: int,
    end_minute: int,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Create team-perspective snapshots only when pre-match strength is complete."""

    if strengths.empty:
        return None, {"status": "blocked_missing_strength", "detail": "No pre-match strength rows supplied."}

    strength = strengths.copy()
    strength["match_id"] = strength["match_id"].astype(str)
    strength["team"] = strength["team"].astype(str)
    duplicate_pairs = strength.duplicated(["match_id", "team"], keep=False)
    if duplicate_pairs.any():
        return None, {
            "status": "blocked_invalid_strength",
            "detail": "Pre-match strength has duplicate match/team pairs.",
            "duplicate_rows": int(duplicate_pairs.sum()),
        }
    if strength["elo_rating"].isna().any():
        return None, {
            "status": "blocked_invalid_strength",
            "detail": "Every supplied strength row needs a numeric elo_rating.",
            "missing_elo_rows": int(strength["elo_rating"].isna().sum()),
        }

    strength_index = strength.set_index(["match_id", "team"])["elo_rating"].to_dict()
    missing_pairs: list[tuple[str, str]] = []
    for match in regulation.itertuples(index=False):
        for team in (match.home_team, match.away_team):
            if (str(match.match_id), str(team)) not in strength_index:
                missing_pairs.append((str(match.match_id), str(team)))
    if missing_pairs:
        return None, {
            "status": "blocked_missing_strength",
            "detail": "Strength coverage must include both teams in every historical match.",
            "missing_pairs": missing_pairs[:20],
            "missing_pair_count": len(missing_pairs),
        }

    event_groups = {
        match_id: group.sort_values(["elapsed_seconds", "event_id"], kind="stable").to_dict("records")
        for match_id, group in historical_events.groupby("match_id", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for match in regulation.itertuples(index=False):
        match_id = str(match.match_id)
        event_rows = event_groups.get(match_id, [])
        home_rating = float(strength_index[(match_id, match.home_team)])
        away_rating = float(strength_index[(match_id, match.away_team)])
        for minute in range(start_minute, end_minute + 1):
            state = _state_at(event_rows, minute * 60)
            for focal_team, opponent_team, focal_score, opponent_score, focal_red, opponent_red, rating_delta in (
                (
                    match.home_team,
                    match.away_team,
                    state["home_score"],
                    state["away_score"],
                    state["home_red_cards"],
                    state["away_red_cards"],
                    home_rating - away_rating,
                ),
                (
                    match.away_team,
                    match.home_team,
                    state["away_score"],
                    state["home_score"],
                    state["away_red_cards"],
                    state["home_red_cards"],
                    away_rating - home_rating,
                ),
            ):
                if focal_team == match.home_team:
                    final_focal, final_opponent = match.home_regulation_score, match.away_regulation_score
                else:
                    final_focal, final_opponent = match.away_regulation_score, match.home_regulation_score
                if final_focal > final_opponent:
                    final_result = "FOCAL_WIN"
                elif final_focal == final_opponent:
                    final_result = "DRAW"
                else:
                    final_result = "FOCAL_LOSS"
                rows.append(
                    {
                        "match_id": match_id,
                        "focal_team": focal_team,
                        "opponent_team": opponent_team,
                        "elapsed_seconds": minute * 60,
                        "goal_difference": focal_score - opponent_score,
                        "red_card_difference": focal_red - opponent_red,
                        "strength_difference": rating_delta,
                        "is_knockout": int(bool(match.is_knockout)),
                        "is_neutral": int(bool(match.is_neutral)),
                        "regulation_result": final_result,
                        "tournament": match.tournament,
                        "year": match.year,
                        "stage": match.stage,
                    }
                )
    return pd.DataFrame(rows), {"status": "ready", "rows": len(rows), "matches": len(regulation)}


def transform_sources(paths: ProjectPaths) -> dict[str, Any]:
    """Load raw source lanes, normalize tables, and create notebook-ready artifacts."""

    paths.ensure_directories()
    config = load_config(paths)
    focal, incidents = _load_manual_inputs(paths)
    historical_config = config["historical_world_cup"]
    raw_historical_dir = paths.root / historical_config["target_dir"]
    matches = _required_csv(raw_historical_dir / "matches.csv", {"match_id", "tournament_name"}, "historical matches")
    goals = _required_csv(
        raw_historical_dir / "goals.csv",
        {"goal_id", "match_id", "team_name", "minute_regulation", "minute_stoppage"},
        "historical goals",
    )
    bookings = _required_csv(
        raw_historical_dir / "bookings.csv",
        {"booking_id", "match_id", "team_name", "minute_regulation", "minute_stoppage", "red_card", "second_yellow_card", "sending_off"},
        "historical bookings",
    )

    strength_config = config["team_strength"]
    ratings = _required_csv(
        paths.root / strength_config["target"], {"year", "team", "rating"}, "pinned team-strength source"
    )
    strength = build_pre_match_strength(
        matches,
        ratings,
        aliases=strength_config.get("team_aliases", {}),
        source_name=strength_config["source_name"],
    )

    pmsr_config = config["pmsr_2026"]
    pmsr_extract = _required_csv(
        paths.root / pmsr_config["raw_target"], PMSR_EXTRACT_COLUMNS, "PMSR 2026 extraction"
    )
    normalized_pmsr_extract = validate_pmsr_extract(pmsr_extract)
    write_csv_atomic(normalized_pmsr_extract, paths.root / pmsr_config["raw_target"])
    pmsr_team_penalties = aggregate_team_penalties(normalized_pmsr_extract)

    focal_strength_config = config["focal_team_strength"]
    focal_strength = _required_csv(
        paths.root / focal_strength_config["raw_target"],
        STRENGTH_COLUMNS,
        "focal pre-match strength snapshot",
    )
    focal_strength = focal_strength.copy()
    focal_strength["elo_rating"] = pd.to_numeric(focal_strength["elo_rating"], errors="raise")
    focal_strength["as_of_date"] = pd.to_datetime(
        focal_strength["as_of_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")

    historical_events, snapshots, regulation = build_historical_artifacts(
        matches,
        goals,
        bookings,
        thresholds=[int(value) for value in config["threshold_minutes"]],
    )

    outputs = {
        "focal_events.csv": focal,
        "incidents.csv": incidents,
        "historical_match_events.csv": historical_events,
        "historical_snapshots.csv": snapshots,
        "pre_match_strength.csv": strength,
        "focal_pre_match_strength.csv": focal_strength,
        "pmsr_2026_team_penalties.csv": pmsr_team_penalties,
    }
    for filename, frame in outputs.items():
        write_csv_atomic(frame, paths.processed_dir / filename)

    model_config = config["model_snapshot_minutes"]
    model_frame, model_status = build_model_frame(
        regulation,
        historical_events,
        strength,
        start_minute=int(model_config["start"]),
        end_minute=int(model_config["end"]),
    )
    if model_frame is not None:
        write_csv_atomic(model_frame, paths.processed_dir / "model_frame.csv")

    write_json_atomic(model_status, paths.processed_dir / "model_frame_status.json")
    artifact_rows = []
    for filename in outputs:
        path = paths.processed_dir / filename
        artifact_rows.append(
            {
                "filename": filename,
                "rows": int(len(outputs[filename])),
                "sha256": sha256_file(path),
            }
        )
    if model_frame is not None:
        model_path = paths.processed_dir / "model_frame.csv"
        artifact_rows.append(
            {"filename": "model_frame.csv", "rows": int(len(model_frame)), "sha256": sha256_file(model_path)}
        )

    manifest = {
        "pipeline": "research_etl.transform",
        "created_at": _utc_now(),
        "artifacts": artifact_rows,
        "model_status": model_status,
        "notes": {
            "historical_timeline_resolution": "Minute-resolution goals and bookings are placed at the end of their recorded minute.",
            "historical_coverage": "Fjelstul World Cup Database covers men's World Cups through 2022; 2026 focal data is held separately.",
        },
    }
    write_json_atomic(manifest, paths.processed_dir / "run_manifest.json")
    return manifest
