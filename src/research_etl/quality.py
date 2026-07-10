from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from research_etl.contracts import (
    FOCAL_EVENT_COLUMNS,
    HISTORICAL_EVENT_COLUMNS,
    INCIDENT_COLUMNS,
    STRENGTH_COLUMNS,
    VALID_INCIDENT_STATUSES,
    missing_columns,
)
from research_etl.paths import ProjectPaths
from research_etl.pmsr import PMSR_TEAM_COLUMNS
from research_etl.sources import write_json_atomic


@dataclass
class QualityIssue:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, **context: Any) -> None:
        self.issues.append(QualityIssue(severity, code, message, context))

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "failed" if self.error_count else "passed_with_warnings" if self.warning_count else "passed",
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "metrics": self.metrics,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _read_processed(paths: ProjectPaths, filename: str, required: set[str], report: QualityReport) -> pd.DataFrame | None:
    path = paths.processed_dir / filename
    if not path.exists():
        report.add("error", "MISSING_ARTIFACT", f"Required processed artifact is missing: {filename}")
        return None
    frame = pd.read_csv(path)
    missing = missing_columns(frame.columns, required)
    if missing:
        report.add(
            "error",
            "SCHEMA_MISMATCH",
            f"{filename} is missing required columns.",
            missing_columns=missing,
        )
        return None
    report.metrics[f"{filename}.rows"] = int(len(frame))
    return frame


def _validate_focal_events(frame: pd.DataFrame, report: QualityReport) -> None:
    if frame["event_id"].duplicated().any():
        report.add(
            "error",
            "DUPLICATE_FOCAL_EVENT_ID",
            "Focal event IDs must be unique.",
            duplicates=int(frame["event_id"].duplicated().sum()),
        )
    if frame["elapsed_seconds"].isna().any() or (pd.to_numeric(frame["elapsed_seconds"], errors="coerce") < 0).any():
        report.add("error", "INVALID_FOCAL_TIME", "Focal event elapsed_seconds must be non-negative numeric values.")
    ordered = frame.sort_values(["match_id", "elapsed_seconds", "event_id"], kind="stable")
    if not ordered.groupby("match_id")["elapsed_seconds"].apply(lambda values: values.is_monotonic_increasing).all():
        report.add("error", "FOCAL_CHRONOLOGY", "Focal events are not chronologically ordered within a match.")

    confirmed_goals = ordered.loc[
        ordered["event_type"].astype(str).str.upper().eq("GOAL")
        & ordered["outcome"].astype(str).str.lower().eq("confirmed")
    ]
    for match_id, goals in confirmed_goals.groupby("match_id", sort=False):
        argentina_score = egypt_score = 0
        for goal in goals.itertuples(index=False):
            if goal.team == "Argentina":
                argentina_score += 1
            elif goal.team == "Egypt":
                egypt_score += 1
            else:
                report.add(
                    "error",
                    "UNKNOWN_FOCAL_TEAM",
                    "A confirmed goal must be assigned to Argentina or Egypt.",
                    match_id=match_id,
                    event_id=goal.event_id,
                    team=goal.team,
                )
                continue
            if int(goal.score_argentina) != argentina_score or int(goal.score_egypt) != egypt_score:
                report.add(
                    "error",
                    "FOCAL_SCORE_TRANSITION",
                    "A confirmed goal does not produce the stated post-event score.",
                    match_id=match_id,
                    event_id=goal.event_id,
                    expected_score=[argentina_score, egypt_score],
                    stated_score=[int(goal.score_argentina), int(goal.score_egypt)],
                )
        if match_id == "M95" and (argentina_score, egypt_score) != (3, 2):
            report.add(
                "error",
                "FOCAL_FINAL_SCORE",
                "The focal M95 timeline must reconcile to Argentina 3-2 Egypt.",
                calculated_score=[argentina_score, egypt_score],
            )


def _validate_incidents(frame: pd.DataFrame, report: QualityReport) -> None:
    if frame["incident_id"].duplicated().any():
        report.add(
            "error",
            "DUPLICATE_INCIDENT_ID",
            "Incident IDs must be unique.",
            duplicates=int(frame["incident_id"].duplicated().sum()),
        )
    unknown_statuses = sorted(set(frame["evidence_status"].dropna()) - VALID_INCIDENT_STATUSES)
    if unknown_statuses:
        report.add(
            "error",
            "INVALID_INCIDENT_STATUS",
            "Incident evidence statuses must use the controlled vocabulary.",
            values=unknown_statuses,
        )
    unresolved = frame["evidence_status"].isin(["reported", "unresolved"]).sum()
    if unresolved:
        report.add(
            "warning",
            "INCIDENTS_NOT_MODEL_READY",
            "Reported or unresolved incidents remain excluded from correctness-assessed analysis; "
            "they may appear only in explicitly conditional scenario-only outputs.",
            incident_count=int(unresolved),
        )


def _validate_historical_events(frame: pd.DataFrame, report: QualityReport) -> None:
    if frame.duplicated(["match_id", "event_id"]).any():
        report.add(
            "error",
            "DUPLICATE_HISTORICAL_EVENT",
            "Historical event IDs must be unique within a match.",
            duplicates=int(frame.duplicated(["match_id", "event_id"]).sum()),
        )
    invalid_periods = frame.loc[~frame["period"].isin([1, 2]), "period"].dropna().unique().tolist()
    if invalid_periods:
        report.add(
            "error",
            "NON_REGULATION_EVENT",
            "Historical event artifact must contain regulation-time events only.",
            periods=invalid_periods,
        )
    for match_id, events in frame.sort_values(["match_id", "elapsed_seconds", "event_id"], kind="stable").groupby("match_id", sort=False):
        if not events["elapsed_seconds"].is_monotonic_increasing:
            report.add("error", "HISTORICAL_CHRONOLOGY", "Historical events are out of order.", match_id=match_id)
        scores = events[["home_score", "away_score"]].apply(pd.to_numeric, errors="coerce")
        if (scores.diff().fillna(0) < 0).any().any():
            report.add("error", "HISTORICAL_SCORE_DECREASE", "Scores cannot decrease within a match.", match_id=match_id)
        if ((scores.diff().fillna(0) > 1).any()).any():
            report.add("error", "HISTORICAL_SCORE_JUMP", "A score increased by more than one at an event.", match_id=match_id)


def _validate_snapshots(paths: ProjectPaths, report: QualityReport) -> None:
    path = paths.processed_dir / "historical_snapshots.csv"
    if not path.exists():
        report.add("error", "MISSING_ARTIFACT", "Required processed artifact is missing: historical_snapshots.csv")
        return
    snapshots = pd.read_csv(path)
    required = {"match_id", "threshold_minute", "goal_difference", "regulation_result"}
    missing = missing_columns(snapshots.columns, required)
    if missing:
        report.add("error", "SCHEMA_MISMATCH", "historical_snapshots.csv has missing columns.", missing_columns=missing)
        return
    report.metrics["historical_snapshots.csv.rows"] = int(len(snapshots))
    if snapshots.duplicated(["match_id", "threshold_minute"]).any():
        report.add("error", "DUPLICATE_SNAPSHOT", "Each match must have one snapshot per threshold.")
    eligible = snapshots.loc[pd.to_numeric(snapshots["goal_difference"], errors="coerce") <= -2]
    report.metrics["historical_snapshots.eligible_late_two_goal_states"] = int(len(eligible))
    if eligible.empty:
        report.add(
            "warning",
            "NO_ELIGIBLE_RARITY_STATES",
            "No late two-goal deficit states were present in the historical source at the registered thresholds.",
        )


def _validate_strength(paths: ProjectPaths, report: QualityReport) -> None:
    strength = _read_processed(paths, "pre_match_strength.csv", STRENGTH_COLUMNS, report)
    status_path = paths.processed_dir / "model_frame_status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        report.metrics["model_frame_status"] = status.get("status")
        if status.get("status") != "ready":
            report.add(
                "warning",
                "MODEL_FRAME_BLOCKED",
                "Win-probability model input has not been built because pre-match strength coverage is incomplete or invalid.",
                model_status=status,
            )
    else:
        report.add("error", "MISSING_MODEL_STATUS", "model_frame_status.json is missing.")
    if strength is not None and strength.empty:
        report.add(
            "warning",
            "EMPTY_STRENGTH_INPUT",
            "Pre-match strength template is empty; historical rarity can run, but calibrated match-state modelling remains blocked.",
        )
    if strength is None or strength.empty:
        return
    if strength.duplicated(["match_id", "team"]).any():
        report.add("error", "DUPLICATE_STRENGTH", "Strength rows must be unique by match_id and team.")
    numeric_elo = pd.to_numeric(strength["elo_rating"], errors="coerce")
    if numeric_elo.isna().any():
        report.add("error", "INVALID_STRENGTH", "Every strength row needs a numeric elo_rating.")
    as_of = pd.to_datetime(strength["as_of_date"], errors="coerce")
    if as_of.isna().any():
        report.add("error", "INVALID_STRENGTH_DATE", "Every strength row needs a valid as_of_date.")

    if not status_path.exists() or status.get("status") != "ready":
        return
    model_required = {
        "match_id", "focal_team", "opponent_team", "elapsed_seconds", "goal_difference",
        "red_card_difference", "strength_difference", "regulation_result", "year",
    }
    model = _read_processed(paths, "model_frame.csv", model_required, report)
    if model is None:
        return
    if model.duplicated(["match_id", "focal_team", "elapsed_seconds"]).any():
        report.add("error", "DUPLICATE_MODEL_STATE", "Model frame state keys must be unique.")
    expected_rows = status.get("rows")
    expected_matches = status.get("matches")
    if expected_rows is not None and len(model) != int(expected_rows):
        report.add(
            "error", "MODEL_ROW_COUNT", "Model frame row count disagrees with model status.",
            expected=int(expected_rows), actual=int(len(model)),
        )
    if expected_matches is not None and model["match_id"].nunique() != int(expected_matches):
        report.add(
            "error", "MODEL_MATCH_COUNT", "Model frame match count disagrees with model status.",
            expected=int(expected_matches), actual=int(model["match_id"].nunique()),
        )
    match_year = model[["match_id", "year"]].drop_duplicates("match_id")
    dated = strength.assign(_as_of=as_of).merge(match_year, on="match_id", how="left")
    if dated["year"].isna().any():
        report.add("error", "STRENGTH_MATCH_JOIN", "Strength rows must resolve to a model-frame match year.")
    elif (dated["_as_of"].dt.year >= pd.to_numeric(dated["year"], errors="coerce")).any():
        report.add("error", "POST_MATCH_STRENGTH", "Strength as_of_date must be strictly before match year.")


def _validate_pmsr(paths: ProjectPaths, report: QualityReport) -> None:
    frame = _read_processed(paths, "pmsr_2026_team_penalties.csv", PMSR_TEAM_COLUMNS, report)
    if frame is None:
        return
    if frame.duplicated(["tournament_name", "team_name"]).any():
        report.add("error", "DUPLICATE_PMSR_TEAM", "PMSR team rows must be unique within the tournament.")
    numeric = frame[["matches_played", "penalties_awarded", "penalties_awarded_per_match"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if numeric.isna().any().any() or (numeric < 0).any().any():
        report.add("error", "INVALID_PMSR_VALUE", "PMSR counts and rates must be non-negative numeric values.")
        return
    expected_rate = numeric["penalties_awarded"] / numeric["matches_played"]
    if not expected_rate.round(12).equals(numeric["penalties_awarded_per_match"].round(12)):
        report.add("error", "PMSR_RATE_MISMATCH", "PMSR rates must equal penalties divided by matches played.")
    if len(frame) != 48 or int(numeric["matches_played"].sum()) != 192:
        report.add(
            "error", "PMSR_CENSUS_MISMATCH", "PMSR output must represent 48 teams and 96 matches.",
            teams=int(len(frame)), match_appearances=int(numeric["matches_played"].sum()),
        )


def _validate_focal_strength(paths: ProjectPaths, report: QualityReport) -> None:
    frame = _read_processed(paths, "focal_pre_match_strength.csv", STRENGTH_COLUMNS, report)
    if frame is None:
        return
    expected_teams = {"Argentina", "Egypt"}
    if len(frame) != 2 or set(frame["team"]) != expected_teams or set(frame["match_id"].astype(str)) != {"M95"}:
        report.add(
            "error", "FOCAL_STRENGTH_COVERAGE",
            "Focal strength must contain exactly Argentina and Egypt for M95.",
        )
    if pd.to_numeric(frame["elo_rating"], errors="coerce").isna().any():
        report.add("error", "FOCAL_STRENGTH_VALUE", "Focal Elo ratings must be numeric.")
    as_of = pd.to_datetime(frame["as_of_date"], errors="coerce")
    if as_of.isna().any() or (as_of >= pd.Timestamp("2026-07-07")).any():
        report.add(
            "error", "FOCAL_STRENGTH_LEAKAGE",
            "Focal strength dates must be valid and strictly before the 2026-07-07 kickoff date.",
        )


def validate_processed(paths: ProjectPaths, *, write_report: bool = True) -> QualityReport:
    """Run stable quality checks over the ETL outputs before the notebook consumes them."""

    report = QualityReport()
    focal = _read_processed(paths, "focal_events.csv", FOCAL_EVENT_COLUMNS, report)
    incidents = _read_processed(paths, "incidents.csv", INCIDENT_COLUMNS, report)
    historical = _read_processed(paths, "historical_match_events.csv", HISTORICAL_EVENT_COLUMNS, report)
    if focal is not None:
        _validate_focal_events(focal, report)
    if incidents is not None:
        _validate_incidents(incidents, report)
    if historical is not None:
        _validate_historical_events(historical, report)
    _validate_snapshots(paths, report)
    _validate_strength(paths, report)
    _validate_pmsr(paths, report)
    _validate_focal_strength(paths, report)

    if write_report:
        payload = report.to_dict()
        write_json_atomic(payload, paths.processed_dir / "data_quality_report.json")
        write_json_atomic(payload, paths.results_dir / "data_quality_report.json")
    return report
