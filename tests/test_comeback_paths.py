from __future__ import annotations

from research_etl.comeback_paths import classify_match_cutoff


def _meta():
    return {
        "match_id": "M-CB",
        "match_date": "2020-06-01",
        "home_team": {"home_team_name": "Home FC"},
        "away_team": {"away_team_name": "Away FC"},
        "competition_stage": {"name": "Regular Season"},
    }


def _goal(team: str, minute: int, event_id: str):
    return {
        "id": event_id,
        "period": 1 if minute <= 45 else 2,
        "minute": minute,
        "second": 0,
        "team": {"name": team},
        "type": {"name": "Shot"},
        "shot": {"outcome": {"name": "Goal"}},
    }


def _penalty(team: str, minute: int, outcome: str, event_id: str):
    return {
        "id": event_id,
        "period": 2,
        "minute": minute,
        "second": 0,
        "team": {"name": team},
        "type": {"name": "Shot"},
        "shot": {"type": {"name": "Penalty"}, "outcome": {"name": outcome}},
    }


def test_cutoff_is_strict_and_clean_comeback_counts_no_late_penalties():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _goal("Home FC", 80, "g3"),
            _goal("Home FC", 85, "g4"),
            _goal("Home FC", 90, "g5"),
            _penalty("Home FC", 78, "Saved", "p-before"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["pre_cutoff_goal_difference"] == -2
    assert row["comeback"] is True
    assert row["clean_strict"] is True
    assert row["primary_path"] == "clean_strict"


def test_late_saved_penalty_is_attempt_assisted_but_outcome_clean():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _goal("Home FC", 80, "g3"),
            _goal("Home FC", 85, "g4"),
            _goal("Home FC", 90, "g5"),
            _penalty("Home FC", 82, "Saved", "p1"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    row = rows[0]
    assert row["clean_strict"] is False
    assert row["clean_outcome"] is True
    assert row["penalty_assisted_by_own_shot"] is True
    assert row["penalty_assisted_by_own_goal"] is False
    assert row["primary_path"] == "own_penalty_attempt_no_goal"


def test_late_penalty_goal_is_distinguished_from_a_missed_attempt():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _goal("Home FC", 80, "g3"),
            _goal("Home FC", 85, "g4"),
            _goal("Home FC", 90, "g5"),
            _penalty("Home FC", 82, "Goal", "p1"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    row = rows[0]
    assert row["clean_outcome"] is False
    assert row["penalty_assisted_by_own_goal"] is True
    assert row["primary_path"] == "own_penalty_goal_assisted"


def test_recovery_path_captures_penalty_equalizer_without_requiring_a_win():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _goal("Home FC", 80, "g3"),
            _penalty("Home FC", 85, "Goal", "p1"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    row = rows[0]
    assert row["comeback"] is False  # 2-2 is a recovery, not a win.
    assert row["own_penalty_goal_while_two_down"] is False
    assert row["own_penalty_goal_as_equalizer"] is True
    assert row["equalized_by_own_penalty"] is True
    assert row["equalized_by_open_play"] is False
    assert row["reached_level_after_cutoff"] is True


def test_recovery_path_captures_penalty_reducing_two_goal_deficit():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _penalty("Home FC", 80, "Goal", "p1"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    row = rows[0]
    assert row["own_penalty_goal_while_two_down"] is True
    assert row["own_penalty_goal_while_two_or_more_down"] is True
    assert row["own_penalty_goal_as_equalizer"] is False


def test_two_penalty_shots_within_ten_minutes_are_tracked_separately_from_goals():
    rows = classify_match_cutoff(
        _meta(),
        [
            _goal("Away FC", 10, "g1"),
            _goal("Away FC", 20, "g2"),
            _penalty("Home FC", 80, "Saved", "p1"),
            _penalty("Home FC", 89, "Saved", "p2"),
        ],
        cutoff_minute=79,
        tournament="Test League",
        tier="club",
        source_version="test",
    )

    row = rows[0]
    assert row["two_own_penalty_shots_within_10m"] is True
    assert row["two_own_penalty_goals_within_10m"] is False
    assert row["minimum_gap_between_own_penalty_shots_seconds"] == 540
