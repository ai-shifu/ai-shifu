#!/usr/bin/env python3
"""Validate repository architecture boundaries with a committed baseline."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "src" / "cook-web" / "src"
BACKEND_ROOT = ROOT / "src" / "api"
DEFAULT_BASELINE = ROOT / "docs" / "generated" / "architecture-boundary-baseline.json"
FIXTURE_ROOT = ROOT / "scripts" / "testdata" / "architecture_boundaries"

IMPORT_FROM_PATTERN = re.compile(
    r"""(?:import|export)\s+(?:[^"'`]+?\s+from\s+)?["']([^"']+)["']""",
    re.MULTILINE,
)
FETCH_PATTERN = re.compile(r"\bfetch\s*\(")
ROUTE_FILE_NAMES = {"route.py", "routes.py"}
FRONTEND_IMPORT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
FRONTEND_FETCH_ALLOWLIST = {
    "lib/request.ts",
    "lib/api.ts",
    "lib/file.ts",
    "lib/initializeEnvData.ts",
    "lib/mock-fixture.ts",
    "lib/unified-i18n-backend.ts",
    "config/environment.ts",
}
BACKEND_SHARED_SERVICES = {"common", "config"}
BACKEND_STABLE_MODULE_SUFFIXES = {"dtos", "models", "consts"}


@dataclass(frozen=True)
class Violation:
    key: str
    rule_id: str
    source: str
    target: str
    message: str
    remediation: str


def make_key(rule_id: str, source: str, target: str) -> str:
    return f"{rule_id}|{source}|{target}"


def normalize_posix(path: Path) -> str:
    return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def collect_frontend_imports(path: Path, frontend_root: Path) -> list[str]:
    imports: list[str] = []
    text = read_text(path)
    for match in IMPORT_FROM_PATTERN.findall(text):
        imports.append(match.strip())
    # Support dynamic imports without `from`.
    for dynamic in re.findall(r"""import\(\s*["']([^"']+)["']\s*\)""", text):
        imports.append(dynamic.strip())
    return imports


def resolve_frontend_import(
    import_source: str, source_path: Path, frontend_root: Path
) -> Path | None:
    if import_source.startswith("@/"):
        base = (frontend_root / import_source[2:]).resolve()
    elif import_source.startswith("."):
        base = (source_path.parent / import_source).resolve()
    else:
        return None

    candidates = [base]
    candidates.extend(
        base.with_suffix(extension) for extension in FRONTEND_IMPORT_EXTENSIONS
    )
    candidates.extend(
        base / f"index{extension}" for extension in FRONTEND_IMPORT_EXTENSIONS
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return base


def top_level_route_scope(app_relative_path: Path) -> str:
    for part in app_relative_path.parts:
        if not part:
            continue
        if part.startswith("(") and part.endswith(")"):
            continue
        if Path(part).suffix:
            return "__root__"
        return part
    return "__root__"


def collect_frontend_violations(frontend_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    app_root = frontend_root / "app"
    components_root = frontend_root / "components"

    for path in sorted(frontend_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        rel_source = normalize_posix(path.relative_to(frontend_root))
        text = read_text(path)

        if rel_source not in FRONTEND_FETCH_ALLOWLIST and FETCH_PATTERN.search(text):
            rule_id = "frontend.disallowed_fetch_callsite"
            target = "fetch(...)"
            violations.append(
                Violation(
                    key=make_key(rule_id, rel_source, target),
                    rule_id=rule_id,
                    source=rel_source,
                    target=target,
                    message=(
                        f"{rel_source} introduces a direct fetch callsite outside the "
                        "shared request/bootstrap allowlist."
                    ),
                    remediation=(
                        "Route new HTTP traffic through src/lib/request.ts, "
                        "src/lib/api.ts, or an existing allowed bootstrap file."
                    ),
                )
            )

        imports = collect_frontend_imports(path, frontend_root)
        source_under_app = path.is_relative_to(app_root)
        source_under_components = path.is_relative_to(components_root)

        for import_source in imports:
            target_path = resolve_frontend_import(import_source, path, frontend_root)
            if target_path is None:
                continue
            if not target_path.exists():
                # Static alias resolution is best-effort; unresolved paths may still
                # point to TS path aliases or generated files, so skip them.
                continue
            if target_path.suffix not in FRONTEND_IMPORT_EXTENSIONS:
                continue

            if source_under_app and target_path.is_relative_to(app_root):
                source_scope = top_level_route_scope(path.relative_to(app_root))
                target_scope = top_level_route_scope(target_path.relative_to(app_root))
                if source_scope != target_scope:
                    rule_id = "frontend.cross_route_app_import"
                    target = normalize_posix(target_path.relative_to(frontend_root))
                    violations.append(
                        Violation(
                            key=make_key(rule_id, rel_source, target),
                            rule_id=rule_id,
                            source=rel_source,
                            target=target,
                            message=(
                                f"{rel_source} imports route-internal code from the "
                                f"{target_scope} scope via {target}."
                            ),
                            remediation=(
                                "Move reusable code into a shared layer such as "
                                "src/components, src/hooks, src/store, src/lib, "
                                "src/types, or an existing maintained c-* surface."
                            ),
                        )
                    )

            if source_under_components and target_path.is_relative_to(app_root):
                rule_id = "frontend.component_imports_route_internal"
                target = normalize_posix(target_path.relative_to(frontend_root))
                violations.append(
                    Violation(
                        key=make_key(rule_id, rel_source, target),
                        rule_id=rule_id,
                        source=rel_source,
                        target=target,
                        message=(
                            f"{rel_source} depends on route-internal implementation "
                            f"{target} under src/app."
                        ),
                        remediation=(
                            "Lift the dependency into a shared module or keep the "
                            "route-only implementation behind a shared component/hook "
                            "boundary."
                        ),
                    )
                )

    return violations


def python_module_parts(path: Path, backend_root: Path) -> list[str]:
    relative = path.relative_to(backend_root).with_suffix("")
    parts = list(relative.parts)
    return parts[:-1]


def resolve_backend_relative_import(
    path: Path, backend_root: Path, node: ast.ImportFrom
) -> list[str]:
    package_parts = python_module_parts(path, backend_root)
    keep_count = len(package_parts) - max(node.level - 1, 0)
    if keep_count < 0:
        return []

    base_parts = package_parts[:keep_count]
    module_parts = node.module.split(".") if node.module else []
    resolved_parts = base_parts + module_parts
    if not resolved_parts:
        return []

    resolved_module = ".".join(resolved_parts)
    module_path = backend_root.joinpath(*resolved_parts)
    if not module_path.is_dir():
        return [resolved_module]

    child_modules: list[str] = []
    for alias in node.names:
        if alias.name == "*":
            continue
        child_path = module_path / alias.name
        if (
            child_path.with_suffix(".py").exists()
            or (child_path / "__init__.py").exists()
        ):
            child_modules.append(f"{resolved_module}.{alias.name}")

    return child_modules or [resolved_module]


def iter_python_imports(path: Path, backend_root: Path) -> list[str]:
    imports: list[str] = []
    tree = ast.parse(read_text(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                imports.extend(
                    resolve_backend_relative_import(path, backend_root, node)
                )
                continue
            if module:
                imports.append(module)
    return imports


def backend_module_suffix(module: str) -> str:
    parts = module.split(".")
    return parts[-1] if parts else module


def collect_backend_violations(backend_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    service_root = backend_root / "flaskr" / "service"

    for path in sorted(service_root.rglob("*.py")):
        rel_source = normalize_posix(path.relative_to(backend_root))
        parts = path.relative_to(service_root).parts
        if not parts:
            continue
        source_service = parts[0]
        is_route_adapter = path.name in ROUTE_FILE_NAMES

        for module in iter_python_imports(path, backend_root):
            if module.startswith("flaskr.route.") and not is_route_adapter:
                rule_id = "backend.service_imports_root_route"
                violations.append(
                    Violation(
                        key=make_key(rule_id, rel_source, module),
                        rule_id=rule_id,
                        source=rel_source,
                        target=module,
                        message=(
                            f"{rel_source} imports root route module {module} outside "
                            "a route adapter."
                        ),
                        remediation=(
                            "Move request/response concerns into route adapters and "
                            "depend on service helpers or shared common/config code "
                            "from non-route modules."
                        ),
                    )
                )

            if module.startswith("flaskr.service."):
                module_parts = module.split(".")
                if len(module_parts) < 3:
                    continue
                target_service = module_parts[2]
                if target_service == source_service:
                    continue

                if backend_module_suffix(module) in {"route", "routes"}:
                    rule_id = "backend.imports_service_route_adapter"
                    violations.append(
                        Violation(
                            key=make_key(rule_id, rel_source, module),
                            rule_id=rule_id,
                            source=rel_source,
                            target=module,
                            message=(
                                f"{rel_source} imports route adapter module {module} "
                                "from another service."
                            ),
                            remediation=(
                                "Depend on shared DTOs, helper functions, or public "
                                "service modules instead of another service's route "
                                "adapter."
                            ),
                        )
                    )
                    continue

                if target_service in BACKEND_SHARED_SERVICES:
                    continue

                suffix = backend_module_suffix(module)
                if suffix in BACKEND_STABLE_MODULE_SUFFIXES:
                    continue

                rule_id = "backend.cross_service_import"
                violations.append(
                    Violation(
                        key=make_key(rule_id, rel_source, module),
                        rule_id=rule_id,
                        source=rel_source,
                        target=module,
                        message=(
                            f"{rel_source} imports cross-service module {module} "
                            "outside the shared/common stable entry points."
                        ),
                        remediation=(
                            "Prefer shared common/config utilities, stable DTO/model/"
                            "const modules, or a deliberate service API boundary."
                        ),
                    )
                )

    return violations


def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(read_text(path))
    return {item["key"] for item in payload.get("violations", [])}


def dedupe_violations(items: list[Violation]) -> list[Violation]:
    deduped: dict[str, Violation] = {}
    for item in items:
        deduped[item.key] = item
    return [deduped[key] for key in sorted(deduped)]


def write_baseline(path: Path, violations: list[Violation]) -> None:
    payload = {
        "version": 1,
        "violations": [
            asdict(item) for item in sorted(violations, key=lambda item: item.key)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def print_summary(
    *,
    current: list[Violation],
    baseline_keys: set[str],
    fail_on_stale_baseline: bool,
) -> int:
    current_keys = {item.key for item in current}
    new_violations = [item for item in current if item.key not in baseline_keys]
    stale_baseline = sorted(baseline_keys - current_keys)

    print(f"Current violations: {len(current)}")
    print(f"Baseline entries: {len(baseline_keys)}")
    print(f"New violations: {len(new_violations)}")
    print(f"Stale baseline entries: {len(stale_baseline)}")

    if current:
        print("Current violation breakdown:")
        counts: dict[str, int] = {}
        for item in current:
            counts[item.rule_id] = counts.get(item.rule_id, 0) + 1
        for rule_id, count in sorted(counts.items()):
            print(f"  - {rule_id}: {count}")

    if new_violations:
        print("New architecture violations detected:", file=sys.stderr)
        for item in new_violations:
            print(
                f" - [{item.rule_id}] {item.source} -> {item.target}", file=sys.stderr
            )
            print(f"   {item.message}", file=sys.stderr)
            print(f"   Remediation: {item.remediation}", file=sys.stderr)

    if stale_baseline:
        stream = sys.stderr if fail_on_stale_baseline else sys.stdout
        print("Stale baseline entries:", file=stream)
        for key in stale_baseline:
            print(f" - {key}", file=stream)

    if new_violations:
        return 1
    if fail_on_stale_baseline and stale_baseline:
        return 1
    print("Architecture boundary validation passed.")
    return 0


def run_fixture_tests() -> int:
    manifest_path = FIXTURE_ROOT / "manifest.json"
    payload = json.loads(read_text(manifest_path))
    failures: list[str] = []

    for case in payload.get("fixtures", []):
        fixture_dir = FIXTURE_ROOT / case["path"]
        violations = collect_frontend_violations(
            fixture_dir / "frontend"
        ) + collect_backend_violations(fixture_dir / "backend")
        actual_rules = sorted(item.rule_id for item in violations)
        expected_rules = sorted(case.get("expected_rule_ids", []))
        if actual_rules != expected_rules:
            failures.append(
                f"{case['name']}: expected {expected_rules}, got {actual_rules}"
            )

    if failures:
        print("Fixture tests failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print("Architecture boundary fixture tests passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate frontend and backend architecture boundaries."
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Path to the committed architecture-boundary baseline JSON file.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write the current repository violations into the baseline file.",
    )
    parser.add_argument(
        "--fail-on-stale-baseline",
        action="store_true",
        help="Fail if the baseline contains entries no longer present in the repository.",
    )
    parser.add_argument(
        "--run-fixture-tests",
        action="store_true",
        help="Run the built-in fixture tests instead of scanning the repository.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.run_fixture_tests:
        return run_fixture_tests()

    baseline_path = Path(args.baseline).resolve()
    current = dedupe_violations(
        collect_frontend_violations(FRONTEND_ROOT)
        + collect_backend_violations(BACKEND_ROOT)
    )

    if args.write_baseline:
        write_baseline(baseline_path, current)
        print(f"Wrote architecture boundary baseline to {baseline_path}")
        return 0

    baseline_keys = load_baseline(baseline_path)
    return print_summary(
        current=current,
        baseline_keys=baseline_keys,
        fail_on_stale_baseline=args.fail_on_stale_baseline,
    )


if __name__ == "__main__":
    raise SystemExit(main())
