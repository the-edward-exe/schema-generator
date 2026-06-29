---
name: schema-markup-generator
description: >-
  Generate SOP-compliant schema.org JSON-LD (structured data) for a website or
  business — single types or a full per-page connected @graph. Trigger when the
  user wants schema markup, JSON-LD, structured data, rich results / rich
  snippets, an entity/knowledge graph, or "schema" for a site, page, product,
  article, local business, FAQ, breadcrumb, service, person, etc. Produces a
  site-wide identity graph plus per-page graphs, following the in-house Schema
  Markup SOP and the Clint Butler / Schema App methodology (entity linking via
  Wikipedia/Wikidata/Google KG, dual descriptions, citation strategy). Outputs to
  "Customer outputs/<Business Name>/".
---

# Schema Markup Generator

Builds schema.org JSON-LD from vetted, neutral templates. The structure of each
template is fixed (it's what "claims" the schema profile); you supply the
per-business values and entity links. Markup is correct by construction — every
node gets an `@id`, descriptions are kept distinct, casing is normalized, and the
output validates.

Schema here is not just tags — it is a **content knowledge graph**: each page's
entities are linked via `sameAs` to authority URIs (Wikipedia, Wikidata, Google
Knowledge Graph machine IDs like `/m/07qy2g`) so search engines understand *which*
entity is meant (Subject → Predicate → Object triples, expressed in JSON-LD).

## Output convention (required)

Always write generated files to:

```
Customer outputs/<Business Name>/
    sitewide.json      # Organization + LocalBusiness + WebSite (header, every page)
    home.json          # WebPage + Breadcrumb (+ page node) per page
    <page>.json        # one file per page
```

`schemagen.project.generate(config, base=".")` does this for you (see Workflow).

## Quick start

Standard library only — no dependencies.

```bash
python -m schemagen project                           # guided wizard (easiest)
python -m schemagen list                              # the 15 types
python -m schemagen build organization --domain acme.com --set name="Acme Co"
python -m schemagen build localbusiness --domain acme.com --set @type=Dentist
python -m schemagen graph --domain acme.com --strict -o sitewide.json
```

**`project`** is the interactive wizard: it asks for the business once and for
each page, then writes the whole connected set to `Customer outputs/<Business Name>/`.
Blank answers are omitted from the output (no template placeholder data ships),
so just fill the strategy fields you have (social `sameAs`, service areas,
keywords, licenses) and skip the rest. `--base <dir>` sets where
`Customer outputs/` is created (default: current directory).

Flags: `--domain` (swaps the example.com placeholder), `--set key=value`
(repeatable; dotted keys + JSON values; `__DELETE__` removes a key), `--strict`
(canonical schema.org casing), `--no-wrap` (bare JSON), `-o` (file).

## Deployment model (from the SOP / Clint Butler)

- **Organization schema is site-wide** and goes in the **header only** — Google
  bots stop crawling past it. Remove any conflicting schema plugins; don't reuse
  the same text across schema types (write fresh or rewrite).
- **Single-location business:** deploy LocalBusiness **site-wide** (header) too.
- **Multi-location business:** Organization site-wide; LocalBusiness only on each
  **service-location page**.
- **Each page** carries its own **WebPage + Breadcrumb** (+ a page-specific node
  such as Article / Product / Service / Person / FAQPage). Page nodes reference
  the site-wide nodes by `@id`, so when both `<script>` blocks render on a page
  Google merges them into one connected graph (one shared `@context`,
  cross-linked `@id`s).
- **Add a FAQ to every page** to claim FAQ schema — but the Q&A **must be visible
  on the page**.
- **Always validate** (this is mandatory):
  https://search.google.com/test/rich-results and https://validator.schema.org/.
  **If Google passes but schema.org errors, go with Google.**

## Global rules (encoded in the generator)

- Every top-level `@type` gets an `@id` with a `#fragment`
  (`https://site.com/#webpage`). Drill-down sub-types get a new `@type` in their
  own `{ }`; sub-types do **not** need their own `@id`.
- `description` (CTR, meta-description style) **and**
  `disambiguatingDescription` (SEO benefit) are **both** filled and **must be
  different** content — the generator warns if they match. Write each like a meta
  description.
- `query` in a SearchAction must be **`query-input`** (Google rejects `query`).
- Add **speakable** for faster indexing where applicable (requires the Google
  speakable program).
- Entity terms in `about`/`mentions` must **also appear in the page content** —
  don't inject entities you don't mention.

## Strategy reference (the important part)

Cross-referenced with the SOP and the Clint Butler course. These are the field
plays that "claim" each profile; the neutral templates already include them.

### Entity linking & the knowledge graph
- `identifier` / `mainEntityOfPage` / `sameAs` link the entity to authority URIs.
  Use **Wikipedia** (titles), **Wikidata** (QIDs, stable even when names change),
  **Google KG** (machine IDs `/m/...`), DBpedia. Any structured/semi-structured
  source is fine (Quora included) — it doesn't have to be Wikipedia.
- `@type: "Thing"` + `name` + `sameAs` is the unit of entity linking in
  `about`/`mentions`. (Templates use lowercase `thing` as house-style; `--strict`
  normalizes to `Thing`.)

### Article (used most; use `newsArticle` only for real news blogs)
- `articleBody`: paste the **entire post** — keyword-stuffing opportunity and a
  crawl backup if Google can't render the page.
- `backstory`: author/why-written — a **trust signal** against thin-content flags.
- `abstract` / `text` / `keywords`: keyword opportunities (meta-description style).
- `awards`: list your **keywords as awards** even without real awards
  (`"2020 Best <service> in <city>"`).
- `alternativeHeadline`: a **People-Also-Ask** headline.
- `sameAs`: **only** for product reviews (manufacturer/original/Amazon URL).
- `mainEntityOfPage`: the article **permalink** (not the entity page).
- `citations` + `reviewedBy`: **only when directed** — required-ish for YMYL
  (doctors, dentists, lawyers, financial, heavily-regulated). Strong trust signal.

### Product
- Use a **real customer review**; add `aggregateRating` only if a real rating
  exists (never fabricate). `gtin`/`globalLocationNumber` (GLN via gs1.org),
  `mpn`, `awards` as keywords, `sameAs` to manufacturer/original/Amazon.

### Organization (site-wide; key for affiliate sites)
- `sameAs` = the **social fortress**: LinkedIn (most important), Facebook,
  Instagram, Twitter/X, YouTube, Pinterest, Google Maps (if local), plus
  IFTTT/social-blast. Use the `www` form. This `sameAs` defines the brand — it is
  **not** a citation.
- `areaServed` (city array), `founder`, `foundingLocation` (+ `Place`/`geo`),
  `knowsAbout` (keyword list), `makesOffer`, `hasCredential` (licenses),
  `aggregateRating`, `brand`, `award` (keywords-as-awards).

### WebSite
- `potentialAction` SearchAction = sitelinks search box (`query-input`).
- `identifier` = entity URL; `alternateName` = parent-company name.

### WebPage (Topical Relevance strategy)
- Start from topicalrelevance.com for the page's entity → recommended word count,
  single semantic keywords, phrases. Put entities in `about` (core) and
  `mentions` (secondary) as `Thing` + `sameAs`. **Don't include entities not in
  the content.**
- `relatedLink`: Wikidata **and** Wikipedia entity links. `significantLink`:
  Contact-Us URL. `lastReviewed`: today (year/month/day). `mainEntityOfPage`: the
  page URL (not the entity).

### LocalBusiness
- Set `@type` to the **industry subtype** (e.g. `Dentist`, `Electrician`) and/or
  `additionalType`. `knowsAbout` = cleaned keyword list. `areaServed` / `location`
  = service cities (address goes in `PostalAddress`, not `location`). `hasMap` =
  GMB share link. `geoCovers` for geographic areas. `globalLocationNumber` (GLN)
  for retail/healthcare/transport/technical.
- `sameAs` here = the **citation blast** (directory listings) — doubles as Tier-1
  link building. The template ships a large neutral directory list to fill.

### Breadcrumb
- Exactly **4 items** (the rich snippet shows 4), each with a `position`. CTR
  value only — no direct SEO benefit. Build with `project.crumb([...])`.

### FAQPage
- `mainEntity` = `Question` → `acceptedAnswer`. Add to every page to claim FAQ
  schema; **answers must be visible on the page**. Build with
  `project.questions([(q, a), ...])`.

### Person / Service / HowTo / Book / Recipe / VideoObject / JobPosting
- Person: author/owner (`worksFor` → `@id` of the business). Service:
  `hasOfferCatalog` of offerings, `provider` → business `@id`. The rest are
  standard schema.org with the same `description`/`disambiguatingDescription` and
  entity-linking conventions.

### Tools the SOP relies on (manual steps — gather, then pass via `--set`)
- webcode.tools (JSON-LD), schema.org (canonical JSON-LD templates at the bottom
  of each type), topicalrelevance.com (entities/keywords),
  microdatagenerator.org localbusiness generator, gs1.org (GLN), wikidata.org +
  Wikipedia (entity URIs). Entity links are **not** auto-fetched.

## Workflow (authoring a project)

1. Gather the business data: name, legal name, domain, phone, email, address,
   social profiles, services, service areas, licenses, owner — and the **entity
   `sameAs` URIs** (Wikipedia/Wikidata/Google KG) for the page's core topics.
2. Build a **sitewide overrides** map (keyed `<fragment>.<dotted.key>`) and a list
   of **page specs** (each: `file`, `path`, `nodes`, `overrides`). Use
   `project.crumb(...)` for breadcrumbs and `project.questions(...)` for FAQs.
   Strip any template residue you don't want with the `__DELETE__` sentinel.
3. `schemagen.project.generate(config)` → files land in
   `Customer outputs/<Business Name>/`.
4. **Validate every page** (Google Rich Results + schema.org; Google wins).

```python
from schemagen import project
config = {
  "project": "Acme Co",
  "domain": "https://www.acme.com",
  "sitewide": {"overrides": {
      "organization.name": "Acme Co",
      "localbusiness.@type": "Dentist",
      "localbusiness.foundingLocation": "__DELETE__",
      # ... real phone, address, sameAs social, knowsAbout, hasCredential ...
  }},
  "pages": [
    {"file": "home", "path": "/", "nodes": ["webpage", "breadcrumb", "faqpage"],
     "overrides": {
        "webpage.headline": "...", "webpage.about": [ {"@type":"Thing","name":"...","sameAs":["https://en.wikipedia.org/wiki/..."]} ],
        "breadcrumb.itemListElement": project.crumb([("Home", "https://www.acme.com/")]),
        "faqpage.mainEntity": project.questions([("Q?", "A.")]),
     }},
  ],
}
project.generate(config)
```

## Architecture

```
schemagen/
  cli.py            python -m schemagen {list, build, graph, project}
  core.py           load skeleton, domain swap, overrides (+__DELETE__), strict
                    casing, @graph assembly, description checks, emit
  project.py        per-page builder + output convention (Customer outputs/<name>/)
  wizard.py         interactive `project` wizard
  registry.py       the 15 types: @type, @id fragment, template, prompt fields
  templates/*.json  neutral, valid JSON skeletons (structure + all profile fields)
```

Add a type: drop a skeleton JSON in `templates/` and add a `registry.TYPES`
entry. The `--strict` casing fixes live in `core._STRICT_KEY_FIXES` /
`_STRICT_TYPE_FIXES`. Every skeleton ships with neutral placeholder values that
demonstrate each field's strategy; replace them per business via `--set` /
`overrides`.
