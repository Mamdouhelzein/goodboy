"""goodboy command line."""
from __future__ import annotations

import argparse
import sys
import textwrap

from . import __version__, config
from . import index as idx
from .install import install, installed, list_files, skill_body
from .repos import SourceError, parse_source
from .router import Model, Router, best_sections

WIDTH = 100


def _err(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _router(args, cfg) -> Router:
    skills = idx.load_index(cfg, refresh=getattr(args, "refresh", False),
                            log=lambda m: print(m, file=sys.stderr))
    model = Model.load(args.model) if getattr(args, "model", None) else None
    return Router(skills, model)


def _clip(text: str, lines: int) -> str:
    rows = text.splitlines()
    return "\n".join(rows[:lines]) + (f"\n    ... ({len(rows) - lines} more lines)" if len(rows) > lines else "")


def fetch(router: Router, request: str, full: bool = False, sections: int = 2, lines: int = 25) -> int:
    ranked = router.rank(request, k=3)
    th = router.model.threshold
    if not ranked or ranked[0][0] < th:
        close = [(p, s) for p, s in ranked if p >= 0.2]
        if close and close[0][0] >= 0.5:
            print("Not sure enough to fetch on my own. Best guesses:")
        else:
            print("Nothing to fetch: this doesn't look like it needs a skill.")
            if close:
                print("\nClosest skills, if it does:")
        if close:
            for p, s in close:
                print(f"  {s.id}  ({p:.0%})   ->  goodboy get {s.name}")
        return 0

    p, skill = ranked[0]
    dest = install(skill)
    body = skill_body(dest)
    print(f"Fetched: {skill.id}  (confidence {p:.0%})")
    print(f"Saved to: {dest}")
    print("\n" + textwrap.fill(skill.description, WIDTH))

    if full:
        print("\n" + "-" * 60 + "\n" + body)
    else:
        for title, text in best_sections(body, request, k=sections):
            print(f"\n## {title}\n{_clip(text, lines)}")
        print(f"\n(Full instructions: {dest / 'SKILL.md'}  or  goodboy fetch --full ...)")

    extras = [f for f in list_files(dest) if f.lower() != "skill.md"]
    scripts = [f for f in extras if f.endswith((".py", ".sh", ".js", ".ts"))]
    if scripts:
        print("\nScripts in this skill: " + ", ".join(scripts[:12]) + (" ..." if len(scripts) > 12 else ""))
        print("Read them before you run them: skills are third-party code.")
    others = [(q, s) for q, s in ranked[1:] if q >= th * 0.6]
    if others:
        print("\nAlso close: " + ", ".join(f"{s.name} ({q:.0%})" for q, s in others))
    return 0


def cmd_fetch(args, cfg) -> int:
    return fetch(_router(args, cfg), " ".join(args.request), args.full, args.sections, args.lines)


def cmd_interactive(args, cfg) -> int:
    router = _router(args, cfg)
    print(f"goodboy {__version__}: {len(router.fx.skills)} skills to fetch from. "
          "Tell me what you need (Ctrl-D to quit).")
    while True:
        try:
            line = input("\nfetch> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line in {"exit", "quit", "sit"}:
            return 0
        if line:
            print()
            fetch(router, line)


def cmd_search(args, cfg) -> int:
    router = _router(args, cfg)
    ranked = router.rank(" ".join(args.query), k=args.n)
    if not ranked:
        print("No matching skills.")
    for p, s in ranked:
        print(f"{p:4.0%}  {s.id}\n      {s.description[:150]}")
    return 0


def cmd_get(args, cfg) -> int:
    skills = idx.load_index(cfg, refresh=args.refresh, log=lambda m: print(m, file=sys.stderr))
    s = idx.resolve(skills, args.name)
    if not s:
        hints = Router(skills).rank(args.name, k=3)
        hint = f" Did you mean: {', '.join(h.id for _, h in hints)}?" if hints else ""
        return _err(f"no skill named {args.name!r}.{hint}")
    dest = install(s)
    print(f"Fetched {s.id} -> {dest}")
    if args.show:
        print("\n" + skill_body(dest))
    return 0


def cmd_list(args, cfg) -> int:
    if args.installed:
        for p in installed():
            print(p)
        return 0
    for s in sorted(idx.load_index(cfg, refresh=args.refresh), key=lambda s: s.id):
        print(f"{s.id}\n    {s.description[:120]}")
    return 0


def cmd_sources(args, cfg) -> int:
    if args.action == "add":
        for spec in args.specs:
            parse_source(spec)  # validate
            if spec not in cfg.sources:
                cfg.sources.append(spec)
        cfg.save()
    elif args.action == "remove":
        cfg.sources = [s for s in cfg.sources if s not in args.specs]
        cfg.save()
    for s in cfg.sources:
        print(s)
    return 0


def cmd_refresh(args, cfg) -> int:
    skills = idx.build_index(cfg.sources, update=True)
    print(f"{len(skills)} skills indexed from {len(cfg.sources)} source(s).")
    return 0


def cmd_model(args, cfg) -> int:
    m = Model.load(args.model) if args.model else Model.load()
    meta = m.meta
    print(f"router: {meta.get('model')} trained {meta.get('trained')} on {meta.get('requests')} requests "
          f"/ {meta.get('skills')} skills, threshold {m.threshold:.2f}")
    for k, r in meta.get("cv", {}).items():
        print(f"  {k:24} top-1 {r['top1']:.1%}  top-3 {r['top3']:.1%}  MRR {r['mrr']:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="goodboy", description="Throw it a task. It fetches the skill from GitHub.")
    p.add_argument("--version", action="version", version=f"goodboy {__version__}")
    p.add_argument("--model", help="path to a retrained router.json")
    p.add_argument("--refresh", action="store_true", help="re-pull sources first")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("fetch", aliases=["ask"], help="find and fetch the skill for a request")
    sp.add_argument("request", nargs="+")
    sp.add_argument("--full", action="store_true", help="print the whole SKILL.md")
    sp.add_argument("-s", "--sections", type=int, default=2, help="relevant sections to show (default 2)")
    sp.add_argument("-l", "--lines", type=int, default=25, help="max lines per section")
    sp.set_defaults(fn=cmd_fetch)
    sp = sub.add_parser("search", help="rank skills for a request without fetching")
    sp.add_argument("query", nargs="+"); sp.add_argument("-n", type=int, default=8); sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("get", help="fetch a skill by name"); sp.add_argument("name")
    sp.add_argument("--show", action="store_true", help="print SKILL.md"); sp.set_defaults(fn=cmd_get)
    sp = sub.add_parser("list", help="list indexed (or --installed) skills")
    sp.add_argument("--installed", action="store_true"); sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("sources", help="show/add/remove skill repos")
    sp.add_argument("action", nargs="?", choices=["add", "remove"]); sp.add_argument("specs", nargs="*")
    sp.set_defaults(fn=cmd_sources)
    sub.add_parser("refresh", help="re-pull all sources and rebuild the index").set_defaults(fn=cmd_refresh)
    sub.add_parser("model", help="show the trained router's stats").set_defaults(fn=cmd_model)

    args = p.parse_args(argv)
    fn = getattr(args, "fn", cmd_interactive)
    try:
        return fn(args, config.Config.load())
    except SourceError as e:
        return _err(str(e))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:  # e.g. `goodboy fetch ... | head`
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
