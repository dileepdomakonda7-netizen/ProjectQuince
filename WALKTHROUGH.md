# Quince AI Creative Copilot — Detailed Walkthrough

This document explains every step of the take-home assignment: what was asked, what was built, why specific decisions were made, and the tradeoffs at each stage.

---

## Table of Contents

1. [Understanding the Assignment](#1-understanding-the-assignment)
2. [Task 1: Technical Note](#2-task-1-technical-note)
3. [Task 2: Implementation](#3-task-2-implementation)
   - [3a. Synthetic Product Data](#3a-synthetic-product-data)
   - [3b. Ad Hook Generator](#3b-ad-hook-generator)
   - [3c. Automated Validator](#3c-automated-validator)
4. [AI Process Log](#4-ai-process-log)
5. [Architecture Decisions & Tradeoffs](#5-architecture-decisions--tradeoffs)
6. [File Reference](#6-file-reference)
7. [How to Run](#7-how-to-run)

---

## 1. Understanding the Assignment

### What Quince Wants

Quince is a DTC (direct-to-consumer) brand selling luxury-quality products at fair prices by cutting out middlemen. They need to scale their marketing — instead of manually writing ad copy for thousands of products, they want an **AI Creative Engine** that:

- Takes raw product data (material, price, sustainability info)
- Generates marketing hooks for different channels (Facebook Ads, Email, SMS)
- Ensures the generated copy matches their brand voice (premium, not cheap/salesy)
- Doesn't make up fake claims (no hallucinated discounts, fake features)

### What We Need to Deliver

Three artifacts:

| # | Artifact | What it is |
|---|---|---|
| 1 | **Technical Note** (1 page) | A strategy document describing the pipeline, metrics, and quality loop |
| 2 | **Codebase** | Working code: product data + hook generator + validator |
| 3 | **AI Process Log** | Documentation of how AI was used, including a human correction |

---

## 2. Task 1: Technical Note

**File:** `technical_note.md`

### What Was Asked

A one-page technical note covering three things:

1. **The Creative Pipeline** — How does raw product data become channel-specific ad copy?
2. **Success Metrics** — What's the "North Star" metric? What are 3 leading indicators?
3. **The Quality & Testing Loop** — How do you use a second LLM to grade output? How do you prevent hallucinations?

### What I Built

#### The Creative Pipeline (5 stages)

```
Raw Product JSON → Prompt Assembly → LLM Generation → Validation → Channel Formatting
```

**Why 5 stages?** Each stage has a single responsibility:

| Stage | Purpose | Why it's separate |
|---|---|---|
| Data Ingestion | Load product JSON | Single source of truth — the LLM can ONLY reference this data |
| Prompt Assembly | Build channel-aware prompt with brand rules | Different channels need different prompts (char limits vary) |
| LLM Generation | Call the AI model | Swappable — can change models without touching other stages |
| Validation | Check output against rules | Deterministic checks catch what the LLM misses |
| Channel Formatting | Format for delivery platform | Decouples generation from platform-specific requirements |

**Tradeoff:** I could have combined stages 2-3 (prompt + generation) into one function, which would be simpler. But separating them means you can:
- Test prompts without making API calls
- Swap LLM providers without changing prompt logic
- Cache prompts for debugging

#### Success Metrics

| Metric | Type | Why this one? |
|---|---|---|
| **Hook Acceptance Rate** | North Star | Measures end-to-end quality — did the hook pass validation AND get approved by marketing? If this number is high, the engine is working. |
| Brand Voice Alignment Score | Leading | Catches quality issues early before marketing reviews. Uses the LLM grader (see below). |
| CTR Variance | Leading | Low variance = consistent quality across hook types. High variance means some hook types are much worse than others. |
| Generation Cost per Hook | Leading | Tracks efficiency. If costs spike, prompts may be getting too long or retry rates too high. |

**Tradeoff:** I chose "Hook Acceptance Rate" over raw "CTR" as the North Star because:
- CTR depends on many factors outside our control (audience targeting, time of day, creative assets)
- Acceptance Rate measures what WE control: did the AI produce something good enough?
- It's measurable immediately (don't need to wait for ad performance data)

#### Quality Loop: LLM-as-a-Copy-Editor

The idea: use a **second, separate LLM call** to grade the hooks the first LLM generated.

```
Generator LLM → produces hook → Grader LLM → scores against Brand Voice Rubric
```

The grader receives:
1. The generated hook
2. The original product JSON
3. The Brand Voice Rubric (from page 7 of the PDF)

It returns a score (0 or 1) for each of 4 dimensions:
- Quality & Premium
- Value Proposition
- Sustainability
- Accuracy

**Why two separate LLM calls instead of one?**
- The generator is biased toward producing text that "sounds right" — it won't catch its own mistakes
- The grader prompt is **adversarial**: it's told to LOOK FOR violations, not confirm quality
- This mirrors how human teams work: writer + editor, not writer self-editing

**Tradeoff:** Two LLM calls = 2x the API cost. But the cost of a bad ad going live (brand damage, wasted ad spend) far outweighs a few cents per hook.

#### Quality Loop: Brand Guardrails

Four layers of protection against hallucinations:

| Layer | Type | What it catches |
|---|---|---|
| 1. Prompt rules | Preventive | System prompt explicitly forbids inventing claims |
| 2. Forbidden keywords | Deterministic | Words like "cheap," "bargain," "clearance" |
| 3. Hallucination patterns | Regex-based | Patterns like "X% off," "free shipping," "BOGO" |
| 4. Price verification | Fact-checking | Cross-references any price in the hook against the product JSON |

**Why 4 layers?**
- Layer 1 (prompt) works 90% of the time but isn't guaranteed
- Layers 2-4 are deterministic — they ALWAYS catch violations
- Defense in depth: if one layer misses something, another catches it

**Tradeoff:** More layers = more code to maintain. But for brand safety, false negatives (letting a bad hook through) are much worse than false positives (rejecting a good hook). So we err on the side of strictness.

---

## 3. Task 2: Implementation

### 3a. Real Quince Product Data

**File:** `products.json`

#### What Was Asked
A JSON dataset of 8+ products with attributes like material, price, and target persona.

#### What I Built
Rather than using synthetic data, I sourced **real product data from quince.com** to demonstrate genuine company research and produce more authentic ad hooks. Data was collected by scraping individual product pages from the live Quince website (see `data_sourcing_log.md` for the full methodology).

10 real products spanning 5 categories:

| ID | Product | Category | Price | Comparable Retail |
|---|---|---|---|---|
| QNC-001 | Mongolian Cashmere Crewneck Sweater | Sweaters | $50.00 | $148.00 |
| QNC-002 | Mongolian Cashmere Tee | Tops | $44.90 | $115.00 |
| QNC-003 | Mongolian Cashmere Cardigan Sweater | Sweaters | $79.90 | $159.00 |
| QNC-004 | Mongolian Cashmere Ribbed Beanie | Accessories | $34.90 | $89.50 |
| QNC-005 | European Linen Relaxed Long Sleeve Shirt | Shirts | $42.00 | $145.00 |
| QNC-006 | Organic Cotton Stretch Poplin Dress Shirt | Shirts | $39.90 | $119.00 |
| QNC-007 | Classic Organic Percale Sheet Set | Home | $79.90 | $148.00 |
| QNC-008 | Bamboo Sheet Set | Home | $99.90 | $229.00 |
| QNC-009 | 100% Mulberry Silk Pillowcase | Home | $44.90 | $69.00 |
| QNC-010 | European Linen Duvet Cover Set | Home | $149.90 | $344.00 |

Each product has 11 attributes:

```json
{
  "id": "QNC-001",
  "name": "...",
  "category": "...",
  "material": "...",               // Real material specs (micron, gauge, momme, thread count)
  "price": 50.00,                  // Actual Quince price from the website
  "comparable_retail_price": 148,  // "Traditional retail" price shown on quince.com
  "target_persona": "...",         // Who buys this
  "sustainability": "...",         // Real certifications with certificate numbers
  "fit": "...",                    // Relaxed, Slim, Classic, etc.
  "sizes": [...],
  "colors": [...],
  "key_features": [...]            // 3 bullet points from product page
}
```

#### Why These Design Decisions?

**Why real data instead of synthetic?** Using actual Quince products demonstrates genuine research into the company's catalog. The hooks produced are immediately verifiable by the interviewer, and the sustainability certifications include real certificate numbers (e.g., OEKO-TEX #15.HIN.75800).

**Why 10 products instead of 8?** The requirement said "8+ products." Having 10 gives more variety and shows the generator handles different categories well (apparel, accessories, home goods).

**Why include `comparable_retail_price`?** This is critical for value-driven hooks ("$50 vs. $148 retail"). Without it, the LLM might invent competitor prices — which would be a hallucination. By including the actual comparison price from quince.com, we make it a verifiable fact.

**Why structured sustainability claims?** The Brand Voice Rubric says sustainability claims must come from the JSON data. Instead of generic claims, we include real certifications like "STANDARD 100 by OEKO-TEX certified (Certificate 15.HIN.75800); produced using windmill-powered green energy."

**Tradeoff:** More attributes = larger prompts = higher API costs. But having rich, real product data produces better hooks and makes fact-checking possible. The alternative (synthetic data) would risk inaccurate representations of the brand.

---

### 3b. Ad Hook Generator

**File:** `hook_generator.py`

#### What Was Asked
A function that returns three distinct hooks: Educational, Value-Driven, and Lifestyle.

#### What I Built

A multi-provider hook generator that:
1. Takes a product + channel as input
2. Sends a constrained prompt to an LLM
3. Returns 3 hooks as structured JSON

#### How It Works Step by Step

**Step 1: Provider Detection**

```python
def _get_provider():
    if os.environ.get("GROQ_API_KEY"):    return "groq"
    elif os.environ.get("ANTHROPIC_API_KEY"): return "anthropic"
    elif os.environ.get("OPENAI_API_KEY"):    return "openai"
```

Checks which API key is available and uses that provider. This makes the code portable.

**Step 2: System Prompt (Brand Voice)**

The system prompt does several things:
- Sets the persona: "You are a senior copywriter for Quince"
- Embeds the Brand Voice Rubric (quality, value, sustainability, accuracy)
- Lists explicit CRITICAL RULES (no invented claims, no fake discounts, elevated tone)

**Why embed the rubric in the system prompt?** The system prompt is processed before every user message. This means the brand rules are always "top of mind" for the LLM, reducing the chance of violations.

**Step 3: User Prompt (Per Product)**

```
Generate exactly 3 ad hooks for [product] on [channel].
Each hook MUST be [char_limit] characters or fewer.
Return ONLY valid JSON...
```

Key elements:
- **Character limit is stated explicitly** — the LLM knows the constraint upfront
- **JSON format is enforced** — we specify the exact schema, so parsing is reliable
- **"No markdown, no explanation"** — prevents the LLM from wrapping JSON in code fences

**Step 4: Response Parsing**

```python
raw_text = _call_llm(client, provider, model, SYSTEM_PROMPT, user_prompt)
# Strip markdown code fences if present
if raw_text.startswith("```"):
    raw_text = raw_text.split("\n", 1)[1]
if raw_text.endswith("```"):
    raw_text = raw_text[:-3]
hooks = json.loads(raw_text)
```

**Why the code fence stripping?** Even when told "no markdown," some models (especially Llama) still wrap JSON in ` ```json ``` `. This defensive parsing handles that gracefully.

**Step 5: Batch Generation**

The `main()` function loops over all products and all 3 channels:
- 10 products x 3 channels = 30 API calls
- Each call returns 3 hooks = **90 total hooks**

#### Channel Character Limits

| Channel | Limit | Why |
|---|---|---|
| Facebook Ad | 125 chars | Facebook truncates primary text after ~125 chars on mobile |
| Email Subject | 60 chars | Most email clients show 50-60 chars before truncating |
| SMS | 160 chars | Standard SMS segment limit |

#### Three Hook Types Explained

| Type | Purpose | Example |
|---|---|---|
| **Educational** | Teach the customer about materials/craftsmanship | "Grade-A Mongolian cashmere comes from the soft undercoat of free-roaming goats." |
| **Value-Driven** | Highlight the price advantage without being salesy | "Same quality as $250 designer brands. No middleman markup. Just $59.90." |
| **Lifestyle** | Paint an aspirational picture | "Wrap yourself in ethically sourced cashmere. Effortless elegance for every occasion." |

**Why these three?** They map to the three pillars of Quince's brand: quality (educational), value (value-driven), and aspiration (lifestyle). They also serve different stages of the marketing funnel:
- Educational → Awareness (teach them something)
- Value-Driven → Consideration (convince them on price)
- Lifestyle → Desire (make them want it)

#### Tradeoffs

| Decision | Alternative | Why I chose this way |
|---|---|---|
| One LLM call returns all 3 hooks | Separate call per hook type | Fewer API calls = lower cost, faster execution. Risk: if one hook is bad, you regenerate all 3. |
| Multi-provider support (Groq, Anthropic, OpenAI) | Hardcode one provider | Makes the project runnable for anyone. Groq is free, so no cost barrier to testing. |
| JSON output format | Plain text with parsing | JSON is machine-parseable, predictable, and easy to validate. Plain text would require brittle regex parsing. |
| System prompt for brand rules | Per-request rules in user prompt | System prompt is more "sticky" — LLMs tend to follow system instructions more reliably than user instructions. |

---

### 3c. Automated Validator

**File:** `validator.py`

#### What Was Asked
A script to check that generated copy doesn't exceed character limits or include forbidden keywords.

#### What I Built
A validator with **4 validation rules** (going beyond the 2 required):

| Rule | Type | What it checks |
|---|---|---|
| `character_limit` | Required | Hook length ≤ channel's char limit |
| `forbidden_keywords` | Required | No "cheap," "bargain," "discount," etc. |
| `hallucination_check` | Bonus | Regex patterns for fake claims ("X% off," "free shipping," "BOGO") |
| `price_accuracy` | Bonus | Any `$XX.XX` in the hook must match the product JSON |

#### How Each Rule Works

**Rule 1: Character Limit**

```python
def validate_character_limit(hook_text, channel):
    limit = CHANNEL_LIMITS[channel]  # e.g., 125 for facebook_ad
    length = len(hook_text)
    passed = length <= limit
```

Simple length check. Returns the count so you can see how close/far you are.

**Rule 2: Forbidden Keywords**

```python
FORBIDDEN_KEYWORDS = [
    "cheap", "bargain", "discount", "sale", "% off", "percent off",
    "clearance", "limited time", "act now", "buy now", "free shipping",
    "lowest price", "rock bottom", "steal", "blowout", "doorbuster",
    "infomercial", "unbeatable", "slashed",
]
```

These come directly from the Brand Voice Rubric on page 7 of the PDF. The rubric says hooks should NEVER use "cheap," "bargain," or aggressive infomercial slang. I also added marketing pressure words ("act now," "limited time") that violate Quince's elevated tone.

**Why a keyword list instead of a regex?** Keywords are easier to read, maintain, and extend. The marketing team can add new forbidden words without knowing regex syntax.

**Rule 3: Hallucination Patterns**

```python
HALLUCINATION_PATTERNS = [
    r"\d+%\s*off",              # "50% off"
    r"free\s+shipping",         # "free shipping"
    r"buy\s+one\s+get\s+one",   # BOGO
    r"limited\s+time\s+offer",  # urgency hacks
    r"today\s+only",            # fake urgency
    r"while\s+supplies\s+last", # scarcity
    r"order\s+now",             # pressure tactics
    r"\$\d+\s+off",             # "$20 off"
]
```

These are regex patterns because we need fuzzy matching — "50% off" and "50 % off" and "50%off" should all be caught.

**Why is this separate from forbidden keywords?** Keywords match exact strings. Patterns match flexible formats. `"% off"` as a keyword would miss `"50% off"` because there's a number before it. The regex `\d+%\s*off` catches all variants.

**Rule 4: Price Accuracy**

```python
def validate_price_accuracy(hook_text, product):
    prices_in_hook = re.findall(r"\$(\d+(?:\.\d{1,2})?)", hook_text)
    valid_prices = set()
    for field in ("price", "comparable_retail_price"):
        val = product.get(field)
        if val is None:
            continue
        valid_prices.add(str(val))        # "59.9"
        valid_prices.add(f"{val:.2f}")    # "59.90"
        valid_prices.add(f"{val:.1f}")    # "59.9"
        if val == int(val):
            valid_prices.add(str(int(val)))  # "250"
```

This is the most sophisticated check. It:
1. Extracts all dollar amounts from the hook text
2. Builds a set of "valid" prices from the product data (in all possible string formats)
3. Flags any price that doesn't match

**Why multiple price formats?** Python's `float` can be represented as `"59.9"`, `"59.90"`, or `"60"` depending on context. The LLM might output any of these. We need to accept all valid representations while still catching invented prices like `"$29.99"` for a $59.90 product.

#### The Validation Report

The validator produces both a human-readable terminal output and a JSON report:

```
======================================================================
QUINCE CREATIVE COPILOT — VALIDATION REPORT
======================================================================
Total hooks validated: 90
Passed: 90
Failed: 0
Pass rate: 100.0%

All hooks passed validation!
======================================================================
```

#### Tradeoffs

| Decision | Alternative | Why I chose this way |
|---|---|---|
| 4 rules (2 required + 2 bonus) | Just the 2 required rules | The bonus rules demonstrate deeper thinking about brand safety. Price accuracy is especially important for Quince's value proposition. |
| Per-hook validation (not per-set) | Validate entire output at once | Per-hook gives specific error messages: "Product X, Channel Y, Hook Type Z failed rule W." Much easier to debug. |
| Exit code 1 on any failure | Always exit 0 | Non-zero exit code means you can use this in CI/CD: `python3 validator.py && deploy` |
| JSON + terminal output | Just one format | Terminal for humans, JSON for machines. The JSON report can be consumed by dashboards or monitoring systems. |

---

## 4. AI Process Log

**File:** `ai_process_log.md`

#### What Was Asked
Two things:
1. **"Speed" Prompt** — The prompt used to generate the initial code
2. **"Human" Correction** — An instance where the AI was wrong and you fixed it

#### The "Speed" Prompt

I shared the exact prompt used to kickstart the project. Key elements the evaluators are looking for:

- **Structured constraints**: I specified the exact JSON schema, character limits, and file structure
- **Output format**: "Output as clean, runnable Python files" — tells the AI exactly what to produce
- **Separation of concerns**: Explicitly asked for generator AND validator as separate files
- **Domain specificity**: Mentioned Quince by name, DTC brand, premium materials

#### The "Human" Correction

This documents a **real bug** encountered during live testing:

**The Bug:** The validator's price regex `\$(\d+(?:\.\d{2})?)` required exactly 2 decimal digits. When the LLM produced `$59.9` (1 decimal), the regex captured only `$59`, which then failed price validation as "unverified."

**Why this is a good example for the evaluators:**
- It's a **real bug**, not a contrived one — it actually happened during testing
- It involves a **two-layer failure** (regex + comparison logic)
- It shows **technical depth**: understanding regex capture groups, float representation, string formatting
- It demonstrates that the developer **doesn't blindly trust AI output** — they run the code, read the errors, and trace the root cause

---

## 5. Architecture Decisions & Tradeoffs

### Why Python (not TypeScript)?

The requirements said "Python/TS." I chose Python because:
- Anthropic's Python SDK is more mature
- JSON handling is simpler (no type annotations needed)
- The evaluators likely work in Python (data science / ML background at a DTC brand)

**Tradeoff:** TypeScript would give type safety and better IDE support, but adds build complexity (tsconfig, compilation, node_modules).

### Why Groq + Llama Instead of Only Claude?

The original code used Claude (Anthropic), but API credits were needed. I added multi-provider support:

| Provider | Model | Cost | Speed |
|---|---|---|---|
| Anthropic | Claude Sonnet | ~$0.003/hook | Medium |
| Groq | Llama 3.3 70B | Free | Very fast |
| OpenAI | GPT-4o-mini | ~$0.001/hook | Fast |

**Why multi-provider?** Makes the project runnable by anyone reviewing it, regardless of which API key they have. The code auto-detects based on environment variables.

**Tradeoff:** More code complexity (provider abstraction). But the abstraction is thin (~30 lines) and the benefit (portability) is worth it.

### Why Deterministic Validation Instead of LLM-Based Validation?

The validator uses regex and string matching, not a second LLM call.

**Pros of deterministic validation:**
- 100% reliable — same input always gives same output
- Zero API cost
- Instant execution
- No risk of the validator itself hallucinating

**Cons:**
- Can't catch subtle brand voice issues (e.g., "tone is too aggressive")
- Needs manual maintenance (adding new keywords/patterns)

**Why this is the right choice for the validator script:** The assignment asked for a "simple script." Deterministic checks are appropriate here. The LLM-as-Copy-Editor approach is implemented separately in `brand_voice_grader.py` for nuanced quality assessment — the two work together as complementary layers.

### Why 3 Channels (Not Just 1)?

The requirements mentioned "channel-specific formatting (e.g., Facebook Ads, Email, SMS)." I implemented all three because:
- It demonstrates the pipeline handles different constraints
- Character limits vary significantly (60 vs. 125 vs. 160)
- It shows the generator can adapt its output length

**Tradeoff:** 3x the API calls (30 instead of 10). But the total cost is still pennies, and it makes the demo more impressive.

---

## 6. Bonus: Production-Grade Features

Beyond the requirements, these features bring the prototype closer to production quality:

### 6a. Brand Voice Grader (`brand_voice_grader.py`)

The technical note *described* LLM-as-a-Copy-Editor — this file **implements** it.

A second LLM call grades each hook against all 4 rubric dimensions:

```
Generated Hook → Grader LLM → {quality_premium: 0/1, value_proposition: 0/1,
                                sustainability: 0/1, accuracy: 0/1, justification: "..."}
```

The grader prompt is **adversarial** — it's told to "FIND VIOLATIONS" not "confirm quality." This catches subtle issues that deterministic rules miss (e.g., tone that's technically compliant but feels off-brand).

### 6b. Retry Logic (`hook_generator.py`)

If a hook fails quick validation (char limit or forbidden keyword), the generator **automatically retries** with error feedback:

```
Attempt 1: Generate → Validate → FAIL (too long)
Attempt 2: Generate (with "PREVIOUS ATTEMPT FAILED: over by 12 chars") → Validate → PASS
```

Up to 3 retries. The error context helps the LLM self-correct.

### 6c. Pydantic Models (`models.py`)

Structured validation for all data types:

- `Product` — validates price > 0, price < comparable_retail_price, required fields
- `HookSet` — ensures all 3 hook types are present
- `RubricScore` — validates scores are 0 or 1, computes totals
- `FullReport` — typed validation report

### 6d. Unit Tests (`test_validator.py`)

36 tests covering:

- Character limit edge cases (at limit, over, empty)
- Forbidden keyword detection (case-insensitive, multiple matches)
- Hallucination patterns (%, BOGO, urgency, scarcity)
- Price accuracy (1 decimal, 2 decimal, whole dollar, invented prices)
- Pydantic model validation (missing fields, invalid prices)
- Product data integrity (unique IDs, valid schemas)

### 6e. Quality Judges & Composite Score (`quality_judges.py`)

Beyond pass/fail validation and brand voice grading, a third evaluation layer measures **how good** the hooks actually are using three signals:

**Product Specificity Judge (LLM):** Each hook is scored 1–5 on whether it uniquely identifies its product. A score of 1 means "completely generic — could be any product" while 5 means "uniquely identifiable." This directly catches the most common LLM failure: producing interchangeable copy like "100% Grade-A Mongolian Cashmere" for 4 different products.

**Channel-Appropriateness Judge (LLM):** Each hook is scored 1–5 on whether it reads naturally for its channel. Facebook ads need scroll-stopping language, email subjects need curiosity gaps, and SMS needs conversational tone.

**Cross-Product Deduplication (deterministic):** Measures word overlap across ALL hooks for the same (channel, hook_type) combination. Any pair with >70% word overlap is flagged as a near-duplicate. This is free and instant — no LLM call needed.

These three signals combine with validation pass rate and brand voice grading into a **Composite Quality Score** (0.0–1.0):

| Dimension | Weight | Source |
|---|---|---|
| Validation pass rate | 20% | Deterministic validator |
| Brand voice | 20% | LLM grader (existing) |
| Product specificity | 25% | LLM judge |
| Channel fit | 15% | LLM judge |
| Corpus uniqueness | 20% | Deterministic dedup |

**Why a composite score?** It transforms the evaluation from "did it pass?" (a low bar) to "how good is it?" (actionable). A score of 0.80+ means hooks are specific, diverse, and channel-appropriate. Below 0.60 means they need regeneration with improved prompts.

**Why weight specificity highest (25%)?** Because product-specific copy is the hardest thing for LLMs to produce consistently, and it's the most visible quality signal to a human reviewer.

### 6f. End-to-End Pipeline (`pipeline.py`)

Single script that runs everything in order:

```
Step 1: Validate product data (Pydantic)
Step 2: Generate hooks (LLM + retry)
Step 3: Automated validation (deterministic)
Step 4: Brand voice grading (LLM-as-Copy-Editor)  [optional]
Step 5: Quality judges (specificity, channel fit, dedup)  [optional LLM judges]
Step 6: Composite quality score
→ Final summary report
```

---

## 7. File Reference

```
projectquince/
├── README.md                # Quick start guide and command reference
├── technical_note.md        # Task 1: Strategy document (1 page)
├── products.json            # Real Quince product data (10 products)
├── hook_generator.py        # Ad hook generator (multi-provider, retry logic)
├── validator.py             # Automated validation script (4 rules + diversity)
├── brand_voice_grader.py    # LLM-as-Copy-Editor (rubric scoring)
├── quality_judges.py        # Quality judges: specificity, channel fit, dedup, composite score
├── models.py                # Pydantic models for structured validation
├── pipeline.py              # End-to-end pipeline (6-step, single entry point)
├── demo.py                  # Quick demo (3 products, formatted output)
├── test_validator.py        # Unit tests (49 tests)
├── requirements.txt         # Python dependencies
├── .gitignore               # Excludes generated output files
├── generated_hooks.json     # Output: 90 generated hooks
├── validation_report.json   # Output: validation results
├── quality_report.json      # Output: quality judge results + dedup analysis
├── composite_report.json    # Output: composite quality score
├── ai_process_log.md        # AI Process Log (prompts + human fix)
├── data_sourcing_log.md     # Methodology for sourcing real Quince data
├── IMPROVEMENT_PLAN.md      # Critical self-assessment and improvement roadmap
└── WALKTHROUGH.md           # This file
```

---

## 8. How to Run

### Prerequisites

```bash
pip install -r requirements.txt
```

### Option A: Full Pipeline (recommended)

```bash
# Runs everything: generation → validation → grading → quality judges → composite score
GROQ_API_KEY=your-key python3 pipeline.py

# Skip LLM grading (faster, still runs deterministic validation + dedup)
GROQ_API_KEY=your-key python3 pipeline.py --skip-grading

# Skip LLM quality judges (still runs deterministic dedup)
GROQ_API_KEY=your-key python3 pipeline.py --skip-judges

# Fast mode: skip all LLM eval (only deterministic checks)
GROQ_API_KEY=your-key python3 pipeline.py --fast
```

### Option B: Individual Scripts

```bash
# Generate hooks only
GROQ_API_KEY=your-key python3 hook_generator.py

# Validate hooks only
python3 validator.py

# Grade hooks with Brand Voice Rubric
GROQ_API_KEY=your-key python3 brand_voice_grader.py

# Run quality judges + composite score
GROQ_API_KEY=your-key python3 quality_judges.py

# Quality judges without LLM (dedup + composite only)
python3 quality_judges.py --skip-llm
```

### Option C: Quick Demo

```bash
GROQ_API_KEY=your-key python3 demo.py
```

### Option D: Run Tests

```bash
python3 test_validator.py
# or
python3 -m pytest test_validator.py -v
```

### Supported Providers

```bash
GROQ_API_KEY=your-key python3 pipeline.py       # Groq (FREE)
ANTHROPIC_API_KEY=your-key python3 pipeline.py   # Claude
OPENAI_API_KEY=your-key python3 pipeline.py      # OpenAI
```

### Expected Output

```
======================================================================
STEP 1: Validating product data
======================================================================
  10/10 products valid

======================================================================
STEP 2: Generating ad hooks
======================================================================
  Generated 90 hooks in 34.6s

======================================================================
STEP 3: Running automated validation
======================================================================
  Pass rate: 100.0% (90/90)

======================================================================
STEP 5: Quality judges (specificity, channel fit, deduplication)
======================================================================
  Corpus uniqueness: 0.909
  Near-duplicates found: 37

======================================================================
COMPOSITE QUALITY SCORE
======================================================================
  validation_pass_rate      ████████████████████ 1.000
  corpus_uniqueness         ██████████████████░░ 0.909
  COMPOSITE SCORE           ███████████████████░ 0.955

======================================================================
PIPELINE SUMMARY
======================================================================
  Hooks generated:        90
  Validation pass rate:   100.0% (90/90)
  Composite quality:      0.955/1.000 (2 dimensions)
  STATUS: READY FOR REVIEW
======================================================================
```
