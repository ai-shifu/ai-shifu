#!/usr/bin/env python3
"""Cross-reference backend routes against ALL known consumer surfaces.

Surfaces:
1. cook-web  : src/cook-web/src/api/api.ts catalog + any raw '/api/...' string
2. cli       : the skills repo (shifu-cli.py uses /api/shifu as base for
               relative '/shifus...' paths; also full /api/... refs)
3. miniprogram: the mini-program client repo (grep /api/ paths)
4. external-callback: paths/handlers matching callback|notify|webhook, and
               /api/open-api/* (external integrator surface)
5. ops       : /health, observability internal metrics/health paths

Classification: an endpoint with no consumer = NO-KNOWN-CONSUMER.

Environment:
  INVENTORY_WORK_DIR   dir holding routes-backend.txt (from extract_routes.py)
  SKILLS_REPO          path to the skills repo (default sibling ../skills)
  MINIAPP_REPO         path to the mini-program repo (skipped when unset)
"""

import os
import re
import subprocess
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
ROOT = str(Path(os.path.join(_SCRIPT_DIR, "..", "..", "..", "..")).resolve())
SP = os.environ.get("INVENTORY_WORK_DIR", str(Path.cwd()))
BACKEND_ROUTES = os.path.join(SP, "routes-backend.txt")
SKILLS = os.environ.get(
    "SKILLS_REPO", str(Path(os.path.join(ROOT, "..", "skills")).resolve())
)
MINIAPP = os.environ.get("MINIAPP_REPO", "")


def norm(path):
    path = path.split("?")[0].rstrip("/")
    segs = []
    for s in path.split("/"):
        if not s:
            continue
        if "${" in s or "{" in s or s.startswith((":", "<")):
            segs.append("*")
        else:
            segs.append(s)
    return tuple(segs)


def grep_paths(root, extra_args=None):
    if not Path(root).is_dir():
        return set()
    # no quote anchoring: f-strings like f"{base}/api/x/{bid}/export" must hit
    cmd = ["grep", "-rhoE", r"/api/[^'\"`[:space:]]*", root]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    paths = set()
    for line in out.splitlines():
        p = line.strip().rstrip(".,;:)]}")
        if not p.startswith("/api/"):
            continue
        n = norm(p)
        # drop over-generic patterns like ("api","*") from e.g. "/api/shifu{path}"
        if len(n) <= 2 and "*" in n:
            continue
        paths.add(n)
    return paths


surfaces = {}

# --- cook-web ---------------------------------------------------------------
fe = set()
cat = None
with open(
    os.path.join(ROOT, "src/cook-web/src/api/api.ts"), encoding="utf-8"
) as catalog_file:
    cat = catalog_file.read()
for m in re.finditer(
    r"'(GET|POST|PUT|DELETE|PATCH|STREAM|STREAMLINE|PROXY)\s+([^']+)'", cat
):
    p = m.group(2)
    if not p.startswith("http"):
        p = "/api" + p
    fe.add(norm(p))
fe |= grep_paths(os.path.join(ROOT, "src/cook-web/src"))
surfaces["cook-web"] = fe

# --- skills CLI --------------------------------------------------------------
cli = grep_paths(SKILLS)
# relative paths in shifu-cli.py are joined onto /api/shifu
cli_file = os.path.join(SKILLS, "skills/ai-shifu-course-creator/scripts/shifu-cli.py")
if Path(cli_file).exists():
    with open(cli_file, encoding="utf-8") as cli_source:
        src = cli_source.read()
    for m in re.finditer(
        r"""["'](/(?:shifus|upfile|url-upfile|mdflow)[^"']*)["']""", src
    ):
        cli.add(norm("/api/shifu" + m.group(1)))
surfaces["cli"] = cli

# --- mini-program ------------------------------------------------------------
surfaces["miniprogram"] = grep_paths(MINIAPP)

# --- backend routes ----------------------------------------------------------
be = []
with open(BACKEND_ROUTES, encoding="utf-8") as backend_routes:
    for line in backend_routes:
        if line.startswith("#"):
            continue
        mm = re.match(r"(\S+)\s+(\S+)\s+\[(.*)\]", line.strip())
        if not mm:
            continue
        method, path, src = mm.groups()
        be.append((method, path, norm(path), src))


def match(be_segs, fe_segs):
    if len(be_segs) != len(fe_segs):
        return False
    return all(
        a in (b, "*") or b == "*" for a, b in zip(be_segs, fe_segs, strict=False)
    )


rows = []
counts = {}
for method, path, segs, src in be:
    consumers = []
    for name, pats in surfaces.items():
        if any(match(segs, f) for f in pats):
            consumers.append(f"used-by-{name}")
    low = path.lower() + " " + src.lower()
    if re.search(r"callback|notify|webhook", low) or path.startswith("/api/open-api/"):
        consumers.append("external-callback")
    if path == "/health" or path.startswith("/internal/") or "observability" in src:
        consumers.append("ops")
    if not consumers:
        consumers = ["NO-KNOWN-CONSUMER"]
    for c in consumers:
        counts[c] = counts.get(c, 0) + 1
    rows.append((method, path, ", ".join(consumers), src))

print("## consumer classification counts (endpoint may have several consumers)")
for c, n in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {c}: {n}")
print(f"  TOTAL endpoints: {len(rows)}")
print()
print("## endpoints NOT referenced by cook-web (with consumer column)")
print(f"{'METHOD':7s} {'PATH':80s} CONSUMER  [handler]")
for method, path, cons, src in sorted(rows, key=lambda r: (r[2], r[1])):
    if "used-by-cook-web" in cons:
        continue
    print(f"{method:7s} {path:80s} {cons}  [{src}]")
