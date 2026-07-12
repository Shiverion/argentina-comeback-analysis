import pandas as pd

from research_etl.opportunity_analysis import (
    clustered_spearman_interval,
    clustered_spearman_permutation,
    fit_oof_penalty_model,
)


def _frame() -> pd.DataFrame:
    rows = []
    for match in range(24):
        for team in ("Alpha", "Beta"):
            box_entries = 10 + match + (3 if team == "Alpha" else 0)
            rows.append(
                {
                    "match_id": str(match),
                    "team_name": team,
                    "box_entries": box_entries,
                    "non_penalty_xg": box_entries / 20,
                    "penalty_shots": 1 if team == "Alpha" else 0,
                }
            )
    return pd.DataFrame(rows)


def test_clustered_spearman_uses_match_clusters():
    result = clustered_spearman_interval(_frame(), x="box_entries", y="penalty_shots", cluster="match_id", replicates=100)
    assert result["rows"] == 48
    assert result["clusters"] == 24
    assert result["lower"] <= result["correlation"] <= result["upper"]


def test_oof_penalty_model_is_grouped_by_match():
    predictions, metadata = fit_oof_penalty_model(_frame(), outcome="penalty_shots", cluster="match_id")
    assert len(predictions) == 48
    assert predictions["expected_penalty_outcome_oof"].ge(0).all()
    assert metadata["matches"] == 24
    assert metadata["nonzero_outcomes"] == 24


def test_clustered_permutation_returns_reproducible_p_value():
    first = clustered_spearman_permutation(
        _frame(), x="box_entries", y="penalty_shots", cluster="match_id", replicates=200
    )
    second = clustered_spearman_permutation(
        _frame(), x="box_entries", y="penalty_shots", cluster="match_id", replicates=200
    )
    assert first == second
    assert 0 <= first["permutation_p_value"] <= 1
    assert first["method"] == "whole_cluster_permutation"
