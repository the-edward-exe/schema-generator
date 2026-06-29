"""Pure builders shared by the wizard and the web app.

`sitewide_overrides(data)` turns a flat dict of business fields into the
site-wide override map (Organization + LocalBusiness + WebSite). `page_pack(...)`
builds one page spec (WebPage + Breadcrumb + optional Service/Person/FAQ).
No I/O here — callers (wizard, webapp) collect the data however they like.
"""
from . import core, project

D = core.DELETE


def _put(d, key, value):
    d[key] = value if value not in (None, "", [], {}) else D


def _credentials(numbers):
    return [{"@type": "EducationalOccupationalCredential", "name": n} for n in numbers]


def sitewide_overrides(data):
    """data keys (all optional except domain): name/business, domain, itype,
    phone, email, desc, disambig, logo, social[list], cities[list], locality,
    region, country, street, owner, keywords[list], licenses[list], hours,
    maps, price, entity."""
    base_url = core.base_url(data["domain"])
    biz = data.get("business") or data.get("name") or ""
    social = data.get("social") or []
    cities = data.get("cities") or []
    keywords = data.get("keywords") or []
    desc = data.get("desc", "")
    disambig = data.get("disambig", "")
    logo = data.get("logo", "")
    email = data.get("email", "")
    phone = data.get("phone", "")
    entity = data.get("entity", "")

    address = {"@type": "PostalAddress"}
    for k, v in (("streetAddress", data.get("street")),
                 ("addressLocality", data.get("locality")),
                 ("addressRegion", data.get("region")),
                 ("addressCountry", data.get("country"))):
        if v:
            address[k] = v
    address = address if len(address) > 1 else None

    contact = None
    if phone or email:
        contact = {"@type": "ContactPoint", "contactType": "customer support"}
        if phone:
            contact["telephone"] = phone
        if email:
            contact["email"] = email

    founder = {"@type": "Person", "name": data["owner"]} if data.get("owner") else None
    creds = _credentials(data["licenses"]) if data.get("licenses") else None

    sw = {}
    _put(sw, "organization.name", biz)
    _put(sw, "organization.legalName", data.get("legal", ""))
    sw["organization.url"] = base_url + "/"
    _put(sw, "organization.description", desc)
    _put(sw, "organization.disambiguatingDescription", disambig)
    _put(sw, "organization.telephone", phone)
    _put(sw, "organization.email", email)
    _put(sw, "organization.logo", logo)
    _put(sw, "organization.image", logo)
    _put(sw, "organization.sameAs", social)
    _put(sw, "organization.areaServed", cities)
    _put(sw, "organization.knowsAbout", keywords)
    _put(sw, "organization.address", address)
    _put(sw, "organization.contactPoint", contact)
    _put(sw, "organization.founder", founder)
    _put(sw, "organization.hasCredential", creds)
    _put(sw, "organization.mainEntityOfPage", entity)
    for gone in ("award", "brand", "foundingLocation", "foundingDate",
                 "actionableFeedbackPolicy", "founders"):
        sw[f"organization.{gone}"] = D

    sw["localbusiness.@type"] = data.get("itype") or "LocalBusiness"
    _put(sw, "localbusiness.name", biz)
    sw["localbusiness.url"] = base_url + "/"
    _put(sw, "localbusiness.description", desc)
    _put(sw, "localbusiness.disambiguatingDescription", disambig)
    sw["localbusiness.mainEntityOfPage"] = base_url + "/"
    _put(sw, "localbusiness.telePhone", phone)
    _put(sw, "localbusiness.email", email)
    _put(sw, "localbusiness.logo", logo)
    _put(sw, "localbusiness.image", logo)
    _put(sw, "localbusiness.address", address)
    _put(sw, "localbusiness.areaServed", cities)
    _put(sw, "localbusiness.location", cities[0] if cities else data.get("locality", ""))
    _put(sw, "localbusiness.knowsAbout", keywords)
    _put(sw, "localbusiness.hasCredential", creds)
    _put(sw, "localbusiness.hasMap", data.get("maps", ""))
    _put(sw, "localbusiness.openingHours", data.get("hours", ""))
    _put(sw, "localbusiness.priceRange", data.get("price", ""))
    _put(sw, "localbusiness.sameAs", social)
    for gone in ("geo", "paymentAccepted", "currenciesAccepted", "slogan",
                 "openingHoursSpecification"):
        sw[f"localbusiness.{gone}"] = D

    sw["website.url"] = base_url + "/"
    _put(sw, "website.name", biz)
    _put(sw, "website.alternateName", data.get("legal", ""))
    _put(sw, "website.description", desc)
    _put(sw, "website.disambiguatingDescription", disambig)
    _put(sw, "website.image", logo)
    _put(sw, "website.identifier", entity)
    _put(sw, "website.mainEntityOfPage", entity)
    # Sitelinks search box. Default to a platform-neutral /search?q= URL; pass
    # data["search_url"] to match your site's actual search endpoint.
    sw["website.potentialAction"] = {
        "@type": "SearchAction",
        "target": data.get("search_url") or (base_url + "/search?q={search_term_string}"),
        "query-input": "required name=search_term_string"}

    # Site-wide breadcrumb (top level: Home). Overrides the template's example
    # items so no placeholder data ships.
    sw["breadcrumb.itemListElement"] = project.crumb([("Home", base_url + "/")])
    sw["breadcrumb.numberOfItems"] = "1"
    _put(sw, "breadcrumb.description", desc)
    _put(sw, "breadcrumb.disambiguatingDescription", disambig)
    sw["breadcrumb.mainEntityOfPage"] = base_url + "/"
    return sw


def page_pack(base_url, file, path, headline, primary, secondary, today,
              node=None, owner="", social=None, faq=None, crumbs=None, wp_type=None):
    """Build one page spec dict {file, path, nodes, overrides}.

    node: extra schema node for the page — "service", "person", or "article".
    wp_type: override the WebPage @type (e.g. "CollectionPage").
    """
    o = {}
    org_id = f"{base_url}/#organization"
    _put(o, "webpage.headline", headline)
    _put(o, "webpage.description", primary)
    _put(o, "webpage.disambiguatingDescription", secondary)
    o["webpage.lastReviewed"] = today
    if wp_type:
        o["webpage.@type"] = wp_type
    for gone in ("about", "mentions", "relatedLink", "sameAs", "significantLink"):
        o["webpage." + gone] = D

    page_url = base_url + path
    items = crumbs or [("Home", base_url + "/"), (headline, page_url)]
    o["breadcrumb.itemListElement"] = project.crumb(items)
    o["breadcrumb.numberOfItems"] = str(len(items))
    _put(o, "breadcrumb.description", primary)
    _put(o, "breadcrumb.disambiguatingDescription", secondary)

    nodes = ["webpage", "breadcrumb"]
    if node == "service":
        nodes.append("service")
        _put(o, "service.name", headline)
        o["service.serviceType"] = [headline] if headline else D
        _put(o, "service.description", primary)
        o["service.provider"] = {"@id": f"{base_url}/#localbusiness"}
        for gone in ("alternateName", "slogan", "sameAs", "category",
                     "termsOfService", "award", "hasOfferCatalog",
                     "disambiguatingDescription", "areaServed"):
            o[f"service.{gone}"] = D
    elif node == "person":
        nodes.append("person")
        _put(o, "person.name", owner or headline)
        o["person.worksFor"] = {"@id": f"{base_url}/#localbusiness"}
        _put(o, "person.sameAs", social or [])
        for gone in ("colleague", "alumniOf", "birthPlace", "birthDate", "height",
                     "nationality", "callSign", "award", "memberOf", "address",
                     "gender", "image", "knowAbout"):
            o[f"person.{gone}"] = D
    elif node == "article":
        nodes.append("article")
        _put(o, "article.headline", headline)
        _put(o, "article.description", primary)
        _put(o, "article.disambiguatingDescription", secondary)
        o["article.url"] = base_url + path
        o["article.author"] = {"@type": "Person", "name": owner} if owner else {"@id": org_id}
        o["article.publisher"] = {"@id": org_id}
        for gone in ("dateCreated", "datePublished", "dateModified", "commentCount",
                     "alternativeHeadline", "award", "editor", "genre", "wordcount",
                     "keywords", "potentialAction", "articleBody", "backstory",
                     "abstract", "text", "citation", "image"):
            o[f"article.{gone}"] = D
    if faq:
        nodes.append("faqpage")
        o["faqpage.mainEntity"] = project.questions(faq)
    return {"file": file, "path": path, "nodes": nodes, "overrides": o}
