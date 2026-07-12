import json
import tempfile
from pathlib import Path

from research_etl.opportunity import (
    build_world_cup_features_from_raw,
    extract_statsbomb_team_match_features,
)
from research_etl.pmsr_stats import parse_pmsr_match_summary_text


def _meta() -> dict:
    return {
        "match_id": 100,
        "match_date": "2022-11-20",
        "home_team": {"home_team_id": 10, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": 20, "away_team_name": "Away FC"},
        "competition": {"competition_name": "FIFA World Cup"},
        "season": {"season_name": "2022"},
        "competition_stage": {"name": "Group Stage"},
        "referee": {"id": 99, "name": "Ref Example"},
    }


def _event(event_id: str, event_type: str, team_id: int, **payload: object) -> dict:
    return {
        "id": event_id,
        "period": 1,
        "minute": 10,
        "second": 0,
        "team": {"id": team_id, "name": "Unexpected Display Name"},
        "possession": 1 if team_id == 10 else 2,
        "possession_team": {"id": team_id, "name": "Unexpected Display Name"},
        "type": {"name": event_type},
        **payload,
    }


def test_extract_statsbomb_opportunity_features_uses_team_ids_and_definitions():
    events = [
        _event("foul-won", "Foul Won", 10, foul_won={"penalty": True}),
        _event("foul-committed", "Foul Committed", 20, foul_committed={"card": {"name": "Yellow Card"}}),
        _event("pass-box", "Pass", 10, location=[90, 40], **{"pass": {"end_location": [108, 40]}}),
        _event("carry-third", "Carry", 10, location=[60, 30], carry={"end_location": [85, 30]}),
        _event("receipt", "Ball Receipt*", 10, location=[110, 40], ball_receipt={}),
        _event(
            "shot-open-play",
            "Shot",
            10,
            location=[108, 40],
            shot={"type": {"name": "Open Play"}, "statsbomb_xg": 0.24},
        ),
        _event(
            "shot-penalty",
            "Shot",
            10,
            location=[108, 40],
            shot={"type": {"name": "Penalty"}, "statsbomb_xg": 0.76},
        ),
        _event("red", "Bad Behaviour", 20, bad_behaviour={"card": {"name": "Red Card"}}),
    ]

    rows = extract_statsbomb_team_match_features(
        _meta(), events, tournament="FIFA World Cup 2022", competition_tier="world_cup", source_version="pin"
    )
    home, away = rows
    assert home["team_name"] == "Home FC"
    assert home["penalty_fouls_won"] == 1
    assert home["fouls_suffered"] == 1
    assert home["box_entries"] == 1
    assert home["final_third_entries"] == 1
    assert home["box_receipts"] == 1
    assert home["shots_in_box"] == 2
    assert home["non_penalty_shots_in_box"] == 1
    assert home["penalty_shots"] == 1
    assert home["non_penalty_xg"] == 0.24
    assert away["fouls_committed"] == 1
    assert away["yellow_cards"] == 1
    assert away["send_offs"] == 1
    assert home["possession_sequence_share"] == 0.5
    assert away["possession_sequence_share"] == 0.5


def test_build_world_cup_features_from_raw_requires_two_rows_per_match():
    with tempfile.TemporaryDirectory() as directory:
        raw = Path(directory)
        (raw / "matches" / "43").mkdir(parents=True)
        (raw / "events").mkdir()
        (raw / "matches" / "43" / "106.json").write_text(json.dumps([_meta()]), encoding="utf-8")
        (raw / "events" / "100.json").write_text(json.dumps([]), encoding="utf-8")
        result = build_world_cup_features_from_raw(raw, competition_id=43, season_ids=[106], source_version="pin")
    assert len(result) == 2
    assert set(result["team_name"]) == {"Home FC", "Away FC"}
    assert set(result["competition_tier"]) == {"world_cup"}


def test_parse_pmsr_match_summary_preserves_contested_possession():
    text = """Match Summary - Key Statistics
Alpha Beta
Possession
Total 51.0% 7.0% 42.0% Total
2 Goals 1
1.23 xG (Expected Goals) 0.44
10 (5) Attempts at Goal (On Target) 7 (2)
500 (450) Total Passes (Complete) 400 (340)
90 % Pass Completion % 85 %
100 Completed Line Breaks 80
12 Defensive Line Breaks 8
120 Receptions in the Final Third 70
9 Crosses 4
30 Ball Progressions 20
200 (40) Defensive Pressures Applied (Direct Pressures) 300 (50)
40 Forced Turnovers 30
60 Second Balls 50
"""
    parsed = parse_pmsr_match_summary_text(text, ["Alpha", "Beta"])
    assert parsed["Alpha"]["team_possession_pct"] == 51.0
    assert parsed["Beta"]["team_possession_pct"] == 42.0
    assert parsed["Alpha"]["contested_possession_pct"] == 7.0
    assert parsed["Alpha"]["shots_on_target"] == 5
    assert parsed["Beta"]["completed_passes"] == 340
    assert parsed["Alpha"]["direct_pressures"] == 40
