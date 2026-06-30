"""Web UI for the schema generator — a thin Flask wrapper over schemagen.

Two pages behind a shared nav:
  /           Schema generator (crawl/auto-build, two-zip JSON-LD export)
  /converter  Output & Conversion (JSON -> JSON Schema / types / SQL DDL)

Web Blend-branded; optional HTTP basic auth; gear Settings (generator defaults).
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
from urllib.parse import urlparse

from flask import Flask, request, send_file, Response, jsonify

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
from schemagen import core, identity, project  # noqa: E402
import crawl  # noqa: E402
import describe  # noqa: E402
import convert  # noqa: E402

app = Flask(__name__)

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


# --------------------------------------------------------------------------- #
# Shared chrome
# --------------------------------------------------------------------------- #
STYLE = """
 :root{--ink:#151515;--surface:#1F1F1F;--surface2:#2A2A2A;--line:#3a3a3a;
   --orange:#FE8F35;--orange2:#ED7A1C;--gold:#F7C74A;--text:#ECECEC;--muted:#B9B9B9;
   --grad:linear-gradient(135deg,#FE8F35 0%,#F7C74A 100%);}
 *{box-sizing:border-box}
 body{font:15px/1.6 'Inter',system-ui,sans-serif;background:var(--ink);color:var(--text);margin:0}
 h1,h2,.appname{font-family:'Poppins',sans-serif;letter-spacing:-.01em}
 .topbar{display:flex;align-items:center;gap:.5rem;padding:.8rem 1.25rem;border-bottom:1px solid var(--line);background:#121212;position:sticky;top:0;z-index:5}
 .brand{display:flex;align-items:center;gap:.6rem}.brand img{height:28px;display:block}
 .appname{font-weight:700;font-size:1rem;background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
 .nav{display:flex;gap:.3rem;margin-left:1rem;flex:1}
 .nav a{color:var(--muted);text-decoration:none;font-weight:600;font-size:.88rem;padding:.45rem .8rem;border-radius:8px}
 .nav a:hover{color:#fff;background:var(--surface2)}
 .nav a.on{color:#151515;background:var(--grad)}
 .gear{background:transparent;border:1px solid var(--line);border-radius:10px;width:38px;height:38px;display:grid;place-items:center;cursor:pointer;color:var(--orange);transition:.2s}
 .gear:hover{border-color:var(--orange);transform:rotate(45deg)}.gear svg{width:19px;height:19px}
 .wrap{max-width:780px;margin:0 auto;padding:1.5rem 1.25rem 4rem}
 .hero{margin:.5rem 0 1.4rem}.hero h1{font-size:1.8rem;margin:.2rem 0 .4rem;line-height:1.15}
 .hero h1 .accent{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
 .lede{color:var(--muted);margin:0;max-width:62ch}.lede code{background:var(--surface2);padding:.05rem .35rem;border-radius:5px;color:#fff;font-size:.85em}
 h2{font-size:1rem;margin:1.8rem 0 .4rem;color:var(--orange);border-bottom:1px solid var(--line);padding-bottom:.35rem}
 label{display:block;margin:.7rem 0 .2rem;font-weight:600;font-size:.83rem;color:#d8d8d8}
 .hint{font-weight:400;color:var(--muted);font-size:.78rem}
 input,textarea,select{width:100%;padding:.55rem .65rem;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--surface2);color:var(--text)}
 input::placeholder,textarea::placeholder{color:#7c7c7c}
 input:focus,textarea:focus,select:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 3px rgba(254,143,53,.18)}
 textarea{min-height:3.5rem;resize:vertical}
 .row{display:flex;gap:.8rem;flex-wrap:wrap}.row>div{flex:1;min-width:160px}
 .card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:1.1rem 1.25rem;margin-top:1rem}
 .auto{background:linear-gradient(135deg,rgba(254,143,53,.12),rgba(247,199,74,.06));border-color:#5a4326}
 .chkrow label{display:inline-flex;align-items:center;font-weight:400;margin-right:1.1rem}
 .chk{width:auto;margin-right:.4rem}
 .switch{display:flex;align-items:center;gap:.6rem;font-weight:600;font-size:.95rem;color:#fff}
 button.primary{margin-top:1.5rem;background:var(--grad);color:#151515;border:0;padding:.8rem 1.6rem;border-radius:10px;font:700 1rem 'Poppins',sans-serif;cursor:pointer;box-shadow:0 6px 18px rgba(254,143,53,.28);transition:.15s}
 button.primary:hover{transform:translateY(-1px);box-shadow:0 9px 24px rgba(254,143,53,.4)}
 .req:after{content:" *";color:var(--orange)}
 .err{color:#ff8f8f;background:#2a1414;border:1px solid #5b2b2b;padding:.7rem 1rem;border-radius:8px;margin-top:1rem}
 .foot{color:#6f6f6f;font-size:.76rem;margin-top:2rem;text-align:center}
 .overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:flex-start;justify-content:center;padding:6vh 1rem;z-index:20}
 .overlay.open{display:flex}
 .modal{background:var(--surface);border:1px solid var(--line);border-radius:16px;width:100%;max-width:480px;padding:1.4rem 1.5rem;box-shadow:0 20px 60px rgba(0,0,0,.5)}
 .modal h2{margin-top:0;border:0;color:var(--text);display:flex;justify-content:space-between;align-items:baseline}
 .modal h2 small{font:400 .72rem 'Inter';color:var(--muted)}
 .actions{display:flex;gap:.6rem;margin-top:1.3rem}
 .actions button{border-radius:9px;padding:.55rem 1rem;font:600 .9rem 'Inter';cursor:pointer;border:1px solid var(--line);background:var(--surface2);color:var(--text)}
 .actions .save{background:var(--grad);color:#151515;border:0;font-family:'Poppins'}.actions .ghost{margin-left:auto;background:transparent}
 .pwrap{height:10px;background:var(--surface2);border-radius:999px;overflow:hidden;margin:1.1rem 0 .7rem}
 .pbar{height:100%;width:38%;background:var(--grad);border-radius:999px;animation:slide 1.3s ease-in-out infinite}
 @keyframes slide{0%{transform:translateX(-120%)}100%{transform:translateX(330%)}}
 #pstatus{color:var(--muted);font-size:.86rem}
 .copybtn{background:var(--surface2);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:.4rem .9rem;font:600 .82rem 'Inter';cursor:pointer}
 .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.82rem;min-height:11rem}
"""

GEAR = ('<button id="gear" class="gear" title="Settings" aria-label="Settings">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 '
        '1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 '
        '19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 '
        '.33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 '
        '0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 '
        '1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 '
        '1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 '
        '0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg></button>')

HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Web Blend &middot; Schema Generator</title>'
        '<link rel="icon" type="image/png" href="/static/favicon.png">'
        '<link rel="apple-touch-icon" href="/static/favicon.png">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&'
        'family=Poppins:wght@600;700&display=swap" rel="stylesheet">'
        '<style>' + STYLE + '</style></head><body>')

TAIL = ('<p class="foot">Web Blend &middot; Schema Generator</p></div></body></html>')


def topbar(active, gear=False):
    a1 = ' class="on"' if active == "gen" else ""
    a2 = ' class="on"' if active == "conv" else ""
    return ('<header class="topbar"><div class="brand">'
            '<img src="/static/webblend-logo.png" alt="Web Blend">'
            '<span class="appname">Schema Generator</span></div>'
            '<nav class="nav"><a href="/"' + a1 + '>Generator</a>'
            '<a href="/converter"' + a2 + '>Output &amp; Conversion</a></nav>'
            + (GEAR if gear else "") + '</header><div class="wrap">')


# --------------------------------------------------------------------------- #
# Generator page
# --------------------------------------------------------------------------- #
GEN_BODY = """
<div class="hero">
  <h1>JSON-LD <span class="accent">Schema Generator</span></h1>
  <p class="lede">Enter a business and domain. Auto-build crawls the site, writes a
  strategic schema.org profile for every page, and fills logo, socials and
  descriptions from the site. Output: bare <code>.json</code> JSON-LD, delivered as
  two zips (site-wide + per-page).</p>
</div>
<form id="genform" method="post" action="/generate">
<input type="hidden" name="search_url" id="f_search_url">
<div class="card auto">
  <label class="switch"><input class="chk" type="checkbox" name="autobuild" id="autobuild" checked> Auto-build schema from the website</label>
  <p class="hint">Crawls the domain, builds a WebPage schema per page (+ Person / Service /
  Article / CollectionPage where detected), and auto-fills any blank Logo / Socials /
  Descriptions from the site. Turn off to build only the pages you tick below.</p>
</div>
<div class="card">
<h2>Business identity (site-wide)</h2>
<div class="row"><div><label class="req">Business name</label><input name="name" required></div>
<div><label class="req">Domain</label><input name="domain" placeholder="https://www.acme.com" required></div></div>
<button type="button" id="scanbtn" class="primary" style="margin-top:.7rem">Fill from Site Scan</button>
<span class="hint" id="scanhint" style="margin-left:.5rem">Crawl the homepage to pre-fill the empty fields below — then review &amp; edit before generating.</span>
<div class="row" style="margin-top:.6rem"><div><label>Industry @type <span class="hint">(Dentist, Restaurant, Store…)</span></label><input name="itype" id="f_itype" placeholder="LocalBusiness"></div>
<div><label>Legal name</label><input name="legal"></div></div>
<div class="row"><div><label>Phone</label><input name="phone"></div><div><label>Email</label><input name="email"></div></div>
<label>Short description <span class="hint">(blank = auto from site)</span></label><textarea name="desc"></textarea>
<label>Second description <span class="hint">(must differ; blank = auto)</span></label><textarea name="disambig"></textarea>
<label>Logo URL <span class="hint">(blank = auto)</span></label><input name="logo">
<label>Social profile URLs <span class="hint">(blank = auto; else one per line / comma)</span></label><textarea name="social"></textarea>
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
<h2>Manual pages <span class="hint">(used when Auto-build is off)</span></h2>
<div class="chkrow">
 <label><input class="chk" type="checkbox" name="std" value="about" id="p_about">About</label>
 <label><input class="chk" type="checkbox" name="std" value="contact" id="p_contact">Contact</label>
 <label><input class="chk" type="checkbox" name="std" value="collection" id="p_collection">Shop / Collection</label>
 <label><input class="chk" type="checkbox" name="std" value="faq_home" id="p_faq">FAQ on home</label>
</div>
<label>Home FAQ <span class="hint">(one per line as <code>Question | Answer</code>)</span></label>
<textarea name="home_faq" placeholder="Do you ship nationwide? | Yes, across the country."></textarea>
<label>Advanced — extra pages as JSON <span class="hint">(optional; list of {file,path,nodes,overrides})</span></label>
<textarea name="pages_json" placeholder="[]"></textarea>
</div>
<button class="primary" type="submit">Generate &amp; download</button>
</form>
<div id="formerr" class="err" style="display:none"></div>

<div class="overlay" id="overlay"><div class="modal">
  <h2>Settings <small>defaults remembered in this browser</small></h2>
  <label>Default industry @type</label><input id="s_itype" placeholder="LocalBusiness">
  <label>Default country</label><input id="s_country" placeholder="US">
  <label>Default site search URL <span class="hint">(uses {search_term_string})</span></label>
  <input id="s_search" placeholder="https://site.com/search?q={search_term_string}">
  <label>Manual pages checked by default</label>
  <div class="chkrow">
    <label><input class="chk" type="checkbox" id="s_p_about">About</label>
    <label><input class="chk" type="checkbox" id="s_p_contact">Contact</label>
    <label><input class="chk" type="checkbox" id="s_p_collection">Collection</label>
    <label><input class="chk" type="checkbox" id="s_p_faq">FAQ</label>
  </div>
  <div class="actions"><button class="save" id="s_save">Save</button>
    <button id="s_reset">Reset</button><button class="ghost" id="s_close">Close</button></div>
</div></div>
<div class="overlay" id="progress"><div class="modal">
  <h2 style="display:block;border:0;color:var(--text)">Generating schema…</h2>
  <div class="pwrap"><div class="pbar"></div></div>
  <div id="pstatus">Starting…</div>
</div></div>
"""

GEN_JS = """<script>
const $=s=>document.querySelector(s);
const SK="schemagen_settings_v1";
function load(){try{return JSON.parse(localStorage.getItem(SK))||{}}catch(e){return{}}}
function apply(){const s=load();
  if(s.itype)$("#f_itype").value=s.itype; if(s.country)$("#f_country").value=s.country;
  if(s.search_url!==undefined)$("#f_search_url").value=s.search_url;
  if(s.pages){$("#p_about").checked=!!s.pages.about;$("#p_contact").checked=!!s.pages.contact;
    $("#p_collection").checked=!!s.pages.collection;$("#p_faq").checked=!!s.pages.faq;}}
function openModal(){const s=load();
  $("#s_itype").value=s.itype||"";$("#s_country").value=s.country||"";$("#s_search").value=s.search_url||"";
  const p=s.pages||{};$("#s_p_about").checked=!!p.about;$("#s_p_contact").checked=!!p.contact;
  $("#s_p_collection").checked=!!p.collection;$("#s_p_faq").checked=!!p.faq;$("#overlay").classList.add("open");}
function closeModal(){$("#overlay").classList.remove("open")}
$("#gear").onclick=openModal;$("#s_close").onclick=closeModal;
$("#overlay").onclick=e=>{if(e.target===$("#overlay"))closeModal()};
$("#s_save").onclick=()=>{const s={itype:$("#s_itype").value.trim(),country:$("#s_country").value.trim(),
  search_url:$("#s_search").value.trim(),pages:{about:$("#s_p_about").checked,contact:$("#s_p_contact").checked,
  collection:$("#s_p_collection").checked,faq:$("#s_p_faq").checked}};
  localStorage.setItem(SK,JSON.stringify(s));apply();closeModal();};
$("#s_reset").onclick=()=>{localStorage.removeItem(SK);
  $("#s_itype").value="";$("#s_country").value="";$("#s_search").value="";
  ["s_p_about","s_p_contact","s_p_collection","s_p_faq"].forEach(i=>$("#"+i).checked=false);
  $("#f_itype").value="";$("#f_country").value="US";$("#f_search_url").value="";
  ["p_about","p_contact","p_collection","p_faq"].forEach(i=>$("#"+i).checked=false);};
apply();
const PF=$("#genform");
$("#scanbtn").onclick=async()=>{
  const dom=PF.querySelector('[name=domain]').value.trim();const fe=$("#formerr");
  if(!dom){fe.textContent="Enter a domain first, then Fill from Site Scan.";fe.style.display="block";fe.scrollIntoView({behavior:"smooth",block:"center"});return;}
  fe.style.display="none";const b=$("#scanbtn"),o=b.textContent;b.disabled=true;b.textContent="Scanning…";
  try{const fd=new FormData();fd.append("domain",dom);
    const r=await fetch("/scan",{method:"POST",body:fd});
    if(r.ok){const d=await r.json();let n=0;
      const FIELDS=["name","itype","legal","phone","email","desc","disambig","logo","social","cities","locality","region","country","street","owner","keywords","hours","price","maps"];
      FIELDS.forEach(k=>{if(!d[k])return;const el=PF.querySelector('[name="'+k+'"]');if(el&&!el.value){el.value=d[k];n++;}});
      const blank=FIELDS.filter(k=>{const el=PF.querySelector('[name="'+k+'"]');return el&&!el.value.trim();});
      b.textContent=(n?("Filled "+n+" field"+(n>1?"s":"")+" ✓"):"Nothing new found");
      $("#scanhint").textContent=(n?("Filled "+n+" from the site."):"No new fields found.")+
        (blank.length?(" Still empty: "+blank.slice(0,10).join(", ")+(blank.length>10?"…":"")+".") :" All fields complete.");
      setTimeout(()=>{b.textContent=o;b.disabled=false;},2200);}
    else{let m="Scan failed.";try{const j=await r.json();if(j&&j.error)m=j.error;}catch(_){}
      fe.textContent="Error: "+m;fe.style.display="block";b.textContent=o;b.disabled=false;}}
  catch(err){fe.textContent="Network error: "+err.message;fe.style.display="block";b.textContent=o;b.disabled=false;}
};
const SA=["Connecting to the site…","Crawling pages (sitemap & links)…","Reading titles & descriptions…","Writing schema for each page…","Packaging JSON into zips…"];
const SM=["Building schema…","Packaging JSON into zips…"];
let pt=null,p0=0;
function showP(auto){const st=auto?SA:SM;let i=0;p0=Date.now();$("#pstatus").textContent=st[0]+" (0s)";$("#progress").classList.add("open");
  pt=setInterval(()=>{const s=Math.round((Date.now()-p0)/1000);if(i<st.length-1&&s>=(i+1)*6)i++;$("#pstatus").textContent=st[i]+" ("+s+"s)";},500);}
function hideP(){clearInterval(pt);$("#progress").classList.remove("open");}
PF.addEventListener("submit",async e=>{e.preventDefault();$("#formerr").style.display="none";showP($("#autobuild").checked);
  try{const r=await fetch("/generate",{method:"POST",body:new FormData(PF)});const ct=r.headers.get("Content-Type")||"";
    if(r.ok&&ct.includes("application/zip")){const b=await r.blob();const cd=r.headers.get("Content-Disposition")||"";
      const m=cd.match(/filename=([^;]+)/);const nm=m?m[1].trim().replace(/"/g,""):"schema.zip";
      const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=nm;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(u);hideP();}
    else{let msg="Something went wrong.";try{const j=await r.json();if(j&&j.error)msg=j.error;}catch(_){}hideP();
      const fe=$("#formerr");fe.textContent="Error: "+msg;fe.style.display="block";fe.scrollIntoView({behavior:"smooth",block:"center"});}}
  catch(err){hideP();const fe=$("#formerr");fe.textContent="Network error: "+err.message;fe.style.display="block";}});
</script>"""


# --------------------------------------------------------------------------- #
# Converter page
# --------------------------------------------------------------------------- #
CONV_BODY = """
<div class="hero">
  <h1>Output &amp; <span class="accent">Conversion</span></h1>
  <p class="lede">Paste any JSON — e.g. a node from your generated schema — and convert it
  to a JSON&nbsp;Schema, typed code, or SQL DDL. Then copy it to the clipboard.</p>
</div>
<div class="card">
<label>JSON input</label>
<textarea id="cv_input" class="mono" placeholder='{"@type":"Organization","name":"Acme Co","numberOfEmployees":12}'></textarea>
<div class="row">
  <div><label>Format</label>
    <select id="cv_format">
      <option value="json-schema">JSON Schema</option>
      <option value="typescript">TypeScript</option>
      <option value="python">Python (TypedDict)</option>
      <option value="go">Go structs</option>
      <option value="java">Java classes</option>
      <option value="sql">SQL DDL</option>
    </select></div>
  <div><label>Root type name</label><input id="cv_root" value="Root"></div>
</div>
<button type="button" class="primary" id="cv_btn">Convert</button>
<div id="cv_err" class="err" style="display:none"></div>
<div style="display:flex;align-items:center;justify-content:space-between;margin-top:1rem">
  <label style="margin:0">Output</label>
  <button type="button" id="cv_copy" class="copybtn">Copy to clipboard</button>
</div>
<textarea id="cv_output" class="mono" readonly></textarea>
</div>
"""

CONV_JS = """<script>
const $=s=>document.querySelector(s);
$("#cv_btn").onclick=async()=>{$("#cv_err").style.display="none";
  const fd=new FormData();fd.append("json",$("#cv_input").value);fd.append("format",$("#cv_format").value);fd.append("root",$("#cv_root").value||"Root");
  try{const r=await fetch("/convert",{method:"POST",body:fd});
    if(r.ok){$("#cv_output").value=await r.text();}
    else{let m="Conversion failed.";try{const j=await r.json();if(j&&j.error)m=j.error;}catch(_){}
      const e=$("#cv_err");e.textContent="Error: "+m;e.style.display="block";}}
  catch(err){const e=$("#cv_err");e.textContent="Network error: "+err.message;e.style.display="block";}};
$("#cv_copy").onclick=async()=>{const t=$("#cv_output").value;if(!t)return;const b=$("#cv_copy"),o=b.textContent;
  try{await navigator.clipboard.writeText(t);}catch(e){$("#cv_output").select();document.execCommand("copy");}
  b.textContent="Copied!";setTimeout(()=>b.textContent=o,1500);};
</script>"""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _split(raw):
    return [x.strip() for x in re.split(r"[\n,]+", raw or "") if x.strip()]


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


def _zip_bytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, path in files:
            z.write(path, arcname=arc)
    b.seek(0)
    return b.read()


def _err(msg, code=400):
    return jsonify({"error": msg}), code


_NODE = {"person": ("person", None), "service": ("service", None),
         "article": ("article", None), "collection": (None, "CollectionPage"),
         "product": (None, "CollectionPage")}


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.route("/")
def home():
    return HEAD + topbar("gen", gear=True) + GEN_BODY + TAIL + GEN_JS


@app.route("/converter")
def converter():
    return HEAD + topbar("conv", gear=False) + CONV_BODY + TAIL + CONV_JS


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/scan", methods=["POST"])
def scan_route():
    dom = request.form.get("domain", "").strip()
    if not dom:
        return _err("Enter a domain to scan.")
    try:
        res = crawl.scan(dom, timeout=int(os.environ.get("CRAWL_TIMEOUT", "20")))
    except Exception as e:
        return _err(f"Scan failed: {type(e).__name__}: {e}")
    if res.get("error"):
        return _err(f"Couldn't scan {dom} — {res['error']}. "
                    "The site may block automated requests or require JavaScript.")
    return jsonify(res)


@app.route("/convert", methods=["POST"])
def convert_route():
    text = request.form.get("json", "")
    fmt = request.form.get("format", "json-schema")
    root = request.form.get("root", "Root") or "Root"
    try:
        out = convert.convert(text, fmt, root=root)
    except ValueError as e:
        return _err(str(e))
    return Response(out, mimetype="text/plain; charset=utf-8")


@app.route("/generate", methods=["POST"])
def generate():
    f = request.form
    if not f.get("name") or not f.get("domain"):
        return _err("Business name and domain are required.")
    data = {k: f.get(k, "").strip() for k in
            ("name", "legal", "domain", "itype", "phone", "email", "desc", "disambig",
             "logo", "locality", "region", "country", "street", "owner", "hours",
             "maps", "price", "entity", "search_url")}
    data["business"] = data["name"]
    data["social"] = _split(f.get("social"))
    data["cities"] = _split(f.get("cities"))
    data["keywords"] = _split(f.get("keywords"))
    data["licenses"] = _split(f.get("licenses"))
    biz = data["name"]
    base_url = core.base_url(data["domain"])
    today = datetime.date.today().strftime("%Y/%m/%d")
    area = data["cities"][0] if data["cities"] else data["locality"]
    auto = bool(f.get("autobuild"))

    site = None
    if auto:
        try:
            site = crawl.crawl(data["domain"],
                               max_pages=int(os.environ.get("CRAWL_MAX", "25")),
                               timeout=int(os.environ.get("CRAWL_TIMEOUT", "20")))
        except Exception as e:
            return _err(f"Crawl failed: {type(e).__name__}: {e}")
        if not site or not site.get("pages"):
            reason = (site or {}).get("error") or "no reachable pages"
            return _err(f"Couldn't crawl {data['domain']} — {reason}. "
                        "The site may block automated requests or require JavaScript. "
                        "Turn off Auto-build to add pages manually.")
        a = site["assets"]
        if not data["logo"] and a.get("logo"):
            data["logo"] = a["logo"]
        if not data["social"] and a.get("social"):
            data["social"] = a["social"]
        if not data["desc"] or not data["disambig"]:
            d1, d2 = describe.describe(site["pages"][0], biz, area)
            data["desc"] = data["desc"] or d1
            data["disambig"] = data["disambig"] or d2

    sw = identity.sitewide_overrides(data)
    pages = []
    std = set(f.getlist("std"))
    home_faq = _faq_lines(f.get("home_faq")) if "faq_home" in std else None
    pages.append(identity.page_pack(base_url, "home", "/", biz, data["desc"],
                                    data["disambig"], today, faq=home_faq,
                                    crumbs=[("Home", base_url + "/")]))

    if auto:
        used = {"home", "sitewide"}
        for m in site["pages"]:
            path = urlparse(m["url"]).path or "/"
            if path == "/":
                continue
            node, wp_type = _NODE.get(crawl.page_node_type(m["url"]), (None, None))
            title = (m.get("title") or path.strip("/").replace("-", " ").title())[:70] or "Page"
            d1, d2 = describe.describe(m, biz, area)
            file = _slug(path)
            while file in used:
                file += "-x"
            used.add(file)
            pages.append(identity.page_pack(
                base_url, file, path, title, d1, d2, today, node=node,
                owner=data["owner"], social=data["social"],
                crumbs=[("Home", base_url + "/"), (title, base_url + path)],
                wp_type=wp_type))
    else:
        if "collection" in std:
            pages.append(identity.page_pack(base_url, "collection", "/shop", f"Shop {biz}",
                data["desc"], data["disambig"], today,
                crumbs=[("Home", base_url + "/"), ("Shop", base_url + "/shop")]))
        if "about" in std:
            pages.append(identity.page_pack(base_url, "about", "/about", f"About {biz}",
                data["desc"], data["disambig"], today, node="person",
                owner=data["owner"], social=data["social"]))
        if "contact" in std:
            pages.append(identity.page_pack(base_url, "contact", "/contact", f"Contact {biz}",
                data["desc"], data["disambig"], today))

    try:
        extra = json.loads(f.get("pages_json") or "[]")
        if isinstance(extra, list):
            pages.extend(extra)
    except json.JSONDecodeError as e:
        return _err(f"Pages JSON invalid: {e}")

    config = {"project": biz, "domain": data["domain"],
              "sitewide": {"overrides": sw}, "pages": pages}

    slug = _slug(biz)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            written = project.generate(config, base=tmp)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        site_files = [p for p in written if os.path.basename(p) == "sitewide.json"]
        page_files = [p for p in written if os.path.basename(p) != "sitewide.json"]
        sitewide_zip = _zip_bytes([(os.path.basename(p), p) for p in site_files])
        pages_zip = _zip_bytes([(os.path.basename(p), p) for p in page_files])
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{slug}-sitewide.zip", sitewide_zip)
            z.writestr(f"{slug}-pages.zip", pages_zip)
        outer.seek(0)
    return send_file(outer, mimetype="application/zip", as_attachment=True,
                     download_name=f"{slug}-schema.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
