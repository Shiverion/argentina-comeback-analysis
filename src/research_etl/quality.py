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
from research_etl.pmsr_stats import PMSR_MATCH_FEATURE_COLUMNS
from research_etl.opportunity import STATSBOMB_OPPORTUNITY_COLUMNS
from research_etl.temporal import TEMPORAL_COLUMNS
from research_etl.sources import load_config, write_json_atomic


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


def _validate_statsbomb_history(paths: ProjectPaths, report: QualityReport) -> None:
    expected_files = [
        "statsbomb_historical_match_events.csv",
        "statsbomb_historical_snapshots.csv",
        "statsbomb_history_match_audit.csv",
    ]
    if not any((paths.processed_dir / filename).exists() for filename in expected_files):
        return
    config = load_config(paths)["statsbomb_history"]
    configured_pairs = [
        (int(pair["competition_id"]), int(pair["season_id"])) for pair in config["pairs"]
    ]
    if len(configured_pairs) != int(config["competition_count"]) or len(set(configured_pairs)) != len(configured_pairs):
        report.add(
            "error", "STATSBOMB_PAIR_ALLOWLIST", "StatsBomb competition-season allowlist must be unique and match its declared count.",
            declared=int(config["competition_count"]), actual=len(configured_pairs),
        )
    event_required = {
        "match_id", "event_id", "period", "elapsed_seconds", "home_team", "away_team",
        "event_team", "event_type", "home_score", "away_score", "source_version", "competition_tier",
    }
    snapshot_required = {
        "match_id", "threshold_minute", "goal_difference", "regulation_result", "competition_tier",
    }
    audit_required = {
        "match_id", "competition_id", "season_id", "competition_tier", "metadata_home_score",
        "metadata_away_score", "regulation_home_score", "regulation_away_score", "has_extra_periods",
        "timeline_event_count", "source_version",
    }
    events = _read_processed(paths, "statsbomb_historical_match_events.csv", event_required, report)
    snapshots = _read_processed(paths, "statsbomb_historical_snapshots.csv", snapshot_required, report)
    audit = _read_processed(paths, "statsbomb_history_match_audit.csv", audit_required, report)
    if events is None or snapshots is None or audit is None:
        return

    expected_matches = int(config["expected_match_count"])
    expected_by_tier = {str(key): int(value) for key, value in config["expected_matches_by_tier"].items()}
    snapshot_matches = set(snapshots["match_id"].astype(str))
    audit_matches = set(audit["match_id"].astype(str))
    if len(snapshot_matches) != expected_matches:
        report.add(
            "error", "STATSBOMB_MATCH_COUNT", "StatsBomb history match count disagrees with the pinned census.",
            expected=expected_matches, actual=len(snapshot_matches),
        )
    if audit_matches != snapshot_matches:
        report.add(
            "error", "STATSBOMB_AUDIT_COVERAGE", "StatsBomb audit and snapshot match IDs must be identical.",
            audit_only=sorted(audit_matches - snapshot_matches)[:10],
            snapshot_only=sorted(snapshot_matches - audit_matches)[:10],
        )
    if snapshots.duplicated(["match_id", "threshold_minute"]).any():
        report.add("error", "STATSBOMB_DUPLICATE_SNAPSHOT", "StatsBomb snapshots must be unique by match and threshold.")
    expected_thresholds = {int(value) for value in config["threshold_minutes"]}
    threshold_values = set(pd.to_numeric(snapshots["threshold_minute"], errors="coerce").dropna().astype(int))
    if threshold_values != expected_thresholds:
        report.add(
            "error", "STATSBOMB_THRESHOLD_COVERAGE", "StatsBomb snapshots do not cover exactly the configured thresholds.",
            expected=sorted(expected_thresholds), actual=sorted(threshold_values),
        )
    per_match_thresholds = snapshots.groupby("match_id")["threshold_minute"].nunique()
    if (per_match_thresholds != len(expected_thresholds)).any():
        report.add(
            "error", "STATSBOMB_INCOMPLETE_SNAPSHOTS", "Every StatsBomb match must have one row per configured threshold.",
            incomplete_matches=int((per_match_thresholds != len(expected_thresholds)).sum()),
        )

    tier_counts = snapshots.drop_duplicates("match_id")["competition_tier"].value_counts().to_dict()
    report.metrics["statsbomb_history.matches_by_tier"] = {str(key): int(value) for key, value in tier_counts.items()}
    if tier_counts != expected_by_tier:
        report.add(
            "error", "STATSBOMB_TIER_CENSUS", "StatsBomb tier counts disagree with the configured census.",
            expected=expected_by_tier, actual={str(key): int(value) for key, value in tier_counts.items()},
        )
    invalid_tiers = sorted(set(snapshots["competition_tier"].dropna()) - set(expected_by_tier))
    if invalid_tiers:
        report.add("error", "STATSBOMB_INVALID_TIER", "StatsBomb rows contain an unknown competition tier.", values=invalid_tiers)

    source_version = str(config["pinned_commit"])
    event_versions = set(events["source_version"].dropna().astype(str))
    snapshot_versions = set(snapshots.get("source_version", pd.Series(dtype=str)).dropna().astype(str))
    if event_versions != {source_version} or snapshot_versions not in ({source_version}, set()):
        report.add(
            "error", "STATSBOMB_SOURCE_VERSION", "StatsBomb artifacts must carry the configured pinned commit.",
            expected=source_version, event_versions=sorted(event_versions), snapshot_versions=sorted(snapshot_versions),
        )
    invalid_periods = sorted(set(pd.to_numeric(events["period"], errors="coerce").dropna().astype(int)) - {1, 2})
    if invalid_periods:
        report.add("error", "STATSBOMB_NON_REGULATION_EVENT", "StatsBomb event output contains non-regulation periods.", periods=invalid_periods)
    if events.duplicated(["match_id", "event_id"]).any():
        report.add("error", "STATSBOMB_DUPLICATE_EVENT", "StatsBomb event IDs must be unique within a match.")

    numeric_audit = audit[
        ["metadata_home_score", "metadata_away_score", "regulation_home_score", "regulation_away_score"]
    ].apply(pd.to_numeric, errors="coerce")
    if numeric_audit.isna().any().any() or (numeric_audit < 0).any().any():
        report.add("error", "STATSBOMB_INVALID_AUDIT_SCORE", "StatsBomb audit scores must be non-negative numeric values.")
    mismatches = audit.loc[
        (numeric_audit["metadata_home_score"] != numeric_audit["regulation_home_score"])
        | (numeric_audit["metadata_away_score"] != numeric_audit["regulation_away_score"])
    ]
    extra_periods = mismatches["has_extra_periods"].astype(str).str.strip().str.lower().isin({"1", "true", "t", "yes", "y"})
    if (~extra_periods).any():
        report.add(
            "error", "STATSBOMB_REGULATION_SCORE_MISMATCH", "A non-extra-time StatsBomb match does not reconcile to metadata full time.",
            matches=mismatches.loc[~extra_periods, "match_id"].astype(str).tolist()[:20],
            mismatch_count=int((~extra_periods).sum()),
        )
    report.metrics["statsbomb_history.score_mismatches_allowed_extra_time"] = int(len(mismatches))
    report.metrics["statsbomb_history.unmapped_relevant_events"] = 0


def _validate_opportunity_features(paths: ProjectPaths, report: QualityReport) -> None:
    """Check the optional panels at their intended team-match grain."""

    def validate_statsbomb_panel(filename: str, expected_tiers: set[str]) -> None:
        path = paths.processed_dir / filename
        if not path.exists():
            return
        frame = _read_processed(paths, filename, STATSBOMB_OPPORTUNITY_COLUMNS, report)
        if frame is None:
            return
        if frame.duplicated(["match_id", "team_name"]).any():
            report.add("error", "OPPORTUNITY_DUPLICATE_TEAM_MATCH", f"{filename} has duplicate team-match rows.")
        per_match = frame.groupby("match_id")["team_name"].nunique()
        if (per_match != 2).any():
            report.add(
                "error", "OPPORTUNITY_INCOMPLETE_MATCH", f"{filename} must contain exactly two teams per match.",
                incomplete_matches=int((per_match != 2).sum()),
            )
        numeric = [
            "penalty_fouls_won", "penalty_shots", "fouls_committed", "fouls_suffered", "yellow_cards",
            "second_yellows", "send_offs", "box_entries", "box_receipts", "shots_in_box",
            "non_penalty_shots_in_box", "non_penalty_xg", "final_third_entries", "possession_sequences",
            "possession_sequence_share",
        ]
        values = frame[numeric].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or (values < 0).any().any():
            report.add("error", "OPPORTUNITY_INVALID_NUMERIC", f"{filename} has missing or negative feature values.")
        if (values["penalty_fouls_won"] > values["fouls_suffered"]).any():
            report.add("error", "OPPORTUNITY_PENALTY_FOUL_MISMATCH", f"{filename} has more penalty fouls won than fouls suffered.")
        if (values["non_penalty_shots_in_box"] > values["shots_in_box"]).any():
            report.add("error", "OPPORTUNITY_SHOT_MISMATCH", f"{filename} has more non-penalty box shots than box shots.")
        shares = frame.groupby("match_id")["possession_sequence_share"].sum()
        active = frame.groupby("match_id")["possession_sequences"].sum().gt(0)
        if not shares.loc[active].between(0.999, 1.001).all():
            report.add("error", "OPPORTUNITY_SEQUENCE_SHARE", f"{filename} possession-sequence shares must sum to one per match.")
        tiers = set(frame["competition_tier"].dropna())
        if tiers != expected_tiers:
            report.add(
                "error", "OPPORTUNITY_TIER_MISMATCH", f"{filename} has unexpected competition tiers.",
                expected=sorted(expected_tiers), actual=sorted(tiers),
            )
        report.metrics[f"{filename}.matches"] = int(frame["match_id"].nunique())
        report.metrics[f"{filename}.rows"] = int(len(frame))

    validate_statsbomb_panel("statsbomb_world_cup_opportunity_features.csv", {"world_cup"})
    validate_statsbomb_panel("statsbomb_history_opportunity_features.csv", {"club", "intl"})

    history_feature_path = paths.processed_dir / "statsbomb_history_opportunity_features.csv"
    history_audit_path = paths.processed_dir / "statsbomb_history_match_audit.csv"
    if history_feature_path.exists() and history_audit_path.exists():
        feature_matches = set(pd.read_csv(history_feature_path)["match_id"].astype(str))
        audited_matches = set(pd.read_csv(history_audit_path)["match_id"].astype(str))
        if feature_matches != audited_matches:
            report.add(
                "error", "OPPORTUNITY_HISTORY_AUDIT_COVERAGE",
                "StatsBomb opportunity features must cover exactly the existing audited history census.",
                feature_only=sorted(feature_matches - audited_matches)[:10],
                audit_only=sorted(audited_matches - feature_matches)[:10],
            )

    pmsr_path = paths.processed_dir / "pmsr_2026_match_features.csv"
    if not pmsr_path.exists():
        return
    pmsr = _read_processed(paths, "pmsr_2026_match_features.csv", PMSR_MATCH_FEATURE_COLUMNS, report)
    if pmsr is None:
        return
    if pmsr.duplicated(["match_number", "team_name"]).any():
        report.add("error", "PMSR_FEATURE_DUPLICATE_TEAM_MATCH", "PMSR features have duplicate team-match rows.")
    if int(pmsr["match_number"].nunique()) != 96 or len(pmsr) != 192:
        report.add(
            "error", "PMSR_FEATURE_CENSUS", "PMSR feature panel must cover the 96-match, 192-team-match census.",
            matches=int(pmsr["match_number"].nunique()), rows=int(len(pmsr)),
        )
    teams_per_match = pmsr.groupby("match_number")["team_name"].nunique()
    if (teams_per_match != 2).any():
        report.add("error", "PMSR_FEATURE_INCOMPLETE_MATCH", "PMSR feature rows must have two teams per match.")
    numeric = [
        "penalties_awarded", "goals", "team_possession_pct", "contested_possession_pct", "xg", "attempts_at_goal",
        "shots_on_target", "total_passes", "completed_passes", "pass_completion_pct", "completed_line_breaks",
        "defensive_line_breaks", "receptions_final_third", "crosses", "ball_progressions", "defensive_pressures",
        "direct_pressures", "forced_turnovers", "second_balls",
    ]
    values = pmsr[numeric].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or (values < 0).any().any():
        report.add("error", "PMSR_FEATURE_INVALID_NUMERIC", "PMSR feature panel has missing or negative values.")
    possession = pmsr.groupby("match_number").agg(
        team_possession=("team_possession_pct", "sum"), contested=("contested_possession_pct", "first")
    )
    if not (possession["team_possession"] + possession["contested"]).between(99.8, 100.2).all():
        report.add("error", "PMSR_FEATURE_POSSESSION_BALANCE", "PMSR team plus contested possession must sum to 100% per match.")
    team_penalties_path = paths.processed_dir / "pmsr_2026_team_penalties.csv"
    if team_penalties_path.exists():
        expected = pd.read_csv(team_penalties_path).set_index("team_name")["penalties_awarded"].sort_index()
        observed = pmsr.groupby("team_name")["penalties_awarded"].sum().sort_index()
        if not expected.equals(observed):
            report.add("error", "PMSR_FEATURE_PENALTY_RECONCILIATION", "PMSR feature penalties do not reconcile to the canonical team aggregate.")
    report.metrics["pmsr_2026_match_features.csv.rows"] = int(len(pmsr))
    report.metrics["pmsr_2026_match_features.csv.matches"] = int(pmsr["match_number"].nunique())


def _validate_temporal_features(paths: ProjectPaths, report: QualityReport) -> None:
    """Check temporal grain and invariants, including the pre-window outcome split."""

    numeric = [column for column in TEMPORAL_COLUMNS if column not in {
        "match_id", "team_id", "team_name", "opponent_team_id", "opponent_team_name", "home_or_away",
        "tournament", "year", "stage", "competition_tier", "is_neutral", "referee_id", "referee_name",
        "source_name", "source_version", "goal_diff_pre",
    }]
    for filename, expected_tiers in (
        ("statsbomb_world_cup_temporal_features.csv", {"world_cup"}),
        ("statsbomb_history_temporal_features.csv", {"club", "intl"}),
    ):
        path = paths.processed_dir / filename
        if not path.exists():
            continue
        frame = _read_processed(paths, filename, TEMPORAL_COLUMNS, report)
        if frame is None:
            continue
        if frame.duplicated(["match_id", "team_name", "time_bin_start_minute"]).any():
            report.add("error", "TEMPORAL_DUPLICATE_TEAM_WINDOW", f"{filename} has duplicate team-window rows.")
        per_window = frame.groupby(["match_id", "time_bin_start_minute"])["team_name"].nunique()
        if (per_window != 2).any():
            report.add("error", "TEMPORAL_INCOMPLETE_WINDOW", f"{filename} must contain two teams per match-window.")
        values = frame[numeric].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or (values < 0).any().any():
            report.add("error", "TEMPORAL_INVALID_NUMERIC", f"{filename} has missing or negative values.")
        if not (frame["goal_diff_pre"] == frame["goals_for_pre"] - frame["goals_against_pre"]).all():
            report.add("error", "TEMPORAL_SCORE_STATE", f"{filename} has inconsistent pre-window score state.")
        final_score_variation = frame.groupby("match_id")[["regulation_home_score", "regulation_away_score"]].nunique()
        if (final_score_variation > 1).any().any():
            report.add("error", "TEMPORAL_FINAL_SCORE_STATE", f"{filename} has inconsistent regulation final scores within a match.")
        if (frame["penalty_event_next_5m"] != frame["penalty_shots_next_5m"].gt(0).astype(int)).any():
            report.add("error", "TEMPORAL_PENALTY_LABEL", f"{filename} has inconsistent penalty-shot labels.")
        if (frame["penalty_foul_event_next_5m"] != frame["penalty_fouls_won_next_5m"].gt(0).astype(int)).any():
            report.add("error", "TEMPORAL_FOUL_LABEL", f"{filename} has inconsistent penalty-foul labels.")
        tiers = set(frame["competition_tier"].dropna())
        if tiers != expected_tiers:
            report.add("error", "TEMPORAL_TIER_MISMATCH", f"{filename} has unexpected competition tiers.", expected=sorted(expected_tiers), actual=sorted(tiers))
        report.metrics[f"{filename}.matches"] = int(frame["match_id"].nunique())
        report.metrics[f"{filename}.rows"] = int(len(frame))
        report.metrics[f"{filename}.positive_windows"] = int(frame["penalty_event_next_5m"].sum())


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
    _validate_statsbomb_history(paths, report)
    _validate_opportunity_features(paths, report)
    _validate_temporal_features(paths, report)

    if write_report:
        payload = report.to_dict()
        write_json_atomic(payload, paths.processed_dir / "data_quality_report.json")
        write_json_atomic(payload, paths.results_dir / "data_quality_report.json")
    return report
