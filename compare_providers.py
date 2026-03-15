"""
Quince AI Creative Copilot — Multi-Provider Comparison

Runs all configured LLM providers in parallel and saves each provider's
output to a separate file for side-by-side comparison.

Usage:
    # Set multiple API keys, then run:
    GROQ_API_KEY=... ANTHROPIC_API_KEY=... GEMINI_API_KEY=... python3 compare_providers.py

    # Optional flags:
    #   --channels facebook_ad,email_subject   (default: all channels)
    #   --max-products 3                       (default: all products)
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from hook_generator import (
    _create_client,
    _get_model,
    generate_hooks,
    CHANNEL_LIMITS,
)
from validator import validate_hook

# Map env var -> provider name
PROVIDER_ENV_MAP = {
    "GEMINI_API_KEY": "gemini",
    "GROQ_API_KEY": "groq",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
}


def detect_available_providers() -> list:
    """Return list of (provider_name, model) for all configured API keys."""
    available = []
    for env_var, provider in PROVIDER_ENV_MAP.items():
        if os.environ.get(env_var):
            model = _get_model(provider)
            available.append((provider, model))
    return available


def run_provider(provider: str, model: str, products: list, channels: list) -> dict:
    """Run hook generation for a single provider. Returns result dict."""
    client = _create_client(provider)
    all_results = []
    total_passed = 0
    total_hooks = 0
    start = time.time()

    for product in products:
        for channel in channels:
            hooks = generate_hooks(product, channel, client, provider, model)
            passed = 0
            for hook_type, text in hooks.items():
                total_hooks += 1
                results = validate_hook(text, channel, product)
                if all(r["passed"] for r in results):
                    passed += 1
                    total_passed += 1

            all_results.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "channel": channel,
                "hooks": hooks,
            })

    elapsed = time.time() - start
    return {
        "provider": provider,
        "model": model,
        "elapsed_seconds": round(elapsed, 1),
        "total_hooks": total_hooks,
        "passed": total_passed,
        "pass_rate": round(total_passed / total_hooks * 100, 1) if total_hooks else 0,
        "hook_sets": all_results,
    }


def print_comparison(results: list):
    """Print a side-by-side comparison table of provider results."""
    width = 80
    print(f"\n{'=' * width}")
    print("  MULTI-PROVIDER COMPARISON")
    print(f"{'=' * width}")

    # Summary table
    print(f"\n  {'Provider':<15} {'Model':<30} {'Time':>6} {'Pass Rate':>10} {'Hooks':>6}")
    print(f"  {'-'*15} {'-'*30} {'-'*6} {'-'*10} {'-'*6}")
    for r in results:
        print(
            f"  {r['provider']:<15} {r['model']:<30} {r['elapsed_seconds']:>5.1f}s "
            f"{r['pass_rate']:>9.1f}% {r['total_hooks']:>5}"
        )

    # Side-by-side hook samples (first product, first channel)
    print(f"\n{'=' * width}")
    print("  SAMPLE HOOKS (first product, first channel)")
    print(f"{'=' * width}")

    for r in results:
        if not r["hook_sets"]:
            continue
        first = r["hook_sets"][0]
        print(f"\n  [{r['provider'].upper()}] {r['model']}")
        print(f"  Product: {first['product_name']} | Channel: {first['channel']}")
        for hook_type, text in first["hooks"].items():
            label = hook_type.replace("_", " ").title()
            print(f"    {label:15s} ({len(text):3d} chars): \"{text}\"")

    print(f"\n{'=' * width}")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(base_dir, "products.json")) as f:
        products = json.load(f)

    # Parse args
    args = sys.argv[1:]
    channels = list(CHANNEL_LIMITS.keys())
    max_products = len(products)

    for i, arg in enumerate(args):
        if arg == "--channels" and i + 1 < len(args):
            channels = args[i + 1].split(",")
        elif arg == "--max-products" and i + 1 < len(args):
            max_products = int(args[i + 1])

    products = products[:max_products]

    # Detect providers
    providers = detect_available_providers()
    if not providers:
        print("Error: No API keys found.")
        print("Set one or more of: GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY")
        sys.exit(1)

    if len(providers) == 1:
        print(f"Only 1 provider configured ({providers[0][0]}). Set more API keys to compare.")
        print("Continuing with single provider...\n")

    print(f"Providers: {', '.join(f'{p} ({m})' for p, m in providers)}")
    print(f"Products:  {len(products)} | Channels: {', '.join(channels)}")
    print(f"Running {len(providers)} providers in parallel...\n")

    # Run all providers in parallel
    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(run_provider, provider, model, products, channels): provider
            for provider, model in providers
        }
        for future in as_completed(futures):
            provider_name = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(f"  [done] {provider_name} ({result['elapsed_seconds']}s)")
            except Exception as e:
                print(f"  [FAIL] {provider_name}: {e}")

    # Sort by provider name for consistent output
    results.sort(key=lambda r: r["provider"])

    # Save per-provider output files
    output_dir = os.path.join(base_dir, "provider_outputs")
    os.makedirs(output_dir, exist_ok=True)

    for r in results:
        output_path = os.path.join(output_dir, f"hooks_{r['provider']}.json")
        with open(output_path, "w") as f:
            json.dump(r, f, indent=2)
        print(f"  Saved: {output_path}")

    # Save combined comparison
    comparison_path = os.path.join(output_dir, "comparison_summary.json")
    summary = [
        {k: v for k, v in r.items() if k != "hook_sets"}
        for r in results
    ]
    with open(comparison_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print comparison
    print_comparison(results)

    print(f"\nOutput files saved to: {output_dir}/")
    print("  hooks_<provider>.json   — full hook output per provider")
    print("  comparison_summary.json — metrics comparison")


if __name__ == "__main__":
    main()
