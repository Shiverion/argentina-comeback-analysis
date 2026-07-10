"""Validation gates for the historical Stage C multinomial baseline."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research_etl.paths import ProjectPaths
from research_etl.sources import SourceError, sha256_file, write_json_atomic

MODEL_FEATURES = [
    "elapsed_seconds", "goal_difference", "red_card_difference",
    "strength_difference", "is_knockout", "is_neutral",
]
OUTCOME_LABELS = ["DRAW", "FOCAL_LOSS", "FOCAL_WIN"]


def make_baseline_model(random_seed: int = 20260707) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2_000, random_state=random_seed)),
        ]
    )


def _aligned_probabilities(model: Any, features: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(features)
    class_index = {label: index for index, label in enumerate(model.classes_)}
    return np.column_stack([raw[:, class_index[label]] for label in OUTCOME_LABELS])


def _indicator(outcomes: pd.Series | np.ndarray) -> np.ndarray:
    values = np.asarray(outcomes)
    return np.column_stack([values == label for label in OUTCOME_LABELS]).astype(float)


def probability_metrics(outcomes: pd.Series | np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    truth = _indicator(outcomes)
    clipped = np.clip(probabilities, 1e-15, 1)
    log_loss = -float(np.mean(np.sum(truth * np.log(clipped), axis=1)))
    brier = float(np.mean(np.sum((probabilities - truth) ** 2, axis=1)))
    ece: dict[str, float] = {}
    for index, label in enumerate(OUTCOME_LABELS):
        bins = np.minimum((probabilities[:, index] * 10).astype(int), 9)
        error = 0.0
        for bin_number in range(10):
            selected = bins == bin_number
            if selected.any():
                error += float(selected.mean()) * abs(
                    float(truth[selected, index].mean()) - float(probabilities[selected, index].mean())
                )
        ece[label] = error
    predicted = np.asarray(OUTCOME_LABELS)[probabilities.argmax(axis=1)]
    return {
        "rows": int(len(truth)),
        "log_loss": log_loss,
        "multiclass_brier": brier,
        "accuracy": float(np.mean(predicted == np.asarray(outcomes))),
        "ece_10bin": ece,
        "max_class_ece": max(ece.values()),
    }


def _grouped_oof(frame: pd.DataFrame, groups: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    folds = min(5, groups.nunique())
    if folds < 2:
        raise SourceError("Grouped validation needs at least two independent groups.")
    probabilities = np.full((len(frame), len(OUTCOME_LABELS)), np.nan)
    null_probabilities = np.full_like(probabilities, np.nan)
    splitter = GroupKFold(n_splits=folds)
    for train_index, test_index in splitter.split(frame, frame["regulation_result"], groups=groups):
        train = frame.iloc[train_index]
        fitted = make_baseline_model().fit(train[MODEL_FEATURES], train["regulation_result"])
        probabilities[test_index] = _aligned_probabilities(fitted, frame.iloc[test_index][MODEL_FEATURES])
        priors = train["regulation_result"].value_counts(normalize=True)
        null_probabilities[test_index] = np.array([priors.get(label, 0.0) for label in OUTCOME_LABELS])
    return probabilities, null_probabilities


def _fit_calibrated_boosting(train: pd.DataFrame, *, random_seed: int) -> CalibratedClassifierCV:
    """Fit and calibrate on disjoint match groups within an outer training fold."""

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=random_seed)
    fit_index, calibration_index = next(
        splitter.split(train, train["regulation_result"], groups=train["match_id"])
    )
    fit_frame = train.iloc[fit_index]
    calibration_frame = train.iloc[calibration_index]
    base = HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=120,
        max_leaf_nodes=15,
        min_samples_leaf=40,
        l2_regularization=0.1,
        random_state=random_seed,
    ).fit(fit_frame[MODEL_FEATURES], fit_frame["regulation_result"])
    calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
    calibrated.fit(calibration_frame[MODEL_FEATURES], calibration_frame["regulation_result"])
    return calibrated


def _calibrated_boosting_oof(frame: pd.DataFrame, groups: pd.Series) -> np.ndarray:
    folds = min(5, groups.nunique())
    if folds < 2:
        raise SourceError("Calibrated grouped validation needs at least two independent groups.")
    probabilities = np.full((len(frame), len(OUTCOME_LABELS)), np.nan)
    splitter = GroupKFold(n_splits=folds)
    for fold, (train_index, test_index) in enumerate(
        splitter.split(frame, frame["regulation_result"], groups=groups)
    ):
        calibrated = _fit_calibrated_boosting(frame.iloc[train_index], random_seed=20260707 + fold)
        probabilities[test_index] = _aligned_probabilities(
            calibrated, frame.iloc[test_index][MODEL_FEATURES]
        )
    return probabilities


def _validation_checks(metrics: dict[str, Any], gate: dict[str, Any]) -> dict[str, bool]:
    return {
        "match_brier_beats_null": (
            metrics["match_grouped_oof"]["multiclass_brier"]
            < metrics["match_grouped_null"]["multiclass_brier"]
        ),
        "tournament_brier_beats_null": (
            metrics["tournament_grouped_oof"]["multiclass_brier"]
            < metrics["tournament_grouped_null"]["multiclass_brier"]
        ),
        "chronological_brier_beats_null": (
            metrics["chronological_holdout"]["multiclass_brier"]
            < metrics["chronological_null"]["multiclass_brier"]
        ),
        "overall_ece_within_gate": (
            metrics["match_grouped_oof"]["max_class_ece"] <= float(gate["max_overall_class_ece"])
        ),
        "late_game_ece_within_gate": (
            metrics["match_grouped_late_game"]["max_class_ece"] <= float(gate["max_late_game_class_ece"])
        ),
    }


def _focal_feature_frame(paths: ProjectPaths) -> tuple[pd.DataFrame, dict[str, float]]:
    strength = pd.read_csv(paths.processed_dir / "focal_pre_match_strength.csv")
    ratings = strength.set_index("team")["elo_rating"].astype(float).to_dict()
    if set(ratings) != {"Argentina", "Egypt"}:
        raise SourceError("Focal prediction requires Argentina and Egypt pre-match Elo ratings.")
    strength_difference = ratings["Argentina"] - ratings["Egypt"]

    events = pd.read_csv(paths.processed_dir / "focal_events.csv")
    goals = events.loc[
        events["event_type"].astype(str).str.upper().eq("GOAL")
        & events["outcome"].astype(str).str.lower().eq("confirmed")
    ].sort_values(["elapsed_seconds", "event_id"], kind="stable")
    rows = []
    for minute in (14, 66, 70, 75, 78, 80, 82, 91):
        elapsed_seconds = minute * 60
        previous = goals.loc[goals["elapsed_seconds"].le(elapsed_seconds)]
        if previous.empty:
            focal_score = opponent_score = 0
        else:
            state = previous.iloc[-1]
            focal_score = int(state["score_argentina"])
            opponent_score = int(state["score_egypt"])
        rows.append(
            {
                "minute": minute,
                "elapsed_seconds": elapsed_seconds,
                "goal_difference": focal_score - opponent_score,
                "red_card_difference": 0,
                "strength_difference": strength_difference,
                "is_knockout": 1,
                "is_neutral": 1,
                "score_argentina": focal_score,
                "score_egypt": opponent_score,
            }
        )
    return pd.DataFrame(rows), ratings


def _write_csv_atomic(frame: pd.DataFrame, destination) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    frame.to_csv(temporary, index=False)
    temporary.replace(destination)


def _write_focal_predictions(
    paths: ProjectPaths,
    historical_frame: pd.DataFrame,
    *,
    selected_model: str,
    support_gate: dict[str, Any],
) -> dict[str, Any]:
    focal, ratings = _focal_feature_frame(paths)
    member_probabilities = []
    splitter = GroupKFold(n_splits=5)
    for fold, (train_index, _) in enumerate(
        splitter.split(
            historical_frame,
            historical_frame["regulation_result"],
            groups=historical_frame["match_id"],
        )
    ):
        train = historical_frame.iloc[train_index]
        if selected_model == "calibrated_hist_gradient_boosting":
            fitted = _fit_calibrated_boosting(train, random_seed=20260901 + fold)
        else:
            fitted = make_baseline_model(random_seed=20260901 + fold).fit(
                train[MODEL_FEATURES], train["regulation_result"]
            )
        member_probabilities.append(_aligned_probabilities(fitted, focal[MODEL_FEATURES]))
    ensemble = np.stack(member_probabilities)
    mean = ensemble.mean(axis=0)
    lower = ensemble.min(axis=0)
    upper = ensemble.max(axis=0)
    result = focal.copy()
    for index, label in enumerate(OUTCOME_LABELS):
        suffix = label.lower()
        result[f"p_{suffix}"] = mean[:, index]
        result[f"p_{suffix}_ensemble_min"] = lower[:, index]
        result[f"p_{suffix}_ensemble_max"] = upper[:, index]
    result["model"] = selected_model
    time_window = int(support_gate["focal_support_time_window_minutes"]) * 60
    strength_window = float(support_gate["focal_support_strength_window"])
    minimum_matches = int(support_gate["focal_support_minimum_matches"])
    support_matches = []
    support_status = []
    for row in result.itertuples(index=False):
        neighborhood = historical_frame.loc[
            historical_frame["elapsed_seconds"].between(
                row.elapsed_seconds - time_window, row.elapsed_seconds + time_window
            )
            & historical_frame["goal_difference"].eq(row.goal_difference)
            & historical_frame["strength_difference"].between(
                row.strength_difference - strength_window,
                row.strength_difference + strength_window,
            )
        ]
        matches = int(neighborhood["match_id"].nunique())
        support_matches.append(matches)
        support_status.append("supported" if matches >= minimum_matches else "extrapolative_low_support")
    result["local_support_matches"] = support_matches
    result["support_status"] = support_status
    result["probability_status"] = "exploratory_support_limited"
    result["uncertainty_note"] = "Min/max across five grouped calibrated ensemble members; not a confidence interval."
    output_path = paths.results_dir / "focal_model_probabilities.csv"
    _write_csv_atomic(result, output_path)
    low_support_rows = int(result["support_status"].eq("extrapolative_low_support").sum())
    return {
        "status": "ready_exploratory_with_support_warnings" if low_support_rows else "ready_exploratory",
        "path": str(output_path.relative_to(paths.root)).replace("\\", "/"),
        "sha256": sha256_file(output_path),
        "rows": int(len(result)),
        "ratings": ratings,
        "strength_difference": ratings["Argentina"] - ratings["Egypt"],
        "as_of_date": "2026-07-06",
        "low_support_rows": low_support_rows,
        "support_gate": {
            "time_window_minutes": int(support_gate["focal_support_time_window_minutes"]),
            "strength_window": strength_window,
            "minimum_matches": minimum_matches,
        },
    }


def run_model_validation(paths: ProjectPaths) -> dict[str, Any]:
    """Validate the baseline without generating a focal-match probability when gates fail."""

    config = json.loads(paths.config_file.read_text(encoding="utf-8"))
    gate = config["model_validation_gate"]
    model_path = paths.processed_dir / "model_frame.csv"
    if not model_path.exists():
        raise SourceError("Model validation requires data/processed/model_frame.csv.")
    frame = pd.read_csv(model_path)
    required = set(MODEL_FEATURES + ["match_id", "tournament", "year", "regulation_result"])
    if missing := sorted(required - set(frame.columns)):
        raise SourceError(f"Model frame missing validation columns: {', '.join(missing)}")

    match_probabilities, match_null = _grouped_oof(frame, frame["match_id"])
    tournament_probabilities, tournament_null = _grouped_oof(frame, frame["tournament"])
    late = frame["elapsed_seconds"].ge(int(gate["late_game_start_minute"]) * 60).to_numpy()

    holdout_year = int(gate["chronological_holdout_year"])
    train = frame.loc[frame["year"].lt(holdout_year)]
    test = frame.loc[frame["year"].eq(holdout_year)]
    if train.empty or test.empty:
        raise SourceError(f"Chronological holdout year {holdout_year} is not available.")
    chronological_model = make_baseline_model().fit(train[MODEL_FEATURES], train["regulation_result"])
    chronological_probabilities = _aligned_probabilities(chronological_model, test[MODEL_FEATURES])
    priors = train["regulation_result"].value_counts(normalize=True)
    chronological_null = np.tile(
        np.array([priors.get(label, 0.0) for label in OUTCOME_LABELS]), (len(test), 1)
    )

    baseline_metrics = {
        "match_grouped_oof": probability_metrics(frame["regulation_result"], match_probabilities),
        "match_grouped_null": probability_metrics(frame["regulation_result"], match_null),
        "match_grouped_late_game": probability_metrics(
            frame.loc[late, "regulation_result"], match_probabilities[late]
        ),
        "tournament_grouped_oof": probability_metrics(frame["regulation_result"], tournament_probabilities),
        "tournament_grouped_null": probability_metrics(frame["regulation_result"], tournament_null),
        "chronological_holdout": probability_metrics(test["regulation_result"], chronological_probabilities),
        "chronological_null": probability_metrics(test["regulation_result"], chronological_null),
    }
    baseline_checks = _validation_checks(baseline_metrics, gate)

    secondary_match = _calibrated_boosting_oof(frame, frame["match_id"])
    secondary_tournament = _calibrated_boosting_oof(frame, frame["tournament"])
    secondary_chronological_model = _fit_calibrated_boosting(train, random_seed=20260801)
    secondary_chronological = _aligned_probabilities(
        secondary_chronological_model, test[MODEL_FEATURES]
    )
    secondary_metrics = {
        "match_grouped_oof": probability_metrics(frame["regulation_result"], secondary_match),
        "match_grouped_null": baseline_metrics["match_grouped_null"],
        "match_grouped_late_game": probability_metrics(
            frame.loc[late, "regulation_result"], secondary_match[late]
        ),
        "tournament_grouped_oof": probability_metrics(
            frame["regulation_result"], secondary_tournament
        ),
        "tournament_grouped_null": baseline_metrics["tournament_grouped_null"],
        "chronological_holdout": probability_metrics(
            test["regulation_result"], secondary_chronological
        ),
        "chronological_null": baseline_metrics["chronological_null"],
    }
    secondary_checks = _validation_checks(secondary_metrics, gate)
    baseline_passed = all(baseline_checks.values())
    secondary_passed = all(secondary_checks.values())
    passed = baseline_passed or secondary_passed
    selected_model = (
        "calibrated_hist_gradient_boosting" if secondary_passed
        else "multinomial_logistic" if baseline_passed else None
    )
    focal_output = (
        _write_focal_predictions(paths, frame, selected_model=selected_model, support_gate=gate)
        if passed else None
    )
    payload = {
        "status": "passed" if passed else "failed_validation_gate",
        "focal_probability_status": (
            "exploratory_support_limited" if focal_output is not None and focal_output["low_support_rows"]
            else "ready_exploratory" if focal_output is not None else "blocked_validation_gate"
        ),
        "focal_output": focal_output,
        "selected_model": selected_model,
        "gate": gate,
        "models": {
            "multinomial_logistic": {
                "status": "passed" if baseline_passed else "failed_validation_gate",
                "checks": baseline_checks,
                "metrics": baseline_metrics,
            },
            "calibrated_hist_gradient_boosting": {
                "status": "passed" if secondary_passed else "failed_validation_gate",
                "checks": secondary_checks,
                "metrics": secondary_metrics,
                "calibration_design": "Outer grouped holdout; inner 80/20 match-group split for sigmoid calibration.",
            },
        },
        "constant_features": [column for column in MODEL_FEATURES if frame[column].nunique(dropna=False) <= 1],
        "notes": [
            "Gate v0.1 was frozen after exploratory inspection of the initial baseline and is not a preregistration.",
            "Rows are minute-level team perspectives; all validation splits keep complete matches together.",
        ],
    }
    write_json_atomic(payload, paths.results_dir / "model_validation.json")
    return payload
