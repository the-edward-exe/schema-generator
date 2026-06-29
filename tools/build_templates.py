"""Extract the source Schema Templates into cleaned, valid JSON skeletons.

The source files in `Schema Templates/` are the canonical structures supplied by
the user. They are wrapped in a `<script type="application/ld+json">` tag and a
few contain JSON-breaking issues (trailing commas, a stray brace, a misplaced
key, a duplicate `@id`). Per the agreed policy we reproduce the structure
faithfully but auto-fix *only* the breakages so the output parses and validates.

Run:  python tools/build_templates.py
Output: schemagen/templates/<name>.json  (pure JSON, no <script> wrapper)
"""
import json
import os
import re
import sys

SRC_DIR = "Schema Templates"
OUT_DIR = os.path.join("schemagen", "templates")

# Map source filename -> output skeleton name used by the registry.
NAME_MAP = {
    "Article Template.json": "article",
    "Book Template.json": "book",
    "Breadcrumb Template.json": "breadcrumb",
    "How To Template.json": "howto",
    "Job Posting.json": "jobposting",
    "Local Business Template.json": "localbusiness",
    "Organization Template.json": "organization",
    "Person Template.json": "person",
    "Product Template.json": "product",
    # recipe.json is hand-maintained (source is too malformed to auto-repair).
    "Service Template.json": "service",
    "Video Template.json": "video",
    "Webpage Template.json": "webpage",
    "Website Template.json": "website",
}


def extract_body(raw: str) -> str:
    m = re.search(r"<script[^>]*>(.*)</script>", raw, re.S)
    return m.group(1) if m else raw


def fix_trailing_commas(s: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", s)


def manual_fix(name: str, body: str) -> str:
    """Targeted structural repairs the generic rules can't handle."""
    if name == "webpage":
        # The source closes the WebPage object, then has one extra stray `}`.
        # Drop the final brace so the single object parses.
        body = body.rstrip()
        if body.endswith("}\n}") or re.search(r"\}\s*\}\s*$", body):
            body = re.sub(r"\}\s*\}\s*$", "}", body, count=1)
    if name == "recipe":
        # `step` is accidentally a sibling of the Recipe object instead of a
        # property of it. Pull it inside: the Recipe object prematurely closes
        # with `},` right before `"step"`. Turn that close into a comma, and
        # remove the now-extra closing braces at the very end.
        body = body.replace('"recipeYield": "12 cookies"\n    },\n    "step"',
                            '"recipeYield": "12 cookies",\n    "step"')
        # The tail had `}]}}` closing the (previously) two top-level values;
        # after merging, one less closing brace is needed.
        body = re.sub(r"\}\]\}\}\s*$", "}]}", body, count=1)
    return body


def dedupe_keys_keep_last(pairs):
    """object_pairs_hook: later duplicate keys win (matches json default)."""
    d = {}
    for k, v in pairs:
        d[k] = v
    return d


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    for fname, outname in NAME_MAP.items():
        path = os.path.join(SRC_DIR, fname)
        raw = open(path, encoding="utf-8").read()
        body = extract_body(raw)
        for attempt in ("raw", "commas", "manual"):
            try:
                obj = json.loads(body, object_pairs_hook=dedupe_keys_keep_last)
                break
            except Exception:
                if attempt == "raw":
                    body = fix_trailing_commas(body)
                elif attempt == "commas":
                    body = manual_fix(outname, body)
                else:
                    results.append((outname, "FAILED"))
                    obj = None
        if obj is None:
            continue
        out_path = os.path.join(OUT_DIR, outname + ".json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
        results.append((outname, "ok"))
    for name, status in results:
        print(f"  {name:24} {status}")
    return 0 if all(s == "ok" for _, s in results) else 1


if __name__ == "__main__":
    sys.exit(main())
