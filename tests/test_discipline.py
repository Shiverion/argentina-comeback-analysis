from __future__ import annotations

import unittest

import pandas as pd

from research_etl.discipline import percentile_rank, team_history, team_tournament_discipline, wilson_interval


def _matches():
    rows = [
        {"match_id": "1", "tournament_name": "1990 FIFA Men's World Cup", "match_date": "1990-06-08",
         "home_team_name": "Alpha", "away_team_name": "Beta"},
        {"match_id": "2", "tournament_name": "1990 FIFA Men's World Cup", "match_date": "1990-06-12",
         "home_team_name": "Alpha", "away_team_name": "Gamma"},
        {"match_id": "3", "tournament_name": "1990 FIFA Men's World Cup", "match_date": "1990-06-16",
         "home_team_name": "Beta", "away_team_name": "Gamma"},
        {"match_id": "4", "tournament_name": "1990 FIFA Women's World Cup", "match_date": "1990-06-20",
         "home_team_name": "Alpha", "away_team_name": "Beta"},
    ]
    return pd.DataFrame(rows)


def _goals():
    mwc = "1990 FIFA Men" + chr(39) + "s World Cup"
    rows = [
        {"match_id": "1", "tournament_name": mwc, "team_name": "Alpha", "penalty": 1},
        {"match_id": "1", "tournament_name": mwc, "team_name": "Alpha", "penalty": 0},
        {"match_id": "2", "tournament_name": mwc, "team_name": "Gamma", "penalty": 0},
        {"match_id": "4", "tournament_name": "1990 FIFA Women" + chr(39) + "s World Cup", "team_name": "Alpha", "penalty": 1},
    ]
    return pd.DataFrame(rows)


def _bookings():
    mwc = "1990 FIFA Men" + chr(39) + "s World Cup"
    rows = [
        {"match_id": "1", "tournament_name": mwc, "team_name": "Beta", "yellow_card": 1, "red_card": 0, "second_yellow_card": 0, "sending_off": 0},
        {"match_id": "1", "tournament_name": mwc, "team_name": "Beta", "yellow_card": 1, "red_card": 0, "second_yellow_card": 0, "sending_off": 0},
        {"match_id": "2", "tournament_name": mwc, "team_name": "Alpha", "yellow_card": 0, "red_card": 1, "second_yellow_card": 0, "sending_off": 1},
        {"match_id": "3", "tournament_name": mwc, "team_name": "Gamma", "yellow_card": 1, "red_card": 0, "second_yellow_card": 0, "sending_off": 0},
    ]
    return pd.DataFrame(rows)


class TeamTournamentDisciplineTests(unittest.TestCase):
    def test_excludes_womens_world_cup(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        self.assertNotIn("1990 FIFA Women's World Cup", discipline["tournament_name"].tolist())

    def test_counts_matches_cards_and_penalty_goals_per_team(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        alpha = discipline.set_index("team_name").loc["Alpha"]
        self.assertEqual(alpha["matches_played"], 2)
        self.assertEqual(alpha["red_cards"], 1)
        self.assertEqual(alpha["yellow_cards"], 0)
        self.assertEqual(alpha["penalty_goals_scored"], 1)

        beta = discipline.set_index("team_name").loc["Beta"]
        self.assertEqual(beta["matches_played"], 2)
        self.assertEqual(beta["yellow_cards"], 2)

    def test_per_match_rate_divides_by_matches_played(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        gamma = discipline.set_index("team_name").loc["Gamma"]
        self.assertEqual(gamma["matches_played"], 2)
        self.assertAlmostEqual(gamma["yellow_cards_per_match"], 0.5)


class PercentileRankTests(unittest.TestCase):
    def test_top_scorer_gets_percentile_one(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        result = percentile_rank(discipline, "1990 FIFA Men's World Cup", "Alpha", "penalty_goals_scored")
        self.assertEqual(result["percentile"], 1.0)
        self.assertTrue(result["low_n_field"])

    def test_unknown_team_raises(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        with self.assertRaises(ValueError):
            percentile_rank(discipline, "1990 FIFA Men's World Cup", "Delta", "yellow_cards")

    def test_large_zero_tie_uses_average_rank(self) -> None:
        frame = pd.DataFrame(
            {
                "tournament_name": ["Cup"] * 4,
                "team_name": ["Alpha", "Beta", "Gamma", "Delta"],
                "red_cards_per_match": [0.0, 0.0, 0.0, 1.0],
            }
        )
        result = percentile_rank(frame, "Cup", "Alpha", "red_cards_per_match")
        self.assertEqual(result["tie_count"], 3)
        self.assertAlmostEqual(result["percentile"], 1 / 3)


class TeamHistoryTests(unittest.TestCase):
    def test_returns_rows_only_for_requested_team(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        history = team_history(discipline, "Alpha")
        self.assertTrue((history["team_name"] == "Alpha").all())

    def test_unknown_team_raises(self) -> None:
        discipline = team_tournament_discipline(_matches(), _goals(), _bookings())
        with self.assertRaises(ValueError):
            team_history(discipline, "Delta")


class WilsonIntervalTests(unittest.TestCase):
    def test_zero_total_returns_nan(self) -> None:
        lower, upper = wilson_interval(0, 0)
        self.assertTrue(pd.isna(lower))
        self.assertTrue(pd.isna(upper))


if __name__ == "__main__":
    unittest.main()
