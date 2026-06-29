"""Interactive project wizard: `python -m schemagen project`.

Prompts for the business once (the site-wide identity) and then for each page,
and writes the whole connected set to  Customer outputs/<Project Name>/ .

Fields left blank are removed from the output (via the __DELETE__ sentinel) so
you never ship template placeholder data — supply real values for the strategy
fields (social sameAs, service areas, keywords, licenses) and skip the rest.
"""
import datetime
import re

from . import core, identity, project


# --------------------------------------------------------------------------- #
# prompt helpers
# --------------------------------------------------------------------------- #
def _ask(label, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"  {label}{suffix}: ").strip()
    except EOFError:
        # stdin closed (non-interactive) — abort rather than loop/produce junk
        raise EOFError
    return v or default


def _ask_list(label):
    raw = _ask(label + " (comma-separated)")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _ask_yn(label, default=False):
    d = "y" if default else "n"
    return _ask(f"{label} (y/n)", d).lower().startswith("y")


def _put(d, key, value):
    """Set an override, or mark the key for deletion when the value is empty."""
    d[key] = value if value not in (None, "", [], {}) else core.DELETE


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "page"


def _credentials(numbers):
    return [{"@type": "EducationalOccupationalCredential", "name": n} for n in numbers]


def _ask_faq():
    """Collect Q&A pairs until an empty question is entered."""
    qa = []
    print("    Enter FAQ items (blank question to finish):")
    while True:
        q = _ask("Q")
        if not q:
            break
        a = _ask("A")
        qa.append((q, a))
    return qa


# --------------------------------------------------------------------------- #
# wizard
# --------------------------------------------------------------------------- #
def run(base="."):
    print("\nschemagen project wizard — blank = skip (skipped fields are omitted)\n")

    name = _ask("Project name", "My Project")
    domain = _ask("Domain (e.g. https://www.acme.com)")
    while not domain:
        domain = _ask("Domain is required")
    base_url = core.base_url(domain)
    today = datetime.date.today().strftime("%Y/%m/%d")

    print("\n— Business identity (site-wide) —")
    biz = _ask("Business name", name)
    legal = _ask("Legal name")
    itype = _ask("Industry @type for LocalBusiness (e.g. Dentist, Electrician)",
                 "LocalBusiness")
    phone = _ask("Phone")
    email = _ask("Email")
    desc = _ask("Short description (meta-style)")
    disambig = _ask("Second description (must differ from the first)")
    if desc and disambig and desc.strip() == disambig.strip():
        print("    ! warning: the two descriptions are identical (SOP wants them distinct)")
    logo = _ask("Logo URL")
    social = _ask_list("Social profile URLs (LinkedIn first)")
    cities = _ask_list("Service-area cities")
    locality = _ask("City / locality")
    region = _ask("State / region")
    country = _ask("Country code", "US")
    street = _ask("Street address")
    owner = _ask("Owner / key person name")
    keywords = _ask_list("Target keywords (knowsAbout)")
    licenses = _ask_list("License / credential numbers")
    hours = _ask("Opening hours (e.g. Mo-Fr 09:00-17:00)")
    maps = _ask("Google Maps / Business Profile link (hasMap)")
    price = _ask("Price range ($, $$, $$$)")
    entity = _ask("Brand entity URL (Wikipedia/Wikidata)")

    sw = identity.sitewide_overrides({
        "name": name, "business": biz, "legal": legal, "domain": domain,
        "itype": itype, "phone": phone, "email": email, "desc": desc,
        "disambig": disambig, "logo": logo, "social": social, "cities": cities,
        "locality": locality, "region": region, "country": country,
        "street": street, "owner": owner, "keywords": keywords,
        "licenses": licenses, "hours": hours, "maps": maps, "price": price,
        "entity": entity,
    })

    # ----- pages -----
    pages = []

    def page_common(over, headline, pdesc, pdisambig):
        _put(over, "webpage.headline", headline)
        _put(over, "webpage.description", pdesc)
        _put(over, "webpage.disambiguatingDescription", pdisambig)
        over["webpage.lastReviewed"] = today
        for gone in ("about", "mentions", "relatedLink", "sameAs", "significantLink"):
            over[f"webpage.{gone}"] = core.DELETE

    def add_node_overrides(over, ntype, title, crumbs_leaf_url):
        if ntype == "service":
            _put(over, "service.name", title)
            over["service.serviceType"] = [title] if title else core.DELETE
            _put(over, "service.description", over.get("webpage.description", ""))
            over["service.provider"] = {"@id": f"{base_url}/#localbusiness"}
            if cities:
                over["service.areaServed"] = {"@type": "City", "name": cities[0]}
            for gone in ("alternateName", "slogan", "sameAs", "category",
                         "termsOfService", "award", "hasOfferCatalog",
                         "disambiguatingDescription"):
                over[f"service.{gone}"] = core.DELETE
        elif ntype == "person":
            _put(over, "person.name", owner or title)
            over["person.worksFor"] = {"@id": f"{base_url}/#localbusiness"}
            _put(over, "person.sameAs", social)
            _put(over, "person.telephone", phone)
            _put(over, "person.email", email)
            for gone in ("colleague", "alumniOf", "birthPlace", "birthDate",
                         "height", "nationality", "callSign", "award", "memberOf",
                         "address", "gender", "image", "knowAbout"):
                over[f"person.{gone}"] = core.DELETE

    # home page
    print("\n— Home page —")
    home = {"file": "home", "path": "/", "nodes": ["webpage", "breadcrumb"],
            "overrides": {}}
    page_common(home["overrides"], desc or biz, desc, disambig)
    home["overrides"]["breadcrumb.itemListElement"] = project.crumb(
        [("Home", base_url + "/")])
    home["overrides"]["breadcrumb.numberOfItems"] = "1"
    _put(home["overrides"], "breadcrumb.description", desc)
    _put(home["overrides"], "breadcrumb.disambiguatingDescription", disambig)
    if _ask_yn("Add an FAQ to the home page?"):
        qa = _ask_faq()
        if qa:
            home["nodes"].append("faqpage")
            home["overrides"]["faqpage.mainEntity"] = project.questions(qa)
    pages.append(home)

    # additional pages
    while _ask_yn("\nAdd another page?"):
        title = _ask("Page title")
        if not title:
            break
        path = _ask("Page path (e.g. /services/)", "/" + _slug(title) + "/")
        if not path.startswith("/"):
            path = "/" + path
        pdesc = _ask("Page description")
        pdisambig = _ask("Second description")
        ntype = _ask("Extra node: none / service / person", "none").lower()
        nodes = ["webpage", "breadcrumb"]
        over = {}
        page_common(over, title, pdesc, pdisambig)
        page_url = base_url + path
        over["breadcrumb.itemListElement"] = project.crumb(
            [("Home", base_url + "/"), (title, page_url)])
        over["breadcrumb.numberOfItems"] = "2"
        _put(over, "breadcrumb.description", pdesc)
        _put(over, "breadcrumb.disambiguatingDescription", pdisambig)
        if ntype in ("service", "person"):
            nodes.append(ntype)
            add_node_overrides(over, ntype, title, page_url)
        if _ask_yn("Add an FAQ to this page?"):
            qa = _ask_faq()
            if qa:
                nodes.append("faqpage")
                over["faqpage.mainEntity"] = project.questions(qa)
        pages.append({"file": _slug(title), "path": path, "nodes": nodes,
                      "overrides": over})

    # The output subfolder is the BUSINESS NAME (falls back to the project name).
    config = {"project": biz or name, "domain": domain,
              "sitewide": {"overrides": sw}, "pages": pages}

    print(f"\nReady: project '{name}', domain {base_url}, {len(pages)} page(s):")
    for p in pages:
        print(f"  - {p['file']}.schema.html  ({p['path']}, nodes: {', '.join(p['nodes'])})")
    if not _ask_yn("\nGenerate now?", True):
        print("Aborted — nothing written.")
        return []

    written = project.generate(config, base=base)
    print("\nWrote:")
    for p in written:
        print("  " + p)
    print("\n" + core.VALIDATORS)
    return written
