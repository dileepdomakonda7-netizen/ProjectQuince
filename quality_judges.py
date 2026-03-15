"""
Quince AI Creative Copilot — Quality Judges & Composite Scorer

Three evaluation layers beyond basic validation:
1. Product Specificity Judge (LLM) — scores how uniquely a hook identifies its product
2. Channel-Appropriateness Judge (LLM) — scores tone/style fit for the channel
3. Composite Quality Score — weighted aggregate of all eval signals into one number

Usage:
    python3 quality_judges.py                    # Run all judges on generated_hooks.json
    python3 quality_judges.py --skip-llm         # Only run deterministic evals
"""

import json
import os
import re
import sys
from collections import defaultdict


# ---------------------------------------------------------------------------
# 1. Product Specificity Judge (LLM-based)
# ---------------------------------------------------------------------------

SPECIFICITY_SYSTEM_PROMPT = """You are an evaluation judge for marketing copy.
Your job is to score how product-specific a hook is — could this hook ONLY be about
this exact product, or is it generic enough to apply to any product in the category?

Be strict. Generic hooks that could apply to any cashmere sweater or any sheet set
should score low, even if they sound nice. The goal is to reward copy that uses
unique product attributes."""

SPECIFICITY_USER_PROMPT = """Score this marketing hook for product-specificity.

HOOK: "{hook_text}"
CHANNEL: {channel}
HOOK TYPE: {hook_type}

PRODUCT DATA (the product this hook is supposed to be about):
{product_json}

Scoring rubric:
1 = Completely generic — "Premium for less" could be any product from any brand
2 = Category-generic — "100% cashmere" applies to any cashmere product, not THIS one
3 = Brand-specific but not product-specific — mentions Quince values but no unique product attributes
4 = Product-specific — references at least one unique attribute (specific price, micron count, certification number, etc.)
5 = Uniquely identifiable — someone could identify the exact product from the hook alone

Return ONLY valid JSON (no markdown, no code fences):
{{"specificity_score": <1-5>, "unique_attributes_used": [<list of specific attributes from product data used in hook>], "reasoning": "<brief explanation>"}}"""


# ---------------------------------------------------------------------------
# 2. Channel-Appropriateness Judge (LLM-based)
# ---------------------------------------------------------------------------

CHANNEL_JUDGE_SYSTEM_PROMPT = """You are a marketing channel expert evaluating whether
ad copy matches the tone, style, and conventions of its target channel. Each channel
has distinct expectations — what works in a Facebook ad fails as an SMS, and vice versa."""

CHANNEL_JUDGE_USER_PROMPT = """Score this hook for channel-appropriateness.

HOOK: "{hook_text}"
CHANNEL: {channel}
HOOK TYPE: {hook_type}

Channel expectations:
- facebook_ad: Scroll-stopping, curiosity-driven, works with visual media. Should make someone pause mid-feed. Can be slightly longer and more descriptive. Emotional hooks and surprising facts work well.
- email_subject: Must create open-worthy intrigue. Subject lines succeed through curiosity gaps, clear personal value, or unexpected specificity. Avoid sounding like marketing — aim for something a friend might write.
- sms: Conversational, direct, feels personal. SMS is an intimate channel — corporate or overly polished tone feels invasive. Short declarative sentences. Can use casual punctuation.

Scoring rubric:
1 = Wrong tone entirely — e.g., corporate press release as SMS, or clickbait as email subject
2 = Technically acceptable but generic — doesn't leverage channel strengths
3 = Decent channel fit — reads naturally for the channel but not optimized
4 = Good channel fit — leverages channel-specific conventions effectively
5 = Perfect channel native — reads like it was written by someone who only writes for this channel

Return ONLY valid JSON (no markdown, no code fences):
{{"channel_fit_score": <1-5>, "reasoning": "<brief explanation>"}}"""


def _judge_hook(hook_text, product, hook_type, channel, system_prompt, user_prompt_template,
                client=None, provider=None, model=None):
    """Run a single LLM judge call and parse the JSON result."""
    from hook_generator import _get_provider, _create_client, _get_model, _call_llm, _parse_json_response

    if provider is None:
        provider = _get_provider()
    if client is None:
        client = _create_client(provider)
    if model is None:
        model = _get_model(provider)

    product_json = json.dumps(product, indent=2)
    user_prompt = user_prompt_template.format(
        hook_text=hook_text,
        channel=channel,
        hook_type=hook_type,
        product_json=product_json,
    )

    raw_text = _call_llm(client, provider, model, system_prompt, user_prompt)
    return _parse_json_response(raw_text)


def judge_specificity(hook_text, product, hook_type, channel, **kwargs):
    """Score a hook's product-specificity (1-5)."""
    return _judge_hook(
        hook_text, product, hook_type, channel,
        SPECIFICITY_SYSTEM_PROMPT, SPECIFICITY_USER_PROMPT, **kwargs
    )


def judge_channel_fit(hook_text, product, hook_type, channel, **kwargs):
    """Score a hook's channel-appropriateness (1-5)."""
    return _judge_hook(
        hook_text, product, hook_type, channel,
        CHANNEL_JUDGE_SYSTEM_PROMPT, CHANNEL_JUDGE_USER_PROMPT, **kwargs
    )


# ---------------------------------------------------------------------------
# 3. Cross-Product Deduplication (deterministic — no LLM)
# ---------------------------------------------------------------------------

def cross_product_similarity(all_hooks: list) -> dict:
    """
    Score uniqueness across ALL generated hooks, not just within a set.
    Groups hooks by (channel, hook_type) and finds near-duplicates across products.

    Returns:
        {
            "corpus_uniqueness": 0.0-1.0,
            "near_duplicates": [...],
            "total_pairs_checked": int,
            "duplicate_pairs_found": int,
        }
    """
    by_channel_type = defaultdict(list)
    for hook_set in all_hooks:
        for hook_type, text in hook_set["hooks"].items():
            by_channel_type[(hook_set["channel"], hook_type)].append({
                "product": hook_set["product_name"],
                "product_id": hook_set["product_id"],
                "text": text,
                "words": set(re.findall(r'\w+', text.lower())),
            })

    duplicates = []
    total_pairs = 0

    for key, hooks in by_channel_type.items():
        for i in range(len(hooks)):
            for j in range(i + 1, len(hooks)):
                total_pairs += 1
                words_a = hooks[i]["words"]
                words_b = hooks[j]["words"]
                if not words_a or not words_b:
                    continue
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap > 0.7:
                    duplicates.append({
                        "channel": key[0],
                        "hook_type": key[1],
                        "product_a": hooks[i]["product"],
                        "product_b": hooks[j]["product"],
                        "similarity": round(overlap, 2),
                        "text_a": hooks[i]["text"],
                        "text_b": hooks[j]["text"],
                    })

    uniqueness = 1.0 - (len(duplicates) / max(1, total_pairs))
    return {
        "corpus_uniqueness": round(uniqueness, 3),
        "total_pairs_checked": total_pairs,
        "duplicate_pairs_found": len(duplicates),
        "near_duplicates": duplicates,
    }


# ---------------------------------------------------------------------------
# 4. Composite Quality Score
# ---------------------------------------------------------------------------

# Weights for each eval dimension — must sum to 1.0
COMPOSITE_WEIGHTS = {
    "validation_pass_rate": 0.20,
    "brand_voice": 0.20,
    "product_specificity": 0.25,
    "channel_fit": 0.15,
    "corpus_uniqueness": 0.20,
}


def compute_composite_score(
    validation_report: dict,
    grading_report: dict = None,
    specificity_scores: list = None,
    channel_fit_scores: list = None,
    dedup_report: dict = None,
) -> dict:
    """
    Combine all eval signals into a single weighted quality score (0.0 - 1.0).

    Each dimension is normalized to 0.0-1.0 before weighting:
    - validation_pass_rate: passed / total (already 0-1)
    - brand_voice: average_score / 4 (scale 0-4 → 0-1)
    - product_specificity: average / 5 (scale 1-5 → 0-1)
    - channel_fit: average / 5 (scale 1-5 → 0-1)
    - corpus_uniqueness: already 0-1
    """
    dimensions = {}

    # Validation pass rate
    total = validation_report.get("total_hooks", 0)
    passed = validation_report.get("passed", 0)
    dimensions["validation_pass_rate"] = {
        "raw": f"{passed}/{total}",
        "normalized": round(passed / max(1, total), 3),
    }

    # Brand voice (optional — requires LLM grading)
    if grading_report:
        avg = grading_report.get("average_score", 0)
        dimensions["brand_voice"] = {
            "raw": f"{avg:.2f}/4",
            "normalized": round(avg / 4, 3),
        }
    else:
        dimensions["brand_voice"] = {"raw": "skipped", "normalized": None}

    # Product specificity (optional — requires LLM judge)
    if specificity_scores:
        avg_spec = sum(s["specificity_score"] for s in specificity_scores) / len(specificity_scores)
        dimensions["product_specificity"] = {
            "raw": f"{avg_spec:.2f}/5",
            "normalized": round(avg_spec / 5, 3),
        }
    else:
        dimensions["product_specificity"] = {"raw": "skipped", "normalized": None}

    # Channel fit (optional — requires LLM judge)
    if channel_fit_scores:
        avg_fit = sum(s["channel_fit_score"] for s in channel_fit_scores) / len(channel_fit_scores)
        dimensions["channel_fit"] = {
            "raw": f"{avg_fit:.2f}/5",
            "normalized": round(avg_fit / 5, 3),
        }
    else:
        dimensions["channel_fit"] = {"raw": "skipped", "normalized": None}

    # Corpus uniqueness (deterministic)
    if dedup_report:
        uniqueness = dedup_report.get("corpus_uniqueness", 0)
        dimensions["corpus_uniqueness"] = {
            "raw": f"{uniqueness:.3f}",
            "normalized": round(uniqueness, 3),
        }
    else:
        dimensions["corpus_uniqueness"] = {"raw": "skipped", "normalized": None}

    # Compute weighted composite — only include dimensions that were evaluated
    weighted_sum = 0.0
    weight_sum = 0.0
    for dim_name, weight in COMPOSITE_WEIGHTS.items():
        norm = dimensions[dim_name]["normalized"]
        if norm is not None:
            weighted_sum += weight * norm
            weight_sum += weight

    composite = round(weighted_sum / max(0.001, weight_sum), 3) if weight_sum > 0 else 0.0

    return {
        "composite_score": composite,
        "dimensions": dimensions,
        "weights": COMPOSITE_WEIGHTS,
        "dimensions_evaluated": sum(1 for d in dimensions.values() if d["normalized"] is not None),
        "dimensions_total": len(COMPOSITE_WEIGHTS),
    }


def print_composite_report(composite: dict):
    """Print a formatted composite quality report."""
    score = composite["composite_score"]
    dims = composite["dimensions"]

    print("\n" + "=" * 70)
    print("COMPOSITE QUALITY SCORE")
    print("=" * 70)

    for name, weight in COMPOSITE_WEIGHTS.items():
        d = dims[name]
        norm = d["normalized"]
        raw = d["raw"]
        w_pct = f"{weight * 100:.0f}%"
        if norm is not None:
            bar = "█" * int(norm * 20) + "░" * (20 - int(norm * 20))
            weighted = norm * weight
            print(f"  {name:25s} {bar} {norm:.3f}  (raw: {raw:>10s}, weight: {w_pct})")
        else:
            print(f"  {name:25s} {'░' * 20} —      (skipped,       weight: {w_pct})")

    print(f"\n  {'COMPOSITE SCORE':25s} {'█' * int(score * 20)}{'░' * (20 - int(score * 20))} {score:.3f}")
    print()

    if score >= 0.80:
        print("  VERDICT: STRONG — hooks are specific, diverse, and channel-appropriate")
    elif score >= 0.60:
        print("  VERDICT: ACCEPTABLE — meets baseline but has room for improvement")
    elif score >= 0.40:
        print("  VERDICT: NEEDS WORK — significant quality gaps detected")
    else:
        print("  VERDICT: POOR — hooks lack specificity and diversity")

    print("=" * 70)


# ---------------------------------------------------------------------------
# 5. Run All Judges
# ---------------------------------------------------------------------------

def run_all_judges(hooks_file: str, products_file: str, skip_llm: bool = False) -> dict:
    """
    Run all quality judges and compute composite score.

    Args:
        hooks_file: Path to generated_hooks.json
        products_file: Path to products.json
        skip_llm: If True, only run deterministic evals (dedup)
    """
    with open(hooks_file) as f:
        hook_sets = json.load(f)
    with open(products_file) as f:
        products = json.load(f)

    product_map = {p["id"]: p for p in products}

    # Always run cross-product dedup (deterministic, free)
    print("  Running cross-product deduplication analysis...")
    dedup_report = cross_product_similarity(hook_sets)
    print(f"    Pairs checked: {dedup_report['total_pairs_checked']}")
    print(f"    Near-duplicates found: {dedup_report['duplicate_pairs_found']}")
    print(f"    Corpus uniqueness: {dedup_report['corpus_uniqueness']:.3f}")

    if dedup_report["near_duplicates"]:
        print(f"\n    Top near-duplicates:")
        for dup in dedup_report["near_duplicates"][:5]:
            print(f"      [{dup['channel']}/{dup['hook_type']}] {dup['similarity']:.0%} similar:")
            print(f"        {dup['product_a']}: \"{dup['text_a']}\"")
            print(f"        {dup['product_b']}: \"{dup['text_b']}\"")

    specificity_scores = []
    channel_fit_scores = []

    if not skip_llm:
        from hook_generator import _get_provider, _create_client, _get_model

        provider = _get_provider()
        client = _create_client(provider)
        model = _get_model(provider)
        print(f"\n  Running LLM judges with: {provider} ({model})")

        for hook_set in hook_sets:
            product = product_map[hook_set["product_id"]]
            channel = hook_set["channel"]

            for hook_type, hook_text in hook_set["hooks"].items():
                label = f"{hook_set['product_name'][:25]:25s} | {channel:15s} | {hook_type}"
                print(f"    Judging: {label}...", end=" ", flush=True)

                try:
                    spec = judge_specificity(
                        hook_text, product, hook_type, channel,
                        client=client, provider=provider, model=model,
                    )
                    spec["product"] = hook_set["product_name"]
                    spec["channel"] = channel
                    spec["hook_type"] = hook_type
                    spec["hook_text"] = hook_text
                    specificity_scores.append(spec)

                    fit = judge_channel_fit(
                        hook_text, product, hook_type, channel,
                        client=client, provider=provider, model=model,
                    )
                    fit["product"] = hook_set["product_name"]
                    fit["channel"] = channel
                    fit["hook_type"] = hook_type
                    fit["hook_text"] = hook_text
                    channel_fit_scores.append(fit)

                    s = spec.get("specificity_score", "?")
                    c = fit.get("channel_fit_score", "?")
                    print(f"specificity={s}/5, channel_fit={c}/5")

                except Exception as e:
                    print(f"ERROR: {e}")

    report = {
        "deduplication": dedup_report,
        "specificity_scores": specificity_scores,
        "channel_fit_scores": channel_fit_scores,
    }

    return report


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    hooks_file = os.path.join(base_dir, "generated_hooks.json")
    products_file = os.path.join(base_dir, "products.json")

    if not os.path.exists(hooks_file):
        print(f"Error: {hooks_file} not found. Run hook_generator.py first.")
        sys.exit(1)

    skip_llm = "--skip-llm" in sys.argv

    print("=" * 70)
    print("QUINCE QUALITY JUDGES")
    print("=" * 70)

    report = run_all_judges(hooks_file, products_file, skip_llm=skip_llm)

    # Load validation report if it exists for composite scoring
    validation_file = os.path.join(base_dir, "validation_report.json")
    grading_file = os.path.join(base_dir, "grading_report.json")

    validation_report = {}
    if os.path.exists(validation_file):
        with open(validation_file) as f:
            validation_report = json.load(f)
    else:
        # Run validation inline
        from validator import validate_all
        validation_report = validate_all(hooks_file, products_file)

    grading_report = None
    if os.path.exists(grading_file):
        with open(grading_file) as f:
            grading_report = json.load(f)

    composite = compute_composite_score(
        validation_report=validation_report,
        grading_report=grading_report,
        specificity_scores=report["specificity_scores"],
        channel_fit_scores=report["channel_fit_scores"],
        dedup_report=report["deduplication"],
    )

    print_composite_report(composite)

    # Save full report
    full_report = {**report, "composite": composite}
    report_path = os.path.join(base_dir, "quality_report.json")
    with open(report_path, "w") as f:
        json.dump(full_report, f, indent=2)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
