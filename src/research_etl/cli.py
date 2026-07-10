from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_etl.analysis import run_descriptive_sensitivity, run_scenario_only_analysis
from research_etl.modeling import run_model_validation
from research_etl.paths import ProjectPaths
from research_etl.quality import validate_processed
from research_etl.sources import SourceError, extract_sources, seed_manual_inputs
from research_etl.transform import transform_sources


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argentina-egypt-etl",
        description="ETL pipeline for the Argentina-Egypt World Cup research notebook.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: current directory).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create directories and seed manual-review templates.")
    init.add_argument("--force", action="store_true", help="Replace existing manual templates with versioned seeds.")

    extract = subparsers.add_parser("extract", help="Download source files and write an extraction manifest.")
    extract.add_argument("--force", action="store_true", help="Re-download cached files.")
    extract.add_argument("--with-statsbomb", action="store_true", help="Also download StatsBomb competition and match metadata.")
    extract.add_argument(
        "--with-statsbomb-events",
        action="store_true",
        help="Also download individual StatsBomb event JSON files for the configured World Cup seasons.",
    )

    subparsers.add_parser("transform", help="Normalize raw data into notebook-ready processed artifacts.")
    subparsers.add_parser("validate", help="Run automated quality gates over processed artifacts.")
    subparsers.add_parser("analyze", help="Run configured scenario-only conditional analyses.")

    run = subparsers.add_parser("run", help="Run extract, transform, and validate in sequence.")
    run.add_argument("--force", action="store_true", help="Re-download cached files.")
    run.add_argument("--with-statsbomb", action="store_true", help="Also download StatsBomb competition and match metadata.")
    run.add_argument(
        "--with-statsbomb-events",
        action="store_true",
        help="Also download individual StatsBomb event JSON files for the configured World Cup seasons.",
    )
    subparsers.add_parser("status", help="Show the most recent ETL and model-readiness state.")
    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _validate_or_return(paths: ProjectPaths) -> int:
    report = validate_processed(paths)
    _print_json(report.to_dict())
    return 1 if report.error_count else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    paths = ProjectPaths(args.root.resolve())

    try:
        if args.command == "init":
            records = seed_manual_inputs(paths, force=args.force)
            _print_json({"status": "ready", "records": records})
            return 0

        if args.command == "extract":
            records = extract_sources(
                paths,
                include_statsbomb=args.with_statsbomb,
                include_statsbomb_events=args.with_statsbomb_events,
                force_download=args.force,
            )
            _print_json({"status": "extracted", "source_files": len(records), "records": records})
            return 0

        if args.command == "transform":
            _print_json(transform_sources(paths))
            return 0

        if args.command == "validate":
            return _validate_or_return(paths)

        if args.command == "analyze":
            _print_json(
                {
                    "scenario_only": run_scenario_only_analysis(paths),
                    "model_validation": run_model_validation(paths),
                    "descriptive_sensitivity": run_descriptive_sensitivity(paths),
                }
            )
            return 0

        if args.command == "run":
            extract_sources(
                paths,
                include_statsbomb=args.with_statsbomb,
                include_statsbomb_events=args.with_statsbomb_events,
                force_download=args.force,
            )
            manifest = transform_sources(paths)
            status = _validate_or_return(paths)
            analysis_manifest = (
                {
                    "scenario_only": run_scenario_only_analysis(paths),
                    "model_validation": run_model_validation(paths),
                    "descriptive_sensitivity": run_descriptive_sensitivity(paths),
                }
                if status == 0 else None
            )
            _print_json(
                {
                    "transform_manifest": manifest,
                    "analysis_manifest": analysis_manifest,
                    "exit_code": status,
                }
            )
            return status

        if args.command == "status":
            status_path = paths.processed_dir / "model_frame_status.json"
            run_manifest_path = paths.processed_dir / "run_manifest.json"
            payload = {
                "processed_dir": str(paths.processed_dir),
                "model_status": json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else None,
                "run_manifest": json.loads(run_manifest_path.read_text(encoding="utf-8")) if run_manifest_path.exists() else None,
            }
            _print_json(payload)
            return 0
    except SourceError as error:
        parser.error(str(error))
    return 2
