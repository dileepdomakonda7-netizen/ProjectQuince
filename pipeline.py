"""
Quince AI Creative Copilot — Full Pipeline

Single entry point that runs the complete creative pipeline:
1. Validate product data (Pydantic)
2. Generate hooks for all products x channels
3. Run automated validation
4. Run brand voice grading (LLM-as-Copy-Editor)
5. Run quality judges (specificity, channel fit, deduplication)
6. Compute composite quality score

Usage:
    GROQ_API_KEY=your-key python3 pipeline.py
    GROQ_API_KEY=your-key python3 pipeline.py --skip-grading   # skip LLM grading (faster)
    GROQ_API_KEY=your-key python3 pipeline.py --skip-judges    # skip LLM quality judges
    GROQ_API_KEY=your-key python3 pipeline.py --fast           # skip all LLM eval (grading + judges)
"""

import json
import os
import sys
import time

from models import Product
from hook_generator import generate_all_hooks, CHANNEL_LIMITS
from validator import validate_all, print_report


def validate_product_data(products_file: str) -> list:
    """Step 1: Validate product data against Pydantic schema."""
    print("=" * 70)
    print("STEP 1: Validating product data")
    print("=" * 70)

    with open(products_file) as f:
        raw_products = json.load(f)

    validated = []
    for i, p in enumerate(raw_products):
        try:
            product = Product(**p)
            validated.append(p)
            print(f"  OK: {p['id']} - {p['name']}")
        except Exception as e:
            print(f"  FAIL: Product {i} - {e}")

    print(f"\n  {len(validated)}/{len(raw_products)} products valid\n")
    return validated


def generate_hooks_step(products: list, output_path: str) -> str:
    """Step 2: Generate hooks for all products x channels."""
    print("=" * 70)
    print("STEP 2: Generating ad hooks")
    print("=" * 70)

    start = time.time()
    all_results = []

    for channel in CHANNEL_LIMITS:
        results = generate_all_hooks(products, channel)
        all_results.extend(results)

    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    elapsed = time.time() - start
    total_hooks = len(all_results) * 3  # 3 hooks per set
    print(f"\n  Generated {total_hooks} hooks in {elapsed:.1f}s")
    print(f"  Saved to {output_path}\n")
    return output_path


def validate_hooks_step(hooks_file: str, products_file: str) -> dict:
    """Step 3: Run automated validation."""
    print("=" * 70)
    print("STEP 3: Running automated validation")
    print("=" * 70)

    report = validate_all(hooks_file, products_file)
    print_report(report)
    return report


def grade_hooks_step(hooks_file: str, products_file: str) -> dict:
    """Step 4: Run brand voice grading (LLM-as-Copy-Editor)."""
    print("\n" + "=" * 70)
    print("STEP 4: Brand voice grading (LLM-as-Copy-Editor)")
    print("=" * 70)

    from brand_voice_grader import grade_all_hooks
    report = grade_all_hooks(hooks_file, products_file)

    report_path = os.path.join(os.path.dirname(hooks_file), "grading_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report


def quality_judges_step(hooks_file: str, products_file: str, skip_llm: bool = False) -> dict:
    """Step 5: Run quality judges (specificity, channel fit, deduplication)."""
    print("\n" + "=" * 70)
    print("STEP 5: Quality judges (specificity, channel fit, deduplication)")
    print("=" * 70)

    from quality_judges import run_all_judges
    report = run_all_judges(hooks_file, products_file, skip_llm=skip_llm)

    report_path = os.path.join(os.path.dirname(hooks_file), "quality_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report


def composite_score_step(validation_report, grading_report, judges_report):
    """Step 6: Compute and display composite quality score."""
    print("\n" + "=" * 70)
    print("STEP 6: Composite quality score")
    print("=" * 70)

    from quality_judges import compute_composite_score, print_composite_report

    composite = compute_composite_score(
        validation_report=validation_report,
        grading_report=grading_report,
        specificity_scores=judges_report.get("specificity_scores"),
        channel_fit_scores=judges_report.get("channel_fit_scores"),
        dedup_report=judges_report.get("deduplication"),
    )

    print_composite_report(composite)
    return composite


def print_summary(validation_report: dict, grading_report: dict = None,
                  composite: dict = None):
    """Print final pipeline summary."""
    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)

    total = validation_report["total_hooks"]
    passed = validation_report["passed"]
    failed = validation_report["failed"]
    rate = (passed / total * 100) if total > 0 else 0

    print(f"  Hooks generated:        {total}")
    print(f"  Validation pass rate:   {rate:.1f}% ({passed}/{total})")

    if grading_report:
        avg = grading_report.get("average_score", 0)
        perfect = grading_report.get("perfect_score_count", 0)
        graded = grading_report.get("total_hooks_graded", 0)
        print(f"  Brand voice avg score:  {avg:.2f}/4")
        print(f"  Perfect brand scores:   {perfect}/{graded}")

    if composite:
        score = composite.get("composite_score", 0)
        dims = composite.get("dimensions_evaluated", 0)
        print(f"  Composite quality:      {score:.3f}/1.000 ({dims} dimensions)")

    print("=" * 70)

    if failed > 0:
        print("  STATUS: NEEDS REVIEW (some hooks failed validation)")
    elif composite and composite.get("composite_score", 1) < 0.60:
        print("  STATUS: NEEDS WORK (composite score below 0.60)")
    elif grading_report and grading_report.get("average_score", 0) < 3.5:
        print("  STATUS: NEEDS REVIEW (brand voice score below 3.5/4)")
    else:
        print("  STATUS: READY FOR REVIEW")

    print("=" * 70)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    products_file = os.path.join(base_dir, "products.json")
    hooks_file = os.path.join(base_dir, "generated_hooks.json")

    args = sys.argv[1:]
    fast_mode = "--fast" in args
    skip_grading = "--skip-grading" in args or fast_mode
    skip_judges = "--skip-judges" in args or fast_mode

    # Step 1: Validate product data
    products = validate_product_data(products_file)
    if not products:
        print("ERROR: No valid products. Aborting.")
        sys.exit(1)

    # Step 2: Generate hooks
    generate_hooks_step(products, hooks_file)

    # Step 3: Validate hooks
    validation_report = validate_hooks_step(hooks_file, products_file)

    # Step 4: Brand voice grading (optional)
    grading_report = None
    if not skip_grading:
        grading_report = grade_hooks_step(hooks_file, products_file)

    # Step 5: Quality judges (dedup is always run; LLM judges optional)
    judges_report = quality_judges_step(
        hooks_file, products_file, skip_llm=skip_judges
    )

    # Step 6: Composite quality score
    composite = composite_score_step(validation_report, grading_report, judges_report)

    # Save composite to report
    composite_path = os.path.join(base_dir, "composite_report.json")
    with open(composite_path, "w") as f:
        json.dump(composite, f, indent=2)

    # Summary
    print_summary(validation_report, grading_report, composite)


if __name__ == "__main__":
    main()
