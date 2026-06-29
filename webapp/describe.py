"""Meta-description handling for auto-built schema.

Deterministic by default: use the page's scraped meta/OG description, or
synthesize a <=160-char one from title + content. If ANTHROPIC_API_KEY is set,
descriptions are written/rewritten with Claude following SEO best practices
(the Edward-SEO approach) — otherwise the deterministic path is used.
"""
import json
import os
import re

import requests

MODEL = os.environ.get("SCHEMA_LLM_MODEL", "claude-haiku-4-5-20251001")


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def cap160(s):
    s = _clean(s)
    if len(s) <= 160:
        return s
    cut = s[:159]
    if " " in cut[120:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,.;:-") + "…"


def _deterministic(page, business):
    title = _clean(page.get("title"))
    md = _clean(page.get("description"))
    og = _clean(page.get("og_description"))
    txt = _clean(page.get("text"))
    primary = md or og or (f"{title}. {txt}".strip(". ") if title else txt) or f"{business} — {title}"
    second = ""
    for c in (og, md, txt, f"{business}: {title}", title):
        c = _clean(c)
        if c and cap160(c) != cap160(primary):
            second = c
            break
    if not second:
        second = f"{business} — {title}. Learn more.".strip() if title else f"{business} official page."
    return cap160(primary), cap160(second)


def _llm(page, business, area=""):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    existing = _clean(page.get("description") or page.get("og_description"))
    prompt = (
        "You are an expert SEO copywriter. Write TWO distinct meta descriptions for "
        "the web page below. Rules: each <=160 characters, active voice, lead with the "
        "primary keyword/topic, include the business name, end with a soft CTA, no "
        "quotes around the text. The two must differ in wording and angle.\n\n"
        f"Business: {business}\nArea served: {area or 'n/a'}\n"
        f"Page title: {_clean(page.get('title'))}\nURL: {page.get('url','')}\n"
        f"Existing description (rewrite & improve if present): {existing or 'none'}\n"
        f"Page content snippet: {_clean(page.get('text'))[:500]}\n\n"
        'Return ONLY JSON: {"description": "...", "disambiguatingDescription": "..."}'
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 400,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30)
        text = r.json()["content"][0]["text"]
        m = re.search(r"\{.*\}", text, re.S)
        obj = json.loads(m.group(0))
        d, dd = cap160(obj["description"]), cap160(obj["disambiguatingDescription"])
        if d and dd and d != dd:
            return d, dd
    except Exception:
        pass
    return None


def describe(page, business, area=""):
    """Return (description, disambiguatingDescription) for a page — AI if a key is
    configured, else deterministic. Always two distinct <=160-char strings."""
    return _llm(page, business, area) or _deterministic(page, business)


def ai_enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
