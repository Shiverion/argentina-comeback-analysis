"""Build leakage-safe pre-match team strength from a pinned yearly Elo source."""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

import pandas as pd

from research_etl.sources import SourceError


def build_pre_match_strength(
    matches: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    aliases: dict[str, str] | None = None,
    source_name: str,
) -> pd.DataFrame:
    """Assign each World Cup team the latest year-end rating strictly before kickoff year."""

    aliases = aliases or {}
    required_matches = {
        "match_id", "tournament_name", "match_date", "home_team_name", "away_team_name"
    }
    required_ratings = {"year", "team", "rating"}
    if missing := sorted(required_matches - set(matches.columns)):
        raise SourceError(f"Historical matches missing strength join columns: {', '.join(missing)}")
    if missing := sorted(required_ratings - set(ratings.columns)):
        raise SourceError(f"Elo source missing columns: {', '.join(missing)}")

    mask = matches["tournament_name"].astype(str).str.contains(
        r"FIFA.*World Cup", case=False, na=False, regex=True
    )
    mask &= ~matches["tournament_name"].astype(str).str.contains("Women", case=False, na=False)
    roster = matches.loc[mask].copy()
    roster["match_id"] = roster["match_id"].astype(str)
    roster["match_date"] = pd.to_datetime(roster["match_date"], errors="coerce")
    if roster["match_date"].isna().any():
        raise SourceError("Every historical match needs a valid match_date for strength leakage checks.")

    source = ratings.copy()
    source["year"] = pd.to_numeric(source["year"], errors="coerce")
    source["rating"] = pd.to_numeric(source["rating"], errors="coerce")
    source["team"] = source["team"].astype(str)
    if source[["year", "rating"]].isna().any().any():
        raise SourceError("Elo source contains non-numeric year or rating values.")
    source["year"] = source["year"].astype(int)
    if source.duplicated(["team", "year"]).any():
        raise SourceError("Elo source contains duplicate team/year rows.")

    lookup: dict[str, tuple[list[int], dict[int, float]]] = {}
    for team, group in source.groupby("team", sort=False):
        ordered = group.sort_values("year", kind="stable")
        years = ordered["year"].astype(int).tolist()
        lookup[str(team)] = (years, dict(zip(years, ordered["rating"].astype(float))))

    output: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for match in roster.sort_values(["match_date", "match_id"], kind="stable").itertuples(index=False):
        match_year = int(match.match_date.year)
        for team in (str(match.home_team_name), str(match.away_team_name)):
            source_team = aliases.get(team, team)
            if source_team not in lookup:
                unresolved.append({"match_id": match.match_id, "team": team, "reason": "team_not_found"})
                continue
            years, values = lookup[source_team]
            position = bisect_left(years, match_year) - 1
            if position < 0:
                unresolved.append({"match_id": match.match_id, "team": team, "reason": "no_prior_year"})
                continue
            rating_year = years[position]
            output.append(
                {
                    "match_id": str(match.match_id),
                    "team": team,
                    "elo_rating": values[rating_year],
                    "fifa_rank": pd.NA,
                    "pre_match_win_odds": pd.NA,
                    "source_name": source_name,
                    "as_of_date": f"{rating_year}-12-31",
                }
            )

    if unresolved:
        raise SourceError(
            "Could not resolve every historical team to a prior-year Elo rating. "
            f"First unresolved rows: {unresolved[:10]}"
        )
    return pd.DataFrame(output)
