import pandas as pd

from research_etl.bridge_analysis import BRIDGE_FEATURE_SETS, _fit_bridge_panel, _impact_summary


def _frame() -> pd.DataFrame:
    rows = []
    all_features = {feature for features in BRIDGE_FEATURE_SETS.values() for feature in features}
    for match in range(60):
        result = ["TEAM_LOSS", "DRAW", "TEAM_WIN"][match % 3]
        for team in ("Home", "Away"):
            for minute in (0, 60, 75, 85, 90):
                row = {
                    "match_id": str(match),
                    "team_name": team,
                    "opponent_team_name": "Away" if team == "Home" else "Home",
                    "time_bin_start_minute": minute,
                    "goal_diff_pre": -2 if minute >= 75 and result == "TEAM_LOSS" else 0,
                    "regulation_result": result if team == "Home" else ("TEAM_WIN" if result == "TEAM_LOSS" else "TEAM_LOSS" if result == "TEAM_WIN" else "DRAW"),
                }
                row.update({feature: (match % 5) / 5 for feature in all_features if feature not in row})
                row["red_cards_for_pre"] = 0
                row["red_cards_against_pre"] = 0
                row["home_indicator"] = int(team == "Home")
                rows.append(row)
    return pd.DataFrame(rows)


def test_bridge_model_reports_robustness_variants_and_counterfactuals():
    predictions, metadata = _fit_bridge_panel(_frame())
    assert len(predictions) == 600
    assert {item["variant"] for item in metadata} == {
        "state_only", "spatial_augmented", "possession_augmented", "opportunity_augmented"
    }
    assert predictions["p_team_win_scored_penalty"].between(0, 1).all()
    assert predictions["p_team_win_opponent_scored_penalty"].between(0, 1).all()


def test_penalty_impact_summary_has_late_two_goal_cohort_when_supported():
    predictions, _ = _fit_bridge_panel(_frame())
    summary = _impact_summary(predictions, panel="test", tier="club")
    assert {"mean_delta_for", "mean_delta_against", "cohort", "time_band"}.issubset(summary.columns)
    assert (summary["rows"] >= 20).all()
