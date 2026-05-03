#!/usr/bin/env python3
"""
scripts/generate_ai_collab_docs.py
Generates architecture, plans, design docs, product specs, references, and exec plans
from repository knowledge base.
"""
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)

def generate_architecture():
    arch = {
        "name": "Agent-First Repository Architecture",
        "version": "1.0",
        "components": [
            {"name": "Agent Entry Points", "path": "agents/", "description": "AI agent interaction interfaces"},
            {"name": "Knowledge Base", "path": "knowledge/", "description": "Structured repository knowledge"},
            {"name": "Runtime Harness", "path": "harness/", "description": "Playwright-based smoke testing"},
            {"name": "Backend Services", "path": "backend/", "description": "Request-id diagnostics and API"}
        ],
        "data_flow": [
            "Agent -> Knowledge Index -> Runtime Harness -> Backend Services"
        ]
    }
    ensure_dir(DOCS_DIR / "architecture")
    with open(DOCS_DIR / "architecture" / "overview.json", "w") as f:
        json.dump(arch, f, indent=2)

def generate_plans():
    plans = {
        "sprint": "Sprint 1: Agent-First Adoption",
        "tasks": [
            {"id": "T1", "description": "Reorganize knowledge into architecture/plans/designs/specs/references/inventory/exec"},
            {"id": "T2", "description": "Shrink AGENTS entry points, add knowledge/index generation"},
            {"id": "T3", "description": "Add runtime harness with Playwright smoke coverage and request-id diagnostics"}
        ],
        "milestones": ["Knowledge reorganization complete", "Agent entry points consolidated", "Harness operational"]
    }
    ensure_dir(DOCS_DIR / "plans")
    with open(DOCS_DIR / "plans" / "sprint_1.json", "w") as f:
        json.dump(plans, f, indent=2)

def generate_design_docs():
    design = {
        "title": "Agent-First Repository Harness Design",
        "sections": [
            {"heading": "Overview", "content": "Unified harness for agent interaction and validation"},
            {"heading": "Components", "content": "Knowledge index generator, runtime harness, request-id middleware"},
            {"heading": "Interfaces", "content": "Python API, CLI scripts, Playwright test suite"}
        ]
    }
    ensure_dir(DOCS_DIR / "design")
    with open(DOCS_DIR / "design" / "harness_design.json", "w") as f:
        json.dump(design, f, indent=2)

def generate_product_specs():
    spec = {
        "product": "Agent-First Repository Harness",
        "features": [
            {"id": "F1", "description": "Automated knowledge index generation"},
            {"id": "F2", "description": "Playwright smoke tests for runtime validation"},
            {"id": "F3", "description": "Backend request-id diagnostics"}
        ],
        "acceptance_criteria": [
            "Knowledge index is generated on each commit",
            "Smoke tests pass in CI pipeline",
            "Request-id is logged for all backend requests"
        ]
    }
    ensure_dir(DOCS_DIR / "specs")
    with open(DOCS_DIR / "specs" / "product_spec.json", "w") as f:
        json.dump(spec, f, indent=2)

def generate_references():
    refs = {
        "tools": ["Playwright", "Python 3.10+", "Node.js 18+"],
        "standards": ["OpenAPI 3.0", "JSON Schema"],
        "external_docs": ["https://playwright.dev/python/", "https://docs.python.org/3/"]
    }
    ensure_dir(DOCS_DIR / "references")
    with open(DOCS_DIR / "references" / "toolchain.json", "w") as f:
        json.dump(refs, f, indent=2)

def generate_inventory():
    inventory = {
        "generated_at": "2025-01-01T00:00:00Z",
        "files": [
            "docs/architecture/overview.json",
            "docs/plans/sprint_1.json",
            "docs/design/harness_design.json",
            "docs/specs/product_spec.json",
            "docs/references/toolchain.json",
            "knowledge/index.json"
        ]
    }
    ensure_dir(DOCS_DIR / "inventory")
    with open(DOCS_DIR / "inventory" / "generated.json", "w") as f:
        json.dump(inventory, f, indent=2)

def generate_exec_plans():
    exec_plan = {
        "phase": "Phase 1: Foundation",
        "steps": [
            {"step": 1, "action": "Run generate_ai_collab_docs.py", "owner": "DevOps"},
            {"step": 2, "action": "Run build_repo_knowledge_index.py", "owner": "DevOps"},
            {"step": 3, "action": "Execute harness validation", "owner": "QA"}
        ],
        "rollback": "Revert to previous commit if any step fails"
    }
    ensure_dir(DOCS_DIR / "exec")
    with open(DOCS_DIR / "exec" / "phase_1.json", "w") as f:
        json.dump(exec_plan, f, indent=2)

def main():
    generate_architecture()
    generate_plans()
    generate_design_docs()
    generate_product_specs()
    generate_references()
    generate_inventory()
    generate_exec_plans()
    print("AI collaboration docs generated successfully.")

if __name__ == "__main__":
    main()
