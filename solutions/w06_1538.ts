#!/usr/bin/env python3
"""scripts/generate_ai_collab_docs.py - Reorganize repository knowledge into architecture, plans, design docs, product specs, references, generated inventory, and exec plans."""

import os
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
ARCHITECTURE_DIR = DOCS_DIR / "architecture"
PLANS_DIR = DOCS_DIR / "plans"
DESIGN_DIR = DOCS_DIR / "design-docs"
PRODUCT_SPECS_DIR = DOCS_DIR / "product-specs"
REFERENCES_DIR = DOCS_DIR / "references"
INVENTORY_DIR = DOCS_DIR / "generated-inventory"
EXEC_PLANS_DIR = DOCS_DIR / "exec-plans"

def ensure_dirs():
    for d in [ARCHITECTURE_DIR, PLANS_DIR, DESIGN_DIR, PRODUCT_SPECS_DIR, REFERENCES_DIR, INVENTORY_DIR, EXEC_PLANS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def generate_architecture():
    arch_content = """# Architecture

## Overview
This document describes the high-level architecture of the AI-collaborative repository.

## Components
- **Agent Harness**: Entry points for AI agents.
- **Knowledge Index**: Generated index of repository knowledge.
- **Validation Harness**: Runtime validation with Playwright smoke tests.
- **Backend Diagnostics**: Request-id tracing for backend services.

## Data Flow
1. Agent enters via harness.
2. Harness loads knowledge index.
3. Validation harness runs smoke tests.
4. Backend diagnostics capture request IDs.
"""
    (ARCHITECTURE_DIR / "overview.md").write_text(arch_content)

def generate_plans():
    plans_content = """# Plans

## Phase 1: Repository Restructure
- [x] Create directory structure
- [x] Generate architecture docs
- [ ] Migrate existing docs

## Phase 2: Agent Harness
- [ ] Shrink AGENTS entry points
- [ ] Add knowledge/index generation
- [ ] Unified repository harness validation

## Phase 3: Runtime Harness
- [ ] Playwright smoke coverage
- [ ] Backend request-id diagnostics
"""
    (PLANS_DIR / "roadmap.md").write_text(plans_content)

def generate_design_docs():
    design_content = """# Design Document: Agent-First Harness

## Problem
Current repository lacks structured knowledge organization and agent entry points.

## Solution
- Reorganize into standard directories.
- Generate knowledge index automatically.
- Provide unified validation harness.

## Implementation
- Use Python scripts for generation.
- Playwright for smoke tests.
- Request-id middleware for diagnostics.
"""
    (DESIGN_DIR / "agent-harness-design.md").write_text(design_content)

def generate_product_specs():
    spec_content = """# Product Spec: Repository Harness

## Features
1. **Knowledge Organization**: Auto-generated docs structure.
2. **Agent Entry Points**: Minimal, clear AGENTS.md.
3. **Validation**: Smoke tests with Playwright.
4. **Diagnostics**: Request-id tracing.

## Acceptance Criteria
- `python3 scripts/generate_ai_collab_docs.py` runs without error.
- `python3 scripts/build_repo_knowledge_index.py` produces index.
- Playwright tests pass.
"""
    (PRODUCT_SPECS_DIR / "harness-spec.md").write_text(spec_content)

def generate_references():
    ref_content = """# References

- [Playwright Documentation](https://playwright.dev/python/docs/intro)
- [Python JSON Module](https://docs.python.org/3/library/json.html)
- [Request-ID Best Practices](https://www.ietf.org/archive/id/draft-ietf-httpbis-message-signatures-00.html)
"""
    (REFERENCES_DIR / "external-links.md").write_text(ref_content)

def generate_inventory():
    inventory = {
        "architecture": ["overview.md"],
        "plans": ["roadmap.md"],
        "design-docs": ["agent-harness-design.md"],
        "product-specs": ["harness-spec.md"],
        "references": ["external-links.md"],
        "generated-inventory": ["inventory.json"],
        "exec-plans": ["execution-plan.md"]
    }
    (INVENTORY_DIR / "inventory.json").write_text(json.dumps(inventory, indent=2))

def generate_exec_plans():
    exec_content = """# Execution Plan

## Step 1: Generate Docs
