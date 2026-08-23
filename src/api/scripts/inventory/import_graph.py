#!/usr/bin/env python3
"""Import-graph reachability for src/api flaskr/.

Roots:
- app.py, celery_app.py (repo root of src/api)
- flaskr/route/__init__.py
- flaskr/command/ (registered via app.cli in flaskr/command/__init__.py,
  imported from app path)
- scripts/*.py
- PLUGIN SCAN: flaskr/framework/plugin/load_plugin.py:load_plugins_from_dir
  is called with flaskr/service (and flaskr/plugins, which is empty). It
  RECURSIVELY imports EVERY *.py file (except __init__.py) under every
  top-level subdirectory of flaskr/service, skipping __pycache__, dirs named
  'migrations', and dotfiles. importlib.import_module of a submodule also
  imports all package __init__.py files on the path. So every module under
  flaskr/service/<dir>/ is import-reachable at startup by construction.

Edges: every ast Import/ImportFrom anywhere in a module (incl. lazy,
function-local imports), resolved to project modules only.
"""

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = str((Path(__file__).resolve().parent / ".." / "..").resolve())

# ---- collect all project modules -----------------------------------------
mods = {}  # module name -> relative file path


def add_tree(base_dir: object):
    """Add tree."""
    for dirpath, dirnames, filenames in os.walk(str(Path(ROOT) / base_dir)):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel = os.path.relpath(dirpath, ROOT)
        parts = Path(rel).parts
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            if fn == "__init__.py":
                name = ".".join(parts)
            else:
                name = ".".join([*parts, fn[:-3]])
            mods[name] = str(Path(rel) / fn)


add_tree("flaskr")
add_tree("scripts")
for top in ("app.py", "celery_app.py"):
    if (Path(ROOT) / top).exists():
        mods[top[:-3]] = top

# ---- parse imports ---------------------------------------------------------
edges = defaultdict(set)
for name, rel in mods.items():
    try:
        with (Path(ROOT) / rel).open(encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read())
    except SyntaxError as e:
        print(f"SYNTAX ERROR {rel}: {e}", file=sys.stderr)
        continue
    pkg_parts = (
        name.split(".")[:-1] if not rel.endswith("__init__.py") else name.split(".")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                edges[name].add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                up = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                base = ".".join(up + ([node.module] if node.module else []))
            if base:
                edges[name].add(base)
            for a in node.names:
                if base:
                    edges[name].add(base + "." + a.name)


def resolve(target: object):
    """Map an imported dotted name to a known project module (or None)."""
    while target:
        if target in mods:
            return target
        if "." not in target:
            return None
        target = target.rsplit(".", 1)[0]
    return None


graph = defaultdict(set)
for src, targets in edges.items():
    for t in targets:
        r = resolve(t)
        if r and r != src:
            graph[src].add(r)
            # importing a submodule imports all ancestor packages
            parts = r.split(".")
            for i in range(1, len(parts)):
                anc = ".".join(parts[:i])
                if anc in mods:
                    graph[src].add(anc)

# ---- roots -----------------------------------------------------------------
roots = set()
for name, rel in mods.items():
    if (
        name in ("app", "celery_app")
        or rel.startswith(("scripts" + os.sep, "flaskr/command"))
        or name == "flaskr.route"
    ):
        roots.add(name)

# plugin scan: emulate load_plugins_from_dir over flaskr/service
svc_dir = str(Path(ROOT) / "flaskr" / "service")
for top in sorted(path.name for path in Path(svc_dir).iterdir()):
    top_path = str(Path(svc_dir) / top)
    if not Path(top_path).is_dir():
        continue
    for dirpath, dirnames, filenames in os.walk(top_path):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ("__pycache__", "migrations") and not d.startswith(".")
        ]
        for fn in filenames:
            if fn.endswith(".py") and fn != "__init__.py" and not fn.startswith("."):
                rel = os.path.relpath(str(Path(dirpath) / fn), ROOT)
                name = rel[:-3].replace(os.sep, ".")
                if name in mods:
                    roots.add(name)
                    # package __init__ chain gets imported too
                    parts = name.split(".")
                    for i in range(1, len(parts)):
                        anc = ".".join(parts[:i])
                        if anc in mods:
                            roots.add(anc)

# ---- reachability ----------------------------------------------------------
seen = set()
stack = list(roots)
while stack:
    m = stack.pop()
    if m in seen:
        continue
    seen.add(m)
    stack.extend(graph.get(m, ()))

unreachable = sorted(set(mods) - seen)
print(f"total project modules: {len(mods)}")
print(
    f"roots: {len(roots)}  (of which plugin-scanned service modules: "
    f"{len([r for r in roots if r.startswith('flaskr.service')])})"
)
print(f"reachable: {len(seen)}")
print(f"UNREACHABLE ({len(unreachable)}):")
for m in unreachable:
    print(f"  {m}  ({mods[m]})")

# extra: reverse-edge counts for specific legacy modules
print("\nREVERSE IMPORTS for adjudicated legacy modules:")
for target in (
    "flaskr.service.learn.listen_element_legacy",
    "flaskr.service.learn.legacy_record_builder",
):
    importers = sorted(s for s, ts in graph.items() if target in ts)
    print(f"  {target}: imported by {len(importers)} modules")
    for i in importers:
        print(f"    - {i}")
