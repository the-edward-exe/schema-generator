"""Core engine: load skeletons, swap the domain, apply overrides, validate, and
assemble single nodes or a connected @graph — then emit script-wrapped JSON-LD.

Policy (agreed with the user):
  * Reproduce the template structure faithfully, including house-style keys
    (e.g. `founders`, lowercase `thing`, `wordcount`). Do NOT silently "correct"
    schema.org casing.
  * Auto-fix only breakages: the skeletons already parse; here we keep @id
    fragments unique inside a @graph and enforce description != disambiguating.
  * Always end by reminding the operator to validate (Google Rich Results +
    schema.org; if they disagree, Google wins) — per the SOP.
"""
import copy
import json
import os
import re

from . import registry

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

SCRIPT_OPEN = '<script type="application/ld+json">'
SCRIPT_CLOSE = "</script>"

VALIDATORS = (
    "Validate before shipping:\n"
    "  - https://search.google.com/test/rich-results\n"
    "  - https://validator.schema.org/\n"
    "  (If Google passes but schema.org errors, go with Google.)"
)

# example.com (and any subdomain, e.g. cdn.example.com) is the placeholder host
# throughout the templates. Real external references (wikipedia.org, wikidata.org,
# schema.org, gravatar, etc.) are left untouched.
_EXAMPLE_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*example\.com")


class SchemaError(Exception):
    pass


def load_skeleton(name: str) -> dict:
    meta = registry.get(name)
    path = os.path.join(TEMPLATE_DIR, meta["template"])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Domain handling
# --------------------------------------------------------------------------- #
def _normalize_domain(domain: str):
    """Return (scheme, host) for a user-supplied domain like 'acme.com' or
    'https://www.acme.com/'."""
    domain = domain.strip()
    m = re.match(r"^(https?)://", domain)
    scheme = m.group(1) if m else "https"
    host = re.sub(r"^https?://", "", domain).strip("/")
    return scheme, host


def base_url(domain: str) -> str:
    """'acme.com' or 'https://www.acme.com/' -> 'https://www.acme.com'."""
    scheme, host = _normalize_domain(domain)
    return f"{scheme}://{host}"


def apply_domain(obj, domain: str):
    """Recursively replace the example.com placeholder host (any scheme, with or
    without www) with the target host, normalizing the scheme. Paths, query
    strings and #fragments are preserved."""
    scheme, host = _normalize_domain(domain)

    def swap(value: str) -> str:
        return _EXAMPLE_HOST_RE.sub(f"{scheme}://{host}", value)

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return swap(node)
        return node

    return walk(obj)


# --------------------------------------------------------------------------- #
# Field overrides
# --------------------------------------------------------------------------- #
# Sentinel override value that removes a key instead of setting it. Useful for
# stripping template residue that has no replacement (e.g. example-specific
# award lists or a placeholder foundingLocation).
DELETE = "__DELETE__"


def set_field(obj: dict, dotted_key: str, value):
    """Set a (possibly nested, dot-separated) key. Intermediate dicts are
    created as needed. Values that look like JSON (start with [ or {) are parsed
    so callers can pass arrays/objects from the CLI. The sentinel value DELETE
    ('__DELETE__') removes the key if present."""
    if isinstance(value, str):
        v = value.strip()
        if v[:1] in "[{":
            try:
                value = json.loads(v)
            except json.JSONDecodeError:
                pass
    parts = dotted_key.split(".")
    cur = obj
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            raise SchemaError(f"cannot descend into non-object key '{p}'")
    if value == DELETE:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = value
    return obj


def apply_overrides(obj: dict, overrides: dict):
    for k, v in (overrides or {}).items():
        set_field(obj, k, v)
    return obj


# --------------------------------------------------------------------------- #
# Validation (SOP rules)
# --------------------------------------------------------------------------- #
def check_descriptions(obj) -> list:
    """The SOP requires description and disambiguatingDescription to both be
    present and to differ. Returns a list of human-readable warnings."""
    warnings = []

    def walk(node, where="root"):
        if isinstance(node, dict):
            t = node.get("@type", "")
            d = node.get("description")
            dd = node.get("disambiguatingDescription")
            if d is not None or dd is not None:
                label = f"{t or where}"
                if d and dd and d.strip() == dd.strip():
                    warnings.append(
                        f"[{label}] description and disambiguatingDescription "
                        f"are identical — the SOP wants distinct content.")
                if d and not dd:
                    warnings.append(
                        f"[{label}] has description but no "
                        f"disambiguatingDescription (SEO opportunity).")
            for k, v in node.items():
                walk(v, where=node.get("@type", where))
        elif isinstance(node, list):
            for v in node:
                walk(v, where)

    walk(obj)
    return warnings


# --------------------------------------------------------------------------- #
# Strict schema.org casing (opt-in)
# --------------------------------------------------------------------------- #
# The templates carry a few house-style deviations from schema.org's canonical
# casing/spelling. Strict mode normalizes ONLY these known ones — it does not
# touch legitimate (if legacy) properties like alternativeHeadline or
# interactionCount. Property keys:
_STRICT_KEY_FIXES = {
    "knowAbout": "knowsAbout",
    "sameas": "sameAs",
    "telePhone": "telephone",
    "wordcount": "wordCount",
}
# Values that appear as an @type (e.g. the lowercase "thing" in about/mentions):
_STRICT_TYPE_FIXES = {
    "thing": "Thing",
}


def _fix_type_value(value):
    if isinstance(value, str):
        return _STRICT_TYPE_FIXES.get(value, value)
    if isinstance(value, list):
        return [_fix_type_value(v) for v in value]
    return value


def strict_casing(node):
    """Return a copy with house-style keys/@type values normalized to canonical
    schema.org casing. Order is preserved; if a corrected key already exists in
    the same object the canonical one wins and the deviant is dropped."""
    if isinstance(node, dict):
        new = {}
        for k, v in node.items():
            nk = _STRICT_KEY_FIXES.get(k, k)
            v2 = strict_casing(v)
            if k == "@type":
                v2 = _fix_type_value(v2)
            if nk in new and nk != k:
                # canonical key already present earlier — keep it, drop deviant
                continue
            new[nk] = v2
        return new
    if isinstance(node, list):
        return [strict_casing(v) for v in node]
    return node


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #
def build_single(name: str, domain: str = None, overrides: dict = None,
                 strict: bool = False) -> dict:
    obj = load_skeleton(name)
    if domain:
        obj = apply_domain(obj, domain)
    if overrides:
        apply_overrides(obj, overrides)
    if strict:
        obj = strict_casing(obj)
    return obj


def assemble_graph(names, domain: str = None, overrides: dict = None,
                   strict: bool = False) -> dict:
    """Combine several single-type nodes into one connected @graph: a single
    top-level @context, each node carrying a unique @id fragment on the target
    domain so the nodes cross-reference cleanly."""
    scheme, host = _normalize_domain(domain) if domain else ("https", "example.com")
    base = f"{scheme}://{host}"

    nodes = []
    for name in names:
        meta = registry.get(name)
        node = load_skeleton(name)
        if domain:
            node = apply_domain(node, domain)
        # Inside a @graph there is one shared @context at the top level.
        node.pop("@context", None)
        # Give every node a unique, resolvable @id so references line up.
        node["@id"] = f"{base}/#{meta['fragment']}"
        nodes.append(node)

    graph = {"@context": "https://schema.org", "@graph": nodes}
    if overrides:
        # Graph-level overrides target a node by fragment: "organization.name=..."
        apply_overrides_graph(graph, overrides)
    if strict:
        graph = strict_casing(graph)
    return graph


def apply_overrides_graph(graph: dict, overrides: dict):
    """Overrides keyed as '<fragment>.<dotted.key>' edit a specific @graph node;
    keys without a known fragment prefix are ignored with no error so callers can
    pass a flat override map."""
    frag_index = {n["@id"].rsplit("#", 1)[-1]: n for n in graph["@graph"]
                  if isinstance(n.get("@id"), str) and "#" in n["@id"]}
    for k, v in overrides.items():
        frag, _, rest = k.partition(".")
        if frag in frag_index and rest:
            set_field(frag_index[frag], rest, v)
    return graph


# --------------------------------------------------------------------------- #
# Emit
# --------------------------------------------------------------------------- #
def to_jsonld(obj, wrap: bool = True, indent: int = 2) -> str:
    body = json.dumps(obj, indent=indent, ensure_ascii=False)
    if not wrap:
        return body
    return f"{SCRIPT_OPEN}\n{body}\n{SCRIPT_CLOSE}"
