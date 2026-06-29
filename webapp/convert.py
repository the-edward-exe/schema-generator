"""Convert a JSON sample into JSON Schema, typed code, or SQL DDL.

Best-effort structural inference (quicktype-lite): walks a JSON value and emits
a chosen output format. Handles the @-prefixed keys common in JSON-LD.
"""
import json
import re

FORMATS = ["json-schema", "typescript", "python", "go", "java", "sql"]


def _words(key):
    key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key.lstrip("@"))  # split camelCase
    return [w for w in re.split(r"[^0-9A-Za-z]+", key) if w] or ["field"]


def _pascal(key):
    return "".join(w[:1].upper() + w[1:] for w in _words(key)) or "Type"


def _camel(key):
    p = _pascal(key)
    return p[:1].lower() + p[1:]


def _snake(key):
    return "_".join(w.lower() for w in _words(key))


def _singular(name):
    return name[:-1] if len(name) > 3 and name.lower().endswith("s") else name


def _is_ident(k):
    return bool(re.match(r"^[A-Za-z_$][\w$]*$", k))


# --------------------------------------------------------------------------- #
# Intermediate model: collect named object types in first-seen order.
# A type-ref is ("scalar", name) | ("array", ref) | ("ref", TypeName)
# --------------------------------------------------------------------------- #
class _Types:
    def __init__(self):
        self.order = []
        self.defs = {}

    def add(self, name, fields):
        base, i = name, 2
        while name in self.defs and self.defs[name] != fields:
            name = f"{base}{i}"; i += 1
        if name not in self.defs:
            self.order.append(name); self.defs[name] = fields
        return name


def _collect(obj, root="Root"):
    T = _Types()

    def ref(v, hint):
        if v is None:
            return ("scalar", "null")
        if isinstance(v, bool):
            return ("scalar", "boolean")
        if isinstance(v, int):
            return ("scalar", "integer")
        if isinstance(v, float):
            return ("scalar", "number")
        if isinstance(v, str):
            return ("scalar", "string")
        if isinstance(v, list):
            if not v:
                return ("array", ("scalar", "any"))
            elem = next((x for x in v if x is not None), v[0])
            return ("array", ref(elem, _singular(hint)))
        if isinstance(v, dict):
            fields = {k: ref(val, k) for k, val in v.items()}
            name = T.add(_pascal(hint), fields)
            return ("ref", name)
        return ("scalar", "any")

    root_ref = ref(obj, root)
    return T, root_ref


# --------------------------------------------------------------------------- #
# JSON Schema (2020-12)
# --------------------------------------------------------------------------- #
def to_json_schema(obj, title="Root"):
    def infer(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, bool):
            return {"type": "boolean"}
        if isinstance(v, int):
            return {"type": "integer"}
        if isinstance(v, float):
            return {"type": "number"}
        if isinstance(v, str):
            return {"type": "string"}
        if isinstance(v, list):
            if not v:
                return {"type": "array", "items": {}}
            elem = next((x for x in v if x is not None), v[0])
            return {"type": "array", "items": infer(elem)}
        if isinstance(v, dict):
            return {"type": "object",
                    "properties": {k: infer(val) for k, val in v.items()},
                    "required": list(v.keys())}
        return {}
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
              "title": title}
    schema.update(infer(obj))
    return json.dumps(schema, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Typed languages
# --------------------------------------------------------------------------- #
_TS = {"string": "string", "number": "number", "integer": "number",
       "boolean": "boolean", "null": "null", "any": "any"}
_PY = {"string": "str", "number": "float", "integer": "int",
       "boolean": "bool", "null": "None", "any": "Any"}
_GO = {"string": "string", "number": "float64", "integer": "int64",
       "boolean": "bool", "null": "interface{}", "any": "interface{}"}
_JAVA = {"string": "String", "number": "double", "integer": "long",
         "boolean": "boolean", "null": "Object", "any": "Object"}


def _render(ref, scalars, arr, refname):
    kind = ref[0]
    if kind == "scalar":
        return scalars[ref[1]]
    if kind == "array":
        return arr(_render(ref[1], scalars, arr, refname))
    return refname(ref[1])


def to_typescript(obj, root="Root"):
    T, _ = _collect(obj, root)
    out = []
    for name in T.order:
        lines = [f"export interface {name} {{"]
        for k, r in T.defs[name].items():
            t = _render(r, _TS, lambda e: e + "[]", lambda n: n)
            key = k if _is_ident(k) else json.dumps(k)
            lines.append(f"  {key}: {t};")
        lines.append("}")
        out.append("\n".join(lines))
    return "\n\n".join(out) or "// (input was not a JSON object)"


def to_python(obj, root="Root"):
    T, _ = _collect(obj, root)
    out = []
    for name in T.order:
        items = []
        for k, r in T.defs[name].items():
            t = _render(r, _PY, lambda e: f"List[{e}]", lambda n: n)
            items.append(f'    "{k}": {t},')
        out.append(f'{name} = TypedDict("{name}", {{\n' + "\n".join(items) + "\n})")
    body = "\n\n".join(out) or "# (input was not a JSON object)"
    return "from typing import Any, List, TypedDict\n\n\n" + body


def to_go(obj, root="Root"):
    T, _ = _collect(obj, root)
    out = []
    for name in T.order:
        lines = [f"type {name} struct {{"]
        for k, r in T.defs[name].items():
            t = _render(r, _GO, lambda e: "[]" + e, lambda n: n)
            lines.append(f'\t{_pascal(k)} {t} `json:"{k}"`')
        lines.append("}")
        out.append("\n".join(lines))
    return "package main\n\n" + "\n\n".join(out) if out else "package main"


def to_java(obj, root="Root"):
    T, _ = _collect(obj, root)
    out = []
    for name in T.order:
        lines = [f"public class {name} {{"]
        for k, r in T.defs[name].items():
            t = _render(r, _JAVA, lambda e: f"List<{e}>", lambda n: n)
            lines.append(f"    public {t} {_camel(k)};")
        lines.append("}")
        out.append("\n".join(lines))
    head = "import java.util.List;\n\n"
    return head + "\n\n".join(out) if out else "// (input was not a JSON object)"


_SQL = {"string": "VARCHAR(512)", "number": "DOUBLE PRECISION",
        "integer": "BIGINT", "boolean": "BOOLEAN", "null": "TEXT", "any": "TEXT"}


def to_sql(obj, table="record"):
    if not isinstance(obj, dict):
        return "-- SQL DDL requires a JSON object at the top level."
    tbl = _snake(table) or "record"
    cols = ["  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"]
    for k, v in obj.items():
        col = _snake(k)
        if isinstance(v, bool):
            t = _SQL["boolean"]
        elif isinstance(v, int):
            t = _SQL["integer"]
        elif isinstance(v, float):
            t = _SQL["number"]
        elif isinstance(v, str):
            t = _SQL["string"]
        elif v is None:
            t = "TEXT"
        else:  # nested object/array -> JSON column
            t = "JSONB"
        cols.append(f"  {col} {t}")
    return f"CREATE TABLE {tbl} (\n" + ",\n".join(cols) + "\n);"


_DISPATCH = {
    "json-schema": to_json_schema, "typescript": to_typescript,
    "python": to_python, "go": to_go, "java": to_java, "sql": to_sql,
}


def convert(text, fmt, root="Root"):
    """Parse JSON `text` and convert to `fmt`. Raises ValueError on bad input."""
    if fmt not in _DISPATCH:
        raise ValueError(f"unknown format '{fmt}'")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}")
    fn = _DISPATCH[fmt]
    if fmt == "sql":
        return fn(obj, table=root)
    if fmt == "json-schema":
        return fn(obj, title=_pascal(root))
    return fn(obj, root=_pascal(root))
