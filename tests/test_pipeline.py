from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from research_etl.paths import ProjectPaths
from research_etl.quality import validate_processed
from research_etl.sources import extract_sources, seed_manual_inputs
from research_etl.transform import build_historical_artifacts, minute_to_elapsed_seconds, transform_sources


class HistoricalTransformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matches = pd.DataFrame(
            [
                {
                    "match_id": "1",
                    "tournament_name": "FIFA World Cup",
                    "match_date": "2022-12-01",
                    "stage_name": "Group Stage",
                    "knockout_stage": False,
                    "home_team_name": "Alpha",
                    "away_team_name": "Beta",
                }
            ]
        )
        self.goals = pd.DataFrame(
            [
                {"goal_id": "g1", "match_id": "1", "team_name": "Beta", "minute_regulation": 14, "minute_stoppage": 0},
                {"goal_id": "g2", "match_id": "1", "team_name": "Beta", "minute_regulation": 66, "minute_stoppage": 0},
                {"goal_id": "g3", "match_id": "1", "team_name": "Alpha", "minute_regulation": 78, "minute_stoppage": 0},
            ]
        )
        self.bookings = pd.DataFrame(
            [
                {
                    "booking_id": "b1",
                    "match_id": "1",
                    "team_name": "Beta",
                    "minute_regulation": 74,
                    "minute_stoppage": 0,
                    "red_card": True,
                    "second_yellow_card": False,
                    "sending_off": True,
                }
            ]
        )

    def test_minute_resolution_places_event_before_threshold_end(self) -> None:
        self.assertEqual(minute_to_elapsed_seconds(70, 0), 4199)
        self.assertEqual(minute_to_elapsed_seconds(90, 1), 5459)
        self.assertIsNone(minute_to_elapsed_seconds("not a minute"))

    def test_historical_snapshots_reconstruct_score_and_red_card_state(self) -> None:
        events, snapshots, regulation = build_historical_artifacts(
            self.matches, self.goals, self.bookings, thresholds=[70, 75, 80]
        )
        self.assertEqual(events.iloc[-1]["home_score"], 1)
        self.assertEqual(events.iloc[-1]["away_score"], 2)
        at_75 = snapshots.loc[snapshots.threshold_minute.eq(75)].iloc[0]
        self.assertEqual(at_75["goal_difference"], -2)
        self.assertEqual(at_75["trailing_team"], "Alpha")
        self.assertEqual(at_75["red_card_difference"], -1)
        self.assertEqual(at_75["regulation_result"], "TRAILING_TEAM_LOSS")
        self.assertEqual(regulation.iloc[0]["home_regulation_score"], 1)


class PipelineQualityTests(unittest.TestCase):
    def test_transform_and_quality_gate_accept_reconciled_seed_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = ProjectPaths(root)
            paths.ensure_directories()
            (root / "config").mkdir(parents=True)
            paths.reference_dir.mkdir(parents=True)
            shutil.copy2(Path("config/sources.json"), root / "config" / "sources.json")

            manual = paths.raw_dir / "manual"
            pd.DataFrame(
                [
                    {
                        "match_id": "M95", "event_id": "goal_1", "period": 1, "minute": 1, "second": 0,
                        "elapsed_seconds": 60, "team": "Argentina", "event_type": "goal", "outcome": "confirmed",
                        "score_argentina": 1, "score_egypt": 0, "player": "Test", "source_url": "https://example.test",
                        "source_tier": "A", "verified": True, "notes": "test",
                    },
                    {
                        "match_id": "M95", "event_id": "goal_2", "period": 2, "minute": 2, "second": 0,
                        "elapsed_seconds": 120, "team": "Argentina", "event_type": "goal", "outcome": "confirmed",
                        "score_argentina": 2, "score_egypt": 0, "player": "Test", "source_url": "https://example.test",
                        "source_tier": "A", "verified": True, "notes": "test",
                    },
                    {
                        "match_id": "M95", "event_id": "goal_3", "period": 2, "minute": 3, "second": 0,
                        "elapsed_seconds": 180, "team": "Argentina", "event_type": "goal", "outcome": "confirmed",
                        "score_argentina": 3, "score_egypt": 0, "player": "Test", "source_url": "https://example.test",
                        "source_tier": "A", "verified": True, "notes": "test",
                    },
                    {
                        "match_id": "M95", "event_id": "goal_4", "period": 2, "minute": 4, "second": 0,
                        "elapsed_seconds": 240, "team": "Egypt", "event_type": "goal", "outcome": "confirmed",
                        "score_argentina": 3, "score_egypt": 1, "player": "Test", "source_url": "https://example.test",
                        "source_tier": "A", "verified": True, "notes": "test",
                    },
                    {
                        "match_id": "M95", "event_id": "goal_5", "period": 2, "minute": 5, "second": 0,
                        "elapsed_seconds": 300, "team": "Egypt", "event_type": "goal", "outcome": "confirmed",
                        "score_argentina": 3, "score_egypt": 2, "player": "Test", "source_url": "https://example.test",
                        "source_tier": "A", "verified": True, "notes": "test",
                    },
                ]
            ).to_csv(manual / "focal_events_reviewed.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "incident_id": "I1", "event_id": "", "elapsed_seconds": "", "claim": "test",
                        "actual_decision": "none", "alternate_decision": "none", "actual_state": "", "alternate_state": "",
                        "beneficiary_if_alternate": "", "law_reference": "", "evidence_status": "reported",
                        "source_urls": "https://example.test", "reviewer_a": "", "reviewer_b": "", "review_notes": "",
                    }
                ]
            ).to_csv(manual / "incidents_reviewed.csv", index=False)
            historical = paths.raw_dir / "fjelstul"
            pd.DataFrame(
                [
                    {
                        "match_id": "1", "tournament_name": "FIFA World Cup", "match_date": "2022-12-01",
                        "stage_name": "Group Stage", "knockout_stage": False, "home_team_name": "Alpha", "away_team_name": "Beta",
                    }
                ]
            ).to_csv(historical / "matches.csv", index=False)
            pd.DataFrame(
                [
                    {"goal_id": "g1", "match_id": "1", "team_name": "Beta", "minute_regulation": 70, "minute_stoppage": 0}
                ]
            ).to_csv(historical / "goals.csv", index=False)
            pd.DataFrame(
                columns=["booking_id", "match_id", "team_name", "minute_regulation", "minute_stoppage", "red_card", "second_yellow_card", "sending_off"]
            ).to_csv(historical / "bookings.csv", index=False)

            pd.DataFrame(
                [
                    {"year": 2021, "team": "Alpha", "rating": 1500},
                    {"year": 2021, "team": "Beta", "rating": 1600},
                ]
            ).to_csv(paths.raw_dir / "jgravier" / "ranking_soccer_1901-2023.csv", index=False)
            shutil.copy2(
                Path("data/reference/pmsr_2026_set_plays_extracted.csv"),
                paths.raw_dir / "fifa" / "pmsr_2026_set_plays_extracted.csv",
            )
            pd.DataFrame(
                [
                    {"match_id": "M95", "team": "Argentina", "elo_rating": 2100,
                     "fifa_rank": pd.NA, "pre_match_win_odds": pd.NA, "source_name": "test",
                     "as_of_date": "2026-07-06"},
                    {"match_id": "M95", "team": "Egypt", "elo_rating": 1700,
                     "fifa_rank": pd.NA, "pre_match_win_odds": pd.NA, "source_name": "test",
                     "as_of_date": "2026-07-06"},
                ]
            ).to_csv(paths.raw_dir / "focal" / "focal_pre_match_strength.csv", index=False)

            transform_sources(paths)
            report = validate_processed(paths)
            self.assertEqual(report.error_count, 0)
            self.assertEqual(report.warning_count, 2)
            manifest = json.loads((paths.processed_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["model_status"]["status"], "ready")
            self.assertEqual(manifest["model_status"]["rows"], 180)

    def test_force_download_does_not_replace_manual_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = ProjectPaths(root)
            paths.ensure_directories()
            (root / "config").mkdir(parents=True)
            paths.reference_dir.mkdir(parents=True)
            shutil.copy2(Path("config/sources.json"), root / "config" / "sources.json")
            for source in Path("data/reference").iterdir():
                if source.is_file():
                    shutil.copy2(source, paths.reference_dir / source.name)

            seed_manual_inputs(paths)
            reviewed = paths.raw_dir / "manual" / "focal_events_reviewed.csv"
            reviewed.write_text("human-reviewed-content\n", encoding="utf-8")

            fake_record = {
                "source_id": "mock", "url": "https://example.test", "path": "mock",
                "status": "downloaded", "bytes": 1, "sha256": "0" * 64,
                "retrieved_at": "2026-01-01T00:00:00+00:00",
            }
            with patch("research_etl.sources.download_file", return_value=fake_record):
                extract_sources(paths, force_download=True)

            self.assertEqual(reviewed.read_text(encoding="utf-8"), "human-reviewed-content\n")
