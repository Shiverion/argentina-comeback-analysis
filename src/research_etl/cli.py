from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_etl.analysis import (
    run_broader_baseline_sensitivity,
    run_descriptive_sensitivity,
    run_scenario_only_analysis,
)
from research_etl.opportunity_analysis import run_opportunity_analysis
from research_etl.bridge_analysis import run_bridge_analysis
from research_etl.comeback_counterfactual import run_comeback_counterfactual
from research_etl.comeback_paths import run_comeback_path_analysis
from research_etl.temporal_analysis import run_temporal_analysis
from research_etl.modeling import run_model_validation
from research_etl.paths import ProjectPaths
from research_etl.quality import validate_processed
from research_etl.sources import SourceError, extract_sources, seed_manual_inputs
from research_etl.transform import build_opportunity_artifacts, transform_sources


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
    extract.add_argument(
        "--with-statsbomb-history",
        action="store_true",
        help="Download the configured broader-baseline StatsBomb match and event streams.",
    )

    transform = subparsers.add_parser("transform", help="Normalize raw data into notebook-ready processed artifacts.")
    transform.add_argument(
        "--with-statsbomb-history",
        action="store_true",
        help="Rebuild broader-baseline processed artifacts from the cached StatsBomb event streams.",
    )
    opportunity = subparsers.add_parser(
        "opportunity",
        help="Build feature panels for the separate opportunity-adjusted officiating analysis.",
    )
    opportunity.add_argument(
        "--with-statsbomb-world-cup",
        action="store_true",
        help="Download configured 2018/2022 World Cup event feeds and build their feature panel.",
    )
    opportunity.add_argument(
        "--with-statsbomb-history",
        action="store_true",
        help="Download the selected broader StatsBomb event cache and build separate club/international panels.",
    )
    opportunity.add_argument(
        "--with-pmsr-2026",
        action="store_true",
        help="Fetch all official 2026 PMSR summaries in memory and build the 96-match feature panel.",
    )
    opportunity.add_argument(
        "--with-statsbomb-temporal",
        action="store_true",
        help="Build pre-decision five-minute StatsBomb panels and grouped hazard outputs.",
    )
    opportunity.add_argument("--all", action="store_true", help="Build every configured opportunity feature panel.")
    comeback = subparsers.add_parser(
        "comeback-path",
        help="Classify clean and penalty-assisted late comebacks from the cached StatsBomb history.",
    )
    comeback.add_argument(
        "--with-statsbomb-history",
        action="store_true",
        help="Download the configured broader StatsBomb event cache before scanning it.",
    )
    comeback.add_argument(
        "--with-counterfactual",
        action="store_true",
        help="Also build the fixed-score and adaptive-support Egypt counterfactual outputs.",
    )
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
    run.add_argument(
        "--with-statsbomb-history",
        action="store_true",
        help="Download and rebuild the configured broader-baseline StatsBomb artifacts.",
    )
    subparsers.add_parser("status", help="Show the most recent ETL and model-readiness state.")
    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _validate_or_return(paths: ProjectPaths) -> int:
    report = validate_processed(paths)
    _print_json(report.to_dict())
    return 1 if report.error_count else 0


def _try_broader_baseline(paths: ProjectPaths) -> dict:
    """Optional: only runs once data/processed/statsbomb_historical_*.csv exist."""

    try:
        return run_broader_baseline_sensitivity(paths)
    except SourceError as error:
        return {"status": "pending", "reason": str(error)}


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
                include_statsbomb_history=args.with_statsbomb_history,
                force_download=args.force,
            )
            _print_json({"status": "extracted", "source_files": len(records), "records": records})
            return 0

        if args.command == "transform":
            _print_json(transform_sources(paths, rebuild_statsbomb_history=args.with_statsbomb_history))
            return 0

        if args.command == "opportunity":
            build_world_features = bool(args.with_statsbomb_world_cup or args.all)
            build_history_features = bool(args.with_statsbomb_history or args.all)
            include_world_cup = build_world_features
            include_history = build_history_features
            include_pmsr = bool(args.with_pmsr_2026 or args.all)
            include_temporal = bool(args.with_statsbomb_temporal or args.all)
            if not any((include_world_cup, include_history, include_pmsr, include_temporal)):
                parser.error("opportunity requires at least one source flag or --all.")
            if include_temporal:
                include_world_cup = True
                include_history = True
            source_records = []
            if include_world_cup or include_history:
                source_records = extract_sources(
                    paths,
                    include_statsbomb=include_world_cup,
                    include_statsbomb_events=include_world_cup,
                    include_statsbomb_history=include_history,
                )
            manifest = build_opportunity_artifacts(
                paths,
                build_statsbomb_world_cup=build_world_features,
                build_statsbomb_history=build_history_features,
                build_pmsr_2026=include_pmsr,
                build_statsbomb_temporal=include_temporal,
            )
            analysis_manifest = run_opportunity_analysis(paths) if any((build_world_features, build_history_features, include_pmsr)) else None
            temporal_manifest = run_temporal_analysis(paths) if include_temporal else None
            bridge_manifest = run_bridge_analysis(paths) if include_temporal else None
            path_manifest = run_comeback_path_analysis(paths) if include_history else None
            dynamic_manifest = run_comeback_counterfactual(paths) if include_temporal else None
            status = _validate_or_return(paths)
            _print_json(
                {
                    "source_files": len(source_records),
                    "opportunity_manifest": manifest,
                    "analysis_manifest": analysis_manifest,
                    "temporal_manifest": temporal_manifest,
                    "bridge_manifest": bridge_manifest,
                    "comeback_path_manifest": path_manifest,
                    "comeback_counterfactual_manifest": dynamic_manifest,
                    "exit_code": status,
                }
            )
            return status

        if args.command == "comeback-path":
            source_records = []
            if args.with_statsbomb_history:
                source_records = extract_sources(paths, include_statsbomb_history=True)
            path_manifest = run_comeback_path_analysis(paths)
            dynamic_manifest = run_comeback_counterfactual(paths) if args.with_counterfactual else None
            _print_json(
                {
                    "source_files": len(source_records),
                    "comeback_path_manifest": path_manifest,
                    "comeback_counterfactual_manifest": dynamic_manifest,
                }
            )
            return 0

        if args.command == "validate":
            return _validate_or_return(paths)

        if args.command == "analyze":
            _print_json(
                {
                    "scenario_only": run_scenario_only_analysis(paths),
                    "model_validation": run_model_validation(paths),
                    "descriptive_sensitivity": run_descriptive_sensitivity(paths),
                    "broader_baseline_sensitivity": _try_broader_baseline(paths),
                }
            )
            return 0

        if args.command == "run":
            extract_sources(
                paths,
                include_statsbomb=args.with_statsbomb,
                include_statsbomb_events=args.with_statsbomb_events,
                include_statsbomb_history=args.with_statsbomb_history,
                force_download=args.force,
            )
            manifest = transform_sources(paths, rebuild_statsbomb_history=args.with_statsbomb_history)
            status = _validate_or_return(paths)
            analysis_manifest = (
                {
                    "scenario_only": run_scenario_only_analysis(paths),
                    "model_validation": run_model_validation(paths),
                    "descriptive_sensitivity": run_descriptive_sensitivity(paths),
                    "broader_baseline_sensitivity": _try_broader_baseline(paths),
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
