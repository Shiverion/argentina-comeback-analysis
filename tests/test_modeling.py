from __future__ import annotations

import unittest

import numpy as np

from research_etl.modeling import probability_metrics


class ProbabilityMetricTests(unittest.TestCase):
    def test_perfect_probabilities_have_zero_loss_and_ece(self) -> None:
        outcomes = np.array(["DRAW", "FOCAL_LOSS", "FOCAL_WIN"])
        probabilities = np.eye(3)
        result = probability_metrics(outcomes, probabilities)
        self.assertAlmostEqual(result["log_loss"], 0.0)
        self.assertAlmostEqual(result["multiclass_brier"], 0.0)
        self.assertAlmostEqual(result["max_class_ece"], 0.0)
