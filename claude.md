# schema-generator — project notes for Claude

JSON-LD schema generator. Python 3.8+, **standard library only** (no deps, no venv).

## Run / test
- `python -m schemagen list`
- `python -m schemagen build <type> --domain <d> [--set k=v ...] [-i] [-o file] [--no-wrap]`
- `python -m schemagen graph [types...] --domain <d>`
- Quick self-check (all types emit valid JSON, graph assembles):
  ```bash
  python - <<'PY'
  import json; from schemagen import core, registry
  for n in registry.TYPES: json.loads(core.to_jsonld(core.build_single(n, domain="acme.com"), wrap=False))
  json.loads(core.to_jsonld(core.assemble_graph(registry.GRAPH_ORDER, domain="acme.com"), wrap=False))
  print("ok")
  PY
  ```

## Architecture
- `registry.py` — single source of truth for the 14 types (`@type`, `@id` fragment,
  template file, interactive prompt fields). Add a type here + a skeleton file.
- `core.py` — `load_skeleton`, `apply_domain`, `apply_overrides`/`set_field`
  (dotted keys + JSON values), `check_descriptions`, `build_single`,
  `assemble_graph` (+ `apply_overrides_graph`), `to_jsonld`.
- `templates/*.json` — cleaned skeletons; **generated** by `tools/build_templates.py`
  from `Schema Templates/`. `recipe.json` is hand-maintained (do not clobber).

## Conventions / decisions (don't silently change these)
- **Fidelity policy**: by default reproduce the source template structure verbatim,
  including non-standard house-style keys (`founders`, lowercase `thing`,
  `wordcount`, `knowAbout`). Fix **only** JSON-breaking issues. `--strict`
  (`core.strict_casing`) opts into canonical schema.org casing; the correction maps
  `_STRICT_KEY_FIXES` / `_STRICT_TYPE_FIXES` list every deviation handled — add new
  ones there. Strict runs last so it also normalizes deviant `--set` keys.
- **Entity linking is manual** (Wikipedia/Wikidata/Google KG `sameAs`) — supplied
  via `--set`, never auto-fetched. This matches the SOP workflow.
- `description` must differ from `disambiguatingDescription`; the generator warns
  but does not block.
- Domain swap targets `*.example.com` only; never rewrite real external URIs.
- Output is `<script type="application/ld+json">`-wrapped by default.

## Source of truth for the methodology
`tech-supporting-documents/` (the SOP + Clint Butler + Schema App PDFs) and
`Schema Templates/` (the canonical structures). When in doubt about a field's
intent, check the SOP.
