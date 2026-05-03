# scripts/generate_ai_collab_docs.py
import os
import json
from pathlib import Path

def generate_architecture_docs():
    """Generate architecture documentation from repository structure"""
    docs = {
        "architecture": {
            "overview": "Agent-first repository harness for blockchain/P2P development",
            "components": {
                "agents": "AI agent entry points and orchestration",
                "backend": "Request handling and diagnostics",
                "frontend": "Playwright smoke test coverage",
                "knowledge": "Repository knowledge index and documentation"
            },
            "data_flow": [
                "Agent receives task → queries knowledge index",
                "Knowledge index provides context → agent executes plan",
                "Plan execution → backend request with request-id",
                "Backend response → Playwright validates smoke test"
            ]
        }
    }

    os.makedirs("docs/architecture", exist_ok=True)
    with open("docs/architecture/overview.json", "w") as f:
        json.dump(docs, f, indent=2)

    return docs

def generate_plans():
    """Generate execution plans"""
    plans = {
        "exec_plans": {
            "phase1": {
                "name": "Repository reorganization",
                "tasks": [
                    "Create architecture docs directory",
                    "Create plans directory",
                    "Create design docs directory",
                    "Create product specs directory",
                    "Create references directory",
                    "Create generated inventory directory",
                    "Create exec plans directory"
                ]
            },
            "phase2": {
                "name": "Agent entry point optimization",
                "tasks": [
                    "Shrink AGENTS entry points",
                    "Add knowledge/index generation",
                    "Add unified repository harness validation",
                    "Retire root tasks.md"
                ]
            },
            "phase3": {
                "name": "Runtime harness implementation",
                "tasks": [
                    "Add Playwright smoke coverage",
                    "Add backend request-id diagnostics",
                    "Validate complete workflow"
                ]
            }
        }
    }

    os.makedirs("docs/plans", exist_ok=True)
    with open("docs/plans/execution_plan.json", "w") as f:
        json.dump(plans, f, indent=2)

    return plans

def generate_design_docs():
    """Generate design documentation"""
    design = {
        "design_docs": {
            "harness": {
                "purpose": "Unified repository harness for agent-first development",
                "components": {
                    "knowledge_index": {
                        "type": "JSON-based index",
                        "location": "docs/generated_inventory/knowledge_index.json"
                    },
                    "validation": {
                        "type": "Automated validation",
                        "script": "scripts/build_repo_knowledge_index.py"
                    },
                    "smoke_tests": {
                        "type": "Playwright tests",
                        "location": "tests/smoke/"
                    }
                }
            }
        }
    }

    os.makedirs("docs/design", exist_ok=True)
    with open("docs/design/harness_design.json", "w") as f:
        json.dump(design, f, indent=2)

    return design

def generate_product_specs():
    """Generate product specifications"""
    specs = {
        "product_specs": {
            "version": "1.0.0",
            "features": [
                "Agent-first repository organization",
                "Automated knowledge index generation",
                "Unified harness validation",
                "Playwright smoke test coverage",
                "Backend request-id diagnostics"
            ],
            "requirements": [
                "Python 3.8+",
                "Playwright",
                "Node.js 14+ (for backend)"
            ]
        }
    }

    os.makedirs("docs/product_specs", exist_ok=True)
    with open("docs/product_specs/specifications.json", "w") as f:
        json.dump(specs, f, indent=2)

    return specs

def generate_references():
    """Generate reference documentation"""
    references = {
        "references": {
            "api": {
                "base_url": "http://localhost:3000",
                "endpoints": {
                    "health": "/api/health",
                    "request_id": "/api/request-id"
                }
            },
            "tools": {
                "playwright": "https://playwright.dev",
                "python": "https://python.org"
            }
        }
    }

    os.makedirs("docs/references", exist_ok=True)
    with open("docs/references/api_reference.json", "w") as f:
        json.dump(references, f, indent=2)

    return references

def generate_inventory():
    """Generate repository inventory"""
    inventory = {
        "generated_inventory": {
            "directories": [
                "docs/architecture",
                "docs/plans",
                "docs/design",
                "docs/product_specs",
                "docs/references",
                "docs/generated_inventory",
                "docs/exec_plans",
                "tests/smoke",
                "scripts"
            ],
            "files": [
                "scripts/generate_ai_collab_docs.py",
                "scripts/build_repo_knowledge_index.py",
                "tests/smoke/test_harness.py",
                "backend/request_id_middleware.js"
            ]
        }
    }

    os.makedirs("docs/generated_inventory", exist_ok=True)
    with open("docs/generated_inventory/inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)

    return inventory

def generate_exec_plans():
    """Generate execution plans"""
    exec_plans = {
        "exec_plans": {
            "current": {
                "phase": "Implementation",
                "steps": [
                    "1. Generate documentation structure",
                    "2. Build knowledge index",
                    "3. Implement Playwright smoke tests",
                    "4. Add backend request-id diagnostics",
                    "5. Validate complete harness"
                ],
                "status": "in_progress"
            }
        }
    }

    os.makedirs("docs/exec_plans", exist_ok=True)
    with open("docs/exec_plans/current_plan.json", "w") as f:
        json.dump(exec_plans, f, indent=2)

    return exec_plans

def main():
    """Main execution function"""
    print("Generating AI collaboration documentation...")

    # Generate all documentation
    generate_architecture_docs()
    generate_plans()
    generate_design_docs()
    generate_product_specs()
    generate_references()
    generate_inventory()
    generate_exec_plans()

    print("Documentation generated successfully!")
    print("Directories created:")
    print("  - docs/architecture")
    print("  - docs/plans")
    print("  - docs/design")
    print("  - docs/product_specs")
    print("  - docs/references")
    print("  - docs/generated_inventory")
    print("  - docs/exec_plans")

if __name__ == "__main__":
    main()
