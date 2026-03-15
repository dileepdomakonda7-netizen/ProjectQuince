"""
Quince AI Creative Copilot — Brand Voice Grader (LLM-as-a-Copy-Editor)

Uses a SECOND LLM call to grade generated hooks against the Quince Brand Voice Rubric.
This is the implementation of the "Quality Loop" described in the technical note.

The grader is intentionally adversarial — it looks for violations rather than confirming quality.
"""

import json
import os

GRADER_SYSTEM_PROMPT = """You are a strict brand compliance auditor for Quince, a premium DTC brand.
Your job is to FIND VIOLATIONS in marketing copy. Be critical and adversarial — do not give the
benefit of the doubt.

You will receive:
1. A marketing hook (the text to grade)
2. The original product data (the ONLY facts allowed)
3. The Brand Voice Rubric (your scoring criteria)

Score each dimension 0 or 1. A score of 0 means ANY violation in that dimension.
Be especially strict about the Accuracy dimension — if the hook mentions ANY fact
not present in the product data, score it 0."""

GRADER_RUBRIC = """
Brand Voice Rubric:

| Attribute | Pass (1) | Fail (0) |
|---|---|---|
| Quality & Premium | Uses elevated language like "ethically sourced," "premium," "artisan" | Uses "cheap," "bargain," or aggressive infomercial slang |
| Value Proposition | Focuses on investment value or lack of retail markups | Mentions specific % off sales or discounts NOT in product data |
| Sustainability | Mentions ONLY sustainability factors from the product JSON | Makes sweeping unverified claims (e.g., "100% eco-friendly") not in source |
| Accuracy (Guardrail) | ALL attributes (price, material, fit) match the product JSON exactly | Invents sales, free shipping, or features NOT in the input |
"""


def grade_hook(hook_text: str, product: dict, hook_type: str, channel: str,
               client=None, provider=None, model=None) -> dict:
    """
    Grade a single hook against the Brand Voice Rubric using a second LLM call.

    Returns a dict with scores (0 or 1) for each rubric dimension plus justification.
    """
    from hook_generator import _get_provider, _create_client, _get_model, _call_llm

    if provider is None:
        provider = _get_provider()
    if client is None:
        client = _create_client(provider)
    if model is None:
        model = _get_model(provider)

    product_json = json.dumps(product, indent=2)

    user_prompt = f"""Grade the following marketing hook against the Quince Brand Voice Rubric.

HOOK TO GRADE:
"{hook_text}"

HOOK TYPE: {hook_type}
CHANNEL: {channel}

ORIGINAL PRODUCT DATA (the ONLY allowed source of facts):
{product_json}

{GRADER_RUBRIC}

Score each dimension 0 or 1. Return ONLY valid JSON (no markdown, no code fences):
{{
  "quality_premium": 0 or 1,
  "value_proposition": 0 or 1,
  "sustainability": 0 or 1,
  "accuracy": 0 or 1,
  "justification": "<brief explanation of any failures>"
}}"""

    raw_text = _call_llm(client, provider, model, GRADER_SYSTEM_PROMPT, user_prompt)

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()

    scores = json.loads(raw_text)
    return scores


def grade_all_hooks(hooks_file: str, products_file: str) -> dict:
    """Grade all generated hooks and produce a quality report."""
    from hook_generator import _get_provider, _create_client, _get_model

    with open(hooks_file) as f:
        hook_sets = json.load(f)
    with open(products_file) as f:
        products = json.load(f)

    product_map = {p["id"]: p for p in products}

    provider = _get_provider()
    client = _create_client(provider)
    model = _get_model(provider)

    print(f"Grading hooks with: {provider} ({model})")
    print(f"{'='*70}")

    results = []
    total_score = 0
    total_possible = 0

    for hook_set in hook_sets:
        product = product_map[hook_set["product_id"]]
        channel = hook_set["channel"]

        for hook_type, hook_text in hook_set["hooks"].items():
            print(f"  Grading: {hook_set['product_name'][:30]:30s} | {channel:15s} | {hook_type}...")

            try:
                scores = grade_hook(
                    hook_text, product, hook_type, channel,
                    client=client, provider=provider, model=model
                )
                score_total = sum(scores.get(k, 0) for k in [
                    "quality_premium", "value_proposition", "sustainability", "accuracy"
                ])
                total_score += score_total
                total_possible += 4

                results.append({
                    "product": hook_set["product_name"],
                    "channel": channel,
                    "hook_type": hook_type,
                    "hook_text": hook_text,
                    "scores": scores,
                    "total": score_total,
                })

                status = "PASS" if score_total == 4 else f"FAIL ({score_total}/4)"
                print(f"    -> {status}")

                if score_total < 4:
                    print(f"    -> {scores.get('justification', 'No justification')}")

            except Exception as e:
                print(f"    -> ERROR: {e}")
                results.append({
                    "product": hook_set["product_name"],
                    "channel": channel,
                    "hook_type": hook_type,
                    "hook_text": hook_text,
                    "scores": None,
                    "error": str(e),
                    "total": 0,
                })
                total_possible += 4

    # Summary
    avg_score = (total_score / total_possible * 4) if total_possible > 0 else 0
    perfect = sum(1 for r in results if r.get("total") == 4)
    failed = sum(1 for r in results if r.get("total", 0) < 4)

    report = {
        "total_hooks_graded": len(results),
        "perfect_score_count": perfect,
        "failed_count": failed,
        "average_score": round(avg_score, 2),
        "total_points": total_score,
        "total_possible": total_possible,
        "details": results,
    }

    print(f"\n{'='*70}")
    print(f"BRAND VOICE GRADING REPORT")
    print(f"{'='*70}")
    print(f"Hooks graded:     {len(results)}")
    print(f"Perfect (4/4):    {perfect}")
    print(f"Failed (<4/4):    {failed}")
    print(f"Average score:    {avg_score:.2f}/4")
    print(f"{'='*70}")

    return report


def main():
    base_dir = os.path.dirname(__file__)
    hooks_file = os.path.join(base_dir, "generated_hooks.json")
    products_file = os.path.join(base_dir, "products.json")

    report = grade_all_hooks(hooks_file, products_file)

    report_path = os.path.join(base_dir, "grading_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
