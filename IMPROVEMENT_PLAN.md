# Improvement Plan — Quince AI Creative Copilot

## Current State Assessment

The project covers all three required deliverables (technical note, codebase, AI process log) and adds bonus features (brand voice grader, Pydantic models, unit tests, pipeline orchestrator, real Quince data). The architecture and documentation are strong.

**However, the single biggest weakness that an interviewer will notice immediately is the quality of the generated hooks in `generated_hooks.json`.** This undermines the entire submission because the output is what the interviewer will judge first.

---

## Critical Issue: Generated Hook Quality

Looking at the actual output in `generated_hooks.json`, the hooks have serious problems:

### Problem 1: Extreme Repetition
- Almost every `lifestyle` hook starts with **"Elevate"** — the exact word the prompt says to NEVER use
- `educational` hooks for cashmere products are nearly identical: "100% Grade-A Mongolian Cashmere" appears 6+ times verbatim
- Email subject hooks are carbon copies across products ("Luxury cashmere, radically fair price" x3)

### Problem 2: Hooks Are Too Short / Generic
- Many email hooks are 20-30 characters when the limit is 60. The prompt says use between 60% and 100% of the limit but the model ignores it.
- "Premium for less" (15 chars) is a wasted email subject line — it's generic and could apply to any product from any brand
- "Sleep cool, live well" says nothing about the product, the material, or Quince

### Problem 3: Value-Driven Hooks Rarely Show the Value
- Most value-driven hooks say "fairly priced" or "minus the markup" without mentioning actual prices
- The whole point of value-driven hooks is "$50 vs $148 retail" — the price gap IS the hook
- Only a handful actually include dollar amounts

### Problem 4: No Product Differentiation
- A cashmere sweater and a cashmere tee get nearly identical hooks
- The beanie, tee, and crewneck hooks are interchangeable
- Material specs (micron count, gauge, fiber length) are almost never used despite being in the data

**Why this matters for the interview:** The evaluator will open `generated_hooks.json`, skim 5-6 entries, see "Elevate your [X] with [Y]" repeated everywhere, and conclude the prompt engineering doesn't work. This overshadows all the good architecture work.

---

## Improvement Plan (Priority Order)

### 1. Re-generate Hooks with Better Output Quality (HIGH — directly visible to interviewer)

**What:** Re-run `hook_generator.py` with a higher-quality model (Claude or GPT-4o) and improved prompt engineering to produce diverse, specific, compelling hooks.

**Why the interviewer cares:** *"Implementation clarity: Clean, readable code that solves the core problem effectively."* The core problem is generating good ad copy. If the output is generic, the solution doesn't effectively solve the problem regardless of how clean the code is.

**Specific changes needed:**
- Use Claude Sonnet or GPT-4o instead of Groq/Llama for the final submission output (keep multi-provider support but ship good output)
- Add few-shot examples in the prompt — show the model what a GOOD hook looks like vs a BAD one
- Add a negative examples section: "DO NOT produce hooks like: 'Elevate your X with Y' or 'Premium Z, fairly priced'"
- Enforce product-specific details: "Each hook MUST reference at least one specific attribute from the product data (e.g., '15.8 micron', '22-momme', 'OEKO-TEX certified')"
- Add a diversity constraint: "All three hooks must start with different words and use different selling angles"

**Expected result:** Hooks like:
- Educational: "Grade-A cashmere starts at 15.8 microns — finer than most luxury brands. Ours comes from free-roaming Mongolian goats."
- Value: "$50 for the same 15.8-micron cashmere that retails for $148. No middleman. No markup."
- Lifestyle: "Sunday morning, coffee in hand, wrapped in cashmere so soft it feels like a secret."

vs what we have now:
- "100% Grade-A Mongolian Cashmere"
- "Luxury cashmere, radically fair price"
- "Elevate your everyday with cashmere"

---

### 2. Add a Hook Diversity Validator Rule (HIGH — shows reliability thinking)

**What:** Add a 5th validation rule that checks for repetition/diversity across hooks within a product AND across products.

**Why the interviewer cares:** *"Reliability thinking: Thoughtfulness around validating outputs and preventing incorrect results."* The current validator catches keyword/hallucination issues but completely misses the most common LLM failure mode: repetitive, low-effort output.

**Specific checks:**
- No two hooks within a set should share >50% of their words (catches "Elevate your X" pattern)
- No hook should be shorter than 60% of the channel's character limit (catches lazy short hooks)
- No hook should start with the same word as another hook in the same set
- Cross-product: flag if >30% of hooks across all products for a channel are near-duplicates (Jaccard similarity)

**Why this is impressive:** It shows you understand that validation isn't just about catching bad content — it's about ensuring the AI actually does useful work. A hook that passes all keyword checks but says nothing specific is still a failure.

---

### 3. Add a Quick Demo Script / `make demo` (MEDIUM — reduces friction for evaluator)

**What:** Create a `demo.py` or a Makefile target that generates hooks for 1-2 products, validates them, and prints a nicely formatted side-by-side comparison — all in ~10 seconds with no setup beyond an API key.

**Why the interviewer cares:** The evaluator will spend 15-30 minutes reviewing. If they can run one command and immediately see the system working end-to-end, that's far more impressive than reading code. First impressions matter.

**Implementation:**
```
$ GROQ_API_KEY=xxx python3 demo.py

╔══════════════════════════════════════════════════════════════╗
║  Mongolian Cashmere Crewneck Sweater — Facebook Ad (≤125)   ║
╠══════════════════════════════════════════════════════════════╣
║  Educational: Grade-A cashmere at 15.8 microns — finer      ║
║               than most luxury brands use. (87 chars) ✓      ║
║  Value:       $50 for the same cashmere that costs $148      ║
║               at traditional retailers. (78 chars) ✓         ║
║  Lifestyle:   Sunday mornings deserve cashmere this soft.    ║
║               Ethically sourced. (65 chars) ✓                ║
╠══════════════════════════════════════════════════════════════╣
║  Validation: 3/3 passed | Brand Voice: 4/4                   ║
╚══════════════════════════════════════════════════════════════╝
```

---

### 4. Add a `README.md` with a 30-Second Overview (MEDIUM — first thing evaluator sees)

**What:** A concise README that gives the evaluator immediate orientation. Not a replacement for WALKTHROUGH.md — a complement.

**Why the interviewer cares:** *"Communication: A short written explanation of your approach and design decisions."* The WALKTHROUGH.md is excellent but it's 600+ lines. The evaluator needs a 30-second entry point.

**Structure:**
```
# Quince AI Creative Copilot

## Quick Start (3 commands)
## What This Does (1 paragraph)
## Architecture (1 diagram)
## Files (table)
## See Also: WALKTHROUGH.md for detailed design decisions
```

---

### 5. Add Integration Test That Runs the Full Pipeline (MEDIUM — shows reliability thinking)

**What:** A test that generates hooks for 1 product, validates them, and asserts the pipeline works end-to-end. Uses a mock/stub LLM response so it runs without an API key.

**Why the interviewer cares:** Unit tests are great but they only test the validator in isolation. An integration test that proves the pipeline works end-to-end (with a canned LLM response) shows systems-level thinking.

**Implementation:**
- Add a `test_pipeline.py` with a fixture that stubs `_call_llm` to return a known-good JSON response
- Test the full flow: product validation → hook generation → validation → all pass
- Also test with a known-bad response (hallucinated prices) to prove the validator catches it
- Runs without API key (`python3 -m pytest test_pipeline.py`)

---

### 6. Handle Edge Cases in `brand_voice_grader.py` (LOW — code quality polish)

**What:** The grader uses a simpler JSON parsing approach than `hook_generator.py`. It should reuse the robust `_parse_json_response` function.

**Why:** Consistency. If the evaluator reads both files and sees the generator handles code fences robustly but the grader doesn't, it looks like an oversight.

**Changes:**
- Import and reuse `_parse_json_response` from `hook_generator.py`
- Add error handling with retry (currently a single JSON parse failure crashes the grader)

---

### 7. Add Temperature/Top-p Control to Generator (LOW — shows LLM expertise)

**What:** Expose `temperature` as a parameter with sensible defaults per hook type.

**Why the interviewer cares:** It shows you understand LLM parameters beyond just "call the API." Educational hooks should be more factual (lower temperature), lifestyle hooks can be more creative (higher temperature).

**Implementation:**
```python
HOOK_TEMPERATURES = {
    "educational": 0.3,   # More factual, less creative
    "value_driven": 0.4,  # Balanced
    "lifestyle": 0.7,     # More creative
}
```

Note: This would require generating hooks individually rather than all 3 in one call, which increases API cost. Worth noting as a tradeoff in the walkthrough.

---

## Summary: What to Prioritize

| # | Improvement | Impact | Effort | Evaluator Signal |
|---|---|---|---|---|
| 1 | Re-generate hooks with quality output | **Critical** | Low | "The output actually works" |
| 2 | Hook diversity validator | High | Medium | Reliability thinking |
| 3 | Demo script | Medium | Low | Reduces evaluator friction |
| 4 | Concise README | Medium | Low | Communication |
| 5 | Integration test with mock LLM | Medium | Medium | Systems thinking |
| 6 | Robust JSON parsing in grader | Low | Low | Code quality |
| 7 | Temperature control | Low | Low | LLM expertise |

**If time is limited, do #1 and #2 only.** The generated hooks are the biggest liability — they're what the interviewer will look at first and judge most harshly. Everything else is polish on top of an already solid architecture.

---

## Mapping to Evaluation Criteria

| Criterion | Current Strength | Gap | Fix |
|---|---|---|---|
| **Problem decomposition** | Strong (5-stage pipeline, clear separation) | None major | — |
| **Implementation clarity** | Strong (clean code, good naming) | Output quality undermines it | #1 |
| **AI-assisted development** | Strong (real bug documented) | — | — |
| **Reliability thinking** | Good (4 validation rules) | Doesn't catch the most common failure: repetition | #2 |
| **Communication** | Thorough walkthrough | No quick entry point | #4 |
