from __future__ import annotations

from pathlib import Path
import unittest

from src.agents.policy_search_agent import CustomerPolicyFeature, build_customer_features
from src.product.proxy_labels import (
    DEFAULT_RISK_CHANGE_PROXY_THRESHOLDS,
    LABEL_INPUT_SCHEMA_VERSION,
    PROXY_LABEL_RULE_ID,
    ProxyLabelFeatureInput,
    RiskChangeProxyThresholds,
    build_hybrid_label_inputs,
    derive_proxy_labels,
    derive_risk_change_proxy_label,
    load_ground_truth_labels,
    normalize_care_decision,
    normalize_proxy_label_input,
    score_hybrid_evaluation_decision,
)


class TestRiskChangeProxyLabels(unittest.TestCase):
    def test_ground_truth_labels_load_and_normalize_from_scenario_fixture(self) -> None:
        labels = load_ground_truth_labels(Path("data/fixtures/scenario_config.json"))

        self.assertEqual(len(labels), 30)
        self.assertEqual(labels["cust_001"].schema_version, LABEL_INPUT_SCHEMA_VERSION)
        self.assertEqual(labels["cust_001"].expected_care_decision, "우대")
        self.assertFalse(labels["cust_001"].risk_change_target)
        self.assertEqual(labels["cust_011"].persona_type, "recent_outer_risk_change")
        self.assertEqual(labels["cust_011"].expected_care_decision, "예방 케어")
        self.assertTrue(labels["cust_011"].risk_change_target)
        self.assertIn("LOW_MILEAGE_WITH_RECENT_OUT_ZONE_RISK", labels["cust_011"].expected_reason_codes)

    def test_proxy_label_input_normalizes_objects_without_identifying_trip_fields(self) -> None:
        feature = CustomerPolicyFeature(
            customer_id="cust_safe_input",
            persona_type="recent_outer_risk_change",
            expected_care_decision="예방 케어",
            risk_change_target=True,
            baseline_total_km=800.0,
            recent_total_km=350.0,
            annualized_recent_km=4200.0,
            recent_trip_count=11,
            recent_in_zone_ratio=0.50,
            recent_out_zone_ratio=0.50,
            baseline_out_zone_ratio=0.10,
            out_zone_ratio_delta=0.40,
            baseline_night_ratio=0.02,
            recent_night_ratio=0.24,
            night_ratio_delta=0.22,
            baseline_risk_rate_per_100km=0.5,
            recent_risk_rate_per_100km=5.5,
            risk_rate_delta_per_100km=5.0,
            recent_risk_signal_count=7,
            recent_in_zone_km=175.0,
            recent_in_zone_trip_count=5,
            recent_in_zone_night_ratio=0.02,
            recent_in_zone_risk_rate_per_100km=0.5,
            recent_out_zone_km=175.0,
            recent_out_zone_trip_count=6,
            recent_out_zone_night_ratio=0.24,
            recent_out_zone_risk_rate_per_100km=6.0,
        )

        label_input = normalize_proxy_label_input(feature, source_artifact="feature-object")

        self.assertIsInstance(label_input, ProxyLabelFeatureInput)
        self.assertEqual(label_input.schema_version, LABEL_INPUT_SCHEMA_VERSION)
        self.assertEqual(label_input.customer_id, "cust_safe_input")
        self.assertTrue(derive_risk_change_proxy_label(label_input.to_proxy_feature()).is_target)
        self.assertNotIn("trip_id", label_input.to_dict())
        self.assertNotIn("driver_id", label_input.to_dict())

    def test_hybrid_label_inputs_align_ground_truth_and_proxy_inputs(self) -> None:
        labels = load_ground_truth_labels(Path("data/fixtures/scenario_config.json"))
        features = build_customer_features(
            Path("data/fixtures/senior_trip_logs.csv"),
            Path("data/fixtures/scenario_config.json"),
        )
        proxy_inputs = [normalize_proxy_label_input(feature) for feature in features]

        hybrid_inputs = build_hybrid_label_inputs(proxy_inputs, labels)

        self.assertEqual(len(hybrid_inputs), 30)
        self.assertTrue(all(item.schema_version == LABEL_INPUT_SCHEMA_VERSION for item in hybrid_inputs))
        self.assertEqual(sum(1 for item in hybrid_inputs if item.ground_truth.risk_change_target), 5)
        self.assertEqual(hybrid_inputs[0].customer_id, hybrid_inputs[0].ground_truth.customer_id)
        self.assertEqual(hybrid_inputs[0].customer_id, hybrid_inputs[0].proxy_feature_input.customer_id)

    def test_hybrid_evaluation_score_prioritizes_ground_truth_over_proxy_correction(self) -> None:
        ground_truth_match = score_hybrid_evaluation_decision(
            decision_detected=True,
            ground_truth_target=True,
            proxy_label_target=False,
        )
        proxy_only_match = score_hybrid_evaluation_decision(
            decision_detected=False,
            ground_truth_target=True,
            proxy_label_target=False,
        )

        self.assertTrue(ground_truth_match.hybrid_target)
        self.assertEqual(ground_truth_match.score, 80.0)
        self.assertEqual(proxy_only_match.score, 20.0)
        self.assertTrue(ground_truth_match.passed)
        self.assertEqual(ground_truth_match.verdict, "pass")
        self.assertFalse(proxy_only_match.passed)
        self.assertEqual(proxy_only_match.verdict, "fail")
        self.assertEqual(ground_truth_match.pass_threshold, 80.0)
        self.assertEqual(ground_truth_match.weights["ground_truth_priority"], 0.8)
        self.assertEqual(ground_truth_match.weights["proxy_label_correction"], 0.2)
        self.assertIn("HYBRID_PROXY_CORRECTION_APPLIED", ground_truth_match.reason_codes)
        self.assertIn("HYBRID_DECISION_MATCHES_GROUND_TRUTH", ground_truth_match.reason_codes)
        self.assertEqual(
            ground_truth_match.exception_rule,
            "HYBRID_EXCEPTION_PROXY_DISAGREEMENT_ALLOWED_WHEN_GROUND_TRUTH_MATCHES",
        )
        self.assertEqual(
            proxy_only_match.exception_rule,
            "HYBRID_EXCEPTION_PROXY_ONLY_MATCH_DOES_NOT_OVERRIDE_GROUND_TRUTH",
        )

    def test_care_decision_aliases_are_canonicalized(self) -> None:
        self.assertEqual(normalize_care_decision("favorable"), "우대")
        self.assertEqual(normalize_care_decision("standard"), "기본")
        self.assertEqual(normalize_care_decision("preventive_care"), "예방 케어")
        self.assertEqual(normalize_care_decision("예방케어"), "예방 케어")

    def test_proxy_label_module_exposes_auditable_thresholds_and_criteria(self) -> None:
        feature = CustomerPolicyFeature(
            customer_id="proxy_target",
            persona_type="recent_outer_risk_change",
            expected_care_decision="기본",
            risk_change_target=False,
            baseline_total_km=900.0,
            recent_total_km=420.0,
            annualized_recent_km=5040.0,
            recent_trip_count=12,
            recent_in_zone_ratio=0.45,
            recent_out_zone_ratio=0.55,
            baseline_out_zone_ratio=0.15,
            out_zone_ratio_delta=0.40,
            baseline_night_ratio=0.05,
            recent_night_ratio=0.30,
            night_ratio_delta=0.25,
            baseline_risk_rate_per_100km=0.4,
            recent_risk_rate_per_100km=6.2,
            risk_rate_delta_per_100km=5.8,
            recent_risk_signal_count=8,
            recent_in_zone_km=189.0,
            recent_in_zone_trip_count=6,
            recent_in_zone_night_ratio=0.08,
            recent_in_zone_risk_rate_per_100km=0.5,
            recent_out_zone_km=231.0,
            recent_out_zone_trip_count=6,
            recent_out_zone_night_ratio=0.30,
            recent_out_zone_risk_rate_per_100km=6.2,
        )

        label = derive_risk_change_proxy_label(feature)

        self.assertTrue(label.is_target)
        self.assertEqual(label.rule_id, PROXY_LABEL_RULE_ID)
        self.assertEqual(label.expected_care_decision, "예방 케어")
        self.assertEqual(label.thresholds, DEFAULT_RISK_CHANGE_PROXY_THRESHOLDS.to_dict())
        self.assertIn("PROXY_OUT_ZONE_RATIO_DELTA_HIGH", label.reason_codes)
        self.assertIn("PROXY_OUT_ZONE_RISK_CONFIRMED", label.reason_codes)

    def test_proxy_threshold_changes_can_make_borderline_customer_non_target(self) -> None:
        feature = {
            "annualized_recent_km": 7000.0,
            "risk_change_score": 72.0,
            "out_zone_ratio_delta": 0.28,
            "night_ratio_delta": 0.18,
            "risk_rate_delta_per_100km": 3.2,
            "recent_out_zone_risk_rate_per_100km": 4.1,
            "recent_out_zone_trip_count": 4,
        }

        default_label = derive_risk_change_proxy_label(feature)
        stricter_label = derive_risk_change_proxy_label(
            feature,
            RiskChangeProxyThresholds(out_zone_ratio_delta_min=0.30),
        )

        self.assertTrue(default_label.is_target)
        self.assertFalse(stricter_label.is_target)
        self.assertEqual(stricter_label.expected_care_decision, "기본")

    def test_fixture_proxy_labels_mark_only_recent_outer_risk_change_group(self) -> None:
        features = build_customer_features(
            Path("data/fixtures/senior_trip_logs.csv"),
            Path("data/fixtures/scenario_config.json"),
        )
        labels = derive_proxy_labels(features)
        target_personas = {
            feature.persona_type
            for feature, label in zip(features, labels)
            if label.is_target
        }

        self.assertEqual(sum(1 for label in labels if label.is_target), 5)
        self.assertEqual(target_personas, {"recent_outer_risk_change"})
        self.assertTrue(all(feature.risk_change_target == label.is_target for feature, label in zip(features, labels)))
        self.assertTrue(all(feature.proxy_label_rule_id == PROXY_LABEL_RULE_ID for feature in features))


if __name__ == "__main__":
    unittest.main()
