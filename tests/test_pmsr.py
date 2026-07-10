from __future__ import annotations

import unittest

import pandas as pd

from research_etl.pmsr import aggregate_team_penalties, normalize_source_url, validate_pmsr_extract


class PmsrTests(unittest.TestCase):
    def test_normalizes_url_spaces(self) -> None:
        value = normalize_source_url("https://example.test/PMSR M01 .pdf")
        self.assertEqual(value, "https://example.test/PMSR%20M01%20.pdf")

    def test_versioned_census_is_complete_and_aggregates(self) -> None:
        raw = pd.read_csv("data/reference/pmsr_2026_set_plays_extracted.csv")
        cleaned = validate_pmsr_extract(raw)
        result = aggregate_team_penalties(cleaned)
        self.assertEqual(cleaned["match_number"].nunique(), 96)
        self.assertEqual(len(result), 48)
        self.assertEqual(int(result["matches_played"].sum()), 192)
        argentina = result.set_index("team_name").loc["Argentina"]
        self.assertEqual(int(argentina["penalties_awarded"]), 3)
        self.assertAlmostEqual(float(argentina["penalties_awarded_per_match"]), 0.6)
