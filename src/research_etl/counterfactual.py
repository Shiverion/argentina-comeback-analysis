"""Stage D: incident-level counterfactual simulation (Project.md S7.4).

A validated scenario starts at the incident elapsed time, changes only the
state implied by the alternate decision, and reads the continuation off
historical matches that passed through a comparable state -- it never
replays the goals Argentina scored later in the match (Project.md S4, S7.4).

This module implements the "comparable historical states" branch of S7.4
(the nonparametric alternative to a fitted scoring model). It remains
independent from the calibrated Stage C model and can therefore provide an
explicitly conditional scenario-only sensitivity without a correctness verdict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd

FocalOutcome = Literal["FOCAL_WIN", "DRAW", "FOCAL_LOSS"]


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. NaN bounds when total is 0."""

    if total == 0:
        return (float("nan"), float("nan"))
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    half_width = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def _match_roster(historical_snapshots: pd.DataFrame) -> pd.DataFrame:
    """One row per match_id with home/away teams, deduplicated across thresholds."""

    return (
        historical_snapshots.sort_values(["match_id", "threshold_minute"], kind="stable")
        .drop_duplicates("match_id")[["match_id", "home_team", "away_team"]]
        .reset_index(drop=True)
    )


def match_final_scores(historical_events: pd.DataFrame, historical_snapshots: pd.DataFrame) -> pd.DataFrame:
    """Regulation full-time home/away score for every historical match.

    Derived from the last event recorded for each match. A match with zero
    rows in historical_events (no goals, no red cards) is a scoreless 0-0
    draw, not a missing observation -- it is filled in from the snapshot
    roster, which covers every match regardless of event count.
    """

    roster = _match_roster(historical_snapshots)
    if historical_events.empty:
        finals = roster.copy()
        finals["home_final_score"] = 0
        finals["away_final_score"] = 0
        return finals

    last_event = (
        historical_events.sort_values(["match_id", "elapsed_seconds", "event_id"], kind="stable")
        .groupby("match_id", sort=False)
        .last()[["home_score", "away_score"]]
        .rename(columns={"home_score": "home_final_score", "away_score": "away_final_score"})
        .reset_index()
    )
    finals = roster.merge(last_event, on="match_id", how="left")
    finals[["home_final_score", "away_final_score"]] = finals[["home_final_score", "away_final_score"]].fillna(0).astype(int)
    return finals


def reconstruct_focal_states(
    historical_events: pd.DataFrame,
    historical_snapshots: pd.DataFrame,
    *,
    elapsed_seconds: int,
) -> pd.DataFrame:
    """Focal-team-perspective state and final result for every historical match at a fixed time.

    Each historical match contributes two focal-perspective rows (once as the
    home team, once as the away team) so a model built from this table can
    learn from both team perspectives without pretending a past team was
    Argentina or Egypt (mirrors build_model_frame conventions in transform.py).
    """

    finals = match_final_scores(historical_events, historical_snapshots)
    if historical_events.empty:
        at_time = finals[["match_id"]].copy()
        at_time["home_score"] = 0
        at_time["away_score"] = 0
    else:
        prior = historical_events.loc[historical_events["elapsed_seconds"] <= elapsed_seconds]
        at_time = (
            prior.sort_values(["match_id", "elapsed_seconds", "event_id"], kind="stable")
            .groupby("match_id", sort=False)
            .last()[["home_score", "away_score"]]
            .reset_index()
        )
        missing = finals.loc[~finals["match_id"].isin(at_time["match_id"]), ["match_id"]].copy()
        if not missing.empty:
            missing["home_score"] = 0
            missing["away_score"] = 0
            at_time = pd.concat([at_time, missing], ignore_index=True)

    frame = finals.merge(at_time, on="match_id", how="left")
    frame[["home_score", "away_score"]] = frame[["home_score", "away_score"]].fillna(0).astype(int)

    rows = []
    for row in frame.itertuples(index=False):
        for focal_side, focal_score, opponent_score, final_focal, final_opponent in (
            ("home", row.home_score, row.away_score, row.home_final_score, row.away_final_score),
            ("away", row.away_score, row.home_score, row.away_final_score, row.home_final_score),
        ):
            if final_focal > final_opponent:
                result = "FOCAL_WIN"
            elif final_focal == final_opponent:
                result = "DRAW"
            else:
                result = "FOCAL_LOSS"
            rows.append(
                {
                    "match_id": row.match_id,
                    "focal_side": focal_side,
                    "elapsed_seconds": elapsed_seconds,
                    "goal_difference": focal_score - opponent_score,
                    "regulation_result": result,
                }
            )
    return pd.DataFrame(rows)


class ContinuationEstimate:
    def __init__(
        self, elapsed_seconds, goal_difference, eligible_matches, eligible_team_states,
        wins, draws, losses, p_win, interval_lower, interval_upper, interval_method,
    ):
        self.elapsed_seconds = elapsed_seconds
        self.goal_difference = goal_difference
        self.eligible_matches = eligible_matches
        self.eligible_team_states = eligible_team_states
        self.wins = wins
        self.draws = draws
        self.losses = losses
        self.p_win = p_win
        self.interval_lower = interval_lower
        self.interval_upper = interval_upper
        self.interval_method = interval_method
        # Backward-compatible aliases for existing notebook cells.
        self.wilson_lower = interval_lower
        self.wilson_upper = interval_upper

    def to_dict(self):
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "goal_difference": self.goal_difference,
            "eligible_matches": self.eligible_matches,
            "eligible_team_states": self.eligible_team_states,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "p_win": self.p_win,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "interval_method": self.interval_method,
        }


def _cluster_bootstrap_interval(
    eligible: pd.DataFrame,
    *,
    confidence: float = 0.95,
    resamples: int = 4_000,
    random_seed: int = 20260707,
) -> tuple[float | None, float | None]:
    """Bootstrap team-state win share while resampling whole historical matches."""

    if eligible.empty:
        return None, None
    match_values = (
        eligible.assign(_win=eligible["regulation_result"].eq("FOCAL_WIN").astype(float))
        .groupby("match_id", sort=False)["_win"]
        .mean()
        .to_numpy()
    )
    if len(match_values) == 1:
        point = float(match_values[0])
        return point, point
    rng = np.random.default_rng(random_seed)
    sampled = rng.choice(match_values, size=(resamples, len(match_values)), replace=True).mean(axis=1)
    alpha = (1 - confidence) / 2
    return float(np.quantile(sampled, alpha)), float(np.quantile(sampled, 1 - alpha))


def continuation_probability(
    historical_events,
    historical_snapshots,
    *,
    elapsed_seconds,
    goal_difference,
    elapsed_seconds_window=0,
):
    """Empirical P(focal-team regulation win | comparable historical state).

    Comparable means the same focal-team goal difference at the same elapsed
    time. At a tied state both home and away perspectives are valid team states;
    they are reported separately but uncertainty is clustered by match.
    """

    if elapsed_seconds_window <= 0:
        states = reconstruct_focal_states(historical_events, historical_snapshots, elapsed_seconds=elapsed_seconds)
        eligible = states.loc[states["goal_difference"].eq(goal_difference)]
    else:
        offsets = range(-elapsed_seconds_window, elapsed_seconds_window + 1)
        collected = []
        for offset in offsets:
            target = max(0, elapsed_seconds + offset)
            states = reconstruct_focal_states(historical_events, historical_snapshots, elapsed_seconds=target)
            selected = states.loc[states["goal_difference"].eq(goal_difference)].copy()
            selected["distance_seconds"] = abs(offset)
            collected.append(selected)
        eligible = (
            pd.concat(collected, ignore_index=True)
            .sort_values(["distance_seconds", "match_id", "focal_side"], kind="stable")
            .drop_duplicates(["match_id", "focal_side"])
            if collected else pd.DataFrame()
        )

    team_states = int(len(eligible))
    unique_matches = int(eligible["match_id"].nunique()) if team_states else 0
    wins = int(eligible["regulation_result"].eq("FOCAL_WIN").sum()) if team_states else 0
    draws = int(eligible["regulation_result"].eq("DRAW").sum()) if team_states else 0
    losses = int(eligible["regulation_result"].eq("FOCAL_LOSS").sum()) if team_states else 0
    p_win = wins / team_states if team_states else None
    if not team_states:
        lower, upper, method = None, None, "none"
    elif team_states == unique_matches:
        lower, upper = wilson_interval(wins, team_states)
        method = "wilson_match_level"
    else:
        lower, upper = _cluster_bootstrap_interval(eligible)
        method = "match_cluster_bootstrap"
    return ContinuationEstimate(
        elapsed_seconds, goal_difference, unique_matches, team_states,
        wins, draws, losses, p_win, lower, upper, method,
    )


def continuation_probability_sensitivity(
    historical_events: pd.DataFrame,
    historical_snapshots: pd.DataFrame,
    *,
    elapsed_seconds_candidates: list[int],
    goal_difference: int,
) -> list[ContinuationEstimate]:
    """Evaluate timing assumptions independently rather than pooling them."""

    return [
        continuation_probability(
            historical_events,
            historical_snapshots,
            elapsed_seconds=int(candidate),
            goal_difference=goal_difference,
        )
        for candidate in elapsed_seconds_candidates
    ]


@dataclass(frozen=True)
class CounterfactualState:
    """One branch of a scenario: a score state at a fixed time, with its probability weight."""

    label: str
    elapsed_seconds: int
    focal_score: int
    opponent_score: int
    weight: float = 1.0

    @property
    def goal_difference(self) -> int:
        return self.focal_score - self.opponent_score


def penalty_branch_states(
    *,
    elapsed_seconds,
    focal_score,
    opponent_score,
    beneficiary,
    conversion_probability,
):
    """Branch a penalty-awarded incident into scored/missed states (Project.md S7.4).

    An unvalidated or awarded-but-undecided penalty must never collapse into a
    certain goal (Project.md S4). The branch weights are the documented
    conversion probability and its complement.
    """

    if not 0 < conversion_probability < 1:
        raise ValueError("conversion_probability must be strictly between 0 and 1.")
    if beneficiary == "focal":
        scored_focal, scored_opponent = focal_score + 1, opponent_score
    elif beneficiary == "opponent":
        scored_focal, scored_opponent = focal_score, opponent_score + 1
    else:
        raise ValueError("beneficiary must be focal or opponent.")
    return [
        CounterfactualState("scored", elapsed_seconds, scored_focal, scored_opponent, weight=conversion_probability),
        CounterfactualState("missed", elapsed_seconds, focal_score, opponent_score, weight=1 - conversion_probability),
    ]


class ScenarioEstimate:
    def __init__(self, scenario_id, p_win, wilson_lower, wilson_upper, branches=None):
        self.scenario_id = scenario_id
        self.p_win = p_win
        self.wilson_lower = wilson_lower
        self.wilson_upper = wilson_upper
        self.branches = branches or []

    def to_dict(self):
        return {
            "scenario_id": self.scenario_id,
            "p_win": self.p_win,
            "wilson_lower": self.wilson_lower,
            "wilson_upper": self.wilson_upper,
            "branches": [branch.to_dict() for branch in self.branches],
        }


def estimate_scenario_win_probability(
    historical_events,
    historical_snapshots,
    states,
    *,
    scenario_id,
    elapsed_seconds_window=0,
):
    """Weight continuation_probability across a scenario branch states.

    A single-state scenario (the disallowed-goal case) is one branch with
    weight 1. A penalty scenario is two branches (scored/missed) whose
    weights must sum to 1. The Wilson bounds are reported as the weighted
    envelope across branches, not a fabricated combined-sample interval --
    branches come from overlapping historical samples, so their uncertainty
    cannot be pooled as if independent.
    """

    if not states:
        raise ValueError("A scenario needs at least one state.")
    total_weight = sum(state.weight for state in states)
    if not math.isclose(total_weight, 1.0, abs_tol=1e-9):
        raise ValueError(f"Branch weights must sum to 1.0, got {total_weight}.")

    branches = [
        continuation_probability(
            historical_events,
            historical_snapshots,
            elapsed_seconds=state.elapsed_seconds,
            goal_difference=state.goal_difference,
            elapsed_seconds_window=elapsed_seconds_window,
        )
        for state in states
    ]
    if any(branch.p_win is None for branch in branches):
        return ScenarioEstimate(scenario_id, None, None, None, branches)

    weights = [state.weight for state in states]
    p_win = sum(w * branch.p_win for w, branch in zip(weights, branches))
    lower = sum(w * branch.wilson_lower for w, branch in zip(weights, branches))
    upper = sum(w * branch.wilson_upper for w, branch in zip(weights, branches))
    return ScenarioEstimate(scenario_id, p_win, lower, upper, branches)


class IncidentEligibility:
    def __init__(self, incident_id, eligible, reason):
        self.incident_id = incident_id
        self.eligible = eligible
        self.reason = reason


PRIMARY_ELIGIBLE_STATUSES = {"video_reviewed", "officially_confirmed"}


def check_incident_eligibility(incident):
    """Gate an incident for the primary counterfactual (Project.md S5.5, S6.2, S8).

    Only a timestamped, independently reviewed incident (not merely
    reported) enters the primary estimate -- everything else stays excluded
    and visible in the ledger rather than silently defaulted.
    """

    incident_id = str(incident.get("incident_id", "unknown"))
    status = str(incident.get("evidence_status", "")).strip().lower()
    has_time = pd.notna(incident.get("elapsed_seconds"))
    if status not in PRIMARY_ELIGIBLE_STATUSES:
        reason = "evidence_status=" + repr(status) + " is not eligible for the primary counterfactual."
        return IncidentEligibility(incident_id, False, reason)
    if not has_time:
        return IncidentEligibility(incident_id, False, "missing a validated elapsed_seconds event time.")
    return IncidentEligibility(incident_id, True, "eligible")


class CounterfactualImpact:
    def __init__(
        self, scenario_id, observed, alternate, impact_probability_points,
        bootstrap_lower=None, bootstrap_upper=None,
    ):
        self.scenario_id = scenario_id
        self.observed = observed
        self.alternate = alternate
        self.impact_probability_points = impact_probability_points
        self.bootstrap_lower = bootstrap_lower
        self.bootstrap_upper = bootstrap_upper

    def to_dict(self):
        return {
            "scenario_id": self.scenario_id,
            "observed": self.observed.to_dict(),
            "alternate": self.alternate.to_dict(),
            "impact_probability_points": self.impact_probability_points,
            "bootstrap_lower": self.bootstrap_lower,
            "bootstrap_upper": self.bootstrap_upper,
        }


def _win_share_by_match(states: pd.DataFrame) -> dict[str, float]:
    if states.empty:
        return {}
    return (
        states.assign(_win=states["regulation_result"].eq("FOCAL_WIN").astype(float))
        .groupby("match_id", sort=False)["_win"]
        .mean()
        .to_dict()
    )


def _bootstrap_impact_interval(
    historical_events: pd.DataFrame,
    historical_snapshots: pd.DataFrame,
    *,
    elapsed_seconds: int,
    observed_goal_difference: int,
    alternate_states: list[CounterfactualState],
    resamples: int = 4_000,
    random_seed: int = 20260707,
) -> tuple[float | None, float | None]:
    roster = _match_roster(historical_snapshots)
    match_ids = roster["match_id"].astype(str).tolist()
    observed_rows = reconstruct_focal_states(
        historical_events, historical_snapshots, elapsed_seconds=elapsed_seconds
    )
    observed_map = _win_share_by_match(
        observed_rows.loc[observed_rows["goal_difference"].eq(observed_goal_difference)]
    )
    branch_maps = []
    for state in alternate_states:
        rows = reconstruct_focal_states(
            historical_events, historical_snapshots, elapsed_seconds=state.elapsed_seconds
        )
        branch_maps.append(
            (state.weight, _win_share_by_match(rows.loc[rows["goal_difference"].eq(state.goal_difference)]))
        )
    if not observed_map or any(not values for _, values in branch_maps):
        return None, None

    observed_values = np.array([observed_map.get(match_id, np.nan) for match_id in match_ids], dtype=float)
    branch_values = [
        (weight, np.array([values.get(match_id, np.nan) for match_id in match_ids], dtype=float))
        for weight, values in branch_maps
    ]
    rng = np.random.default_rng(random_seed)
    impacts = []
    for _ in range(resamples):
        sample = rng.integers(0, len(match_ids), size=len(match_ids))
        observed_sample = observed_values[sample]
        if np.isnan(observed_sample).all():
            continue
        alternate_probability = 0.0
        valid = True
        for weight, values in branch_values:
            branch_sample = values[sample]
            if np.isnan(branch_sample).all():
                valid = False
                break
            alternate_probability += weight * float(np.nanmean(branch_sample))
        if valid:
            impacts.append(float(np.nanmean(observed_sample)) - alternate_probability)
    if not impacts:
        return None, None
    return float(np.quantile(impacts, 0.025)), float(np.quantile(impacts, 0.975))


def counterfactual_impact(
    historical_events,
    historical_snapshots,
    *,
    scenario_id,
    observed_elapsed_seconds,
    observed_focal_score,
    observed_opponent_score,
    alternate_states,
    elapsed_seconds_window=0,
):
    """Impact_ARG = P(focal win | observed) - P(focal win | alternate) (Project.md S5.4).

    The sign describes the modelled advantage of the observed state, not the
    correctness or intention behind the decision that produced it.
    """

    observed_estimate = estimate_scenario_win_probability(
        historical_events,
        historical_snapshots,
        [CounterfactualState("observed", observed_elapsed_seconds, observed_focal_score, observed_opponent_score)],
        scenario_id=scenario_id + "::observed",
        elapsed_seconds_window=elapsed_seconds_window,
    )
    alternate_estimate = estimate_scenario_win_probability(
        historical_events,
        historical_snapshots,
        alternate_states,
        scenario_id=scenario_id + "::alternate",
        elapsed_seconds_window=elapsed_seconds_window,
    )
    impact = None
    if observed_estimate.p_win is not None and alternate_estimate.p_win is not None:
        impact = observed_estimate.p_win - alternate_estimate.p_win
    lower, upper = _bootstrap_impact_interval(
        historical_events,
        historical_snapshots,
        elapsed_seconds=observed_elapsed_seconds,
        observed_goal_difference=observed_focal_score - observed_opponent_score,
        alternate_states=alternate_states,
    )
    return CounterfactualImpact(
        scenario_id, observed_estimate, alternate_estimate, impact, lower, upper
    )


def scenario_timing_sensitivity(
    historical_events: pd.DataFrame,
    historical_snapshots: pd.DataFrame,
    *,
    scenario_id: str,
    elapsed_seconds_candidates: list[int],
    observed_focal_score: int,
    observed_opponent_score: int,
    alternate_focal_score: int,
    alternate_opponent_score: int,
    evidence_status: str = "reported",
) -> pd.DataFrame:
    """Run conditional alternate-state impacts without assessing decision correctness."""

    records = []
    for elapsed_seconds in elapsed_seconds_candidates:
        result = counterfactual_impact(
            historical_events,
            historical_snapshots,
            scenario_id=f"{scenario_id}::{elapsed_seconds}",
            observed_elapsed_seconds=int(elapsed_seconds),
            observed_focal_score=observed_focal_score,
            observed_opponent_score=observed_opponent_score,
            alternate_states=[
                CounterfactualState(
                    "alternate", int(elapsed_seconds), alternate_focal_score, alternate_opponent_score
                )
            ],
        )
        records.append(
            {
                "scenario_id": scenario_id,
                "elapsed_seconds": int(elapsed_seconds),
                "timing_minute": int(elapsed_seconds) / 60,
                "evidence_status": evidence_status,
                "analysis_status": "exploratory_conditional",
                "decision_correctness_status": "not_assessed",
                "observed_goal_difference": observed_focal_score - observed_opponent_score,
                "alternate_goal_difference": alternate_focal_score - alternate_opponent_score,
                "observed_p_win": result.observed.p_win,
                "alternate_p_win": result.alternate.p_win,
                "impact_probability_points": result.impact_probability_points,
                "bootstrap_lower": result.bootstrap_lower,
                "bootstrap_upper": result.bootstrap_upper,
                "observed_eligible_matches": result.observed.branches[0].eligible_matches,
                "alternate_eligible_matches": result.alternate.branches[0].eligible_matches,
            }
        )
    return pd.DataFrame(records)
