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

UA = {"User-Agent": "Mozilla/5.0 (compatible; WebBlendSchemaBot/1.0; +https://webblend.us)"}

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


def _get(url, timeout=8):
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r
    except requests.RequestException:
        pass
    return None


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


def _page_meta(url):
    r = _get(url, timeout=8)
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

    home = _get(base + "/", timeout=timeout)
    assets = _extract_assets(home.text, base) if home else {"logo": "", "social": [], "description": ""}

    urls = _sitemap_urls(base, host, max_pages) or _crawl_links(base + "/", host, max_pages)
    # homepage first, dedup, cap
    ordered, seen = [], set()
    for u in [base + "/"] + urls:
        if u not in seen:
            ordered.append(u); seen.add(u)
        if len(ordered) >= max_pages:
            break

    pages = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for m in ex.map(_page_meta, ordered):
            if m:
                pages.append(m)
    return {"base": base, "host": host, "assets": assets, "pages": pages}


def page_node_type(url):
    path = urlparse(url).path.lower()
    for kw, node in PAGE_TYPE_HINTS:
        if kw in path:
            return node
    return None
