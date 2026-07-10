"""Team-level discipline statistics per World Cup edition.

Descriptive, not causal: this counts cards and scored penalties per team per
tournament from the Fjelstul World Cup Database (1930-2022, men's editions
only). It answers "is this team an outlier on this raw count, relative to
the rest of the field in the same tournament" -- it does not control for
possession, opponent quality, scoreline context, or which referee was
assigned, so an outlier reading here is a prompt for further investigation,
not evidence of bias (Project.md S4, S5.5, S8).
"""

from __future__ import annotations

from statistics import NormalDist
import math

import pandas as pd


def _mens_world_cup_matches(matches: pd.DataFrame) -> pd.DataFrame:
    mask = matches["tournament_name"].astype(str).str.contains(r"FIFA.*World Cup", case=False, na=False, regex=True)
    mask &= ~matches["tournament_name"].astype(str).str.contains("Women", case=False, na=False)
    selected = matches.loc[mask].copy()
    selected["match_id"] = selected["match_id"].astype(str)
    selected["year"] = pd.to_datetime(selected["match_date"], errors="coerce").dt.year
    return selected


def team_tournament_discipline(
    matches: pd.DataFrame, goals: pd.DataFrame, bookings: pd.DataFrame
) -> pd.DataFrame:
    """One row per (tournament, team): matches played, cards, and scored penalties.

    Cards and penalty goals are drawn straight from the source's own flags
    (`yellow_card`, `red_card`, `second_yellow_card`, `sending_off`,
    `penalty`) -- fouls, offsides, and VAR checks are not present in this
    source and are not estimated here.
    """

    wc_matches = _mens_world_cup_matches(matches)
    valid_match_ids = set(wc_matches["match_id"])

    appearances = pd.concat(
        [
            wc_matches[["match_id", "tournament_name", "year", "home_team_name"]].rename(
                columns={"home_team_name": "team_name"}
            ),
            wc_matches[["match_id", "tournament_name", "year", "away_team_name"]].rename(
                columns={"away_team_name": "team_name"}
            ),
        ],
        ignore_index=True,
    )
    matches_played = (
        appearances.groupby(["tournament_name", "year", "team_name"])["match_id"]
        .nunique()
        .rename("matches_played")
        .reset_index()
    )

    bookings = bookings.copy()
    bookings["match_id"] = bookings["match_id"].astype(str)
    bookings = bookings.loc[bookings["match_id"].isin(valid_match_ids)]
    bookings["is_red"] = (
        bookings["red_card"].astype(bool)
        | bookings["second_yellow_card"].astype(bool)
        | bookings["sending_off"].astype(bool)
    )
    card_counts = (
        bookings.groupby(["tournament_name", "team_name"])
        .agg(yellow_cards=("yellow_card", "sum"), red_cards=("is_red", "sum"))
        .reset_index()
    )

    goals = goals.copy()
    goals["match_id"] = goals["match_id"].astype(str)
    goals = goals.loc[goals["match_id"].isin(valid_match_ids)]
    penalty_counts = (
        goals.groupby(["tournament_name", "team_name"])["penalty"]
        .sum()
        .rename("penalty_goals_scored")
        .reset_index()
    )

    frame = matches_played.merge(card_counts, on=["tournament_name", "team_name"], how="left")
    frame = frame.merge(penalty_counts, on=["tournament_name", "team_name"], how="left")
    for column in ("yellow_cards", "red_cards", "penalty_goals_scored"):
        frame[column] = frame[column].fillna(0).astype(int)

    for column in ("yellow_cards", "red_cards", "penalty_goals_scored"):
        frame[f"{column}_per_match"] = frame[column] / frame["matches_played"]

    return frame.sort_values(["year", "team_name"], kind="stable").reset_index(drop=True)


def percentile_rank(discipline: pd.DataFrame, tournament_name: str, team_name: str, metric: str) -> dict:
    """Where a team sits in one tournament's field on one per-match metric.

    Ties receive their average rank, scaled so a unique minimum is 0 and a
    unique maximum is 1. This prevents a large tied-at-zero group from being
    described as high-percentile merely because every tie was counted below
    itself. n < 8 tournaments are flagged as low-n.
    """

    field = discipline.loc[discipline["tournament_name"].eq(tournament_name)]
    if field.empty:
        raise ValueError(f"No teams found for tournament {tournament_name!r}.")
    target_rows = field.loc[field["team_name"].eq(team_name)]
    if target_rows.empty:
        raise ValueError(f"{team_name!r} did not appear in {tournament_name!r}.")
    target_value = float(target_rows.iloc[0][metric])

    values = field[metric].astype(float).to_numpy()
    less = int((values < target_value).sum())
    tied = int((values == target_value).sum())
    average_rank = less + (tied + 1) / 2
    percentile = (average_rank - 1) / (len(values) - 1) if len(values) > 1 else 0.5
    return {
        "tournament_name": tournament_name,
        "team_name": team_name,
        "metric": metric,
        "value": target_value,
        "field_size": int(len(values)),
        "field_median": float(pd.Series(values).median()),
        "percentile": percentile,
        "tie_count": tied,
        "average_rank": average_rank,
        "low_n_field": len(values) < 8,
    }


def team_history(discipline: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """A team's discipline record across every men's World Cup it has played, oldest first."""

    history = discipline.loc[discipline["team_name"].eq(team_name)].copy()
    if history.empty:
        raise ValueError(f"{team_name!r} not found in the discipline table.")
    return history.sort_values("year", kind="stable").reset_index(drop=True)


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. NaN bounds when total is 0."""

    if total == 0:
        return (float("nan"), float("nan"))
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    half_width = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return max(0.0, centre - half_width), min(1.0, centre + half_width)
