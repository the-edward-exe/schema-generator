"""Lightweight site crawler/scraper for auto-building schema.

Given a domain, discovers pages (sitemap.xml, else same-domain homepage links)
and extracts per-page metadata (title, meta/OG description, canonical) plus
site-wide assets from the homepage (logo, social profile URLs, description).

Best-effort and defensive: any network/parse failure degrades to whatever was
found so far. Used by the web app; not part of the stdlib-only schemagen package.
"""
import concurrent.futures
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SOCIAL = {
    "facebook.com": "facebook", "fb.com": "facebook",
    "instagram.com": "instagram", "x.com": "x", "twitter.com": "twitter",
    "linkedin.com": "linkedin", "youtube.com": "youtube", "youtu.be": "youtube",
    "tiktok.com": "tiktok", "pinterest.com": "pinterest",
}

# Path keywords -> the extra schema node a page should carry (see app.py).
PAGE_TYPE_HINTS = [
    ("about", "person"), ("our-story", "person"), ("team", "person"),
    ("service", "service"), ("our-services", "service"),
    ("product", "product"), ("shop", "collection"), ("collection", "collection"),
    ("store", "collection"),
    ("blog", "article"), ("news", "article"), ("article", "article"), ("post", "article"),
    ("faq", "faq"),
    ("contact", "contact"),
]


def _norm(base, host, href):
    if not href:
        return None
    href = href.split("#")[0].strip()
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    u = urljoin(base, href)
    p = urlparse(u)
    if p.scheme not in ("http", "https") or p.netloc.replace("www.", "") != host.replace("www.", ""):
        return None
    return p.scheme + "://" + p.netloc + p.path.rstrip("/") if p.path != "/" else p.scheme + "://" + p.netloc + "/"


def _fetch(url, timeout=12, retries=1):
    """Return (response, error_reason). response is None on failure."""
    reason = "unreachable"
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r, None
            if r.status_code in (401, 403, 406, 429, 503):
                return None, (f"the site returned HTTP {r.status_code} — it likely "
                              "blocks automated requests (bot protection/WAF)")
            reason = f"HTTP {r.status_code}"
        except requests.Timeout:
            reason = f"timed out after {timeout}s"
            timeout = min(timeout + 8, 25)
        except requests.RequestException as e:
            reason = type(e).__name__.replace("Error", " error")
    return None, reason


def _get(url, timeout=8):
    r, _ = _fetch(url, timeout=timeout, retries=0)
    return r


def _sitemap_urls(base, host, cap):
    """Collect URLs from sitemap.xml / sitemap index / robots.txt Sitemap entries."""
    seeds = [urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml")]
    robots = _get(urljoin(base, "/robots.txt"), timeout=6)
    if robots:
        seeds += re.findall(r"(?i)sitemap:\s*(\S+)", robots.text)
    found, seen_maps = [], set()
    queue = list(dict.fromkeys(seeds))
    while queue and len(found) < cap * 3:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        r = _get(sm, timeout=8)
        if not r:
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            continue
        tag = root.tag.lower()
        locs = [e.text.strip() for e in root.iter() if e.tag.lower().endswith("loc") and e.text]
        if tag.endswith("sitemapindex"):
            queue += locs  # nested sitemaps
        else:
            for loc in locs:
                u = _norm(base, host, loc)
                if u and u not in found:
                    found.append(u)
    return found


def _crawl_links(base, host, cap):
    """Fallback: one level of same-domain links from the homepage."""
    r = _get(base, timeout=8)
    urls = [base]
    if r:
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            u = _norm(base, host, a["href"])
            if u and u not in urls:
                urls.append(u)
            if len(urls) >= cap:
                break
    return urls


def _extract_assets(html, base):
    """Logo, social URLs, description from the homepage HTML."""
    soup = BeautifulSoup(html, "html.parser")

    def meta(*sel):
        for name, key in sel:
            t = soup.find("meta", attrs={name: key})
            if t and t.get("content"):
                return t["content"].strip()
        return ""

    desc = meta(("name", "description"), ("property", "og:description"))

    # logo: og:image -> <img ...logo...> -> apple-touch-icon -> icon
    logo = meta(("property", "og:image"),)
    if not logo:
        for img in soup.find_all("img"):
            blob = " ".join(filter(None, [img.get("src", ""), img.get("alt", ""),
                                          " ".join(img.get("class", []) or [])])).lower()
            if "logo" in blob and img.get("src"):
                logo = urljoin(base, img["src"])
                break
    if not logo:
        for rel in ("apple-touch-icon", "icon", "shortcut icon"):
            t = soup.find("link", rel=lambda v: v and rel in " ".join(v if isinstance(v, list) else [v]).lower())
            if t and t.get("href"):
                logo = urljoin(base, t["href"])
                break

    if logo and not logo.lower().startswith(("http://", "https://")):
        logo = ""  # reject data: URIs and junk

    socials, seen = [], set()
    for a in soup.find_all("a", href=True):
        netloc = urlparse(a["href"]).netloc.lower().replace("www.", "")
        for dom, plat in SOCIAL.items():
            if netloc.endswith(dom) and plat not in seen:
                socials.append(a["href"].split("?")[0]); seen.add(plat)
    return {"logo": logo, "social": socials, "description": desc}


def _page_meta(url, timeout=8):
    r = _get(url, timeout=timeout)
    if not r or "html" not in r.headers.get("Content-Type", "").lower():
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    h1 = soup.find("h1")
    h1 = h1.get_text(strip=True) if h1 else ""

    def meta(name, key):
        t = soup.find("meta", attrs={name: key})
        return t["content"].strip() if t and t.get("content") else ""

    body = soup.find("main") or soup.body or soup
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))[:600] if body else ""
    return {
        "url": url, "title": title or h1, "h1": h1,
        "description": meta("name", "description"),
        "og_description": meta("property", "og:description"),
        "text": text, "html": r.text,
    }


def crawl(domain, max_pages=25, timeout=8):
    """Return {homepage, assets, pages:[meta,...]} for a domain."""
    base = domain if domain.startswith("http") else "https://" + domain
    p = urlparse(base)
    base = p.scheme + "://" + p.netloc
    host = p.netloc

    # Fetch the homepage first (with a retry). If this fails, bail fast with the
    # real reason instead of grinding through sitemap/link attempts.
    home, err = _fetch(base + "/", timeout=timeout, retries=1)
    if not home:
        return {"base": base, "host": host, "error": err,
                "assets": {"logo": "", "social": [], "description": ""}, "pages": []}
    assets = _extract_assets(home.text, base)

    urls = _sitemap_urls(base, host, max_pages) or _crawl_links(base + "/", host, max_pages)
    # homepage first, dedup, cap
    ordered, seen = [], set()
    for u in [base + "/"] + urls:
        if u not in seen:
            ordered.append(u); seen.add(u)
        if len(ordered) >= max_pages:
            break

    pages = []
    per_page = max(6, min(timeout, 20))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for m in ex.map(lambda u: _page_meta(u, timeout=per_page), ordered):
            if m:
                pages.append(m)
    return {"base": base, "host": host, "assets": assets, "pages": pages,
            "error": None if pages else "no crawlable pages were found"}


_LB = {"LocalBusiness", "Store", "OnlineStore", "Restaurant", "ProfessionalService",
       "Organization", "ElectronicsStore", "Dentist", "Plumber", "Electrician",
       "HomeAndConstructionBusiness", "Corporation"}


def _types(n):
    t = n.get("@type")
    return [str(x) for x in (t if isinstance(t, list) else [t])] if t else []


def _text(v):
    if isinstance(v, dict):
        return str(v.get("name") or v.get("url") or "").strip()
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    return ""


def _img(v):
    if isinstance(v, dict):
        return _text(v.get("url") or v.get("contentUrl"))
    return v if isinstance(v, str) else ""


def _names(v):
    if v is None:
        return []
    items = v if isinstance(v, list) else [v]
    return [n for n in (_text(x) for x in items) if n]


def _contacts(soup):
    """(email, phone) from mailto:/tel: links."""
    email = phone = ""
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        low = h.lower()
        if low.startswith("mailto:") and not email:
            email = h.split(":", 1)[1].split("?")[0].strip()
        elif low.startswith("tel:") and not phone:
            phone = h.split(":", 1)[1].strip()
    return email, phone


def _jsonld_nodes(html):
    nodes = []
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = s.string or s.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        items = items if isinstance(items, list) else [items]
        nodes += [it for it in items if isinstance(it, dict)]
    return nodes


def scan(domain, timeout=20):
    """Crawl just the homepage and extract the form-fillable fields (meta tags +
    any existing JSON-LD). Returns {field: value} for the generator form, or
    {"error": reason}. Does NOT build a schema profile."""
    base = domain if domain.startswith("http") else "https://" + domain
    p = urlparse(base)
    base = p.scheme + "://" + p.netloc
    home, err = _fetch(base + "/", timeout=timeout, retries=1)
    if not home:
        return {"error": err or "homepage unreachable"}

    soup = BeautifulSoup(home.text, "html.parser")
    assets = _extract_assets(home.text, base)

    def meta(name, key):
        t = soup.find("meta", attrs={name: key})
        return (t.get("content") or "").strip() if t and t.get("content") else ""
    md, og = meta("name", "description"), meta("property", "og:description")

    org = website = address = person = None
    for n in _jsonld_nodes(home.text):
        ts = _types(n)
        if "WebSite" in ts and not website:
            website = n
        if not org and (set(ts) & _LB or any(t.endswith("Business") for t in ts)):
            org = n
        if "PostalAddress" in ts and not address:
            address = n
        if "Person" in ts and not person:
            person = n
    if not org:
        for n in _jsonld_nodes(home.text):
            if n.get("name") and (n.get("telephone") or n.get("address") or n.get("sameAs")):
                org = n
                break
    org = org or {}
    web = website or {}

    def g(k):
        return org.get(k)

    addr = address or (g("address") if isinstance(g("address"), dict) else {}) or {}
    spec = next((t for t in _types(org) if t not in ("Organization", "Thing", "LocalBusiness")), "")
    sa = g("sameAs")
    socials = [x for x in (sa if isinstance(sa, list) else [sa] if sa else []) if isinstance(x, str)]
    desc = _text(md or og or g("description") or assets.get("description"))
    disa = _text(g("disambiguatingDescription"))
    if not disa:
        disa = og if (og and og != desc) else (md if (md and md != desc) else "")
    if disa == desc:
        disa = ""
    res = {
        "name": _text(g("name") or web.get("name")),
        "itype": spec,
        "legal": _text(g("legalName")),
        "phone": _text(g("telephone") or web.get("telephone")),
        "email": _text(g("email")),
        "desc": desc,
        "disambig": disa,
        "logo": _img(g("logo")) or assets.get("logo") or "",
        "social": "\n".join(socials or assets.get("social") or []),
        "locality": _text(addr.get("addressLocality")),
        "region": _text(addr.get("addressRegion")),
        "country": _text(addr.get("addressCountry")),
        "street": _text(addr.get("streetAddress")),
        "cities": ", ".join(_names(g("areaServed"))),
        "owner": _text((_names(g("founder") or g("founders") or person) or [""])[0]),
        "keywords": ", ".join(_names(g("knowsAbout"))) or _text(g("keywords")),
        "hours": ", ".join(_names(g("openingHours"))) if isinstance(g("openingHours"), list) else _text(g("openingHours")),
        "price": _text(g("priceRange")),
        "maps": _img(g("hasMap")) or _text(g("hasMap")),
    }

    # Homepage mailto:/tel: fallback for contact details.
    hemail, hphone = _contacts(soup)
    res["email"] = res["email"] or hemail
    res["phone"] = res["phone"] or hphone

    # Deep fallback: if still missing phone/email/address, check a Contact/About page.
    if not (res["phone"] and res["email"] and res["locality"]):
        host = p.netloc
        target = None
        for a in soup.find_all("a", href=True):
            u = _norm(base, host, a["href"])
            if u and any(k in u.lower() for k in ("contact", "about")):
                target = u
                break
        if target:
            cr = _get(target, timeout=timeout)
            if cr:
                csoup = BeautifulSoup(cr.text, "html.parser")
                ce, cp = _contacts(csoup)
                res["email"] = res["email"] or ce
                res["phone"] = res["phone"] or cp
                for n in _jsonld_nodes(cr.text):
                    res["phone"] = res["phone"] or _text(n.get("telephone"))
                    res["email"] = res["email"] or _text(n.get("email"))
                    ad = n if "PostalAddress" in _types(n) else (
                        n.get("address") if isinstance(n.get("address"), dict) else None)
                    if ad:
                        res["locality"] = res["locality"] or _text(ad.get("addressLocality"))
                        res["region"] = res["region"] or _text(ad.get("addressRegion"))
                        res["country"] = res["country"] or _text(ad.get("addressCountry"))
                        res["street"] = res["street"] or _text(ad.get("streetAddress"))
    return {k: v for k, v in res.items() if v}


def page_node_type(url):
    path = urlparse(url).path.lower()
    for kw, node in PAGE_TYPE_HINTS:
        if kw in path:
            return node
    return None
