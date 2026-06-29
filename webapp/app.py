"""Web UI for the schema generator — a thin Flask wrapper over schemagen.

Fill the business form, optionally tick standard pages / paste advanced page
specs, and download a ZIP of the schema files (one per page, plus sitewide).
Web Blend-branded landing page + a gear Settings panel (browser-stored defaults).
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


FORM = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Web Blend · Schema Generator</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Poppins:wght@600;700&display=swap" rel="stylesheet">
<style>
 :root{
   --ink:#151515; --surface:#1F1F1F; --surface2:#2A2A2A; --line:#3a3a3a;
   --orange:#FE8F35; --orange2:#ED7A1C; --gold:#F7C74A;
   --text:#ECECEC; --muted:#B9B9B9;
   --grad:linear-gradient(135deg,#FE8F35 0%,#F7C74A 100%);
 }
 *{box-sizing:border-box}
 body{font:15px/1.6 'Inter',system-ui,sans-serif;background:var(--ink);color:var(--text);margin:0}
 h1,h2,.appname{font-family:'Poppins',sans-serif;letter-spacing:-.01em}
 .topbar{display:flex;align-items:center;justify-content:space-between;
   padding:.9rem 1.25rem;border-bottom:1px solid var(--line);
   background:#121212;position:sticky;top:0;z-index:5}
 .brand{display:flex;align-items:center;gap:.7rem}
 .brand img{height:30px;display:block}
 .appname{font-weight:700;font-size:1.05rem;background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
 .gear{background:transparent;border:1px solid var(--line);border-radius:10px;width:40px;height:40px;
   display:grid;place-items:center;cursor:pointer;color:var(--orange);transition:.2s}
 .gear:hover{border-color:var(--orange);transform:rotate(45deg)}
 .gear svg{width:20px;height:20px}
 .wrap{max-width:780px;margin:0 auto;padding:1.5rem 1.25rem 4rem}
 .hero{margin:.5rem 0 1.6rem}
 .hero h1{font-size:1.9rem;margin:.2rem 0 .4rem;line-height:1.15}
 .hero h1 .accent{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
 .lede{color:var(--muted);margin:0;max-width:60ch}
 .lede code{background:var(--surface2);padding:.05rem .35rem;border-radius:5px;color:#fff;font-size:.85em}
 h2{font-size:1rem;margin:1.8rem 0 .4rem;color:var(--orange);
   border-bottom:1px solid var(--line);padding-bottom:.35rem}
 label{display:block;margin:.7rem 0 .2rem;font-weight:600;font-size:.83rem;color:#d8d8d8}
 .hint{font-weight:400;color:var(--muted);font-size:.78rem}
 input,textarea,select{width:100%;padding:.55rem .65rem;border:1px solid var(--line);
   border-radius:8px;font:inherit;background:var(--surface2);color:var(--text)}
 input::placeholder,textarea::placeholder{color:#7c7c7c}
 input:focus,textarea:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 3px rgba(254,143,53,.18)}
 textarea{min-height:3.5rem;resize:vertical}
 .row{display:flex;gap:.8rem;flex-wrap:wrap}.row>div{flex:1;min-width:160px}
 .card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:1.1rem 1.25rem;margin-top:1rem}
 .chkrow label{display:inline-flex;align-items:center;font-weight:400;margin-right:1.1rem}
 .chk{width:auto;margin-right:.4rem}
 button.primary{margin-top:1.5rem;background:var(--grad);color:#151515;border:0;
   padding:.8rem 1.6rem;border-radius:10px;font:700 1rem 'Poppins',sans-serif;cursor:pointer;
   box-shadow:0 6px 18px rgba(254,143,53,.28);transition:.15s}
 button.primary:hover{transform:translateY(-1px);box-shadow:0 9px 24px rgba(254,143,53,.4)}
 .req:after{content:" *";color:var(--orange)}
 .err{color:#ff8f8f;background:#2a1414;border:1px solid #5b2b2b;padding:.7rem 1rem;border-radius:8px;margin-top:1rem}
 .foot{color:#6f6f6f;font-size:.76rem;margin-top:2rem;text-align:center}
 /* settings modal */
 .overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;
   align-items:flex-start;justify-content:center;padding:6vh 1rem;z-index:20}
 .overlay.open{display:flex}
 .modal{background:var(--surface);border:1px solid var(--line);border-radius:16px;
   width:100%;max-width:480px;padding:1.4rem 1.5rem;box-shadow:0 20px 60px rgba(0,0,0,.5)}
 .modal h2{margin-top:0;border:0;color:var(--text);display:flex;justify-content:space-between;align-items:baseline}
 .modal h2 small{font:400 .72rem 'Inter';color:var(--muted)}
 .actions{display:flex;gap:.6rem;margin-top:1.3rem}
 .actions button{flex:0 0 auto;border-radius:9px;padding:.55rem 1rem;font:600 .9rem 'Inter';cursor:pointer;border:1px solid var(--line);background:var(--surface2);color:var(--text)}
 .actions .save{background:var(--grad);color:#151515;border:0;font-family:'Poppins'}
 .actions .ghost{margin-left:auto;background:transparent}
</style></head><body>
<header class="topbar">
  <div class="brand"><img src="/static/webblend-logo.png" alt="Web Blend"><span class="appname">Schema Generator</span></div>
  <button id="gear" class="gear" title="Settings" aria-label="Settings">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"></circle>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
    </svg>
  </button>
</header>
<div class="wrap">
<div class="hero">
  <h1>JSON-LD <span class="accent">Schema Generator</span></h1>
  <p class="lede">Generate SOP-compliant schema.org structured data for any business.
  Blank fields are omitted (no placeholder data ships). Output: one
  <code>.html</code> JSON-LD file per page + <code>sitewide.schema.html</code>, zipped.</p>
</div>
<form method="post" action="/generate">
<input type="hidden" name="search_url" id="f_search_url">
<div class="card">
<h2>Business identity (site-wide)</h2>
<div class="row"><div><label class="req">Business name</label><input name="name" required></div>
<div><label class="req">Domain</label><input name="domain" placeholder="https://www.acme.com" required></div></div>
<div class="row"><div><label>Industry @type <span class="hint">(Dentist, Restaurant, Store, ProfessionalService…)</span></label><input name="itype" id="f_itype" placeholder="LocalBusiness"></div>
<div><label>Legal name</label><input name="legal"></div></div>
<div class="row"><div><label>Phone</label><input name="phone"></div><div><label>Email</label><input name="email"></div></div>
<label>Short description <span class="hint">(meta-style)</span></label><textarea name="desc"></textarea>
<label>Second description <span class="hint">(must differ)</span></label><textarea name="disambig"></textarea>
<label>Logo URL</label><input name="logo">
<label>Social profile URLs <span class="hint">(one per line or comma-separated; LinkedIn first)</span></label><textarea name="social"></textarea>
<label>Service-area cities <span class="hint">(comma / newline separated)</span></label><textarea name="cities"></textarea>
<div class="row"><div><label>City</label><input name="locality"></div><div><label>State/region</label><input name="region"></div>
<div><label>Country</label><input name="country" id="f_country" value="US"></div></div>
<label>Street address</label><input name="street">
<label>Owner / key person</label><input name="owner">
<label>Target keywords <span class="hint">(comma / newline separated)</span></label><textarea name="keywords"></textarea>
<label>License / credential numbers <span class="hint">(comma separated)</span></label><input name="licenses">
<div class="row"><div><label>Opening hours</label><input name="hours" placeholder="Mo,Tu,We,Th,Fr 09:00-17:00"></div>
<div><label>Price range</label><input name="price" placeholder="$$"></div></div>
<label>Google Maps / Business link (hasMap)</label><input name="maps">
<label>Brand entity URL <span class="hint">(Wikipedia/Wikidata)</span></label><input name="entity">
</div>

<div class="card">
<h2>Pages</h2>
<p class="hint">Home is always built. Tick standard pages to include:</p>
<div class="chkrow">
 <label><input class="chk" type="checkbox" name="std" value="about" id="p_about">About</label>
 <label><input class="chk" type="checkbox" name="std" value="contact" id="p_contact">Contact</label>
 <label><input class="chk" type="checkbox" name="std" value="collection" id="p_collection">Shop / Collection</label>
 <label><input class="chk" type="checkbox" name="std" value="faq_home" id="p_faq">FAQ on home</label>
</div>
<label>Home FAQ <span class="hint">(only if ticked; one per line as <code>Question | Answer</code>)</span></label>
<textarea name="home_faq" placeholder="Do you ship nationwide? | Yes, across the country."></textarea>
<label>Advanced — extra pages as JSON <span class="hint">(optional; list of {file,path,nodes,overrides})</span></label>
<textarea name="pages_json" placeholder="[]"></textarea>
</div>
<button class="primary" type="submit">Generate &amp; download ZIP</button>
</form>
{% if error %}<p class="err"><b>Error:</b> {{ error }}</p>{% endif %}
<p class="foot">Web Blend · Schema Generator — structured data that helps Google understand the business.</p>
</div>

<div class="overlay" id="overlay">
  <div class="modal">
    <h2>Settings <small>defaults remembered in this browser</small></h2>
    <label>Default industry @type</label><input id="s_itype" placeholder="LocalBusiness">
    <label>Default country</label><input id="s_country" placeholder="US">
    <label>Default site search URL <span class="hint">(uses {search_term_string})</span></label>
    <input id="s_search" placeholder="https://site.com/search?q={search_term_string}">
    <label>Pages checked by default</label>
    <div class="chkrow">
      <label><input class="chk" type="checkbox" id="s_p_about">About</label>
      <label><input class="chk" type="checkbox" id="s_p_contact">Contact</label>
      <label><input class="chk" type="checkbox" id="s_p_collection">Collection</label>
      <label><input class="chk" type="checkbox" id="s_p_faq">FAQ</label>
    </div>
    <div class="actions">
      <button class="save" id="s_save">Save</button>
      <button id="s_reset">Reset</button>
      <button class="ghost" id="s_close">Close</button>
    </div>
  </div>
</div>

<script>
const SK="schemagen_settings_v1";
const $=s=>document.querySelector(s);
function load(){try{return JSON.parse(localStorage.getItem(SK))||{}}catch(e){return{}}}
function apply(){
  const s=load();
  if(s.itype) $("#f_itype").value=s.itype;
  if(s.country) $("#f_country").value=s.country;
  if(s.search_url!==undefined) $("#f_search_url").value=s.search_url;
  if(s.pages){
    $("#p_about").checked=!!s.pages.about;
    $("#p_contact").checked=!!s.pages.contact;
    $("#p_collection").checked=!!s.pages.collection;
    $("#p_faq").checked=!!s.pages.faq;
  }
}
function openModal(){
  const s=load();
  $("#s_itype").value=s.itype||"";
  $("#s_country").value=s.country||"";
  $("#s_search").value=s.search_url||"";
  const p=s.pages||{};
  $("#s_p_about").checked=!!p.about; $("#s_p_contact").checked=!!p.contact;
  $("#s_p_collection").checked=!!p.collection; $("#s_p_faq").checked=!!p.faq;
  $("#overlay").classList.add("open");
}
function closeModal(){$("#overlay").classList.remove("open")}
$("#gear").onclick=openModal;
$("#s_close").onclick=closeModal;
$("#overlay").onclick=e=>{if(e.target===$("#overlay"))closeModal()};
$("#s_save").onclick=()=>{
  const s={itype:$("#s_itype").value.trim(),country:$("#s_country").value.trim(),
    search_url:$("#s_search").value.trim(),
    pages:{about:$("#s_p_about").checked,contact:$("#s_p_contact").checked,
      collection:$("#s_p_collection").checked,faq:$("#s_p_faq").checked}};
  localStorage.setItem(SK,JSON.stringify(s)); apply(); closeModal();
};
$("#s_reset").onclick=()=>{localStorage.removeItem(SK);
  $("#s_itype").value="";$("#s_country").value="";$("#s_search").value="";
  ["s_p_about","s_p_contact","s_p_collection","s_p_faq"].forEach(i=>$("#"+i).checked=false);
  $("#f_itype").value="";$("#f_country").value="US";$("#f_search_url").value="";
  ["p_about","p_contact","p_collection","p_faq"].forEach(i=>$("#"+i).checked=false);
};
apply();
</script>
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
             "maps", "price", "entity", "search_url")}
    data["business"] = data["name"]
    data["social"] = _split(f.get("social"))
    data["cities"] = _split(f.get("cities"))
    data["keywords"] = _split(f.get("keywords"))
    data["licenses"] = _split(f.get("licenses"))

    base_url = core.base_url(data["domain"])
    today = datetime.date.today().strftime("%Y/%m/%d")
    biz = data["name"]
    sw = identity.sitewide_overrides(data)

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
        except Exception as e:
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
