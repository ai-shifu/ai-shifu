# scripts/generate_ai_collab_docs.py
#!/usr/bin/env python3
"""Generate AI collaboration documentation from repository structure."""

import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def generate_architecture_doc():
    """Generate architecture documentation."""
    arch = {
        "name": "Repository Architecture",
        "version": "1.0.0",
        "components": {
            "frontend": {
                "path": "src/frontend",
                "tech": ["React", "TypeScript", "Playwright"],
                "description": "Web application interface"
            },
            "backend": {
                "path": "src/backend",
                "tech": ["Python", "FastAPI", "PostgreSQL"],
                "description": "API server and business logic"
            },
            "blockchain": {
                "path": "src/blockchain",
                "tech": ["Solidity", "Web3.py"],
                "description": "Smart contracts and blockchain integration"
            }
        },
        "data_flow": [
            "Client -> Frontend -> API Gateway -> Backend Services",
            "Backend -> Database/Blockchain -> Response"
        ]
    }
    
    os.makedirs(REPO_ROOT / "docs" / "architecture", exist_ok=True)
    with open(REPO_ROOT / "docs" / "architecture" / "overview.json", "w") as f:
        json.dump(arch, f, indent=2)

def generate_plans_doc():
    """Generate development plans documentation."""
    plans = {
        "current_sprint": {
            "goal": "Adopt agent-first repository harness",
            "tasks": [
                "Reorganize repository knowledge",
                "Add knowledge index generation",
                "Implement runtime harness with Playwright",
                "Add backend request-id diagnostics"
            ]
        },
        "next_sprint": {
            "goal": "Enhance agent capabilities",
            "tasks": [
                "Implement agent communication protocol",
                "Add agent monitoring dashboard",
                "Optimize agent resource usage"
            ]
        }
    }
    
    os.makedirs(REPO_ROOT / "docs" / "plans", exist_ok=True)
    with open(REPO_ROOT / "docs" / "plans" / "sprint_plans.json", "w") as f:
        json.dump(plans, f, indent=2)

def generate_design_docs():
    """Generate design documentation."""
    design = {
        "system_design": {
            "architecture_pattern": "Microservices",
            "scalability": "Horizontal scaling with load balancers",
            "security": "JWT authentication, rate limiting, input validation"
        },
        "api_design": {
            "rest_endpoints": [
                {"path": "/api/v1/agents", "method": "GET", "description": "List all agents"},
                {"path": "/api/v1/agents/{id}", "method": "POST", "description": "Create/update agent"},
                {"path": "/api/v1/agents/{id}/execute", "method": "POST", "description": "Execute agent task"}
            ],
            "websocket_endpoints": [
                {"path": "/ws/agent/{id}", "description": "Real-time agent communication"}
            ]
        }
    }
    
    os.makedirs(REPO_ROOT / "docs" / "design", exist_ok=True)
    with open(REPO_ROOT / "docs" / "design" / "system_design.json", "w") as f:
        json.dump(design, f, indent=2)

def generate_product_specs():
    """Generate product specifications."""
    specs = {
        "product_name": "Agent-First Repository Harness",
        "version": "1.0.0",
        "features": [
            {
                "id": "F-001",
                "name": "Knowledge Index Generation",
                "description": "Automatically generate and maintain repository knowledge index",
                "priority": "high"
            },
            {
                "id": "F-002",
                "name": "Runtime Harness Validation",
                "description": "Validate repository harness with Playwright smoke tests",
                "priority": "high"
            },
            {
                "id": "F-003",
                "name": "Backend Request-ID Diagnostics",
                "description": "Add request tracking and diagnostics to backend services",
                "priority": "medium"
            }
        ]
    }
    
    os.makedirs(REPO_ROOT / "docs" / "product_specs", exist_ok=True)
    with open(REPO_ROOT / "docs" / "product_specs" / "features.json", "w") as f:
        json.dump(specs, f, indent=2)

def generate_references():
    """Generate reference documentation."""
    refs = {
        "external_docs": [
            {"name": "Playwright Documentation", "url": "https://playwright.dev/docs/intro"},
            {"name": "FastAPI Documentation", "url": "https://fastapi.tiangolo.com/"},
            {"name": "Web3.py Documentation", "url": "https://web3py.readthedocs.io/"}
        ],
        "internal_docs": [
            {"name": "Architecture Overview", "path": "docs/architecture/overview.json"},
            {"name": "Development Plans", "path": "docs/plans/sprint_plans.json"},
            {"name": "System Design", "path": "docs/design/system_design.json"}
        ]
    }
    
    os.makedirs(REPO_ROOT / "docs" / "references", exist_ok=True)
    with open(REPO_ROOT / "docs" / "references" / "references.json", "w") as f:
        json.dump(refs, f, indent=2)

def generate_inventory():
    """Generate repository inventory."""
    inventory = {
        "directories": [],
        "files": []
    }
    
    for root, dirs, files in os.walk(REPO_ROOT):
        if '.git' in root or '__pycache__' in root or 'node_modules' in root:
            continue
        rel_path = os.path.relpath(root, REPO_ROOT)
        if rel_path != '.':
            inventory["directories"].append(rel_path)
        for file in files:
            file_path = os.path.join(rel_path, file)
            inventory["files"].append(file_path)
    
    os.makedirs(REPO_ROOT / "docs" / "generated_inventory", exist_ok=True)
    with open(REPO_ROOT / "docs" / "generated_inventory" / "inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)

def generate_exec_plans():
    """Generate execution plans."""
    exec_plans = {
        "phase_1": {
            "name": "Repository Reorganization",
            "tasks": [
                "Create docs/architecture directory",
                "Create docs/plans directory",
                "Create docs/design directory",
                "Create docs/product_specs directory",
                "Create docs/references directory",
                "Create docs/generated_inventory directory",
                "Create docs/exec_plans directory"
            ],
            "status": "completed"
        },
        "phase_2": {
            "name": "Knowledge Index Generation",
            "tasks": [
                "Implement generate_ai_collab_docs.py",
                "Implement build_repo_knowledge_index.py",
                "Add unified repository harness validation"
            ],
            "status": "in_progress"
        },
        "phase_3": {
            "name": "Runtime Harness Implementation",
            "tasks": [
                "Add Playwright smoke coverage",
                "Add backend request-id diagnostics",
                "Retire root tasks.md"
            ],
            "status": "pending"
        }
    }
    
    os.makedirs(REPO_ROOT / "docs" / "exec_plans", exist_ok=True)
    with open(REPO_ROOT / "docs" / "exec_plans" / "execution_plan.json", "w") as f:
        json.dump(exec_plans, f, indent=2)

def main():
    """Main execution function."""
    print("Generating AI collaboration documentation...")
    
    generate_architecture_doc()
    print("✓ Architecture documentation generated")
    
    generate_plans_doc()
    print("✓ Plans documentation generated")
    
    generate_design_docs()
    print("✓ Design documentation generated")
    
    generate_product_specs()
    print("✓ Product specifications generated")
    
    generate_references()
    print("✓ References generated")
    
    generate_inventory()
    print("✓ Inventory generated")
    
    generate_exec_plans()
    print("✓ Execution plans generated")
    
    print("\nAll documentation generated successfully!")

if __name__ == "__main__":
    main()
