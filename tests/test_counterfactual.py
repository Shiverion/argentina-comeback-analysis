from __future__ import annotations

import unittest

import pandas as pd

from research_etl.counterfactual import (
    CounterfactualState,
    check_incident_eligibility,
    continuation_probability,
    counterfactual_impact,
    estimate_scenario_win_probability,
    match_final_scores,
    penalty_branch_states,
    reconstruct_focal_states,
    scenario_timing_sensitivity,
    wilson_interval,
)


def _events():
    rows = [
        {"match_id": "A", "event_id": "e1", "elapsed_seconds": 600, "home_score": 0, "away_score": 1},
        {"match_id": "A", "event_id": "e2", "elapsed_seconds": 2400, "home_score": 0, "away_score": 2},
        {"match_id": "A", "event_id": "e3", "elapsed_seconds": 4500, "home_score": 1, "away_score": 2},
        {"match_id": "A", "event_id": "e4", "elapsed_seconds": 5100, "home_score": 2, "away_score": 2},
        {"match_id": "B", "event_id": "e1", "elapsed_seconds": 1200, "home_score": 1, "away_score": 0},
        {"match_id": "D", "event_id": "e1", "elapsed_seconds": 600, "home_score": 0, "away_score": 1},
        {"match_id": "D", "event_id": "e2", "elapsed_seconds": 2400, "home_score": 0, "away_score": 2},
        {"match_id": "D", "event_id": "e3", "elapsed_seconds": 4500, "home_score": 1, "away_score": 2},
        {"match_id": "D", "event_id": "e4", "elapsed_seconds": 4800, "home_score": 2, "away_score": 2},
        {"match_id": "D", "event_id": "e5", "elapsed_seconds": 5300, "home_score": 3, "away_score": 2},
    ]
    return pd.DataFrame(rows)


def _snapshots():
    rows = [
        {"match_id": "A", "threshold_minute": 70, "home_team": "Alpha", "away_team": "Beta"},
        {"match_id": "B", "threshold_minute": 70, "home_team": "Gamma", "away_team": "Delta"},
        {"match_id": "C", "threshold_minute": 70, "home_team": "Epsilon", "away_team": "Zeta"},
        {"match_id": "D", "threshold_minute": 70, "home_team": "Eta", "away_team": "Theta"},
    ]
    return pd.DataFrame(rows)


class MatchFinalScoresTests(unittest.TestCase):
    def test_reads_last_event_for_matches_with_goals(self) -> None:
        finals = match_final_scores(_events(), _snapshots()).set_index("match_id")
        self.assertEqual((finals.loc["A", "home_final_score"], finals.loc["A", "away_final_score"]), (2, 2))
        self.assertEqual((finals.loc["B", "home_final_score"], finals.loc["B", "away_final_score"]), (1, 0))
        self.assertEqual((finals.loc["D", "home_final_score"], finals.loc["D", "away_final_score"]), (3, 2))

    def test_scoreless_match_with_no_events_is_zero_zero(self) -> None:
        finals = match_final_scores(_events(), _snapshots()).set_index("match_id")
        self.assertEqual((finals.loc["C", "home_final_score"], finals.loc["C", "away_final_score"]), (0, 0))


class ReconstructFocalStatesTests(unittest.TestCase):
    def test_state_at_seventy_minutes_matches_expected_deficits(self) -> None:
        states = reconstruct_focal_states(_events(), _snapshots(), elapsed_seconds=4200)
        by_match = states.set_index(["match_id"]).groupby(level=0)
        alpha_row = states[(states.match_id == "A")].iloc[0]
        self.assertEqual(alpha_row.goal_difference, -2)
        self.assertEqual(alpha_row.regulation_result, "DRAW")
        eta_row = states[(states.match_id == "D")].iloc[0]
        self.assertEqual(eta_row.goal_difference, -2)
        self.assertEqual(eta_row.regulation_result, "FOCAL_WIN")

    def test_match_with_no_events_yields_zero_zero_state(self) -> None:
        states = reconstruct_focal_states(_events(), _snapshots(), elapsed_seconds=4200)
        epsilon_row = states[states.match_id == "C"].iloc[0]
        self.assertEqual(epsilon_row.goal_difference, 0)
        self.assertEqual(epsilon_row.regulation_result, "DRAW")


class ContinuationProbabilityTests(unittest.TestCase):
    def test_two_goal_deficit_at_seventy_minutes_pools_one_win_one_draw(self) -> None:
        estimate = continuation_probability(
            _events(), _snapshots(), elapsed_seconds=4200, goal_difference=-2
        )
        self.assertEqual(estimate.eligible_matches, 2)
        self.assertEqual(estimate.wins, 1)
        self.assertEqual(estimate.draws, 1)
        self.assertEqual(estimate.losses, 0)
        self.assertAlmostEqual(estimate.p_win, 0.5)

    def test_empty_denominator_returns_none_probability(self) -> None:
        estimate = continuation_probability(
            _events(), _snapshots(), elapsed_seconds=4200, goal_difference=-9
        )
        self.assertEqual(estimate.eligible_matches, 0)
        self.assertIsNone(estimate.p_win)

    def test_tied_state_reports_unique_matches_and_clustered_team_states(self) -> None:
        estimate = continuation_probability(
            _events(), _snapshots(), elapsed_seconds=4200, goal_difference=0
        )
        self.assertEqual(estimate.eligible_matches, 1)
        self.assertEqual(estimate.eligible_team_states, 2)
        self.assertEqual(estimate.interval_method, "match_cluster_bootstrap")


class PenaltyBranchTests(unittest.TestCase):
    def test_branches_weight_scored_and_missed_states(self) -> None:
        branches = penalty_branch_states(
            elapsed_seconds=4200, focal_score=0, opponent_score=1,
            beneficiary="focal", conversion_probability=0.8,
        )
        scored, missed = branches
        self.assertEqual((scored.focal_score, scored.opponent_score), (1, 1))
        self.assertAlmostEqual(scored.weight, 0.8)
        self.assertEqual((missed.focal_score, missed.opponent_score), (0, 1))
        self.assertAlmostEqual(missed.weight, 0.2)

    def test_rejects_out_of_range_conversion_probability(self) -> None:
        with self.assertRaises(ValueError):
            penalty_branch_states(
                elapsed_seconds=4200, focal_score=0, opponent_score=1,
                beneficiary="focal", conversion_probability=1.0,
            )

    def test_rejects_unknown_beneficiary(self) -> None:
        with self.assertRaises(ValueError):
            penalty_branch_states(
                elapsed_seconds=4200, focal_score=0, opponent_score=1,
                beneficiary="referee", conversion_probability=0.5,
            )


class ScenarioAndImpactTests(unittest.TestCase):
    def test_single_state_scenario_matches_continuation_probability(self) -> None:
        direct = continuation_probability(_events(), _snapshots(), elapsed_seconds=4200, goal_difference=-2)
        scenario = estimate_scenario_win_probability(
            _events(), _snapshots(),
            [CounterfactualState("alt", 4200, 0, 2)],
            scenario_id="test",
        )
        self.assertAlmostEqual(scenario.p_win, direct.p_win)

    def test_branch_weights_must_sum_to_one(self) -> None:
        with self.assertRaises(ValueError):
            estimate_scenario_win_probability(
                _events(), _snapshots(),
                [CounterfactualState("only", 4200, 0, 2, weight=0.5)],
                scenario_id="bad",
            )

    def test_counterfactual_impact_is_observed_minus_alternate(self) -> None:
        result = counterfactual_impact(
            _events(), _snapshots(),
            scenario_id="disallowed_goal",
            observed_elapsed_seconds=4200,
            observed_focal_score=1,
            observed_opponent_score=2,
            alternate_states=[CounterfactualState("alt", 4200, 0, 2)],
        )
        expected = result.observed.p_win - result.alternate.p_win
        self.assertAlmostEqual(result.impact_probability_points, expected)
        self.assertIsNotNone(result.bootstrap_lower)
        self.assertIsNotNone(result.bootstrap_upper)

    def test_scenario_timing_sensitivity_keeps_correctness_unassessed(self) -> None:
        result = scenario_timing_sensitivity(
            _events(), _snapshots(),
            scenario_id="reported_goal",
            elapsed_seconds_candidates=[3600, 3720, 4020],
            observed_focal_score=0,
            observed_opponent_score=1,
            alternate_focal_score=0,
            alternate_opponent_score=2,
        )
        self.assertEqual(result["timing_minute"].tolist(), [60.0, 62.0, 67.0])
        self.assertTrue((result["decision_correctness_status"] == "not_assessed").all())
        self.assertTrue((result["analysis_status"] == "exploratory_conditional").all())


class IncidentEligibilityTests(unittest.TestCase):
    def test_reported_status_is_not_eligible(self) -> None:
        incident = pd.Series({"incident_id": "INC_001", "evidence_status": "reported", "elapsed_seconds": 900})
        result = check_incident_eligibility(incident)
        self.assertFalse(result.eligible)

    def test_confirmed_without_timestamp_is_not_eligible(self) -> None:
        incident = pd.Series({"incident_id": "INC_001", "evidence_status": "officially_confirmed", "elapsed_seconds": None})
        result = check_incident_eligibility(incident)
        self.assertFalse(result.eligible)

    def test_confirmed_with_timestamp_is_eligible(self) -> None:
        incident = pd.Series({"incident_id": "INC_001", "evidence_status": "officially_confirmed", "elapsed_seconds": 900})
        result = check_incident_eligibility(incident)
        self.assertTrue(result.eligible)


class WilsonIntervalTests(unittest.TestCase):
    def test_zero_total_returns_nan_bounds(self) -> None:
        lower, upper = wilson_interval(0, 0)
        self.assertTrue(pd.isna(lower))
        self.assertTrue(pd.isna(upper))

    def test_bounds_contain_the_point_estimate(self) -> None:
        lower, upper = wilson_interval(5, 10)
        self.assertLessEqual(lower, 0.5)
        self.assertGreaterEqual(upper, 0.5)


if __name__ == "__main__":
    unittest.main()
