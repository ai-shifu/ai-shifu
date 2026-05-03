# scripts/generate_ai_collab_docs.py
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def generate_architecture_docs():
    """Generate architecture documentation from source code structure"""
    docs = {
        "architecture": {
            "overview": "Agent-first repository harness for P2P blockchain development",
            "components": []
        }
    }

    # Scan source directories
    src_dirs = ['src', 'contracts', 'tests']
    for dir_name in src_dirs:
        dir_path = REPO_ROOT / dir_name
        if dir_path.exists():
            components = []
            for item in dir_path.iterdir():
                if item.is_dir():
                    components.append({
                        "name": item.name,
                        "path": str(item.relative_to(REPO_ROOT)),
                        "type": "module"
                    })
            docs["architecture"]["components"].extend(components)

    return docs

def generate_plans():
    """Generate execution plans from task structure"""
    plans = {
        "exec_plans": {
            "phase_1": {
                "name": "Repository Harness Setup",
                "tasks": [
                    "Reorganize repository structure",
                    "Add knowledge index generation",
                    "Implement validation harness",
                    "Add Playwright smoke tests"
                ],
                "status": "in_progress"
            },
            "phase_2": {
                "name": "Backend Diagnostics",
                "tasks": [
                    "Add request-id middleware",
                    "Implement diagnostic endpoints",
                    "Add test coverage"
                ],
                "status": "planned"
            }
        }
    }
    return plans

def generate_design_docs():
    """Generate design documentation from existing specs"""
    design_docs = {
        "design": {
            "harness": {
                "description": "Unified repository validation harness",
                "components": [
                    "Knowledge index generator",
                    "Validation scripts",
                    "Smoke test suite"
                ]
            },
            "backend": {
                "description": "Backend with request-id diagnostics",
                "features": [
                    "Request tracing",
                    "Error logging",
                    "Performance metrics"
                ]
            }
        }
    }
    return design_docs

def generate_product_specs():
    """Generate product specifications"""
    specs = {
        "product_specs": {
            "version": "1.0.0",
            "features": [
                {
                    "id": "FEAT-001",
                    "name": "Repository Harness",
                    "description": "Unified validation and documentation generation"
                },
                {
                    "id": "FEAT-002",
                    "name": "Backend Diagnostics",
                    "description": "Request tracing and error logging"
                }
            ]
        }
    }
    return specs

def generate_references():
    """Generate reference documentation"""
    refs = {
        "references": {
            "api": {
                "endpoints": [
                    {"path": "/health", "method": "GET", "description": "Health check"},
                    {"path": "/diagnostics", "method": "GET", "description": "Diagnostic info"}
                ]
            },
            "config": {
                "required_env_vars": [
                    "PORT",
                    "LOG_LEVEL",
                    "DATABASE_URL"
                ]
            }
        }
    }
    return refs

def generate_inventory():
    """Generate inventory of all files and directories"""
    inventory = {
        "inventory": {
            "directories": [],
            "files": []
        }
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

        rel_path = Path(root).relative_to(REPO_ROOT)
        if str(rel_path) == '.':
            continue

        if dirs:
            inventory["inventory"]["directories"].extend([
                str(Path(rel_path) / d) for d in dirs
            ])

        for file in files:
            if not file.startswith('.'):
                inventory["inventory"]["files"].append(
                    str(Path(rel_path) / file)
                )

    return inventory

def main():
    """Main function to generate all documentation"""
    output_dir = REPO_ROOT / 'docs' / 'generated'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate all documentation
    docs = {
        **generate_architecture_docs(),
        **generate_plans(),
        **generate_design_docs(),
        **generate_product_specs(),
        **generate_references(),
        **generate_inventory()
    }

    # Write to file
    output_file = output_dir / 'ai_collab_docs.json'
    with open(output_file, 'w') as f:
        json.dump(docs, f, indent=2)

    print(f"Generated AI collaboration docs at {output_file}")

if __name__ == "__main__":
    main()
