from research_etl.temporal import extract_temporal_match_features


def _meta():
    return {
        "match_id": "T1",
        "match_date": "2024-01-01",
        "home_team": {"home_team_id": 1, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": 2, "away_team_name": "Away FC"},
        "competition_stage": {"name": "Group Stage"},
    }


def test_temporal_features_use_only_events_before_window():
    events = [
        {
            "id": "goal",
            "period": 1,
            "minute": 1,
            "second": 0,
            "team": {"id": 2, "name": "Away"},
            "type": {"name": "Shot"},
            "shot": {"outcome": {"name": "Goal"}, "type": {"name": "Open Play"}},
        },
        {
            "id": "pass-at-boundary",
            "period": 1,
            "minute": 45,
            "second": 0,
            "team": {"id": 1, "name": "Home"},
            "type": {"name": "Pass"},
            "location": [90, 30],
            "pass": {"end_location": [104, 30]},
        },
        {
            "id": "penalty",
            "period": 2,
            "minute": 1,
            "second": 0,
            "team": {"id": 1, "name": "Home"},
            "type": {"name": "Shot"},
            "location": [105, 34],
            "shot": {"type": {"name": "Penalty"}, "outcome": {"name": "Saved"}},
        },
    ]
    frame = extract_temporal_match_features(
        _meta(), events, tournament="Test", competition_tier="club", source_version="test"
    )
    home = [row for row in frame if row["team_name"] == "Home FC" and row["time_bin_start_minute"] == 45][0]
    assert home["goals_against_pre"] == 1
    assert home["regulation_home_score"] == 0
    assert home["regulation_away_score"] == 1
    assert home["box_entries_prev_5m"] == 0  # event at exactly minute 45 is not pre-window
    assert home["penalty_shots_next_5m"] == 1
    assert home["penalty_event_next_5m"] == 1


def test_temporal_features_create_two_team_rows_per_window():
    frame = extract_temporal_match_features(
        _meta(), [], tournament="Test", competition_tier="intl", source_version="test"
    )
    assert len(frame) == 36
    assert {(row["team_name"], row["home_or_away"]) for row in frame[:2]} == {
        ("Home FC", "home"),
        ("Away FC", "away"),
    }
