"""Command-line interface for schemagen.

Examples:
  python -m schemagen list
  python -m schemagen build organization --domain acme.com --set name="Acme Co"
  python -m schemagen build website --domain acme.com -o website.json
  python -m schemagen graph organization website webpage --domain acme.com
  python -m schemagen build localbusiness --domain acme.com \
        --set @type=Dentist --set name="Bright Smiles"
  python -m schemagen build article --domain acme.com -i   # interactive prompts
"""
import argparse
import sys

from . import core, registry


def _parse_set(pairs):
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--set expects key=value, got: {item}")
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def _emit(obj, args):
    warnings = core.check_descriptions(obj)
    text = core.to_jsonld(obj, wrap=not args.no_wrap)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    print("\n" + core.VALIDATORS, file=sys.stderr)


def _interactive(name, overrides):
    """Prompt for the type's primary fields, pre-filled with template defaults."""
    meta = registry.get(name)
    skeleton = core.load_skeleton(name)
    print(f"Interactive build: {name} ({meta['schema_type']})", file=sys.stderr)
    print("Press Enter to keep the template default; type a new value to override.",
          file=sys.stderr)
    for field in meta["prompt_fields"]:
        if field in overrides:
            continue
        default = skeleton.get(field, "")
        shown = default if isinstance(default, str) else "(structured)"
        try:
            entered = input(f"  {field} [{shown[:60]}]: ").strip()
        except EOFError:
            entered = ""
        if entered:
            overrides[field] = entered
    return overrides


def cmd_list(args):
    print("Available schema types:\n")
    for key, meta in registry.TYPES.items():
        print(f"  {key:14} {meta['schema_type']:22} {meta['blurb']}")
    print("\nGraph assembly order:", " > ".join(registry.GRAPH_ORDER))


def cmd_build(args):
    overrides = _parse_set(args.set)
    if args.interactive:
        overrides = _interactive(args.type, overrides)
    try:
        obj = core.build_single(args.type, domain=args.domain,
                                overrides=overrides, strict=args.strict)
    except KeyError:
        raise SystemExit(f"Unknown type '{args.type}'. Try: python -m schemagen list")
    _emit(obj, args)


def cmd_project(args):
    from . import wizard
    try:
        wizard.run(base=args.base)
    except (EOFError, KeyboardInterrupt):
        print("\nInput closed — aborting (nothing written).", file=sys.stderr)


def cmd_graph(args):
    overrides = _parse_set(args.set)
    names = args.types if args.types else registry.GRAPH_ORDER
    for n in names:
        try:
            registry.get(n)
        except KeyError:
            raise SystemExit(f"Unknown type '{n}'. Try: python -m schemagen list")
    obj = core.assemble_graph(names, domain=args.domain, overrides=overrides,
                              strict=args.strict)
    _emit(obj, args)


def build_parser():
    p = argparse.ArgumentParser(
        prog="schemagen",
        description="Generate SOP-compliant schema.org JSON-LD from templates.")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="list available schema types")
    pl.set_defaults(func=cmd_list)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--domain", help="target domain, e.g. acme.com "
                        "(replaces example.com in @id/url)")
    common.add_argument("--set", action="append", metavar="key=value",
                        help="override a field (dotted keys + JSON values ok); "
                        "repeatable")
    common.add_argument("-o", "--output", help="write to file instead of stdout")
    common.add_argument("--no-wrap", action="store_true",
                        help="emit bare JSON (no <script> wrapper)")
    common.add_argument("--strict", action="store_true",
                        help="normalize house-style keys/@type to canonical "
                        "schema.org casing (knowsAbout, sameAs, telephone, "
                        "wordCount, Thing)")

    pb = sub.add_parser("build", parents=[common], help="build a single schema type")
    pb.add_argument("type", help="schema type key (see `list`)")
    pb.add_argument("-i", "--interactive", action="store_true",
                    help="prompt for the primary fields")
    pb.set_defaults(func=cmd_build)

    pg = sub.add_parser("graph", parents=[common],
                        help="assemble several types into one @graph")
    pg.add_argument("types", nargs="*",
                    help="types to include (default: full-site order)")
    pg.set_defaults(func=cmd_graph)

    pw = sub.add_parser("project",
                        help="interactive wizard -> Customer outputs/<name>/")
    pw.add_argument("--base", default=".",
                    help="base dir that will contain 'Customer outputs/'")
    pw.set_defaults(func=cmd_project)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
