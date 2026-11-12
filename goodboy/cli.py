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
from . import discover as disc

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


def _local_sources() -> set[str]:
    return set(config.Config.load().sources)


def _fmt_stars(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _local_router(args, cfg) -> Router:
    return _router(args, cfg)


def _github_router(args, request: str):
    """Router over the skills of the top-starred GitHub repos for this request."""
    log = lambda m: print(m, file=sys.stderr)
    kws, found = disc.discover(request, top=args.repos, log=log)
    if not kws:
        return None, {}
    print(f"Searched GitHub for: {' '.join(kws)} skill")
    if not found:
        print("No GitHub repo with a matching skill found for that.")
        return None, {}
    stars = {}
    print(f"Top {len(found)} repos by stars that have a matching skill:")
    for repo, skills, _ in found:
        stars[repo.full_name] = repo.stars
        print(f"  {_fmt_stars(repo.stars):>6} stars  {repo.full_name}  ({len(skills)} skill{'s' * (len(skills) != 1)})")
    print()
    model = Model.load(args.model) if getattr(args, "model", None) else None
    return Router([s for _, sk, _ in found for s in sk], model), stars


def fetch(router: Router, request: str, full: bool = False, sections: int = 2, lines: int = 25,
          stars: dict | None = None) -> int:
    ranked = router.rank(request, k=5)
    if stars and ranked:
        # near-ties go to the more-starred repo
        best = ranked[0][0]
        ranked.sort(key=lambda ps: (ps[0] < best - 0.05, -stars.get(ps[1].source, 0), -ps[0]))
    ranked = ranked[:3]
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
                ref = s.name if s.source in _local_sources() else s.id
                print(f"  {s.id}  ({p:.0%})   ->  goodboy get '{ref}'")
        return 0

    p, skill = ranked[0]
    disc.materialize(skill)
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
    request = " ".join(args.request)
    if args.local:
        return fetch(_router(args, cfg), request, args.full, args.sections, args.lines)
    router, stars = _github_router(args, request)
    if router is None:
        print("Nothing to fetch.")
        return 0
    return fetch(router, request, args.full, args.sections, args.lines, stars=stars)


def cmd_interactive(args, cfg) -> int:
    local = _router(args, cfg) if args.local else None
    where = f"{len(local.fx.skills)} local skills" if local else "the top GitHub skill repos"
    print(f"goodboy {__version__}: fetching from {where}. Tell me what you need (Ctrl-D to quit).")
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
            try:
                if local:
                    fetch(local, line)
                else:
                    router, stars = _github_router(args, line)
                    fetch(router, line, stars=stars) if router else print("Nothing to fetch.")
            except disc.DiscoveryError as e:
                print(f"error: {e}")


def cmd_search(args, cfg) -> int:
    query = " ".join(args.query)
    router = _router(args, cfg) if args.local else _github_router(args, query)[0]
    if router is None:
        return 0
    ranked = router.rank(query, k=args.n)
    if not ranked:
        print("No matching skills.")
    for p, s in ranked:
        print(f"{p:4.0%}  {s.id}\n      {s.description[:150]}")
    return 0


def cmd_get(args, cfg) -> int:
    s = None
    if ":" in args.name and args.name.split(":", 1)[0] not in cfg.sources:
        s = disc.get_remote(args.name)          # owner/repo:skill straight from GitHub
        if s is None:
            return _err(f"no skill {args.name!r} found on GitHub")
        disc.materialize(s)
        dest = install(s)
        print(f"Fetched {s.id} -> {dest}")
        if args.show:
            print("\n" + skill_body(dest))
        return 0
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


def _discovery_flags(sp) -> None:
    sp.add_argument("--local", action="store_true", default=argparse.SUPPRESS,
                    help="only your saved sources, no live GitHub search")
    sp.add_argument("--repos", type=int, default=argparse.SUPPRESS, help="top-starred repos to use (default 3)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="goodboy", description="Throw it a task. It fetches the skill from GitHub.",
                                epilog="By default every request searches GitHub live for the top-starred "
                                       "skill repos on that topic. Use --local for your saved sources only.")
    p.add_argument("--version", action="version", version=f"goodboy {__version__}")
    p.add_argument("--model", help="path to a retrained router.json")
    p.add_argument("--refresh", action="store_true", help="re-pull sources first")
    p.add_argument("--local", action="store_true",
                   help="only use your saved sources (goodboy sources), not a live GitHub search")
    p.add_argument("--repos", type=int, default=3, help="how many top-starred repos to search (default 3)")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("fetch", aliases=["ask"], help="find and fetch the skill for a request")
    sp.add_argument("request", nargs="+")
    sp.add_argument("--full", action="store_true", help="print the whole SKILL.md")
    sp.add_argument("-s", "--sections", type=int, default=2, help="relevant sections to show (default 2)")
    sp.add_argument("-l", "--lines", type=int, default=25, help="max lines per section")
    sp.set_defaults(fn=cmd_fetch)
    _discovery_flags(sp)
    sp = sub.add_parser("search", help="rank skills for a request without fetching")
    sp.add_argument("query", nargs="+"); sp.add_argument("-n", type=int, default=8); sp.set_defaults(fn=cmd_search)
    _discovery_flags(sp)
    sp = sub.add_parser("get", help="fetch a skill by name, or owner/repo:skill from GitHub"); sp.add_argument("name")
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
    except (SourceError, disc.DiscoveryError) as e:
        return _err(str(e))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:  # e.g. `goodboy fetch ... | head`
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
