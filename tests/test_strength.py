from __future__ import annotations

import unittest

import pandas as pd

from research_etl.sources import SourceError
from research_etl.strength import build_pre_match_strength


class StrengthBuildTests(unittest.TestCase):
    def test_uses_latest_strictly_prior_year_and_alias(self) -> None:
        matches = pd.DataFrame(
            [{
                "match_id": "1", "tournament_name": "2022 FIFA Men's World Cup",
                "match_date": "2022-11-20", "home_team_name": "Alpha",
                "away_team_name": "Republic of Ireland",
            }]
        )
        ratings = pd.DataFrame(
            [
                {"year": 2020, "team": "Alpha", "rating": 1500},
                {"year": 2021, "team": "Alpha", "rating": 1510},
                {"year": 2022, "team": "Alpha", "rating": 1999},
                {"year": 2021, "team": "Ireland", "rating": 1600},
            ]
        )
        result = build_pre_match_strength(
            matches, ratings, aliases={"Republic of Ireland": "Ireland"}, source_name="test"
        ).set_index("team")
        self.assertEqual(result.loc["Alpha", "elo_rating"], 1510)
        self.assertEqual(result.loc["Republic of Ireland", "elo_rating"], 1600)
        self.assertEqual(result.loc["Alpha", "as_of_date"], "2021-12-31")

    def test_rejects_team_without_prior_rating(self) -> None:
        matches = pd.DataFrame(
            [{
                "match_id": "1", "tournament_name": "2022 FIFA Men's World Cup",
                "match_date": "2022-11-20", "home_team_name": "Alpha", "away_team_name": "Beta",
            }]
        )
        ratings = pd.DataFrame([{"year": 2021, "team": "Alpha", "rating": 1500}])
        with self.assertRaises(SourceError):
            build_pre_match_strength(matches, ratings, source_name="test")
