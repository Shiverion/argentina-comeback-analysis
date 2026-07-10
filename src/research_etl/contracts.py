from __future__ import annotations

from typing import Iterable


FOCAL_EVENT_COLUMNS = {
    "match_id",
    "event_id",
    "period",
    "minute",
    "second",
    "elapsed_seconds",
    "team",
    "event_type",
    "outcome",
    "score_argentina",
    "score_egypt",
    "player",
    "source_url",
    "source_tier",
    "verified",
    "notes",
}

INCIDENT_COLUMNS = {
    "incident_id",
    "event_id",
    "elapsed_seconds",
    "claim",
    "actual_decision",
    "alternate_decision",
    "actual_state",
    "alternate_state",
    "beneficiary_if_alternate",
    "law_reference",
    "evidence_status",
    "source_urls",
    "reviewer_a",
    "reviewer_b",
    "review_notes",
}

STRENGTH_COLUMNS = {
    "match_id",
    "team",
    "elo_rating",
    "fifa_rank",
    "pre_match_win_odds",
    "source_name",
    "as_of_date",
}

HISTORICAL_EVENT_COLUMNS = {
    "match_id",
    "event_id",
    "tournament",
    "year",
    "stage",
    "period",
    "elapsed_seconds",
    "home_team",
    "away_team",
    "event_team",
    "event_type",
    "outcome",
    "home_score",
    "away_score",
    "home_red_cards",
    "away_red_cards",
    "is_neutral",
    "source_name",
    "source_version",
}

VALID_INCIDENT_STATUSES = {
    "reported",
    "video_reviewed",
    "officially_confirmed",
    "unresolved",
    "excluded",
}


def missing_columns(columns: Iterable[str], required: set[str]) -> list[str]:
    return sorted(required - set(columns))
