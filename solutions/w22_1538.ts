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
                "description": "Backend services and APIs",
                "technologies": ["Python", "FastAPI", "PostgreSQL"]
            },
            "frontend": {
                "path": "frontend/",
                "description": "Web application frontend",
                "technologies": ["React", "TypeScript", "WebSocket"]
            },
            "contracts": {
                "path": "contracts/",
                "description": "Smart contracts and blockchain integration",
                "technologies": ["Solidity", "Web3"]
            }
        },
        "data_flow": [
            {"from": "client", "to": "api_gateway", "protocol": "HTTPS"},
            {"from": "api_gateway", "to": "backend_services", "protocol": "gRPC"},
            {"from": "backend_services", "to": "blockchain", "protocol": "Web3"}
        ]
    }

    output_path = REPO_ROOT / "architecture" / "architecture.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(arch, f, indent=2)
    print(f"Generated architecture doc: {output_path}")

def generate_plans_doc():
    """Generate development plans documentation."""
    plans = {
        "title": "Development Plans",
        "generated_at": datetime.utcnow().isoformat(),
        "phases": [
            {
                "name": "Phase 1: Foundation",
                "tasks": [
                    "Set up repository structure",
                    "Implement core backend services",
                    "Create basic frontend scaffolding"
                ],
                "status": "in_progress"
            },
            {
                "name": "Phase 2: Integration",
                "tasks": [
                    "Integrate blockchain contracts",
                    "Implement WebSocket communication",
                    "Add authentication and authorization"
                ],
                "status": "planned"
            },
            {
                "name": "Phase 3: Production",
                "tasks": [
                    "Performance optimization",
                    "Security audit",
                    "Deployment automation"
                ],
                "status": "planned"
            }
        ]
    }

    output_path = REPO_ROOT / "plans" / "plans.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(plans, f, indent=2)
    print(f"Generated plans doc: {output_path}")

def generate_design_docs():
    """Generate design documentation."""
    design = {
        "title": "Design Documents",
        "generated_at": datetime.utcnow().isoformat(),
        "api_design": {
            "base_url": "/api/v1",
            "endpoints": [
                {"path": "/users", "methods": ["GET", "POST", "PUT", "DELETE"]},
                {"path": "/transactions", "methods": ["GET", "POST"]},
                {"path": "/blocks", "methods": ["GET"]}
            ],
            "authentication": "JWT Bearer Token"
        },
        "database_design": {
            "type": "PostgreSQL",
            "tables": ["users", "transactions", "blocks", "contracts"],
            "indexes": ["user_id", "transaction_hash", "block_number"]
        },
        "blockchain_design": {
            "network": "Testnet",
            "consensus": "Proof of Stake",
            "block_time": "2 seconds"
        }
    }

    output_path = REPO_ROOT / "design_docs" / "design.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(design, f, indent=2)
    print(f"Generated design docs: {output_path}")

def generate_product_specs():
    """Generate product specifications."""
    specs = {
        "title": "Product Specifications",
        "generated_at": datetime.utcnow().isoformat(),
        "features": [
            {
                "id": "F001",
                "name": "User Registration",
                "description": "Allow users to create accounts",
                "priority": "high",
                "acceptance_criteria": [
                    "User can register with email and password",
                    "Email verification required",
                    "Password must be at least 8 characters"
                ]
            },
            {
                "id": "F002",
                "name": "Transaction Processing",
                "description": "Handle blockchain transactions",
                "priority": "high",
                "acceptance_criteria": [
                    "Transactions are validated before processing",
                    "Transactions are recorded on blockchain",
                    "Users receive transaction confirmations"
                ]
            },
            {
                "id": "F003",
                "name": "Block Explorer",
                "description": "View blockchain blocks and transactions",
                "priority": "medium",
                "acceptance_criteria": [
                    "Display blocks in chronological order",
                    "Show transaction details",
                    "Search functionality available"
                ]
            }
        ]
    }

    output_path = REPO_ROOT / "product_specs" / "specs.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(specs, f, indent=2)
    print(f"Generated product specs: {output_path}")

def generate_references():
    """Generate reference documentation."""
    refs = {
        "title": "References",
        "generated_at": datetime.utcnow().isoformat(),
        "external_docs": [
            {"name": "FastAPI Documentation", "url": "https://fastapi.tiangolo.com/"},
            {"name": "Web3.py Documentation", "url": "https://web3py.readthedocs.io/"},
            {"name": "React Documentation", "url": "https://reactjs.org/docs/getting-started.html"}
        ],
        "internal_docs": [
            {"name": "API Reference", "path": "docs/api_reference.md"},
            {"name": "Deployment Guide", "path": "docs/deployment.md"},
            {"name": "Contributing Guidelines", "path": "CONTRIBUTING.md"}
        ],
        "standards": [
            {"name": "PEP 8", "description": "Python style guide"},
            {"name": "OpenAPI 3.0", "description": "API specification standard"},
            {"name": "ERC-20", "description": "Token standard"}
        ]
    }

    output_path = REPO_ROOT / "references" / "references.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(refs, f, indent=2)
    print(f"Generated references: {output_path}")

def generate_inventory():
    """Generate repository inventory."""
    inventory = {
        "title": "Repository Inventory",
        "generated_at": datetime.utcnow().isoformat(),
        "directories": [],
        "files": []
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip hidden directories and common build artifacts
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv']]

        rel_path = os.path.relpath(root, REPO_ROOT)
        if rel_path != '.':
            inventory["directories"].append({
                "path": rel_path,
                "file_count": len(files)
            })

        for file in files:
            file_path = os.path.join(rel_path, file)
            if not file.startswith('.'):
                inventory["files"].append({
                    "path": file_path,
                    "size": os.path.getsize(os.path.join(root, file))
                })

    output_path = REPO_ROOT / "generated_inventory" / "inventory.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(inventory, f, indent=2)
    print(f"Generated inventory: {output_path}")

def generate_exec_plans():
    """Generate execution plans."""
    exec_plans = {
        "title": "Execution Plans",
        "generated_at": datetime.utcnow().isoformat(),
        "sprints": [
            {
                "id": "S001",
                "name": "Sprint 1: Foundation",
                "duration": "2 weeks",
                "tasks": [
                    {"id": "T001", "description": "Set up CI/CD pipeline", "assignee": "devops"},
                    {"id": "T002", "description": "Implement user authentication", "assignee": "backend"},
                    {"id": "T003", "description": "Create landing page", "assignee": "frontend"}
                ],
                "start_date": "2024-01-01",
                "end_date": "2024-01-14"
            },
            {
                "id": "S002",
                "name": "Sprint 2: Core Features",
                "duration": "2 weeks",
                "tasks": [
                    {"id": "T004", "description": "Implement transaction API", "assignee": "backend"},
                    {"id": "T005", "description": "Integrate smart contracts", "assignee": "blockchain"},
                    {"id": "T006", "description": "Build dashboard UI", "assignee": "frontend"}
                ],
                "start_date": "2024-01-15",
                "end_date": "2024-01-28"
            }
        ]
    }

    output_path = REPO_ROOT / "exec_plans" / "exec_plans.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(exec_plans, f, indent=2)
    print(f"Generated exec plans: {output_path}")

def main():
    """Main function to generate all documentation."""
    print("Generating AI collaboration documentation...")

    generate_architecture_doc()
    generate_plans_doc()
    generate_design_docs()
    generate_product_specs()
    generate_references()
    generate_inventory()
    generate_exec_plans()

    print("\nAll documentation generated successfully!")

if __name__ == "__main__":
    main()
