"""
Quince AI Creative Copilot — Quick Demo

Generates hooks for 3 products, validates them, runs quality evaluation,
and prints a formatted preview with composite quality score.
Runs in ~15 seconds with any provider.

Usage:
    GROQ_API_KEY=your-key python3 demo.py
"""

import json
import os
import sys

from hook_generator import (
    generate_hooks, _get_provider, _create_client, _get_model, CHANNEL_LIMITS
)
from validator import validate_hook
from quality_judges import cross_product_similarity, compute_composite_score, print_composite_report


def print_hook_card(product_name, channel, char_limit, hooks, product):
    """Print a nicely formatted hook card with validation results."""
    width = 72
    print(f"\n{'=' * width}")
    print(f"  {product_name}")
    print(f"  Channel: {channel} (max {char_limit} chars)")
    print(f"{'-' * width}")

    passed_count = 0
    total_count = 0

    for hook_type, text in hooks.items():
        total_count += 1
        results = validate_hook(text, channel, product)
        all_passed = all(r["passed"] for r in results)
        if all_passed:
            passed_count += 1
        icon = "+" if all_passed else "x"

        label = hook_type.replace("_", " ").title()
        print(f"  [{icon}] {label:15s} ({len(text):3d} chars)")
        print(f"      \"{text}\"")

        if not all_passed:
            for r in results:
                if not r["passed"]:
                    print(f"      -> {r['rule']}: {r['detail']}")

    print(f"{'-' * width}")
    print(f"  Validation: {passed_count}/{total_count} passed")
    print(f"{'=' * width}")

    return passed_count, total_count


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(base_dir, "products.json")) as f:
        products = json.load(f)

    try:
        provider = _get_provider()
    except RuntimeError as e:
        print(f"Error: {e}")
        print("Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY to run the demo.")
        sys.exit(1)

    client = _create_client(provider)
    model = _get_model(provider)

    print(f"Quince AI Creative Copilot — Demo")
    print(f"Provider: {provider} ({model})")
    print(f"Products: {len(products[:3])} (demo subset)")

    # Generate for 3 products across 2 channels
    demo_products = products[:3]
    demo_channels = ["facebook_ad", "email_subject"]

    all_hook_sets = []
    total_passed = 0
    total_hooks = 0

    for product in demo_products:
        for channel in demo_channels:
            print(f"\nGenerating: {product['name'][:40]} ({channel})...", end="", flush=True)
            hooks = generate_hooks(product, channel, client, provider, model)
            print(" done.")

            passed, count = print_hook_card(
                product["name"], channel, CHANNEL_LIMITS[channel], hooks, product
            )
            total_passed += passed
            total_hooks += count

            all_hook_sets.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "channel": channel,
                "hooks": hooks,
            })

    # Run cross-product dedup analysis
    print(f"\n{'=' * 72}")
    print("  QUALITY EVALUATION")
    print(f"{'=' * 72}")

    dedup = cross_product_similarity(all_hook_sets)
    print(f"  Cross-product uniqueness: {dedup['corpus_uniqueness']:.3f}")
    print(f"  Near-duplicate pairs:     {dedup['duplicate_pairs_found']}")

    if dedup["near_duplicates"]:
        print(f"\n  Flagged duplicates:")
        for dup in dedup["near_duplicates"][:3]:
            print(f"    [{dup['hook_type']}] {dup['similarity']:.0%} similar:")
            print(f"      \"{dup['text_a']}\"")
            print(f"      \"{dup['text_b']}\"")

    # Composite score (deterministic only for demo speed)
    validation_report = {"total_hooks": total_hooks, "passed": total_passed, "failed": total_hooks - total_passed}
    composite = compute_composite_score(
        validation_report=validation_report,
        dedup_report=dedup,
    )
    print_composite_report(composite)

    print(f"Demo complete. Run 'python3 pipeline.py' for the full pipeline with LLM judges.")


if __name__ == "__main__":
    main()
