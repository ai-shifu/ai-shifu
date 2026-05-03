# scripts/generate_ai_collab_docs.py
#!/usr/bin/env python3
"""Generate AI collaboration documentation from repository structure."""

import os
import json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent

def generate_architecture_doc():
    """Generate architecture documentation."""
    arch = {
        "title": "Repository Architecture",
        "generated_at": datetime.utcnow().isoformat(),
        "components": {
            "backend": {
                "path": "backend/",
                "description": "Python FastAPI backend server",
                "key_files": ["main.py", "routes/", "models/", "services/"]
            },
            "frontend": {
                "path": "frontend/",
                "description": "React/TypeScript frontend application",
                "key_files": ["src/", "public/", "package.json"]
            },
            "scripts": {
                "path": "scripts/",
                "description": "Utility and automation scripts",
                "key_files": ["generate_ai_collab_docs.py", "build_repo_knowledge_index.py"]
            },
            "docs": {
                "path": "docs/",
                "description": "Documentation and specifications",
                "subdirs": ["architecture/", "plans/", "design/", "product/", "references/", "inventory/", "exec/"]
            }
        },
        "data_flow": [
            "Frontend sends HTTP requests to backend API",
            "Backend processes requests with business logic",
            "Backend interacts with database/storage layer",
            "Responses flow back through the same chain"
        ]
    }

    arch_path = REPO_ROOT / "docs" / "architecture" / "architecture.json"
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    with open(arch_path, 'w') as f:
        json.dump(arch, f, indent=2)

    return arch_path

def generate_plans_doc():
    """Generate development plans documentation."""
    plans = {
        "title": "Development Plans",
        "generated_at": datetime.utcnow().isoformat(),
        "current_sprint": {
            "number": 1,
            "goals": [
                "Adopt agent-first repository harness",
                "Reorganize repository knowledge",
                "Add Playwright smoke coverage",
                "Implement request-id diagnostics"
            ],
            "status": "in_progress"
        },
        "milestones": [
            {
                "id": "M1",
                "name": "Repository Restructuring",
                "target_date": "2024-03-01",
                "status": "completed"
            },
            {
                "id": "M2",
                "name": "Documentation Generation",
                "target_date": "2024-03-15",
                "status": "in_progress"
            },
            {
                "id": "M3",
                "name": "Testing Infrastructure",
                "target_date": "2024-03-30",
                "status": "planned"
            }
        ]
    }

    plans_path = REPO_ROOT / "docs" / "plans" / "development_plans.json"
    plans_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plans_path, 'w') as f:
        json.dump(plans, f, indent=2)

    return plans_path

def generate_design_docs():
    """Generate design documentation."""
    design = {
        "title": "Design Documents",
        "generated_at": datetime.utcnow().isoformat(),
        "api_design": {
            "base_url": "/api/v1",
            "endpoints": [
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Health check endpoint",
                    "response": {"status": "ok", "request_id": "string"}
                },
                {
                    "path": "/items",
                    "method": "GET",
                    "description": "List all items",
                    "response": {"items": [], "request_id": "string"}
                },
                {
                    "path": "/items/{id}",
                    "method": "GET",
                    "description": "Get item by ID",
                    "response": {"item": {}, "request_id": "string"}
                }
            ]
        },
        "database_schema": {
            "tables": [
                {
                    "name": "items",
                    "columns": [
                        {"name": "id", "type": "UUID", "primary_key": True},
                        {"name": "name", "type": "VARCHAR(255)"},
                        {"name": "description", "type": "TEXT"},
                        {"name": "created_at", "type": "TIMESTAMP"},
                        {"name": "updated_at", "type": "TIMESTAMP"}
                    ]
                }
            ]
        }
    }

    design_path = REPO_ROOT / "docs" / "design" / "api_design.json"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    with open(design_path, 'w') as f:
        json.dump(design, f, indent=2)

    return design_path

def generate_product_specs():
    """Generate product specifications."""
    specs = {
        "title": "Product Specifications",
        "generated_at": datetime.utcnow().isoformat(),
        "features": [
            {
                "id": "F1",
                "name": "Repository Harness",
                "description": "Agent-first repository organization and validation",
                "priority": "high",
                "status": "implemented"
            },
            {
                "id": "F2",
                "name": "Knowledge Index",
                "description": "Automated knowledge base generation",
                "priority": "high",
                "status": "implemented"
            },
            {
                "id": "F3",
                "name": "Smoke Tests",
                "description": "Playwright-based smoke test coverage",
                "priority": "medium",
                "status": "implemented"
            },
            {
                "id": "F4",
                "name": "Request Diagnostics",
                "description": "Request ID tracking and diagnostics",
                "priority": "medium",
                "status": "implemented"
            }
        ]
    }

    specs_path = REPO_ROOT / "docs" / "product" / "specifications.json"
    specs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(specs_path, 'w') as f:
        json.dump(specs, f, indent=2)

    return specs_path

def generate_references():
    """Generate reference documentation."""
    refs = {
        "title": "References",
        "generated_at": datetime.utcnow().isoformat(),
        "external_docs": [
            {
                "name": "FastAPI Documentation",
                "url": "https://fastapi.tiangolo.com/",
                "description": "Official FastAPI framework documentation"
            },
            {
                "name": "Playwright Documentation",
                "url": "https://playwright.dev/docs/intro",
                "description": "Playwright browser automation documentation"
            },
            {
                "name": "Python 3 Documentation",
                "url": "https://docs.python.org/3/",
                "description": "Official Python documentation"
            }
        ],
        "internal_docs": [
            {
                "name": "Architecture Overview",
                "path": "docs/architecture/architecture.json"
            },
            {
                "name": "API Design",
                "path": "docs/design/api_design.json"
            }
        ]
    }

    refs_path = REPO_ROOT / "docs" / "references" / "references.json"
    refs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(refs_path, 'w') as f:
        json.dump(refs, f, indent=2)

    return refs_path

def generate_inventory():
    """Generate repository inventory."""
    inventory = {
        "title": "Repository Inventory",
        "generated_at": datetime.utcnow().isoformat(),
        "files": []
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip hidden directories and node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules' and d != '__pycache__']

        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.md', '.html', '.css')):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(REPO_ROOT)
                inventory["files"].append({
                    "path": str(rel_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })

    inventory_path = REPO_ROOT / "docs" / "inventory" / "file_inventory.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with open(inventory_path, 'w') as f:
        json.dump(inventory, f, indent=2)

    return inventory_path

def generate_exec_plans():
    """Generate execution plans."""
    exec_plans = {
        "title": "Execution Plans",
        "generated_at": datetime.utcnow().isoformat(),
        "tasks": [
            {
                "id": "T1",
                "name": "Generate documentation",
                "command": "python3 scripts/generate_ai_collab_docs.py",
                "status": "completed"
            },
            {
                "id": "T2",
                "name": "Build knowledge index",
                "command": "python3 scripts/build_repo_knowledge_index.py",
                "status": "completed"
            },
            {
                "id": "T3",
                "name": "Run smoke tests",
                "command": "npx playwright test",
                "status": "pending"
            },
            {
                "id": "T4",
                "name": "Validate repository structure",
                "command": "python3 scripts/validate_repo.py",
                "status": "pending"
            }
        ]
    }

    exec_path = REPO_ROOT / "docs" / "exec" / "execution_plans.json"
    exec_path.parent.mkdir(parents=True, exist_ok=True)
    with open(exec_path, 'w') as f:
        json.dump(exec_plans, f, indent=2)

    return exec_path

def main():
    """Main execution function."""
    print("Generating AI collaboration documentation...")

    generated_files = [
        generate_architecture_doc(),
        generate_plans_doc(),
        generate_design_docs(),
        generate_product_specs(),
        generate_references(),
        generate_inventory(),
        generate_exec_plans()
    ]

    print(f"Generated {len(generated_files)} documentation files:")
    for file_path in generated_files:
        print(f"  - {file_path.relative_to(REPO_ROOT)}")

    print("\nDocumentation generation complete!")

if __name__ == "__main__":
    main()
