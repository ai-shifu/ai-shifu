# scripts/generate_ai_collab_docs.py
#!/usr/bin/env python3
"""Generate AI collaboration documentation from repository structure."""

import os
import json
import yaml
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent

def generate_architecture_doc():
    """Generate architecture documentation."""
    arch = {
        "name": "Repository Architecture",
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat(),
        "components": {
            "backend": {
                "path": "backend/",
                "description": "Backend services and APIs",
                "technologies": ["Python", "FastAPI", "PostgreSQL"]
            },
            "frontend": {
                "path": "frontend/",
                "description": "Frontend application",
                "technologies": ["React", "TypeScript", "Web3"]
            },
            "contracts": {
                "path": "contracts/",
                "description": "Smart contracts",
                "technologies": ["Solidity", "Hardhat"]
            },
            "scripts": {
                "path": "scripts/",
                "description": "Utility and automation scripts"
            }
        },
        "data_flow": {
            "user_request": "Frontend -> Backend API -> Smart Contract",
            "blockchain_event": "Smart Contract -> Backend Listener -> Frontend"
        }
    }

    output_path = REPO_ROOT / "architecture" / "system_architecture.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(arch, f, indent=2)

    return output_path

def generate_plans_doc():
    """Generate development plans documentation."""
    plans = {
        "current_sprint": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-14",
            "goals": [
                "Implement agent-first repository harness",
                "Add Playwright smoke tests",
                "Add request-id diagnostics"
            ]
        },
        "backlog": [
            {
                "id": "PLAN-001",
                "title": "Adopt agent-first repository structure",
                "status": "in_progress",
                "priority": "high"
            },
            {
                "id": "PLAN-002",
                "title": "Add unified validation harness",
                "status": "in_progress",
                "priority": "high"
            }
        ]
    }

    output_path = REPO_ROOT / "plans" / "development_plans.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(plans, f, indent=2)

    return output_path

def generate_design_docs():
    """Generate design documentation."""
    design = {
        "api_design": {
            "base_url": "/api/v1",
            "endpoints": {
                "health": {
                    "method": "GET",
                    "path": "/health",
                    "description": "Health check endpoint"
                },
                "request_diagnostics": {
                    "method": "GET",
                    "path": "/diagnostics/request/{request_id}",
                    "description": "Get request diagnostics"
                }
            }
        },
        "database_design": {
            "tables": {
                "requests": {
                    "columns": [
                        {"name": "id", "type": "UUID", "primary_key": True},
                        {"name": "request_id", "type": "VARCHAR(255)", "index": True},
                        {"name": "timestamp", "type": "TIMESTAMP"},
                        {"name": "method", "type": "VARCHAR(10)"},
                        {"name": "path", "type": "VARCHAR(255)"},
                        {"name": "status_code", "type": "INTEGER"},
                        {"name": "duration_ms", "type": "INTEGER"}
                    ]
                }
            }
        }
    }

    output_path = REPO_ROOT / "design" / "technical_design.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(design, f, indent=2)

    return output_path

def generate_product_specs():
    """Generate product specifications."""
    specs = {
        "product_name": "Agent-First Repository Harness",
        "version": "1.0.0",
        "features": [
            {
                "id": "FEAT-001",
                "name": "Repository Knowledge Index",
                "description": "Automated generation of repository knowledge index",
                "acceptance_criteria": [
                    "Index all documentation files",
                    "Generate searchable knowledge base",
                    "Support markdown and JSON formats"
                ]
            },
            {
                "id": "FEAT-002",
                "name": "Unified Validation Harness",
                "description": "Centralized validation for repository structure",
                "acceptance_criteria": [
                    "Validate directory structure",
                    "Check file existence",
                    "Verify documentation completeness"
                ]
            },
            {
                "id": "FEAT-003",
                "name": "Playwright Smoke Tests",
                "description": "Browser-based smoke tests for frontend",
                "acceptance_criteria": [
                    "Test page load",
                    "Verify API connectivity",
                    "Check error handling"
                ]
            }
        ]
    }

    output_path = REPO_ROOT / "product_specs" / "product_specifications.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(specs, f, indent=2)

    return output_path

def generate_references():
    """Generate reference documentation."""
    references = {
        "api_reference": {
            "base_url": "http://localhost:8000",
            "endpoints": {
                "GET /health": {
                    "description": "Health check",
                    "response": {"status": "healthy", "timestamp": "ISO8601"}
                },
                "GET /diagnostics/request/{request_id}": {
                    "description": "Get request diagnostics",
                    "parameters": {
                        "request_id": {"type": "string", "required": True}
                    },
                    "response": {
                        "request_id": "string",
                        "method": "string",
                        "path": "string",
                        "status_code": "integer",
                        "duration_ms": "integer",
                        "timestamp": "ISO8601"
                    }
                }
            }
        },
        "configuration_reference": {
            "environment_variables": {
                "DATABASE_URL": {"description": "PostgreSQL connection string"},
                "REDIS_URL": {"description": "Redis connection string"},
                "LOG_LEVEL": {"description": "Logging level", "default": "INFO"}
            }
        }
    }

    output_path = REPO_ROOT / "references" / "api_reference.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(references, f, indent=2)

    return output_path

def generate_inventory():
    """Generate repository inventory."""
    inventory = {
        "generated_at": datetime.utcnow().isoformat(),
        "directories": [],
        "files": [],
        "total_size_bytes": 0
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip hidden directories and node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']

        rel_path = os.path.relpath(root, REPO_ROOT)
        if rel_path != '.':
            inventory["directories"].append(rel_path)

        for file in files:
            file_path = os.path.join(root, file)
            rel_file_path = os.path.relpath(file_path, REPO_ROOT)
            inventory["files"].append({
                "path": rel_file_path,
                "size_bytes": os.path.getsize(file_path),
                "extension": os.path.splitext(file)[1]
            })
            inventory["total_size_bytes"] += os.path.getsize(file_path)

    output_path = REPO_ROOT / "inventory" / "repository_inventory.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(inventory, f, indent=2)

    return output_path

def generate_exec_plans():
    """Generate execution plans."""
    exec_plans = {
        "phase_1": {
            "name": "Repository Restructuring",
            "tasks": [
                {"id": "TASK-001", "description": "Create architecture directory", "status": "completed"},
                {"id": "TASK-002", "description": "Create plans directory", "status": "completed"},
                {"id": "TASK-003", "description": "Create design directory", "status": "completed"},
                {"id": "TASK-004", "description": "Create product_specs directory", "status": "completed"},
                {"id": "TASK-005", "description": "Create references directory", "status": "completed"},
                {"id": "TASK-006", "description": "Create inventory directory", "status": "completed"},
                {"id": "TASK-007", "description": "Create exec_plans directory", "status": "completed"}
            ]
        },
        "phase_2": {
            "name": "Documentation Generation",
            "tasks": [
                {"id": "TASK-008", "description": "Generate architecture docs", "status": "completed"},
                {"id": "TASK-009", "description": "Generate plans docs", "status": "completed"},
                {"id": "TASK-010", "description": "Generate design docs", "status": "completed"},
                {"id": "TASK-011", "description": "Generate product specs", "status": "completed"},
                {"id": "TASK-012", "description": "Generate references", "status": "completed"},
                {"id": "TASK-013", "description": "Generate inventory", "status": "completed"},
                {"id": "TASK-014", "description": "Generate exec plans", "status": "completed"}
            ]
        },
        "phase_3": {
            "name": "Validation Harness",
            "tasks": [
                {"id": "TASK-015", "description": "Implement validation script", "status": "pending"},
                {"id": "TASK-016", "description": "Add Playwright tests", "status": "pending"},
                {"id": "TASK-017", "description": "Add request-id diagnostics", "status": "pending"}
            ]
        }
    }

    output_path = REPO_ROOT / "exec_plans" / "execution_plans.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(exec_plans, f, indent=2)

    return output_path

def main():
    """Main execution function."""
    print("Generating AI collaboration documentation...")

    # Generate all documentation
    arch_path = generate_architecture_doc()
    print(f"✓ Architecture docs: {arch_path}")

    plans_path = generate_plans_doc()
    print(f"✓ Plans docs: {plans_path}")

    design_path = generate_design_docs()
    print(f"✓ Design docs: {design_path}")

    specs_path = generate_product_specs()
    print(f"✓ Product specs: {specs_path}")

    refs_path = generate_references()
    print(f"✓ References: {refs_path}")

    inv_path = generate_inventory()
    print(f"✓ Inventory: {inv_path}")

    exec_path = generate_exec_plans()
    print(f"✓ Exec plans: {exec_path}")

    print("\nAll documentation generated successfully!")

if __name__ == "__main__":
    main()
