from __future__ import annotations

import builtins
import inspect
import unittest
from unittest.mock import patch

from src.agents.evaluation_agent import build_evaluation_input, evaluate_selected_policy
from src.product import scoring_engine
from src.product.scoring_engine import (
    LOCAL_SCORING_ENGINE_ID,
    build_score_input_from_feature,
    calculate_local_score_result,
)


class TestLocalScoringEngine(unittest.TestCase):
    def test_scoring_engine_source_has_no_llm_or_report_agent_dependency(self) -> None:
        source = inspect.getsource(scoring_engine)

        self.assertNotIn("src.llm", source)
        self.assertNotIn("OpenAI", source)
        self.assertNotIn("report_agent", source)

    def test_core_scores_run_when_llm_imports_are_blocked(self) -> None:
        evaluation_input = build_evaluation_input()
        selected_policy = evaluation_input["selected_policy"]
        weights = {key: float(value) for key, value in selected_policy["weights"].items()}

        with patch.object(builtins, "__import__", side_effect=_reject_llm_imports):
            result = evaluate_selected_policy(evaluation_input)

        self.assertEqual(result["summary_metrics"]["customer_count"], 30)
        self.assertTrue(result["summary_metrics"]["passes_approval_gate"])
        self.assertEqual(
            {snapshot["llm_report"]["mode"] for snapshot in result["customer_snapshots"]},
            {"pending_report_agent"},
        )
        for feature in evaluation_input["customer_features"]:
            local_score = calculate_local_score_result(build_score_input_from_feature(feature), weights)
            snapshot = next(
                row for row in result["customer_snapshots"] if row["customer_id"] == feature.customer_id
            )

            self.assertEqual(local_score.engine_id, LOCAL_SCORING_ENGINE_ID)
            self.assertEqual(snapshot["mileage_baseline_score"], local_score.mileage_baseline_score)
            self.assertEqual(snapshot["senior_safe_mileage_score"], local_score.senior_safe_mileage_score)
            self.assertEqual(snapshot["risk_change_score"], local_score.risk_change_score)
            self.assertEqual(
                snapshot["ab_comparison"]["metrics"]["proposed_model"]["input_summary"]["scoring_engine_id"],
                LOCAL_SCORING_ENGINE_ID,
            )


def _reject_llm_imports(name: str, *args: object, **kwargs: object) -> object:
    if name.startswith("src.llm") or name == "src.agents.report_agent":
        raise AssertionError(f"core scoring attempted forbidden import: {name}")
    return _ORIGINAL_IMPORT(name, *args, **kwargs)


_ORIGINAL_IMPORT = builtins.__import__


if __name__ == "__main__":
    unittest.main()
