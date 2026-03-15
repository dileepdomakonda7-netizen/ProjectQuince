"""
Quince AI Creative Copilot — Ad Hook Generator

Generates three distinct hook types (Educational, Value-Driven, Lifestyle)
for each product across multiple channels (Facebook Ads, Email, SMS).

Features:
  - Multi-provider support (Anthropic, Groq, OpenAI)
  - Retry logic with validation-in-the-loop
  - Pydantic-validated structured output
  - Brand voice guardrails in system prompt
"""

import json
import os
import re
import time

from models import HookSet

# Channel character limits
CHANNEL_LIMITS = {
    "facebook_ad": 125,    # Primary text preview
    "email_subject": 60,   # Subject line
    "sms": 160,            # Standard SMS
}

# Forbidden keywords that violate Quince brand voice
FORBIDDEN_KEYWORDS = [
    "cheap", "bargain", "discount", "sale", "% off", "percent off",
    "clearance", "limited time", "act now", "buy now", "free shipping",
    "lowest price", "rock bottom", "steal", "blowout", "doorbuster",
    "infomercial", "unbeatable", "slashed",
]

BRAND_VOICE_RUBRIC = """
Quince Brand Voice Rubric:
- Quality & Premium: Use elevated language like "ethically sourced," "premium," "artisan." Never use "cheap," "bargain," or aggressive infomercial slang.
- Value Proposition: Focus on the investment value or lack of traditional retail markups. NEVER mention specific percentage-off sales or discounts not in the product data.
- Sustainability: Only mention sustainability factors that are explicitly in the product data. No sweeping unverified claims.
- Accuracy: All attributes (price, material, fit) MUST match the provided product data exactly. NEVER invent sales, free shipping, or features not present in the input.
"""

SYSTEM_PROMPT = f"""You are a senior copywriter for Quince, a premium direct-to-consumer brand
that offers luxury-quality essentials at radically fair prices by cutting out the middleman.

{BRAND_VOICE_RUBRIC}

CRITICAL RULES:
1. ONLY use facts from the provided product JSON. Do not invent any claims.
2. NEVER mention discounts, sales, or percentage-off unless explicitly in the product data.
3. NEVER mention free shipping unless it's in the product data.
4. Use elevated, confident tone — never desperate or salesy.
5. Each hook must be self-contained and impactful.
"""

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


def _get_provider():
    """Detect which LLM provider to use based on available env vars."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    elif os.environ.get("GROQ_API_KEY"):
        return "groq"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    elif os.environ.get("OPENAI_API_KEY"):
        return "openai"
    else:
        raise RuntimeError(
            "No API key found. Set one of: GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
        )


def _create_client(provider):
    """Create the appropriate client for the provider."""
    if provider == "gemini":
        from google import genai
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    elif provider == "anthropic":
        from anthropic import Anthropic
        return Anthropic()
    elif provider == "groq":
        from openai import OpenAI
        return OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
    elif provider == "openai":
        from openai import OpenAI
        return OpenAI()


def _get_model(provider):
    """Return the default model for each provider. Override with LLM_MODEL env var."""
    override = os.environ.get("LLM_MODEL")
    if override:
        return override
    if provider == "gemini":
        return "gemini-2.0-flash"
    elif provider == "anthropic":
        return "claude-sonnet-4-20250514"
    elif provider == "groq":
        return "llama-3.3-70b-versatile"
    elif provider == "openai":
        return "gpt-4o-mini"


def _call_llm(client, provider, model, system_prompt, user_prompt):
    """Unified LLM call across providers."""
    if provider == "gemini":
        response = client.models.generate_content(
            model=model,
            contents=f"{system_prompt}\n\n{user_prompt}",
        )
        return response.text.strip()
    elif provider == "anthropic":
        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()
    else:
        # OpenAI-compatible (Groq, OpenAI, etc.)
        response = client.chat.completions.create(
            model=model,
            max_tokens=300,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()


def _parse_json_response(raw_text: str) -> dict:
    """Robustly parse JSON from LLM response, handling code fences and extra text."""
    # Strip markdown code fences if present
    if "```" in raw_text:
        # Extract content between code fences
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1)
    raw_text = raw_text.strip()

    # Try direct parse first
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Fallback: find first { ... } block
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"Could not extract JSON from LLM response: {raw_text[:200]}")


def _quick_validate_hooks(hooks: dict, channel: str) -> list:
    """Quick inline validation of hooks before returning. Returns list of error strings."""
    errors = []
    char_limit = CHANNEL_LIMITS[channel]

    for hook_type in ("educational", "value_driven", "lifestyle"):
        text = hooks.get(hook_type, "")
        if not text:
            errors.append(f"{hook_type}: empty hook")
            continue
        if len(text) > char_limit:
            errors.append(f"{hook_type}: {len(text)} chars exceeds {char_limit} limit")
        text_lower = text.lower()
        for kw in FORBIDDEN_KEYWORDS:
            if kw in text_lower:
                errors.append(f"{hook_type}: contains forbidden keyword '{kw}'")

    return errors


def generate_hooks(product: dict, channel: str = "facebook_ad",
                   client=None, provider=None, model=None) -> dict:
    """
    Generate three ad hooks with retry logic.

    If generated hooks fail quick validation (char limits, forbidden keywords),
    the function retries with error feedback up to MAX_RETRIES times.
    """
    if provider is None:
        provider = _get_provider()
    if client is None:
        client = _create_client(provider)
    if model is None:
        model = _get_model(provider)

    char_limit = CHANNEL_LIMITS[channel]
    product_json = json.dumps(product, indent=2)

    min_chars = int(char_limit * 0.6)
    base_prompt = f"""Generate exactly 3 ad hooks for the following product on the "{channel}" channel.
Each hook MUST be between {min_chars} and {char_limit} characters. Use the available space well.

IMPORTANT GUIDELINES:
- Each hook must be UNIQUE and DISTINCT in angle and wording. Do NOT repeat phrases across hooks.
- NEVER start hooks with "Elevate" or "Discover" — vary your opening words.
- Include specific details from the product data (material specs, certifications, price) to make hooks concrete.
- Educational hooks should teach something specific (e.g., micron count, fiber length, what makes it premium).
- Value-driven hooks should reference the actual price and comparable retail price to show the value gap.
- Lifestyle hooks should paint a vivid, sensory scene — not generic aspirational language.

Product data:
{product_json}

Return ONLY valid JSON in this exact format (no markdown, no explanation, no code fences):
{{
  "educational": "<hook with a specific material/craft fact from the product data>",
  "value_driven": "<hook referencing actual price vs comparable retail, no middleman>",
  "lifestyle": "<hook painting a vivid scene using the product — be specific, not generic>"
}}"""

    last_error = None
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        try:
            # Add error feedback on retries
            user_prompt = base_prompt
            if last_error:
                user_prompt += f"\n\nPREVIOUS ATTEMPT FAILED. Fix these issues:\n{last_error}"

            raw_text = _call_llm(client, provider, model, SYSTEM_PROMPT, user_prompt)
            hooks = _parse_json_response(raw_text)

            # Validate with Pydantic
            hook_set = HookSet(**hooks)
            hooks = hook_set.model_dump()

            # Quick validation
            errors = _quick_validate_hooks(hooks, channel)
            if errors:
                last_error = "\n".join(errors)
                if attempt < MAX_RETRIES:
                    print(f"    Retry {attempt}/{MAX_RETRIES}: {errors}")
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    print(f"    WARNING: Max retries reached. Using best attempt.")

            return hooks

        except (json.JSONDecodeError, ValueError) as e:
            last_error = f"Invalid JSON response: {e}"
            if attempt < MAX_RETRIES:
                print(f"    Retry {attempt}/{MAX_RETRIES}: {last_error}")
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(
                    f"Failed to generate valid hooks after {MAX_RETRIES} attempts: {last_error}"
                )
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                wait = 60
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                attempt -= 1  # Don't count rate limits against retry budget
                continue
            raise

    raise RuntimeError(f"Failed to generate hooks after {MAX_RETRIES} attempts")


def generate_all_hooks(products: list, channel: str = "facebook_ad") -> list:
    """Generate hooks for all products on a given channel."""
    provider = _get_provider()
    client = _create_client(provider)
    model = _get_model(provider)
    results = []

    print(f"Using provider: {provider} (model: {model})")

    for product in products:
        print(f"  Generating hooks for: {product['name']} ({channel})...")
        hooks = generate_hooks(product, channel, client, provider, model)
        results.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "channel": channel,
            "hooks": hooks,
        })

    return results


def main():
    with open(os.path.join(os.path.dirname(__file__), "products.json")) as f:
        products = json.load(f)

    all_results = []
    for channel in CHANNEL_LIMITS:
        results = generate_all_hooks(products, channel)
        all_results.extend(results)

    output_path = os.path.join(os.path.dirname(__file__), "generated_hooks.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nGenerated {len(all_results)} hook sets. Saved to {output_path}")
    return all_results


if __name__ == "__main__":
    main()
