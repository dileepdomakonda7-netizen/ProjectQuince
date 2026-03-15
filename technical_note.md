# Technical Note: AI Creative Engine — Pipeline, Metrics & Quality Loop

## 1. The Creative Pipeline

```
Raw Product JSON → Prompt Assembly → LLM Generation → Validation → Channel Formatting → Output
```

**Stage 1 — Data Ingestion:** Product attributes (material, price, sustainability claims, target persona) are loaded from a structured JSON source of truth. This is the *only* data the LLM is allowed to reference.

**Stage 2 — Prompt Assembly:** A channel-aware prompt is constructed that includes: (a) the Quince Brand Voice Rubric as a system prompt, (b) the product JSON, (c) the target channel and its character limits, and (d) the hook type (Educational / Value-Driven / Lifestyle). The prompt explicitly forbids inventing claims not present in the source data.

**Stage 3 — LLM Generation:** The assembled prompt is sent to the generation model (e.g., Claude Sonnet). Structured JSON output is enforced so downstream systems can parse hooks programmatically.

**Stage 4 — Automated Validation:** A deterministic validator checks every hook against character limits, forbidden keywords, hallucination-pattern regexes, and price accuracy against the source JSON. Hooks that fail are flagged for regeneration or human review.

**Stage 5 — Channel Formatting:** Validated hooks are formatted per channel spec — Facebook primary text (≤125 chars), email subject lines (≤60 chars), SMS (≤160 chars) — and batched for delivery to the marketing platform.

## 2. Success Metrics

| Metric | Type | Definition |
|---|---|---|
| **Hook Acceptance Rate** (North Star) | Outcome | % of generated hooks that pass automated validation AND are approved by the marketing team without edits. Target: ≥85%. |
| Brand Voice Alignment Score | Leading | Average score (0–4) from the LLM-as-Copy-Editor grader across the four rubric dimensions. Target: ≥3.5/4. |
| CTR Variance (A/B) | Leading | Standard deviation of click-through rates across hook types per product. Lower variance = more consistent quality. Target: σ < 15% of mean CTR. |
| Generation Cost per Hook | Leading | Average API cost (tokens × price) per accepted hook. Tracks efficiency as prompt engineering improves. Target: < $0.005/hook. |

## 3. The Quality & Testing Loop

### LLM-as-a-Copy-Editor

A *second* LLM call acts as an automated grader. It receives: (1) the generated hook, (2) the original product JSON, and (3) the Brand Voice Rubric. It returns a structured score (0 or 1) for each of the four rubric dimensions (Quality & Premium, Value Proposition, Sustainability, Accuracy) plus a brief justification. Hooks scoring below 4/4 are either auto-regenerated (up to 2 retries) or routed to a human reviewer queue.

This two-model separation ensures the grader is not biased by the generation prompt's framing. The grader prompt is adversarial: it is told to *look for* violations rather than confirm quality.

### Brand Guardrails

Hallucination prevention is layered:

1. **Prompt-level:** The system prompt explicitly lists forbidden patterns (discounts, free shipping, unverified claims) and instructs the model to ONLY reference attributes from the provided JSON.
2. **Deterministic post-processing:** Regex-based checks catch `% off`, `free shipping`, `buy one get one`, fake urgency phrases, and any price not present in the source data.
3. **Fact-verification:** Mentioned prices are cross-referenced against the product JSON. Any price not matching `price` or `comparable_retail_price` triggers a failure.
4. **Keyword blocklist:** Terms like "cheap," "bargain," "clearance," and "blowout" are automatically flagged — these violate Quince's premium positioning.

Together, these layers make it structurally difficult for a hallucinated claim to reach production.

### Quality Judges & Composite Score

Beyond pass/fail validation, a deeper evaluation layer measures *how good* the hooks actually are:

1. **Product Specificity Judge (LLM):** Scores each hook 1–5 on whether it uniquely identifies its product vs. being generic copy that could apply to anything. This catches the most common LLM failure mode — bland, interchangeable output.

2. **Channel-Appropriateness Judge (LLM):** Scores each hook 1–5 on whether it reads naturally for its target channel. A Facebook ad needs scroll-stopping language; an SMS needs conversational tone; an email subject needs a curiosity gap.

3. **Cross-Product Deduplication (deterministic):** Measures word overlap across all hooks for the same channel and hook type. Flags near-duplicate pairs (>70% word similarity) that indicate the generator produced cookie-cutter output instead of product-specific copy.

These signals feed into a **Composite Quality Score** (0.0–1.0) that weights all evaluation dimensions:

| Dimension | Weight |
|---|---|
| Validation pass rate | 20% |
| Brand voice (LLM grader) | 20% |
| Product specificity (LLM judge) | 25% |
| Channel fit (LLM judge) | 15% |
| Corpus uniqueness (deterministic) | 20% |

The composite score provides a single, actionable number: scores above 0.80 indicate strong output; below 0.60 indicates hooks need regeneration with improved prompts. This transforms evaluation from "did it pass?" to "how good is it?"
