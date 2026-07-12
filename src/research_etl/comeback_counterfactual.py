"""Linked fixed-score and adaptive-support counterfactual outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research_etl.counterfactual import wilson_interval
from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, sha256_file, write_json_atomic
from research_etl.transform import write_csv_atomic


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _bridge_rows(path: Path, *, state: int, minimum_minute: int, maximum_minute: int) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "match_id", "time_bin_start_minute", "goal_diff_pre", "regulation_result",
        "p_team_win_observed", "p_team_win_opponent_scored_penalty",
    }
    missing = required - set(frame.columns)
    if missing:
        raise SourceError(f"Bridge prediction file {path} is missing: {', '.join(sorted(missing))}")
    return frame.loc[
        frame["goal_diff_pre"].eq(state)
        & frame["time_bin_start_minute"].between(minimum_minute, maximum_minute)
    ].copy()


def run_comeback_counterfactual(paths: ProjectPaths) -> dict[str, Any]:
    """Write a transparent 0-3 score branch and a low-support adaptive branch.

    The fixed branch changes only the score state in an out-of-fold bridge
    model.  The adaptive branch does not invent tactical behavior: it reports
    the empirical support and a Wilson upper bound for real three-goal-deficit
    states in the same pre-window range.
    """

    rows: list[dict[str, Any]] = []
    bridge_files = [
        ("world_cup", paths.results_dir / "bridge_statsbomb_world_cup_oof_predictions.csv"),
        ("club", paths.results_dir / "bridge_statsbomb_club_oof_predictions.csv"),
        ("intl", paths.results_dir / "bridge_statsbomb_intl_oof_predictions.csv"),
    ]
    for tier, path in bridge_files:
        if not path.exists():
            continue
        fixed = _bridge_rows(path, state=-2, minimum_minute=60, maximum_minute=70)
        if not fixed.empty:
            rows.append(
                {
                    "branch": "fixed_score_0_3",
                    "tier": tier,
                    "window_minutes": "60-70",
                    "state_before": -2,
                    "state_after": -3,
                    "support_rows": int(len(fixed)),
                    "support_matches": int(fixed["match_id"].nunique()),
                    "observed_win_rate": float(fixed["p_team_win_observed"].mean()),
                    "counterfactual_win_rate": float(fixed["p_team_win_opponent_scored_penalty"].mean()),
                    "delta_percentage_points": float(
                        (fixed["p_team_win_opponent_scored_penalty"] - fixed["p_team_win_observed"]).mean() * 100
                    ),
                    "observed_wins": "model prediction",
                    "status": "modelled_score_state_sensitivity",
                    "interpretation": "Out-of-fold model changes the score state by one goal; it does not simulate tactical adaptation.",
                }
            )

        adaptive = _bridge_rows(path, state=-3, minimum_minute=50, maximum_minute=70)
        if adaptive.empty:
            continue
        match_results = adaptive[["match_id", "regulation_result"]].drop_duplicates("match_id")
        wins = int(match_results["regulation_result"].eq("TEAM_WIN").sum())
        matches = int(len(match_results))
        lower, upper = wilson_interval(wins, matches)
        rows.append(
            {
                "branch": "adaptive_historical_support",
                "tier": tier,
                "window_minutes": "50-70",
                "state_before": -3,
                "state_after": -3,
                "support_rows": int(len(adaptive)),
                "support_matches": matches,
                "observed_win_rate": float(wins / matches) if matches else 0.0,
                "counterfactual_win_rate": None,
                "delta_percentage_points": None,
                "observed_wins": wins,
                "wilson_lower": lower,
                "wilson_upper": upper,
                "status": "low_support_extrapolative",
                "interpretation": "Historical three-goal-deficit support is reported as evidence, not as a precise adaptive probability.",
            }
        )

    if not rows:
        raise SourceError("No bridge prediction files were available for the comeback counterfactual.")
    output = pd.DataFrame(rows)
    path = paths.results_dir / "comeback_counterfactual.csv"
    write_csv_atomic(output, path)
    manifest = {
        "pipeline": "research_etl.comeback_counterfactual",
        "created_at": _utc_now(),
        "status": "ready",
        "focal_question": "Could Argentina still come back if Egypt's disallowed goal had stood and the later 66-minute goal made the state 0-3?",
        "branches": {
            "fixed_score_0_3": "Mechanically changes a real 0-2 pre-window state to 0-3 in an out-of-fold model.",
            "adaptive_historical_support": "Reports actual three-goal-deficit matches and Wilson uncertainty; does not claim the future would be unchanged.",
        },
        "important_limit": "A dynamic tactical response to an alternate goal is not identifiable from one focal match and sparse historical three-goal-deficit wins.",
        "artifacts": [{"path": str(path.relative_to(paths.root)).replace("\\", "/"), "rows": int(len(output)), "sha256": sha256_file(path)}],
    }
    manifest_path = paths.results_dir / "comeback_counterfactual_manifest.json"
    write_json_atomic(manifest, manifest_path)
    return manifest

