"""Validation and aggregation for the compact FIFA PMSR 2026 extraction."""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

import pandas as pd

from research_etl.sources import SourceError

PMSR_EXTRACT_COLUMNS = {"match_number", "filename", "source_url", "team", "penalties_awarded"}
PMSR_TEAM_COLUMNS = {
    "tournament_name", "year", "team_name", "matches_played",
    "penalties_awarded", "penalties_awarded_per_match",
}


def normalize_source_url(url: str) -> str:
    """Percent-encode path spaces while preserving URL structure."""

    parts = urlsplit(str(url).strip())
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%-._~"), parts.query, parts.fragment))


def validate_pmsr_extract(frame: pd.DataFrame, *, expected_matches: int = 96) -> pd.DataFrame:
    """Return a normalized extract after enforcing the 96-match census contract."""

    if missing := sorted(PMSR_EXTRACT_COLUMNS - set(frame.columns)):
        raise SourceError(f"PMSR extraction missing columns: {', '.join(missing)}")
    cleaned = frame.copy()
    cleaned["match_number"] = pd.to_numeric(cleaned["match_number"], errors="coerce")
    cleaned["penalties_awarded"] = pd.to_numeric(cleaned["penalties_awarded"], errors="coerce")
    if cleaned[["match_number", "penalties_awarded"]].isna().any().any():
        raise SourceError("PMSR extraction contains non-numeric match or penalty values.")
    cleaned["match_number"] = cleaned["match_number"].astype(int)
    cleaned["penalties_awarded"] = cleaned["penalties_awarded"].astype(int)
    cleaned["team"] = cleaned["team"].astype(str).str.strip()
    cleaned["source_url"] = cleaned["source_url"].map(normalize_source_url)
    if (cleaned["penalties_awarded"] < 0).any():
        raise SourceError("PMSR penalties_awarded cannot be negative.")
    expected_ids = set(range(1, expected_matches + 1))
    actual_ids = set(cleaned["match_number"])
    if actual_ids != expected_ids:
        raise SourceError(
            f"PMSR match coverage mismatch: missing={sorted(expected_ids - actual_ids)}, "
            f"unexpected={sorted(actual_ids - expected_ids)}"
        )
    if cleaned.duplicated(["match_number", "team"]).any():
        raise SourceError("PMSR extraction contains duplicate match/team rows.")
    invalid_sizes = cleaned.groupby("match_number").size().loc[lambda values: values.ne(2)]
    if not invalid_sizes.empty:
        raise SourceError(f"Every PMSR match needs exactly two team rows: {invalid_sizes.to_dict()}")
    return cleaned.sort_values(["match_number", "team"], kind="stable").reset_index(drop=True)


def aggregate_team_penalties(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a validated match-team extraction into one row per 2026 team."""

    cleaned = validate_pmsr_extract(frame)
    result = (
        cleaned.groupby("team", sort=True)
        .agg(
            matches_played=("match_number", "nunique"),
            penalties_awarded=("penalties_awarded", "sum"),
        )
        .reset_index()
        .rename(columns={"team": "team_name"})
    )
    result.insert(0, "year", 2026)
    result.insert(0, "tournament_name", "2026 FIFA World Cup")
    result["penalties_awarded_per_match"] = result["penalties_awarded"] / result["matches_played"]
    return result
