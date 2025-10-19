#!/usr/bin/env python3
"""List remaining Python-based translation modules."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "src" / "api" / "flaskr" / "i18n"


def find_python_modules() -> list[str]:
    modules: list[str] = []
    if not I18N_DIR.exists():
        return modules

    for path in I18N_DIR.rglob("*.py"):
        relative = path.relative_to(ROOT)
        # skip __init__.py in the i18n package because it is the loader itself
        if path.name == "__init__.py" and path.parent == I18N_DIR:
            continue
        modules.append(str(relative))
    return sorted(modules)


def main() -> None:
    modules = find_python_modules()
    if not modules:
        print("No Python translation modules remaining.")
        return

    print("Python translation modules found (pending migration):")
    for module in modules:
        print(f" - {module}")


if __name__ == "__main__":
    main()
