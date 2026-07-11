from __future__ import annotations

import pandas as pd

from research_etl.statsbomb_history import build_snapshots, extract_match_timeline


def _match_meta(match_id, home, away, date="2020-06-01", stage="Group Stage"):
    return {
        "match_id": match_id,
        "match_date": date,
        "home_team": {"home_team_name": home},
        "away_team": {"away_team_name": away},
        "competition_stage": {"name": stage},
    }


def _shot_goal(team, minute, second=0, event_id="e1"):
    return {
        "id": event_id,
        "period": 1 if minute <= 45 else 2,
        "minute": minute,
        "second": second,
        "team": {"name": team},
        "type": {"name": "Shot"},
        "shot": {"outcome": {"name": "Goal"}},
    }


def _own_goal_for(team, minute, second=0, event_id="og1"):
    return {
        "id": event_id,
        "period": 1 if minute <= 45 else 2,
        "minute": minute,
        "second": second,
        "team": {"name": team},
        "type": {"name": "Own Goal For"},
    }


def _red_card(team, minute, second=0, event_id="r1", via="foul", name="Red Card"):
    key = "foul_committed" if via == "foul" else "bad_behaviour"
    return {
        "id": event_id,
        "period": 1 if minute <= 45 else 2,
        "minute": minute,
        "second": second,
        "team": {"name": team},
        "type": {"name": "Foul Committed" if via == "foul" else "Bad Behaviour"},
        key: {"card": {"name": name}},
    }


def _non_goal_shot(team, minute, event_id="s1"):
    return {
        "id": event_id,
        "period": 1,
        "minute": minute,
        "second": 0,
        "team": {"name": team},
        "type": {"name": "Shot"},
        "shot": {"outcome": {"name": "Saved"}},
    }


def test_extract_match_timeline_reconstructs_scoreline():
    meta = _match_meta("M1", "Home FC", "Away FC")
    events = [
        _shot_goal("Away FC", 10, event_id="e1"),
        _non_goal_shot("Home FC", 20, event_id="s1"),
        _own_goal_for("Home FC", 55, event_id="og1"),
        _shot_goal("Home FC", 80, event_id="e2"),
    ]
    rows = extract_match_timeline(meta, events, tournament="Test League", tier="club")
    assert [r["event_type"] for r in rows] == ["GOAL", "GOAL", "GOAL"]
    assert rows[-1]["home_score"] == 2
    assert rows[-1]["away_score"] == 1
    assert rows[0]["elapsed_seconds"] == 600
    assert all(r["competition_tier"] == "club" for r in rows)
    assert all(r["is_neutral"] is False for r in rows)


def test_extract_match_timeline_counts_red_and_second_yellow():
    meta = _match_meta("M2", "Home FC", "Away FC")
    events = [
        _red_card("Away FC", 30, event_id="r1", via="foul", name="Red Card"),
        _red_card("Home FC", 60, event_id="r2", via="bad_behaviour", name="Second Yellow"),
        _red_card("Away FC", 70, event_id="y1", via="foul", name="Yellow Card"),
    ]
    rows = extract_match_timeline(meta, events, tournament="Test League", tier="intl")
    assert len(rows) == 2  # the plain Yellow Card is not counted
    assert rows[0]["away_red_cards"] == 1 and rows[0]["home_red_cards"] == 0
    assert rows[1]["home_red_cards"] == 1 and rows[1]["away_red_cards"] == 1
    assert all(r["is_neutral"] is True for r in rows)


def test_extract_match_timeline_ignores_extra_time():
    meta = _match_meta("M3", "Home FC", "Away FC")
    events = [
        {
            "id": "e_et",
            "period": 3,
            "minute": 100,
            "second": 0,
            "team": {"name": "Home FC"},
            "type": {"name": "Shot"},
            "shot": {"outcome": {"name": "Goal"}},
        },
        _shot_goal("Home FC", 10, event_id="e1"),
    ]
    rows = extract_match_timeline(meta, events, tournament="Test League", tier="club")
    assert len(rows) == 1
    assert rows[0]["elapsed_seconds"] == 600


def test_build_snapshots_trailing_perspective():
    events_df = pd.DataFrame(
        extract_match_timeline(
            _match_meta("M4", "Home FC", "Away FC"),
            [
                _shot_goal("Away FC", 10, event_id="e1"),
                _shot_goal("Away FC", 20, event_id="e2"),
                _shot_goal("Home FC", 85, event_id="e3"),
            ],
            tournament="Test League",
            tier="club",
        )
    )
    matches_meta = [
        {
            **_match_meta("M4", "Home FC", "Away FC"),
            "_tournament": "Test League",
            "_year": 2020,
            "_tier": "club",
        }
    ]
    snapshots = build_snapshots(events_df, matches_meta, thresholds=[70, 80])
    row70 = snapshots.loc[snapshots.threshold_minute.eq(70)].iloc[0]
    assert row70.trailing_team == "Home FC"
    assert row70.goal_difference == -2
    assert row70.regulation_result == "TRAILING_TEAM_LOSS"

    row80 = snapshots.loc[snapshots.threshold_minute.eq(80)].iloc[0]
    assert row80.goal_difference == -2
    assert row80.regulation_result == "TRAILING_TEAM_LOSS"  # only 1 goal back by full time


def test_build_snapshots_no_events_is_scoreless_draw():
    matches_meta = [
        {
            **_match_meta("M5", "Home FC", "Away FC"),
            "_tournament": "Test League",
            "_year": 2020,
            "_tier": "intl",
        }
    ]
    empty_events = pd.DataFrame(columns=["match_id", "elapsed_seconds", "home_score", "away_score", "home_red_cards", "away_red_cards"])
    snapshots = build_snapshots(empty_events, matches_meta, thresholds=[70])
    row = snapshots.iloc[0]
    assert row.regulation_result == "NOT_TRAILING"
    assert row.goal_difference == 0
