# AI Process Log

## The "Speed" Prompt

The following prompt was used to kickstart the core generation logic:

> "Build a Python-based AI Creative Copilot for Quince (a DTC luxury brand). I need:
> 1. A JSON dataset of 10 products with attributes: id, name, category, material, price, comparable_retail_price, target_persona, sustainability, fit, sizes, colors, key_features. Products should span categories like sweaters, tees, accessories, home goods, and outerwear. Use realistic Quince-style products with premium materials (cashmere, silk, organic cotton, Italian leather).
> 2. A hook_generator.py that uses the Anthropic SDK to generate 3 hook types (Educational, Value-Driven, Lifestyle) per product per channel (Facebook Ads ≤125 chars, Email subject ≤60 chars, SMS ≤160 chars). The system prompt must embed the Quince Brand Voice Rubric and forbid hallucinated claims.
> 3. A validator.py that checks generated hooks against: character limits, a forbidden keyword list (cheap, bargain, discount, sale, % off, etc.), regex patterns for hallucinated claims (free shipping, X% off, BOGO), and price accuracy against the source JSON.
> Output as clean, runnable Python files with no unnecessary abstractions."

**What this prompt demonstrates:** Structured constraints (JSON schema, char limits), explicit brand rules embedded in the prompt, and a clear separation of concerns (generator vs. validator).

---

## The "Human" Course Correction

### Bug 1: Validator Price Regex Only Matched Two-Decimal Prices

**The Bug/Issue:** The AI-generated validator used the regex `\$(\d+(?:\.\d{2})?)` to extract prices from hook text. This pattern requires exactly two decimal digits (e.g., `$59.90`) or no decimals at all (e.g., `$59`). However, when running the generator against a live LLM (Groq/Llama 3.3), the model frequently produced prices with a single decimal like `$59.9`, `$39.9`, `$99.9` — which is how Python's `str(59.9)` naturally renders the float. The regex captured only the integer portion (`$59`) and then flagged it as an "unverified price," producing 9 false-positive failures out of 90 hooks (10% failure rate from a validator bug, not a generation bug).

**How I identified it:** After running `python3 validator.py`, the report showed 9 failures — all on `value_driven` hooks, all with the same pattern: the "unverified price" was the integer part of a legitimate product price (e.g., `$39` flagged for a $39.90 product). I traced the root cause through two layers:

1. **Regex layer:** `\$(\d+(?:\.\d{2})?)` — the `{2}` quantifier rejects single-decimal prices. For the text `$39.9`, the regex captures group `"39"` (stops before `.9` since `.9` isn't `.XX`).
2. **Comparison layer:** `"39"` is not in the valid_prices set `{"39.9", "39.90", "150.0", "150.00", "150"}`, so it's flagged as hallucinated.

**The Fix:** Two changes were needed:

```python
# BEFORE (AI-generated):
prices_in_hook = re.findall(r"\$(\d+(?:\.\d{2})?)", hook_text)
valid_prices = {str(product["price"]), str(product.get("comparable_retail_price", ""))}

# AFTER (human fix):
# 1. Regex now accepts 1 or 2 decimal digits
prices_in_hook = re.findall(r"\$(\d+(?:\.\d{1,2})?)", hook_text)

# 2. Valid prices include all format variants (str, .1f, .2f, int)
valid_prices = set()
for field in ("price", "comparable_retail_price"):
    val = product.get(field)
    if val is None:
        continue
    valid_prices.add(str(val))       # "59.9"
    valid_prices.add(f"{val:.2f}")   # "59.90"
    valid_prices.add(f"{val:.1f}")   # "59.9"
    if val == int(val):
        valid_prices.add(str(int(val)))  # "250" for whole-dollar prices
```

After the fix, all 90 hooks passed validation (100% pass rate).

**Why this matters:** This is a two-layer bug — a regex that silently truncates matches combined with an incomplete price-format set. The AI's code looked correct at a glance and even passed unit tests with neatly formatted prices like `$59.90`. It only broke when a real LLM produced the natural Python float representation `$59.9`. This is exactly the kind of edge case where human review of AI output is essential: the validator was supposed to catch LLM errors, but it had its own blind spot that produced false positives and would have eroded trust in the quality pipeline.

---

### Bug 2: Channel-Fit Judge Was Rewarding Patterns That Quince's Own Brand Rules Forbid

**The Bug/Issue:** After wiring up the channel-appropriateness judge in `quality_judges.py`, I ran it on 90 hooks and noticed something contradictory in the results. Several hooks were scoring **4–5/5** on channel fit from the judge while simultaneously scoring **0/1** on the Accuracy dimension from the brand voice grader. The same hook was being rated "excellent channel fit" and "brand violation" at the same time.

I pulled one flagged hook to investigate:
- Hook: `"Don't settle for overpriced cashmere. Get Grade-A Mongolian for $50 — today only."`
- Channel-fit score: **5/5** ("strong urgency, direct CTA, classic Facebook scroll-stopper")
- Brand voice accuracy: **0/1** ("contains 'today only' — fake urgency not in product data")

The channel judge was doing its job correctly by general marketing standards — urgency language *is* what performs well on Facebook. But Quince doesn't play that game. Their entire brand positioning is "elevated, not desperate." The AI-generated judge prompt (`CHANNEL_JUDGE_SYSTEM_PROMPT`) described itself as `"a marketing channel expert"` evaluating against generic channel conventions. It had no idea that Quince deliberately opts out of high-pressure tactics.

**How I identified it:** I wrote a quick script to cross-reference the judge outputs: find any hook where `channel_fit_score >= 4` AND brand voice `accuracy == 0`. There were 7 matches. Every single one used some form of urgency or scarcity language. The two evaluation layers were independently correct but architecturally contradictory — the channel judge was rewarding exactly the tactics that the brand grader was penalizing.

**The Fix:** I embedded Quince-specific channel norms directly into the channel judge's user prompt, replacing generic platform expectations with brand-aware expectations:

```python
# BEFORE (AI-generated):
Channel expectations:
- facebook_ad: Scroll-stopping, urgency-driven, strong CTA. Should trigger
  immediate action. Emotional hooks and FOMO work well.

# AFTER (human fix):
Channel expectations:
- facebook_ad: Scroll-stopping, curiosity-driven, works with visual media.
  Should make someone pause mid-feed. Can be slightly longer and more
  descriptive. Emotional hooks and surprising facts work well.
  NOTE: Quince does NOT use urgency, scarcity, or pressure tactics —
  these should score LOW even though they are common on this channel.
```

The key word changes: `"urgency-driven"` → `"curiosity-driven"`, `"FOMO"` → `"surprising facts"`, added the explicit Quince exception. After the fix, those 7 conflicting hooks dropped to 2–3/5 on channel fit, and the two evaluation layers stopped contradicting each other.

**Why this matters:** This is an *architectural* bug, not a code bug. Both components worked correctly in isolation. The problem was that the AI designed two evaluation subsystems without a shared understanding of the domain constraints. It's the same class of problem you get in microservices when two services implement the same business rule differently. The fix wasn't in either component's logic — it was in aligning their assumptions. In a production system, I'd extract the brand constraints into a shared config that both the grader and all judges reference, so they can't drift apart.

---

### Bug 3: Dedup Similarity Metric Was Biased Against Short Hooks Due to `min()` Denominator

**The Bug/Issue:** The cross-product deduplication in `quality_judges.py` calculates word overlap between hooks grouped by `(channel, hook_type)`. The AI-generated similarity formula on line 161 was:

```python
overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
```

This uses the **overlap coefficient** — dividing the intersection by the *smaller* set. The problem: this massively inflates similarity scores when one hook is short. For example:

- Hook A (email subject, 7 words): `"Premium cashmere at a fair price"`
- Hook B (email subject, 14 words): `"Premium cashmere crewneck at a fair price — 15.8 micron Grade-A Mongolian"`

Shared words: `{premium, cashmere, at, a, fair, price}` = 6 words.
- With `min()` denominator: 6 / min(7, 14) = 6/7 = **0.86** → flagged as near-duplicate
- With Jaccard (union) denominator: 6 / 15 = **0.40** → not flagged

Hook B is *clearly* better — it has 7 additional words with real product specifics (crewneck, 15.8 micron, Grade-A, Mongolian). But the `min()` metric treats it as a duplicate of Hook A because Hook A is entirely *contained within* Hook B.

**How I identified it:** The dedup report was flagging 52 near-duplicate pairs, which seemed excessive. I sampled 10 flagged pairs and noticed a pattern: in 8 of them, one hook was noticeably shorter than the other. The shorter hook had generic language like `"Luxury for less"` and the longer one was a genuinely improved version with product specifics. The metric was penalizing the *better* hook for containing the same common words as the worse one.

I also noticed this was specifically hammering email subject hooks — which have a 60-char limit and naturally share common short phrases. A 7-word email subject and a 10-word email subject will share a high % of words just because there aren't enough words to differentiate.

**The Fix:** Switched from overlap coefficient to Jaccard similarity (intersection / union):

```python
# BEFORE (AI-generated — overlap coefficient):
overlap = len(words_a & words_b) / min(len(words_a), len(words_b))

# AFTER (human fix — Jaccard index):
intersection = words_a & words_b
union = words_a | words_b
overlap = len(intersection) / len(union) if union else 0.0
```

After the fix, flagged pairs dropped from 52 to 37. The 15 pairs that were de-flagged were all cases where a longer, more specific hook was being unfairly penalized for containing the same base words as a shorter, weaker hook. The remaining 37 were genuine near-duplicates — hooks that were truly interchangeable.

**Why this matters:** The `min()` vs Jaccard distinction is subtle but has real consequences. The overlap coefficient asks *"what fraction of the smaller set is contained in the larger?"* — which is the wrong question for dedup. The right question is *"if I merged these two hooks' vocabularies, how much redundancy is there?"* — which is what Jaccard measures. The AI picked a valid similarity metric (overlap coefficient is used in information retrieval), but it wasn't the right metric for this specific use case. Choosing between similar-sounding algorithms based on what you actually want to measure is exactly the kind of judgment call that requires understanding the problem domain, not just the math.

---

## Iteration Log: Judge Prompt Engineering

**Context:** After building the quality judges, I noticed the specificity judge (`SPECIFICITY_SYSTEM_PROMPT`) was clustering most hooks around 3–4/5 — a compressed range that doesn't give useful signal.

**The problem with the AI-generated prompt:** The AI wrote a clean scoring rubric (1–5 scale with descriptions), but the examples it used were too abstract. The rubric said `"1 = Completely generic"` and `"5 = Uniquely identifiable"` — but without concrete examples tied to *this* product catalog, the LLM defaulted to a generous center.

**What I changed:** I added a concrete Quince-specific calibration line to the system prompt:

```
Be strict. Generic hooks that could apply to any cashmere sweater or any
sheet set should score low, even if they sound nice. The goal is to reward
copy that uses unique product attributes.
```

This single sentence — anchoring "generic" to the actual categories in our data (cashmere sweaters, sheet sets) — shifted the score distribution from a narrow 3–4 range to a spread across 1–5, because the judge now had concrete context for what "generic" means *in this corpus*. The LLM could picture the 4 cashmere products and recognize that `"Grade-A cashmere, ethically sourced"` doesn't distinguish any of them.

**Takeaway:** LLM judges need domain-specific calibration, not just abstract rubrics. A scoring rubric that says "1 = bad, 5 = good" gives you nothing. A rubric that says "1 = could describe any cashmere sweater in our catalog" gives you a real signal.

---

## Iteration Log: Multi-Provider Comparison

**Context:** The original implementation was hardcoded to Anthropic's Claude API. During development I hit rate limits and realized I needed to test multiple models to compare hook quality and pick the best one for the final output.

**Prompt used:**
> "Refactor `hook_generator.py` to support multiple LLM providers (Anthropic, Groq/Llama, OpenAI, Gemini). Auto-detect the provider based on which API key is set in environment variables. The Groq provider should use the OpenAI SDK with a custom base_url. Keep the same function signatures."

**What the AI got right:** Clean provider abstraction with `_get_provider()`, `_create_client()`, `_get_model()`, and `_call_llm()` functions. The Groq integration using OpenAI SDK with a custom base URL was correct on the first try.

**What I changed manually:** The AI put Anthropic as the first priority in `_get_provider()`. I reordered to check Groq first since it's free — makes the project runnable by any reviewer without spending API credits. Small change, big impact on first-run experience.

**Later addition:** After getting multi-provider working sequentially, I realized running them one-at-a-time was slow and I couldn't easily diff the outputs. So I built `compare_providers.py` — it detects all configured providers from env vars, runs them in parallel using `ThreadPoolExecutor`, saves per-provider output to `provider_outputs/hooks_<provider>.json`, and prints a comparison table (speed, pass rate, sample hooks). This is the kind of tool I'd want in production: before committing to a model, you A/B test outputs side-by-side.
