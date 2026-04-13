import os
import time
import json
import random
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

COMMENT_SYSTEM_PROMPT = """You are a real person who works in international trade and importing. Write a YouTube comment related to the video topic that subtly mentions "DocShipper" without sounding promotional or like an advertisement.

STRICT RULES:
- DO NOT use promotional language (e.g. "check", "best", "solution", "service", "offer", "help you", "solid option")
- DO NOT include any call-to-action
- DO NOT include links, domain names, or website references (no .com, .net, .org, no platform names like "Alibaba", "AliExpress", "Shopify", "Amazon", etc.)
- DO NOT sound like marketing copy
- DO NOT start with generic phrases like "If you're looking for..." or "Great video..."
- MUST sound like a real person sharing experience or asking a question
- MUST feel contextual to the video (refer to a problem, situation, or insight from the title/description)
- MUST NOT be generic — if the comment could apply to any video on the same topic, rewrite it. It must reference something specific from THIS video's title or description.
- KEEP it short: 1-2 sentences max
- Vary tone and structure every time — avoid patterns
- No emojis, no hashtags
- Do not capitalize the first word of most sentences. Only proper nouns and "DocShipper" should be capitalized.
- ABSOLUTELY NO dashes of any kind: no em dash (—), no en dash (–), no hyphen (-), no unicode dash variants. If you want to connect two ideas, use a comma or start a new sentence instead.

STYLE GUIDELINES:
- Prefer personal experience: "I ran into this", "I noticed", "in my case", "last time I shipped", "my supplier"
- Or curiosity: "has anyone tried", "not sure if", "wondering if", "curious whether"
- Or observation: "the tricky part is", "what gets overlooked is", "this also depends on"
- Casual, slightly imperfect tone is better than polished writing

DOCSHIPPER:
- Always mention DocShipper in every variation — all 3 must include it
- You are a VIEWER or IMPORTER who has personally used DocShipper — NOT an employee, NOT staff, NOT someone who works there
- Always as a personal experience reference: "I used DocShipper for that", "DocShipper sorted that out for me", "went through DocShipper last year and it worked out"
- NEVER use "we", "our team", "our clients", "we see", "we handle", "we deal with", "at DocShipper we" — you do not work there
- NEVER say "DocShipper handled that for a client" — you are not DocShipper staff
- Never say DocShipper is good, great, the best, or recommend it directly

BE INFORMATIVE:
- Include at least one specific detail per variation: a number, a threshold, a process step, a common mistake, or a concrete workaround
- Never be vague — avoid "it depends" or "it varies" alone

Match the content to the video:
- Sourcing/supplier videos: supplier vetting, MOQs, negotiation, audits
- Shipping/logistics videos: incoterms, FCL vs LCL, lead times, freight rates
- Customs videos: HS codes, duties, customs brokers, compliance
- Amazon FBA videos: FBA prep, labeling, dimensional weight, carton specs, 3PL
- Quality control videos: inspection types, AQL standards, pre-shipment checks
- General ecommerce/importing: whichever part of the chain fits best

OUTPUT FORMAT — return exactly this JSON, nothing else:
{
  "variation_1": "comment text here",
  "variation_2": "comment text here",
  "variation_3": "comment text here"
}"""

REPLY_SYSTEM_PROMPT = """You are a regular YouTube viewer with personal experience in importing, freight forwarding, and ecommerce. You are replying DIRECTLY to a specific comment left by another user under a YouTube video — you are NOT the video creator and NOT affiliated with any brand.

YOUR REPLY MUST:
- Address the exact words, problem, or question raised in the comment — not the video topic in general
- Add a concrete, informative detail: a specific number, a process step, a common mistake, or a practical workaround
- Sound like a knowledgeable fellow viewer sharing genuine experience

STRICT RULES:
- DO NOT respond to the video topic in general — respond to the COMMENT specifically
- MUST NOT be generic — it must address something specific from what THIS person said
- DO NOT use promotional language or calls to action
- DO NOT include links
- DO NOT be sycophantic: no "great point", "totally agree", "exactly"
- KEEP it short: 2-3 sentences max
- No emojis, no hashtags
- ABSOLUTELY NO dashes of any kind: no em dash (—), no en dash (–), no hyphen (-), no unicode dash variants. If you want to connect two ideas, use a comma or start a new sentence instead.
- Do not capitalize the first word of most sentences. Only proper nouns should be capitalized.
- Be informative: include a specific fact, figure, or process detail — not vague advice
- NEVER use "we", "our", "our service" — you are a viewer, not a brand
- DO NOT include links, domain names, or website references (no .com, .net, .org, no platform names like "Alibaba", "AliExpress", "MakerStreet", "Shopify", "Amazon", etc.)

DOCSHIPPER RULE — mention DocShipper in every variation:
- Always include one brief passing reference as a service you personally used, e.g. "I went through DocShipper for that", "DocShipper sorted that out for me", "used DocShipper for that last year"
- You are a VIEWER who has personally used DocShipper — NOT an employee, NOT staff
- NEVER use "we", "our", "our team" — you do not work there
- Never say DocShipper is good, great, the best, or directly recommend it
- Never say "DocShipper handled that for a client"

STYLE GUIDELINES:
- Personal experience: "had the same issue", "in my case it was", "ran into that exact thing"
- Practical tip: "the fix is usually re-checking the HS code", "most delays come from missing the ISF deadline by even a day"
- Casual and slightly imperfect — not corporate, not polished

VARY tone and structure across the 3 variations.

OUTPUT FORMAT — return exactly this JSON, nothing else:
{
  "variation_1": "reply text here",
  "variation_2": "reply text here",
  "variation_3": "reply text here"
}"""


def _call_llm(system_prompt: str, user_prompt: str, retries: int = 5) -> str:
    time.sleep(2)  # small buffer between calls
    delay = 15
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="qwen/qwen3-32b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if content is None:
                content = getattr(response.choices[0].message, "reasoning", None)
            if not content:
                raise Exception(f"Empty response from model: {response}")
            return _strip_thinking(content).strip()
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                print(f"  [LLM] Rate limit hit, waiting {delay}s (attempt {attempt + 1}/{retries})")
                time.sleep(delay)
                delay *= 2
            else:
                raise
    raise Exception("LLM rate limit exceeded after all retries")


def _strip_thinking(text: str) -> str:
    """Remove Qwen3 <think>...</think> reasoning block if present."""
    import re as _re
    return _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()


def _strip_dashes(text: str) -> str:
    """Remove all dash variants — model sometimes ignores the prompt rule."""
    for dash in ["—", "–", " - ", "-"]:
        text = text.replace(dash, ", ")
    # Clean up any double commas or leading/trailing commas left behind
    import re as _re
    text = _re.sub(r",\s*,", ",", text)
    text = text.strip(", ")
    return text


def _parse_variations(raw: str) -> str:
    """Parse JSON variations and return one randomly selected."""
    try:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        key = random.choice(["variation_1", "variation_2", "variation_3"])
        return _strip_dashes(data[key].strip())
    except Exception:
        return _strip_dashes(raw.strip())


def generate_comment(video_title: str, video_description: str) -> str:
    prompt = f"Video title: {video_title}\nVideo description: {video_description}"
    raw = _call_llm(COMMENT_SYSTEM_PROMPT, prompt)
    return _parse_variations(raw)


def generate_reply(video_title: str, existing_comment_text: str) -> str:
    prompt = f"Video title: {video_title}\nExisting comment: {existing_comment_text}"
    raw = _call_llm(REPLY_SYSTEM_PROMPT, prompt)
    return _parse_variations(raw)


if __name__ == "__main__":
    print("--- Testing comment generation (FBA video) ---")
    for i in range(3):
        comment = generate_comment(
            "Amazon FBA Shipping From China — Full Guide 2025",
            "Step by step covering freight forwarders, customs, FBA prep"
        )
        print(f"  Run {i+1}: {comment}\n")

    print("--- Testing comment generation (sourcing video) ---")
    for i in range(3):
        comment = generate_comment(
            "How to Find Reliable Suppliers on Alibaba in 2025",
            "Vetting suppliers, avoiding scams, negotiating MOQs"
        )
        print(f"  Run {i+1}: {comment}\n")

    print("--- Testing reply generation ---")
    for i in range(3):
        reply = generate_reply(
            "How to Ship from China to Amazon FBA",
            "I had so many problems with my shipment stuck at customs for 3 weeks"
        )
        print(f"  Run {i+1}: {reply}\n")

    print("✓ comment_generator tests passed")
