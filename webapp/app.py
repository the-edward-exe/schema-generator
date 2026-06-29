"""Web UI for the schema generator — a thin Flask wrapper over schemagen.

Fill the business form, optionally tick standard pages / paste advanced page
specs, and download a ZIP of the schema files (one per page, plus sitewide).
Designed for DigitalOcean App Platform (gunicorn webapp.app:app).
"""
import datetime
import hmac
import io
import json
import os
import re
import sys
import tempfile
import zipfile

from flask import Flask, request, send_file, render_template_string, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemagen import core, identity, project  # noqa: E402

app = Flask(__name__)

# Optional HTTP basic auth. Set AUTH_USER + AUTH_PASS (env vars / App Platform
# secrets) to require login on every route except the platform health check.
# If unset (e.g. local dev), the app is open.
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")


@app.before_request
def _require_auth():
    if not (AUTH_USER and AUTH_PASS) or request.path == "/healthz":
        return None
    a = request.authorization
    ok = (a and a.type == "basic"
          and hmac.compare_digest(a.username or "", AUTH_USER)
          and hmac.compare_digest(a.password or "", AUTH_PASS))
    if not ok:
        return Response("Authentication required.", 401,
                        {"WWW-Authenticate": 'Basic realm="Schema Generator"'})
    return None

FORM = """<!doctype html><html><head><meta charset="utf-8">
<title>Schema Generator</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{font:15px/1.5 system-ui,sans-serif;max-width:780px;margin:2rem auto;padding:0 1rem;color:#1a1a2e}
 h1{font-size:1.4rem} h2{font-size:1rem;margin-top:1.6rem;border-bottom:1px solid #ddd;padding-bottom:.3rem}
 label{display:block;margin:.6rem 0 .15rem;font-weight:600;font-size:.85rem}
 input,textarea,select{width:100%;padding:.5rem;border:1px solid #ccc;border-radius:6px;font:inherit;box-sizing:border-box}
 textarea{min-height:3.5rem} .row{display:flex;gap:.8rem}.row>div{flex:1}
 .hint{font-weight:400;color:#666;font-size:.78rem} .chk{display:inline-block;width:auto;margin-right:.4rem}
 .chkrow label{display:inline-block;font-weight:400;margin-right:1.2rem}
 button{margin-top:1.4rem;background:#5b5bd6;color:#fff;border:0;padding:.7rem 1.4rem;border-radius:8px;font-size:1rem;cursor:pointer}
 .req:after{content:" *";color:#c0392b}
</style></head><body>
<h1>JSON-LD Schema Generator</h1>
<p class="hint">Blank fields are omitted (no placeholder data ships). Output: one
<code>.html</code> JSON-LD file per page + <code>sitewide.schema.html</code>, zipped.</p>
<form method="post" action="/generate">
<h2>Business identity (site-wide)</h2>
<div class="row"><div><label class="req">Business name</label><input name="name" required></div>
<div><label class="req">Domain</label><input name="domain" placeholder="https://www.acme.com" required></div></div>
<div class="row"><div><label>Industry @type <span class="hint">(Dentist, Restaurant, Store, ProfessionalService…)</span></label><input name="itype" placeholder="LocalBusiness"></div>
<div><label>Legal name</label><input name="legal"></div></div>
<div class="row"><div><label>Phone</label><input name="phone"></div><div><label>Email</label><input name="email"></div></div>
<label>Short description <span class="hint">(meta-style)</span></label><textarea name="desc"></textarea>
<label>Second description <span class="hint">(must differ)</span></label><textarea name="disambig"></textarea>
<label>Logo URL</label><input name="logo">
<label>Social profile URLs <span class="hint">(one per line or comma-separated; LinkedIn first)</span></label><textarea name="social"></textarea>
<label>Service-area cities <span class="hint">(comma / newline separated)</span></label><textarea name="cities"></textarea>
<div class="row"><div><label>City</label><input name="locality"></div><div><label>State/region</label><input name="region"></div>
<div><label>Country</label><input name="country" value="US"></div></div>
<label>Street address</label><input name="street">
<label>Owner / key person</label><input name="owner">
<label>Target keywords <span class="hint">(comma / newline separated)</span></label><textarea name="keywords"></textarea>
<label>License / credential numbers <span class="hint">(comma separated)</span></label><input name="licenses">
<div class="row"><div><label>Opening hours</label><input name="hours" placeholder="Mo,Tu,We,Th,Fr 09:00-17:00"></div>
<div><label>Price range</label><input name="price" placeholder="$$"></div></div>
<label>Google Maps / Business link (hasMap)</label><input name="maps">
<label>Brand entity URL <span class="hint">(Wikipedia/Wikidata)</span></label><input name="entity">

<h2>Pages</h2>
<p class="hint">Home is always built. Tick standard pages to include:</p>
<div class="chkrow">
 <label><input class="chk" type="checkbox" name="std" value="about">About</label>
 <label><input class="chk" type="checkbox" name="std" value="contact">Contact</label>
 <label><input class="chk" type="checkbox" name="std" value="collection">Shop / Collection</label>
 <label><input class="chk" type="checkbox" name="std" value="faq_home">FAQ on home</label>
</div>
<label>Home FAQ <span class="hint">(only if ticked; one per line as <code>Question | Answer</code>)</span></label>
<textarea name="home_faq" placeholder="Do you ship nationwide? | Yes, across the country."></textarea>
<label>Advanced — extra pages as JSON <span class="hint">(optional; list of {file,path,nodes,overrides})</span></label>
<textarea name="pages_json" placeholder='[]'></textarea>
<button type="submit">Generate &amp; download ZIP</button>
</form>
{% if error %}<p style="color:#c0392b"><b>Error:</b> {{ error }}</p>{% endif %}
</body></html>"""


def _split(raw):
    if not raw:
        return []
    return [x.strip() for x in re.split(r"[\n,]+", raw) if x.strip()]


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "page"


def _faq_lines(raw):
    qa = []
    for line in (raw or "").splitlines():
        if "|" in line:
            q, a = line.split("|", 1)
            if q.strip():
                qa.append((q.strip(), a.strip()))
    return qa


@app.route("/")
def home():
    return render_template_string(FORM, error=None)


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/generate", methods=["POST"])
def generate():
    f = request.form
    if not f.get("name") or not f.get("domain"):
        return render_template_string(FORM, error="Business name and domain are required.")
    data = {k: f.get(k, "").strip() for k in
            ("name", "legal", "domain", "itype", "phone", "email", "desc", "disambig",
             "logo", "locality", "region", "country", "street", "owner", "hours",
             "maps", "price", "entity")}
    data["business"] = data["name"]
    data["social"] = _split(f.get("social"))
    data["cities"] = _split(f.get("cities"))
    data["keywords"] = _split(f.get("keywords"))
    data["licenses"] = _split(f.get("licenses"))

    base_url = core.base_url(data["domain"])
    today = datetime.date.today().strftime("%Y/%m/%d")
    biz = data["name"]
    sw = identity.sitewide_overrides(data)

    # Home (+ optional FAQ)
    std = set(f.getlist("std"))
    home_faq = _faq_lines(f.get("home_faq")) if "faq_home" in std else None
    pages = [identity.page_pack(base_url, "home", "/", biz, data["desc"],
                                data["disambig"], today, faq=home_faq,
                                crumbs=[("Home", base_url + "/")])]

    if "collection" in std:
        pages.append(identity.page_pack(
            base_url, "collection", "/shop", f"Shop {biz}",
            data["desc"], data["disambig"], today,
            crumbs=[("Home", base_url + "/"), ("Shop", base_url + "/shop")]))
    if "about" in std:
        pages.append(identity.page_pack(
            base_url, "about", "/about", f"About {biz}", data["desc"],
            data["disambig"], today, node="person", owner=data["owner"],
            social=data["social"]))
    if "contact" in std:
        pages.append(identity.page_pack(
            base_url, "contact", "/contact", f"Contact {biz}", data["desc"],
            data["disambig"], today))

    # Advanced JSON pages
    try:
        extra = json.loads(f.get("pages_json") or "[]")
        if isinstance(extra, list):
            pages.extend(extra)
    except json.JSONDecodeError as e:
        return render_template_string(FORM, error=f"Pages JSON invalid: {e}")

    config = {"project": biz, "domain": data["domain"],
              "sitewide": {"overrides": sw}, "pages": pages}

    with tempfile.TemporaryDirectory() as tmp:
        try:
            written = project.generate(config, base=tmp)
        except Exception as e:  # surface config errors to the form
            return render_template_string(FORM, error=f"{type(e).__name__}: {e}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in written:
                z.write(p, arcname=os.path.join(biz, os.path.basename(p)))
        buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{_slug(biz)}-schema.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
