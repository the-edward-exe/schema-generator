"""Per-page project builder.

Generalizes the site-wide-vs-per-page deployment model: build one site-wide
identity graph (Organization + LocalBusiness + WebSite) that ships in the header
on every page, plus one graph per page (WebPage + Breadcrumb + a page node) whose
nodes carry page-specific @ids and reference the site-wide nodes by @id. When both
<script> blocks render on a page, Google merges them into one connected graph.

Outputs are written to  <base>/Customer outputs/<Project Name>/  — one .html file
per page, plus sitewide.schema.html.

Drive it with a config dict (see generate()), or call build_sitewide/build_page
directly. No business data lives here — supply it via the config/overrides.
"""
import os

from . import core

OUTPUT_ROOT = "Customer outputs"

# Node fragments eligible to be a page's primary entity (first match wins).
_MAIN_ENTITY_PREFERENCE = ("service", "product", "article", "person", "howto",
                           "recipe", "book", "video", "jobposting")


def project_dir(project_name: str, base: str = ".") -> str:
    return os.path.join(base, OUTPUT_ROOT, project_name)


def crumb(items):
    """items = [(name, url), ...] -> a positioned itemListElement array."""
    return [{"@type": "ListItem", "position": i + 1,
             "item": {"@id": url, "name": name}}
            for i, (name, url) in enumerate(items)]


def questions(qa):
    """qa = [(question, answer), ...] -> FAQPage mainEntity array."""
    return [{"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]


def build_sitewide(domain, overrides=None,
                   nodes=("organization", "localbusiness", "website", "breadcrumb"), strict=True):
    """The identity graph deployed in the header on every page."""
    return core.assemble_graph(list(nodes), domain=domain,
                               overrides=overrides or {}, strict=strict)


def build_page(domain, path, nodes, overrides=None, strict=True,
               sitewide_fragments=("organization", "localbusiness", "website", "breadcrumb")):
    """Build one page graph, re-scope its @ids to the page URL, and wire the
    cross-references back to the site-wide identity nodes.

    path is the page path beginning with '/', e.g. '/' or '/services/'."""
    g = core.assemble_graph(list(nodes), domain=domain,
                            overrides=overrides or {}, strict=strict)
    base = core.base_url(domain)
    page_url = base + path
    nmap = {n["@id"].rsplit("#", 1)[-1]: n for n in g["@graph"]}

    # page-scoped @ids
    for frag, node in nmap.items():
        node["@id"] = f"{page_url}#{frag}"

    has = set(sitewide_fragments)
    wp = nmap.get("webpage")
    if wp:
        if "website" in has:
            wp["isPartOf"] = {"@id": f"{base}/#website"}
        if "organization" in has:
            wp["publisher"] = {"@id": f"{base}/#organization"}
        if "localbusiness" in has:
            about = wp.get("about")
            extra = about if isinstance(about, list) else ([about] if about else [])
            wp["about"] = [{"@id": f"{base}/#localbusiness"}] + extra
        if "breadcrumb" in nmap:
            wp["breadcrumb"] = {"@id": f"{page_url}#breadcrumb"}
        for frag in _MAIN_ENTITY_PREFERENCE:
            if frag in nmap:
                wp["mainEntity"] = {"@id": f"{page_url}#{frag}"}
                break
        if "faqpage" in nmap:
            wp["hasPart"] = {"@id": f"{page_url}#faqpage"}

    for frag in list(_MAIN_ENTITY_PREFERENCE) + ["faqpage"]:
        if frag in nmap:
            nmap[frag]["mainEntityOfPage"] = page_url
    if "faqpage" in nmap and "website" in has:
        nmap["faqpage"]["isPartOf"] = {"@id": f"{base}/#website"}
    return g


def write(graph, project_name, filename, base="."):
    d = project_dir(project_name, base)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(core.to_jsonld(graph, wrap=False) + "\n")  # bare JSON-LD
    return path


def generate(config, base="."):
    """Build a whole project from a config dict and write the files.

    config = {
      "project": "Acme Co",                # -> Customer outputs/Acme Co/
      "domain": "https://www.acme.com",
      "sitewide": {                        # optional override of the identity nodes
        "nodes": ["organization", "localbusiness", "website"],
        "overrides": { "organization.name": "Acme Co", ... },
      },
      "pages": [
        { "file": "home", "path": "/",
          "nodes": ["webpage", "breadcrumb"],
          "overrides": { "webpage.headline": "...", "breadcrumb.itemListElement": [...] } },
        ...
      ],
    }
    Returns the list of written file paths.
    """
    name = config["project"]
    domain = config["domain"]
    written = []

    sw = config.get("sitewide", {})
    sw_graph = build_sitewide(domain, sw.get("overrides", {}),
                              nodes=sw.get("nodes",
                                           ("organization", "localbusiness", "website", "breadcrumb")))
    written.append(write(sw_graph, name, "sitewide.json", base))
    sw_frags = tuple(sw.get("nodes", ("organization", "localbusiness", "website", "breadcrumb")))

    for page in config.get("pages", []):
        g = build_page(domain, page["path"], page["nodes"],
                       page.get("overrides", {}), sitewide_fragments=sw_frags)
        written.append(write(g, name, page["file"] + ".json", base))
    return written
