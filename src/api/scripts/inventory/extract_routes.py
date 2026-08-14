#!/usr/bin/env python3
"""Extract all Flask route registrations (path + methods) from src/api.

Handles:
- flaskr/route/<mod>.py register_* functions, called from
  flaskr/route/__init__.py with explicit prefixes (PATH_PREFIX default /api)
- service routes registered by the plugin loader calling @inject register_*
  functions with their path_prefix DEFAULT value (positional or kw-only)
- local string-constant prefix variables (e.g. admin_path_prefix = "...")
- app.config.get("KEY", "default") prefix variables (observability paths)
"""

import ast
import os

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)

CALLED_PREFIX = {
    "flaskr/route/common.py": "",
    "flaskr/route/config.py": "/api",
    "flaskr/route/storage.py": "/api",
    "flaskr/route/user.py": "/api/user",
    "flaskr/route/dicts.py": "/api/dict",
    "flaskr/route/order.py": "/api/order",
    "flaskr/route/callback.py": "/api/callback",
    "flaskr/route/open_api.py": "/api/open-api/v1",
    "flaskr/route/creator_analytics.py": "/api/creator-analytics",
    "flaskr/service/referral/routes.py": "/api/referral",
}

route_files = []
for base in ("flaskr/route", "flaskr/service", "flaskr/common"):
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                if ".route(" in open(p, encoding="utf-8").read():
                    route_files.append(os.path.relpath(p, ROOT))

results = []


def literal(node, env):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id, f"<{node.id}>")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return literal(node.left, env) + literal(node.right, env)
    if isinstance(node, ast.JoinedStr):
        out = ""
        for v in node.values:
            if isinstance(v, ast.Constant):
                out += str(v.value)
            elif isinstance(v, ast.FormattedValue):
                out += literal(v.value, env)
        return out
    return "<expr:%s>" % ast.unparse(node)


def config_get_default(node):
    """app.config.get('KEY', 'default') -> 'default'."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return node.args[1].value
    return None


def collect_routes(scope_body, env, rel):
    for node in scope_body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            if isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, str
            ):
                env[name] = node.value.value
            else:
                d = config_get_default(node.value)
                if d is not None:
                    env[name] = d
                elif isinstance(node.value, (ast.BinOp, ast.JoinedStr, ast.Name)):
                    v = literal(node.value, env)
                    if "<" not in v:
                        env[name] = v
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "route"
                    and dec.args
                ):
                    path = literal(dec.args[0], env)
                    methods = ["GET"]
                    for kw in dec.keywords:
                        if kw.arg == "methods":
                            try:
                                methods = ast.literal_eval(kw.value)
                            except Exception:
                                methods = ["<dyn>"]
                    for m in methods:
                        results.append((m, path, rel, node.lineno, node.name))
            # recurse into nested scopes (rare but cheap)
            collect_routes(node.body, dict(env), rel)
        elif isinstance(node, (ast.If, ast.With, ast.Try, ast.For, ast.While)):
            collect_routes(node.body, env, rel)
            for h in getattr(node, "handlers", []):
                collect_routes(h.body, env, rel)
            collect_routes(getattr(node, "orelse", []), env, rel)


for rel in sorted(route_files):
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    tree = ast.parse(src)
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        env = {}
        a = fn.args
        # positional defaults
        pos = a.args
        for i, arg in enumerate(pos):
            di = i - (len(pos) - len(a.defaults))
            if (
                di >= 0
                and isinstance(a.defaults[di], ast.Constant)
                and isinstance(a.defaults[di].value, str)
            ):
                env[arg.arg] = a.defaults[di].value
        # keyword-only defaults
        for arg, d in zip(a.kwonlyargs, a.kw_defaults):
            if (
                d is not None
                and isinstance(d, ast.Constant)
                and isinstance(d.value, str)
            ):
                env[arg.arg] = d.value
        if rel in CALLED_PREFIX:
            env["path_prefix"] = CALLED_PREFIX[rel]
            env["prefix"] = CALLED_PREFIX[rel]
        collect_routes(fn.body, env, rel)
    # module-level routes
    collect_routes(
        [
            n
            for n in tree.body
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        or [],
        {},
        rel,
    )
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "route"
                    and dec.args
                ):
                    path = literal(dec.args[0], {})
                    methods = ["GET"]
                    for kw in dec.keywords:
                        if kw.arg == "methods":
                            try:
                                methods = ast.literal_eval(kw.value)
                            except Exception:
                                methods = ["<dyn>"]
                    for m in methods:
                        results.append((m, path, rel, node.lineno, node.name))

seen = set()
unresolved = 0
for m, path, rel, lineno, name in sorted(results, key=lambda r: (r[1], r[0])):
    key = (m, path)
    if key in seen:
        continue
    seen.add(key)
    if "<expr" in path or path.startswith("<"):
        unresolved += 1
    print(f"{m:7s} {path}  [{rel}:{lineno} {name}]")
print(f"# total unique method+path: {len(seen)} (unresolved prefix: {unresolved})")
