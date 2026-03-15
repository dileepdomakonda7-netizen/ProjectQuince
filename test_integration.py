"""
Integration tests for the Quince AI Creative Copilot pipeline.

These tests mock the LLM call so the full pipeline can be verified
end-to-end WITHOUT an API key. They prove:
  1. Valid product data → generation → validation passes
  2. Hallucinated content gets caught by the validator
  3. The composite scorer handles partial evaluation correctly
  4. The dedup correctly flags near-duplicate hooks

Run:
    python3 test_integration.py
    python3 -m pytest test_integration.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))


# --- Canned LLM responses for mocking ---

GOOD_HOOKS_FACEBOOK = json.dumps({
    "educational": "Grade-A Mongolian cashmere at 15.8 microns — finer than most luxury brands use in their premium lines.",
    "value_driven": "$50 for the same 15.8-micron cashmere that retails for $148. No middleman. No markup.",
    "lifestyle": "Sunday morning, coffee in hand, wrapped in cashmere so soft your shoulders finally relax."
})

GOOD_HOOKS_EMAIL = json.dumps({
    "educational": "15.8 micron cashmere: why fiber diameter matters",
    "value_driven": "$50 cashmere vs $148 retail — no middleman",
    "lifestyle": "That cashmere-against-skin feeling, every morning"
})

GOOD_HOOKS_SMS = json.dumps({
    "educational": "Fun fact: Grade-A cashmere uses 15.8 micron fibers from free-roaming Mongolian goats. Finer than most luxury brands. Feel the difference at $50.",
    "value_driven": "Same 15.8-micron Mongolian cashmere that retails for $148. We cut the middleman, you pay $50. Real luxury, real price.",
    "lifestyle": "Sunday morning, coffee in hand, wrapped in cashmere sourced from Mongolia. That cozy weight feeling? It's your $50 Quince crewneck."
})

BAD_HOOKS_HALLUCINATED = json.dumps({
    "educational": "Our cashmere is 50% off this weekend only — grab it before it's gone!",
    "value_driven": "Free shipping on all cashmere — buy now and save big with our clearance event!",
    "lifestyle": "Get this cheap cashmere bargain at rock bottom prices. Limited time offer!"
})

GOOD_HOOKS_PRODUCT_B = json.dumps({
    "educational": "22-momme mulberry silk — the weight that five-star hotels specify for pillowcases that last a decade.",
    "value_driven": "$44.90 for 22-momme silk that retails for $69. Same quality, no retail markup.",
    "lifestyle": "Your hair glides across silk so smooth it feels like sleeping on a cloud of cool."
})

SAMPLE_PRODUCT_A = {
    "id": "QNC-001",
    "name": "Mongolian Cashmere Crewneck Sweater",
    "category": "Sweaters",
    "material": "100% Grade-A Mongolian Cashmere (15.8-16.2 micron, 12 gauge knit, 34-36mm fiber length)",
    "price": 50.00,
    "comparable_retail_price": 148.00,
    "target_persona": "Style-conscious professional, 28-45",
    "sustainability": "Ethically sourced from free-roaming Mongolian goats",
    "fit": "Relaxed",
    "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
    "colors": ["Black", "Ivory", "Burgundy"],
    "key_features": ["15.8-16.2 micron fiber", "12-gauge knit", "Cozy weight"]
}

SAMPLE_PRODUCT_B = {
    "id": "QNC-009",
    "name": "100% Mulberry Silk Pillowcase",
    "category": "Home",
    "material": "100% Mulberry Silk (22 momme, 6A grade)",
    "price": 44.90,
    "comparable_retail_price": 69.00,
    "target_persona": "Skincare-conscious sleeper, 25-50",
    "sustainability": "OEKO-TEX certified",
    "fit": "Standard/King",
    "sizes": ["Standard", "King"],
    "colors": ["White", "Champagne", "Dusty Rose"],
    "key_features": ["22 momme weight", "Hidden zipper closure", "Temperature regulating"]
}


class TestPipelineIntegration(unittest.TestCase):
    """End-to-end pipeline tests with mocked LLM."""

    def setUp(self):
        """Create temp files for test products and hooks."""
        self.test_dir = tempfile.mkdtemp()
        self.products_file = os.path.join(self.test_dir, "products.json")
        self.hooks_file = os.path.join(self.test_dir, "hooks.json")

        with open(self.products_file, "w") as f:
            json.dump([SAMPLE_PRODUCT_A, SAMPLE_PRODUCT_B], f)

    def test_valid_hooks_pass_full_validation(self):
        """Good hooks should pass all 4 validation rules."""
        from validator import validate_all

        hook_sets = [
            {"product_id": "QNC-001", "product_name": "Mongolian Cashmere Crewneck Sweater",
             "channel": "facebook_ad", "hooks": json.loads(GOOD_HOOKS_FACEBOOK)},
            {"product_id": "QNC-001", "product_name": "Mongolian Cashmere Crewneck Sweater",
             "channel": "email_subject", "hooks": json.loads(GOOD_HOOKS_EMAIL)},
            {"product_id": "QNC-001", "product_name": "Mongolian Cashmere Crewneck Sweater",
             "channel": "sms", "hooks": json.loads(GOOD_HOOKS_SMS)},
        ]

        with open(self.hooks_file, "w") as f:
            json.dump(hook_sets, f)

        report = validate_all(self.hooks_file, self.products_file)
        self.assertEqual(report["failed"], 0, f"Expected 0 failures, got: {report.get('failures', [])}")
        self.assertEqual(report["passed"], 9)  # 3 channels x 3 hooks

    def test_hallucinated_hooks_caught_by_validator(self):
        """Hooks with forbidden keywords and hallucinated claims should fail."""
        from validator import validate_all

        hook_sets = [
            {"product_id": "QNC-001", "product_name": "Mongolian Cashmere Crewneck Sweater",
             "channel": "facebook_ad", "hooks": json.loads(BAD_HOOKS_HALLUCINATED)},
        ]

        with open(self.hooks_file, "w") as f:
            json.dump(hook_sets, f)

        report = validate_all(self.hooks_file, self.products_file)
        self.assertGreater(report["failed"], 0, "Hallucinated hooks should fail validation")

        # Check that specific violation types were caught
        all_violations = []
        for failure in report["failures"]:
            for v in failure["violations"]:
                all_violations.append(v["rule"])

        self.assertIn("forbidden_keywords", all_violations,
                      "Should catch forbidden keywords like 'cheap', 'bargain'")
        self.assertIn("hallucination_check", all_violations,
                      "Should catch hallucination patterns like '50% off'")

    def test_generate_with_mocked_llm(self):
        """Hook generator should work end-to-end with a mocked LLM response."""
        from hook_generator import generate_hooks

        with patch("hook_generator._call_llm", return_value=GOOD_HOOKS_FACEBOOK):
            hooks = generate_hooks(
                SAMPLE_PRODUCT_A, "facebook_ad",
                client="mock", provider="groq", model="mock"
            )

        self.assertIn("educational", hooks)
        self.assertIn("value_driven", hooks)
        self.assertIn("lifestyle", hooks)
        self.assertTrue(len(hooks["educational"]) > 0)

    def test_generate_retries_on_bad_output(self):
        """Generator should retry when LLM produces forbidden keywords."""
        from hook_generator import generate_hooks

        call_count = {"n": 0}

        def mock_llm(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return BAD_HOOKS_HALLUCINATED  # First attempt fails
            return GOOD_HOOKS_FACEBOOK  # Retry succeeds

        with patch("hook_generator._call_llm", side_effect=mock_llm):
            hooks = generate_hooks(
                SAMPLE_PRODUCT_A, "facebook_ad",
                client="mock", provider="groq", model="mock"
            )

        self.assertGreater(call_count["n"], 1, "Should have retried at least once")
        self.assertNotIn("cheap", hooks["lifestyle"].lower())


class TestDedupIntegration(unittest.TestCase):
    """Test cross-product dedup with realistic hook data."""

    def test_similar_hooks_flagged(self):
        """Near-duplicate hooks across products should be detected."""
        from quality_judges import cross_product_similarity

        hook_sets = [
            {"product_id": "QNC-001", "product_name": "Cashmere Crewneck",
             "channel": "facebook_ad", "hooks": {
                 "educational": "Grade-A Mongolian cashmere at 15.8 microns — finer than most luxury brands.",
                 "value_driven": "$50 for premium cashmere. No middleman markup.",
                 "lifestyle": "Sunday morning wrapped in cashmere so soft.",
             }},
            {"product_id": "QNC-002", "product_name": "Cashmere Tee",
             "channel": "facebook_ad", "hooks": {
                 "educational": "Grade-A Mongolian cashmere at 15.8 microns — softer than most luxury brands.",
                 "value_driven": "$44.90 for premium cashmere tee. No middleman markup.",
                 "lifestyle": "Weekday morning layered under a blazer, pure cashmere.",
             }},
        ]

        report = cross_product_similarity(hook_sets)
        self.assertGreater(report["duplicate_pairs_found"], 0,
                           "Should flag near-duplicate educational hooks")
        self.assertLess(report["corpus_uniqueness"], 1.0)

    def test_diverse_hooks_pass(self):
        """Hooks for very different products should not be flagged."""
        from quality_judges import cross_product_similarity

        hook_sets = [
            {"product_id": "QNC-001", "product_name": "Cashmere Crewneck",
             "channel": "facebook_ad", "hooks": json.loads(GOOD_HOOKS_FACEBOOK)},
            {"product_id": "QNC-009", "product_name": "Silk Pillowcase",
             "channel": "facebook_ad", "hooks": json.loads(GOOD_HOOKS_PRODUCT_B)},
        ]

        report = cross_product_similarity(hook_sets)
        self.assertEqual(report["duplicate_pairs_found"], 0,
                         "Different products with distinct hooks should have no duplicates")


class TestCompositeScoreIntegration(unittest.TestCase):
    """Test composite scorer with realistic inputs."""

    def test_partial_evaluation_transparency(self):
        """Composite score should track how many dimensions were evaluated."""
        from quality_judges import compute_composite_score

        composite = compute_composite_score(
            validation_report={"total_hooks": 9, "passed": 9},
        )

        self.assertEqual(composite["dimensions_evaluated"], 1)
        self.assertEqual(composite["dimensions_total"], 5)

    def test_full_evaluation(self):
        """Composite with all dimensions should evaluate 5/5."""
        from quality_judges import compute_composite_score

        composite = compute_composite_score(
            validation_report={"total_hooks": 9, "passed": 9},
            grading_report={"average_score": 3.8},
            specificity_scores=[{"specificity_score": 4}] * 9,
            channel_fit_scores=[{"channel_fit_score": 4}] * 9,
            dedup_report={"corpus_uniqueness": 0.95},
        )

        self.assertEqual(composite["dimensions_evaluated"], 5)
        self.assertGreater(composite["composite_score"], 0.7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
