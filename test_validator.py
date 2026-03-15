"""
Unit tests for the Quince Creative Copilot validator and quality judges.

Run: python3 -m pytest test_validator.py -v
  or: python3 test_validator.py
"""

import json
import os
import sys
import unittest

from validator import (
    validate_character_limit,
    validate_forbidden_keywords,
    validate_hallucination_patterns,
    validate_price_accuracy,
    validate_hook,
)
from models import Product, HookSet

# Sample product for testing
SAMPLE_PRODUCT = {
    "id": "QNC-001",
    "name": "Mongolian Cashmere Crewneck Sweater",
    "category": "Sweaters",
    "material": "100% Grade-A Mongolian Cashmere (15.8-16.2 micron, 12 gauge, 34-36mm fiber length)",
    "price": 50.00,
    "comparable_retail_price": 148.00,
    "target_persona": "Professional women, 28-45, who value luxury basics",
    "sustainability": "Ethically produced; sustainably sourced Grade-A cashmere from free-roaming goats in Inner Mongolia",
    "fit": "Relaxed",
    "sizes": ["XS", "S", "M", "L", "XL"],
    "colors": ["Ivory", "Rich Burgundy", "Charcoal", "Black"],
    "key_features": ["Cozy Weight with increased yarn tension", "Ribbed cuffs and hem", "Temperature-regulating fibers"],
}


class TestCharacterLimit(unittest.TestCase):
    """Tests for channel character limit validation."""

    def test_within_facebook_limit(self):
        result = validate_character_limit("Short hook here", "facebook_ad")
        self.assertTrue(result["passed"])

    def test_exceeds_facebook_limit(self):
        result = validate_character_limit("x" * 200, "facebook_ad")
        self.assertFalse(result["passed"])
        self.assertIn("OVER", result["detail"])

    def test_exactly_at_limit(self):
        result = validate_character_limit("x" * 125, "facebook_ad")
        self.assertTrue(result["passed"])

    def test_email_subject_limit(self):
        result = validate_character_limit("x" * 61, "email_subject")
        self.assertFalse(result["passed"])

    def test_sms_limit(self):
        result = validate_character_limit("x" * 160, "sms")
        self.assertTrue(result["passed"])

    def test_empty_string(self):
        result = validate_character_limit("", "facebook_ad")
        self.assertTrue(result["passed"])


class TestForbiddenKeywords(unittest.TestCase):
    """Tests for forbidden keyword detection."""

    def test_clean_copy(self):
        result = validate_forbidden_keywords("Premium cashmere at a fair price")
        self.assertTrue(result["passed"])

    def test_detects_cheap(self):
        result = validate_forbidden_keywords("This is a cheap option")
        self.assertFalse(result["passed"])
        self.assertIn("cheap", result["detail"])

    def test_detects_bargain(self):
        result = validate_forbidden_keywords("What a great bargain!")
        self.assertFalse(result["passed"])

    def test_detects_free_shipping(self):
        result = validate_forbidden_keywords("Enjoy free shipping today")
        self.assertFalse(result["passed"])

    def test_detects_multiple_keywords(self):
        result = validate_forbidden_keywords("Cheap bargain at the clearance sale!")
        self.assertFalse(result["passed"])
        # Should find multiple forbidden words
        self.assertIn("cheap", result["detail"])
        self.assertIn("bargain", result["detail"])

    def test_case_insensitive(self):
        result = validate_forbidden_keywords("CHEAP AND BARGAIN")
        self.assertFalse(result["passed"])

    def test_keyword_in_middle_of_word(self):
        # "sale" should be caught even inside a sentence
        result = validate_forbidden_keywords("Big end of season sale here")
        self.assertFalse(result["passed"])


class TestHallucinationPatterns(unittest.TestCase):
    """Tests for hallucination pattern detection."""

    def test_clean_copy(self):
        result = validate_hallucination_patterns("Crafted from Grade-A cashmere")
        self.assertTrue(result["passed"])

    def test_detects_percent_off(self):
        result = validate_hallucination_patterns("Get 50% off today!")
        self.assertFalse(result["passed"])

    def test_detects_free_shipping(self):
        result = validate_hallucination_patterns("Includes free shipping")
        self.assertFalse(result["passed"])

    def test_detects_bogo(self):
        result = validate_hallucination_patterns("Buy one get one free")
        self.assertFalse(result["passed"])

    def test_detects_dollar_off(self):
        result = validate_hallucination_patterns("Save $20 off your purchase")
        self.assertFalse(result["passed"])

    def test_detects_urgency(self):
        result = validate_hallucination_patterns("Today only special!")
        self.assertFalse(result["passed"])

    def test_detects_scarcity(self):
        result = validate_hallucination_patterns("Order while supplies last")
        self.assertFalse(result["passed"])


class TestPriceAccuracy(unittest.TestCase):
    """Tests for price accuracy against product data."""

    def test_correct_price_two_decimals(self):
        result = validate_price_accuracy("Only $50.00 for luxury", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])

    def test_correct_price_one_decimal(self):
        result = validate_price_accuracy("Only $50.0 for luxury", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])

    def test_correct_comparable_price(self):
        result = validate_price_accuracy("Comparable brands charge $148", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])

    def test_both_prices_valid(self):
        result = validate_price_accuracy("$50 vs $148 retail", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])

    def test_invented_price_fails(self):
        result = validate_price_accuracy("Now only $39.99!", SAMPLE_PRODUCT)
        self.assertFalse(result["passed"])
        self.assertIn("39.99", result["detail"])

    def test_no_price_passes(self):
        result = validate_price_accuracy("Luxury cashmere for less", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])

    def test_whole_dollar_comparable(self):
        # $148.00 as "148" should be valid
        result = validate_price_accuracy("Brands charge $148 for this", SAMPLE_PRODUCT)
        self.assertTrue(result["passed"])


class TestFullHookValidation(unittest.TestCase):
    """Integration tests running all validation rules on a hook."""

    def test_perfect_hook_passes_all(self):
        results = validate_hook(
            "Ethically sourced Grade-A Mongolian cashmere. Premium quality at $50.",
            "facebook_ad",
            SAMPLE_PRODUCT,
        )
        self.assertTrue(all(r["passed"] for r in results))

    def test_bad_hook_fails_multiple(self):
        results = validate_hook(
            "CHEAP cashmere! 50% off! Free shipping! Buy now for only $29.99! " * 3,
            "facebook_ad",
            SAMPLE_PRODUCT,
        )
        failures = [r for r in results if not r["passed"]]
        # Should fail: character limit, forbidden keywords, hallucination, price accuracy
        self.assertGreaterEqual(len(failures), 3)


class TestPydanticModels(unittest.TestCase):
    """Tests for Pydantic model validation."""

    def test_valid_product(self):
        product = Product(**SAMPLE_PRODUCT)
        self.assertEqual(product.id, "QNC-001")
        self.assertEqual(product.price, 50.00)

    def test_product_price_must_be_positive(self):
        bad_product = {**SAMPLE_PRODUCT, "price": -10}
        with self.assertRaises(Exception):
            Product(**bad_product)

    def test_product_price_less_than_comparable(self):
        bad_product = {**SAMPLE_PRODUCT, "price": 300, "comparable_retail_price": 250}
        with self.assertRaises(Exception):
            Product(**bad_product)

    def test_valid_hookset(self):
        hooks = HookSet(
            educational="Learn about cashmere",
            value_driven="Premium for less",
            lifestyle="Elevate your wardrobe",
        )
        self.assertEqual(hooks.educational, "Learn about cashmere")

    def test_hookset_missing_field(self):
        with self.assertRaises(Exception):
            HookSet(educational="test", value_driven="test")  # missing lifestyle


class TestProductDataIntegrity(unittest.TestCase):
    """Tests that the actual products.json file is valid."""

    def test_all_products_valid(self):
        products_path = os.path.join(os.path.dirname(__file__), "products.json")
        with open(products_path) as f:
            products = json.load(f)

        self.assertGreaterEqual(len(products), 8, "Must have 8+ products")

        for p in products:
            product = Product(**p)
            self.assertTrue(product.price > 0)
            self.assertTrue(product.price < product.comparable_retail_price)
            self.assertTrue(len(product.sizes) > 0)
            self.assertTrue(len(product.colors) > 0)
            self.assertTrue(len(product.key_features) > 0)

    def test_unique_product_ids(self):
        products_path = os.path.join(os.path.dirname(__file__), "products.json")
        with open(products_path) as f:
            products = json.load(f)

        ids = [p["id"] for p in products]
        self.assertEqual(len(ids), len(set(ids)), "Product IDs must be unique")


class TestCrossProductSimilarity(unittest.TestCase):
    """Tests for cross-product deduplication scoring."""

    def setUp(self):
        from quality_judges import cross_product_similarity
        self.cross_product_similarity = cross_product_similarity

    def test_identical_hooks_across_products(self):
        """Identical hooks for different products should be flagged as duplicates."""
        hook_sets = [
            {"product_id": "A", "product_name": "Product A", "channel": "facebook_ad",
             "hooks": {"educational": "100% Grade-A Cashmere", "value_driven": "Fair price", "lifestyle": "Feel great"}},
            {"product_id": "B", "product_name": "Product B", "channel": "facebook_ad",
             "hooks": {"educational": "100% Grade-A Cashmere", "value_driven": "Fair price", "lifestyle": "Feel great"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        self.assertGreater(result["duplicate_pairs_found"], 0)
        self.assertLess(result["corpus_uniqueness"], 1.0)

    def test_unique_hooks_across_products(self):
        """Completely different hooks should have no duplicates."""
        hook_sets = [
            {"product_id": "A", "product_name": "Cashmere Sweater", "channel": "facebook_ad",
             "hooks": {"educational": "15.8 micron cashmere fiber from Mongolia",
                       "value_driven": "$50 versus $148 at traditional retail",
                       "lifestyle": "Sunday morning wrapped in cashmere softness"}},
            {"product_id": "B", "product_name": "Linen Shirt", "channel": "facebook_ad",
             "hooks": {"educational": "European flax linen with OEKO-TEX certification",
                       "value_driven": "Premium dress shirts without department store markup",
                       "lifestyle": "Breathe easy on warm summer evenings"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        self.assertEqual(result["duplicate_pairs_found"], 0)
        self.assertEqual(result["corpus_uniqueness"], 1.0)

    def test_empty_hooks_list(self):
        """Empty input should return perfect uniqueness."""
        result = self.cross_product_similarity([])
        self.assertEqual(result["corpus_uniqueness"], 1.0)
        self.assertEqual(result["duplicate_pairs_found"], 0)

    def test_single_product(self):
        """Single product has no cross-product pairs to compare."""
        hook_sets = [
            {"product_id": "A", "product_name": "Product A", "channel": "facebook_ad",
             "hooks": {"educational": "Test hook", "value_driven": "Another hook", "lifestyle": "Third hook"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        self.assertEqual(result["duplicate_pairs_found"], 0)

    def test_different_channels_not_compared(self):
        """Hooks on different channels should not be compared to each other."""
        hook_sets = [
            {"product_id": "A", "product_name": "Product A", "channel": "facebook_ad",
             "hooks": {"educational": "100% Grade-A Cashmere", "value_driven": "Fair price", "lifestyle": "Feel great"}},
            {"product_id": "B", "product_name": "Product B", "channel": "email_subject",
             "hooks": {"educational": "100% Grade-A Cashmere", "value_driven": "Fair price", "lifestyle": "Feel great"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        # Same text but different channels — should NOT be flagged
        self.assertEqual(result["duplicate_pairs_found"], 0)

    def test_partial_overlap_below_threshold(self):
        """Hooks with <70% word overlap should not be flagged."""
        hook_sets = [
            {"product_id": "A", "product_name": "Product A", "channel": "facebook_ad",
             "hooks": {"educational": "Mongolian cashmere sweater with premium fibers",
                       "value_driven": "x", "lifestyle": "y"}},
            {"product_id": "B", "product_name": "Product B", "channel": "facebook_ad",
             "hooks": {"educational": "European linen shirt with breathable weave",
                       "value_driven": "x2", "lifestyle": "y2"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        # "with" is the only shared word — well below 70%
        edu_dups = [d for d in result["near_duplicates"] if d["hook_type"] == "educational"]
        self.assertEqual(len(edu_dups), 0)

    def test_similarity_value_in_range(self):
        """Similarity scores in duplicates should be between 0.7 and 1.0."""
        hook_sets = [
            {"product_id": "A", "product_name": "Product A", "channel": "sms",
             "hooks": {"educational": "premium cashmere soft warm", "value_driven": "a", "lifestyle": "b"}},
            {"product_id": "B", "product_name": "Product B", "channel": "sms",
             "hooks": {"educational": "premium cashmere soft cozy", "value_driven": "c", "lifestyle": "d"}},
        ]
        result = self.cross_product_similarity(hook_sets)
        for dup in result["near_duplicates"]:
            self.assertGreaterEqual(dup["similarity"], 0.7)
            self.assertLessEqual(dup["similarity"], 1.0)


class TestCompositeScore(unittest.TestCase):
    """Tests for composite quality score computation."""

    def setUp(self):
        from quality_judges import compute_composite_score
        self.compute_composite_score = compute_composite_score

    def test_perfect_scores(self):
        """All perfect inputs should yield composite close to 1.0."""
        result = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 10, "failed": 0},
            grading_report={"average_score": 4.0},
            specificity_scores=[{"specificity_score": 5}] * 10,
            channel_fit_scores=[{"channel_fit_score": 5}] * 10,
            dedup_report={"corpus_uniqueness": 1.0},
        )
        self.assertEqual(result["composite_score"], 1.0)
        self.assertEqual(result["dimensions_evaluated"], 5)

    def test_zero_scores(self):
        """All zero inputs should yield composite of 0.0."""
        result = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 0, "failed": 10},
            grading_report={"average_score": 0.0},
            specificity_scores=[{"specificity_score": 0}] * 10,
            channel_fit_scores=[{"channel_fit_score": 0}] * 10,
            dedup_report={"corpus_uniqueness": 0.0},
        )
        self.assertEqual(result["composite_score"], 0.0)

    def test_skipped_dimensions(self):
        """Skipped dimensions should not affect the score — weights re-normalize."""
        result_full = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 10, "failed": 0},
            grading_report={"average_score": 4.0},
            specificity_scores=[{"specificity_score": 5}] * 10,
            channel_fit_scores=[{"channel_fit_score": 5}] * 10,
            dedup_report={"corpus_uniqueness": 1.0},
        )
        result_partial = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 10, "failed": 0},
            dedup_report={"corpus_uniqueness": 1.0},
        )
        # Both should be 1.0 since all evaluated dimensions are perfect
        self.assertEqual(result_full["composite_score"], 1.0)
        self.assertEqual(result_partial["composite_score"], 1.0)

    def test_dimensions_evaluated_count(self):
        """Should correctly count how many dimensions were evaluated."""
        result = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 10, "failed": 0},
        )
        self.assertEqual(result["dimensions_evaluated"], 1)

    def test_mixed_scores(self):
        """Composite should be a weighted average, not a simple average."""
        result = self.compute_composite_score(
            validation_report={"total_hooks": 10, "passed": 10, "failed": 0},
            dedup_report={"corpus_uniqueness": 0.5},
        )
        # validation=1.0 (weight 0.20) + dedup=0.5 (weight 0.20)
        # weighted = (0.20*1.0 + 0.20*0.5) / (0.20 + 0.20) = 0.30/0.40 = 0.75
        self.assertEqual(result["composite_score"], 0.75)

    def test_empty_validation_report(self):
        """Empty validation report (0 hooks) should handle division by zero."""
        result = self.compute_composite_score(
            validation_report={"total_hooks": 0, "passed": 0, "failed": 0},
        )
        self.assertEqual(result["dimensions_evaluated"], 1)
        self.assertEqual(result["dimensions"]["validation_pass_rate"]["normalized"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
