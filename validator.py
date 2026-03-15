"""
Quince AI Creative Copilot — Automated Validator

Validates generated ad hooks against:
1. Channel character limits
2. Forbidden keywords (brand guardrails)
3. Hallucination checks (invented discounts, fake features)
"""

import json
import os
import re
import sys

from hook_generator import CHANNEL_LIMITS, FORBIDDEN_KEYWORDS

# Patterns that indicate hallucinated claims
HALLUCINATION_PATTERNS = [
    r"\d+%\s*off",                    # "50% off"
    r"free\s+shipping",               # "free shipping"
    r"buy\s+one\s+get\s+one",         # BOGO
    r"limited\s+time\s+offer",        # urgency hacks
    r"today\s+only",                  # fake urgency
    r"while\s+supplies\s+last",       # scarcity
    r"order\s+now",                   # pressure tactics
    r"\$\d+\s+off",                   # "$20 off"
]


def validate_character_limit(hook_text: str, channel: str) -> dict:
    """Check if hook exceeds the channel's character limit."""
    limit = CHANNEL_LIMITS[channel]
    length = len(hook_text)
    passed = length <= limit
    return {
        "rule": "character_limit",
        "passed": passed,
        "detail": f"{length}/{limit} chars" if passed else f"OVER by {length - limit} chars ({length}/{limit})",
    }


def validate_forbidden_keywords(hook_text: str) -> dict:
    """Check if hook contains any forbidden keywords."""
    text_lower = hook_text.lower()
    found = [kw for kw in FORBIDDEN_KEYWORDS if kw in text_lower]
    return {
        "rule": "forbidden_keywords",
        "passed": len(found) == 0,
        "detail": f"Found: {found}" if found else "Clean",
    }


def validate_hallucination_patterns(hook_text: str) -> dict:
    """Check for patterns that suggest hallucinated claims."""
    text_lower = hook_text.lower()
    found = [p for p in HALLUCINATION_PATTERNS if re.search(p, text_lower)]
    return {
        "rule": "hallucination_check",
        "passed": len(found) == 0,
        "detail": f"Suspicious patterns: {found}" if found else "Clean",
    }


def validate_price_accuracy(hook_text: str, product: dict) -> dict:
    """Check that any price mentioned in the hook matches the product data."""
    prices_in_hook = re.findall(r"\$(\d+(?:\.\d{1,2})?)", hook_text)
    valid_prices = set()
    for field in ("price", "comparable_retail_price"):
        val = product.get(field)
        if val is None:
            continue
        valid_prices.add(str(val))
        valid_prices.add(f"{val:.2f}")
        valid_prices.add(f"{val:.1f}")
        if val == int(val):
            valid_prices.add(str(int(val)))

    invalid = [p for p in prices_in_hook if p not in valid_prices]
    return {
        "rule": "price_accuracy",
        "passed": len(invalid) == 0,
        "detail": f"Unverified prices: ${', $'.join(invalid)}" if invalid else "Clean",
    }


def validate_hook_diversity(hooks: dict, channel: str) -> list:
    """Check that the 3 hooks within a set are diverse and not repetitive."""
    results = []
    texts = list(hooks.values())
    char_limit = CHANNEL_LIMITS[channel]
    min_chars = int(char_limit * 0.4)

    # Check minimum length — hooks shouldn't waste available space
    for hook_type, text in hooks.items():
        if len(text) < min_chars:
            results.append({
                "rule": "min_length",
                "passed": False,
                "detail": f"{hook_type}: only {len(text)} chars, minimum is {min_chars} for {channel}",
            })

    # Check that hooks don't start with the same word
    first_words = [t.split()[0].lower() if t.split() else "" for t in texts]
    if len(first_words) != len(set(first_words)):
        results.append({
            "rule": "diversity_opening",
            "passed": False,
            "detail": f"Multiple hooks start with the same word: {first_words}",
        })

    # Check word overlap — hooks sharing >60% words are too similar
    def word_set(text):
        return set(re.findall(r'\w+', text.lower()))

    hook_types = list(hooks.keys())
    for i in range(len(hook_types)):
        for j in range(i + 1, len(hook_types)):
            words_a = word_set(hooks[hook_types[i]])
            words_b = word_set(hooks[hook_types[j]])
            if not words_a or not words_b:
                continue
            overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
            if overlap > 0.6:
                results.append({
                    "rule": "diversity_content",
                    "passed": False,
                    "detail": f"{hook_types[i]} and {hook_types[j]} share {overlap:.0%} of words — too similar",
                })

    return results


def validate_hook(hook_text: str, channel: str, product: dict) -> list:
    """Run all validations on a single hook."""
    return [
        validate_character_limit(hook_text, channel),
        validate_forbidden_keywords(hook_text),
        validate_hallucination_patterns(hook_text),
        validate_price_accuracy(hook_text, product),
    ]


def validate_all(hooks_file: str, products_file: str) -> dict:
    """Validate all generated hooks against all rules."""
    with open(hooks_file) as f:
        hook_sets = json.load(f)
    with open(products_file) as f:
        products = json.load(f)

    product_map = {p["id"]: p for p in products}
    report = {"total_hooks": 0, "passed": 0, "failed": 0, "failures": []}

    diversity_warnings = []

    for hook_set in hook_sets:
        product = product_map[hook_set["product_id"]]
        channel = hook_set["channel"]

        # Per-hook validation
        for hook_type, hook_text in hook_set["hooks"].items():
            report["total_hooks"] += 1
            results = validate_hook(hook_text, channel, product)
            all_passed = all(r["passed"] for r in results)

            if all_passed:
                report["passed"] += 1
            else:
                report["failed"] += 1
                failures = [r for r in results if not r["passed"]]
                report["failures"].append({
                    "product": hook_set["product_name"],
                    "channel": channel,
                    "hook_type": hook_type,
                    "hook_text": hook_text,
                    "violations": failures,
                })

        # Per-set diversity validation (warnings, not failures)
        diversity_issues = validate_hook_diversity(hook_set["hooks"], channel)
        if diversity_issues:
            diversity_warnings.append({
                "product": hook_set["product_name"],
                "channel": channel,
                "issues": diversity_issues,
            })

    report["diversity_warnings"] = diversity_warnings

    return report


def print_report(report: dict):
    """Print a human-readable validation report."""
    print("=" * 70)
    print("QUINCE CREATIVE COPILOT — VALIDATION REPORT")
    print("=" * 70)
    print(f"Total hooks validated: {report['total_hooks']}")
    print(f"Passed: {report['passed']}")
    print(f"Failed: {report['failed']}")
    pass_rate = (report["passed"] / report["total_hooks"] * 100) if report["total_hooks"] > 0 else 0
    print(f"Pass rate: {pass_rate:.1f}%")
    print()

    if report["failures"]:
        print("FAILURES:")
        print("-" * 70)
        for f in report["failures"]:
            print(f"  Product:   {f['product']}")
            print(f"  Channel:   {f['channel']}")
            print(f"  Hook Type: {f['hook_type']}")
            print(f"  Text:      \"{f['hook_text']}\"")
            for v in f["violations"]:
                print(f"    FAIL [{v['rule']}]: {v['detail']}")
            print()
    else:
        print("All hooks passed validation!")

    # Diversity warnings
    warnings = report.get("diversity_warnings", [])
    if warnings:
        print(f"\nDIVERSITY WARNINGS ({len(warnings)} hook sets):")
        print("-" * 70)
        for w in warnings:
            print(f"  Product: {w['product']} ({w['channel']})")
            for issue in w["issues"]:
                print(f"    WARN [{issue['rule']}]: {issue['detail']}")
            print()

    print("=" * 70)


def main():
    base_dir = os.path.dirname(__file__)
    hooks_file = os.path.join(base_dir, "generated_hooks.json")
    products_file = os.path.join(base_dir, "products.json")

    if not os.path.exists(hooks_file):
        print(f"Error: {hooks_file} not found. Run hook_generator.py first.")
        sys.exit(1)

    report = validate_all(hooks_file, products_file)
    print_report(report)

    report_path = os.path.join(base_dir, "validation_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {report_path}")

    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
