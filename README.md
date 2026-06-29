# schema-generator

A Python CLI that generates **SOP-compliant schema.org JSON-LD** — single types or
a connected `@graph` — from a set of vetted templates. Built to follow the in-house
Schema Markup SOP and the Schema App / Clint Butler methodology.

## Why

Schema markup here isn't just tags — it's a **content knowledge graph**: every
page's entities are linked via `sameAs` to authority URIs (Wikipedia, Wikidata,
Google Knowledge Graph machine IDs) so search engines understand *which* entity is
meant. This tool encodes the SOP's structures so output is correct by construction;
you supply the per-business values and entity links manually.

## Install

No dependencies — standard-library Python 3.8+.

```bash
python -m schemagen list
```

## Usage

```bash
# List the 14 supported types
python -m schemagen list

# Build a single type, swapping example.com -> your domain, overriding fields
python -m schemagen build organization --domain acme.com \
    --set name="Acme Co" \
    --set 'description=...' --set 'disambiguatingDescription=...'

# Set the LocalBusiness industry subtype
python -m schemagen build localbusiness --domain acme.com --set @type=Dentist

# Interactive prompts for the primary fields
python -m schemagen build article --domain acme.com -i

# Assemble a full-site connected @graph (one shared @context, cross-linked @ids)
python -m schemagen graph --domain acme.com -o site-schema.html

# Pick which nodes go in the graph
python -m schemagen graph organization website webpage breadcrumb --domain acme.com

# Bare JSON instead of the <script> wrapper
python -m schemagen build website --domain acme.com --no-wrap

# Strict schema.org casing (normalize house-style keys for max Rich Results pass)
python -m schemagen build article --domain acme.com --strict
python -m schemagen graph --domain acme.com --strict -o site-schema.html
```

### `--strict` casing

By default the output preserves the templates' house-style verbatim. `--strict`
normalizes the known deviations to canonical schema.org casing (runs last, so it
also fixes deviant `--set` keys):

| house-style | strict |
|---|---|
| `wordcount` | `wordCount` |
| `knowAbout` | `knowsAbout` |
| `telePhone` | `telephone` |
| `sameas` | `sameAs` |
| `"@type": "thing"` | `"@type": "Thing"` |

Legitimate (if legacy) properties like `alternativeHeadline` and `interactionCount`
are left as-is.

### Overrides

`--set key=value` is repeatable and supports:
- **Dotted paths**: `--set address.addressLocality=Phoenix`
- **JSON values**: `--set 'areaServed=["Phoenix, AZ","Mesa, AZ"]'`
- **Graph targeting**: in `graph` mode, prefix with the node fragment —
  `--set organization.name="Acme"`, `--set localbusiness.@type=Dentist`

## What it does (and the rules it enforces)

- Replaces the `example.com` placeholder host (incl. `cdn.`/`www.` subdomains)
  with your domain across `@id`, `url`, etc. Real external links
  (wikipedia/wikidata/schema.org) are untouched.
- In `@graph` mode: one shared top-level `@context`, each node gets a unique
  resolvable `#fragment` `@id` so nodes cross-reference cleanly.
- Warns when `description` and `disambiguatingDescription` are identical or one is
  missing (the SOP wants both, and distinct).
- Always prints the validator reminder. **Always validate before shipping:**
  - https://search.google.com/test/rich-results
  - https://validator.schema.org/
  - If Google passes but schema.org errors, go with Google.

## Manual steps (by design, per the SOP)

The tool does **not** auto-fetch these — gather them and pass via `--set`:
- Entity `sameAs` URIs (Wikipedia / Wikidata QIDs / Google KG machine IDs) for
  `about` / `mentions` / `identifier` / `mainEntityOfPage`
- GLN/GTIN (gs1.org), lat/long (Google Maps), topicalrelevance.com keywords

## Layout

```
schemagen/
  cli.py            # command-line interface
  core.py           # load skeleton, domain swap, overrides, graph assembly, emit
  registry.py       # the 14 types: @type, @id fragment, template, prompt fields
  templates/*.json  # cleaned, valid JSON skeletons (structure from Schema Templates/)
tools/
  build_templates.py  # regenerates templates/ from the source Schema Templates/
Schema Templates/   # original source templates (canonical structure)
tech-supporting-documents/  # the SOP + course PDFs the methodology is drawn from
```

## Regenerating templates

The skeletons in `schemagen/templates/` are derived from `Schema Templates/`
(`<script>` wrapper stripped, JSON breakages repaired). To rebuild:

```bash
python tools/build_templates.py
```

`recipe.json` is hand-maintained (its source is too malformed to auto-repair).

## Notes on fidelity

Per project decision, template **structure is reproduced faithfully** by default —
including house-style choices that differ from strict schema.org casing (e.g.
`founders`, lowercase `thing` in `about`/`mentions`, `wordcount`). Only JSON-breaking
issues were fixed. Pass `--strict` to normalize the casing deviations (see above).
