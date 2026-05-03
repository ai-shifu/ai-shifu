# scripts/generate_ai_collab_docs.py
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def generate_architecture_docs():
    """Generate architecture documentation from repository structure"""
    docs = {
        "architecture": {
            "name": "Agent-First Repository",
            "version": "1.0.0",
            "components": [],
            "data_flow": []
        }
    }

    # Scan for key directories and files
    for root, dirs, files in os.walk(REPO_ROOT):
        rel_path = Path(root).relative_to(REPO_ROOT)

        # Identify components
        if "src" in dirs or "lib" in dirs:
            docs["architecture"]["components"].append({
                "path": str(rel_path),
                "type": "source",
                "language": detect_language(root)
            })

        # Identify config files
        for f in files:
            if f.endswith((".json", ".yaml", ".yml", ".toml", ".cfg")):
                docs["architecture"]["components"].append({
                    "path": str(rel_path / f),
                    "type": "configuration"
                })

    return docs

def detect_language(path):
    """Detect programming language from directory contents"""
    extensions = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust"
    }

    for f in os.listdir(path):
        ext = Path(f).suffix
        if ext in extensions:
            return extensions[ext]
    return "Unknown"

def generate_plans():
    """Generate execution plans from repository structure"""
    plans = {
        "execution_plans": {
            "phases": [
                {
                    "name": "Phase 1: Foundation",
                    "tasks": [
                        "Setup repository harness",
                        "Configure CI/CD pipeline",
                        "Add smoke tests"
                    ]
                },
                {
                    "name": "Phase 2: Core Development",
                    "tasks": [
                        "Implement agent-first architecture",
                        "Add backend request-id diagnostics",
                        "Create knowledge index"
                    ]
                },
                {
                    "name": "Phase 3: Testing & Validation",
                    "tasks": [
                        "Add Playwright smoke coverage",
                        "Validate repository structure",
                        "Generate documentation"
                    ]
                }
            ]
        }
    }
    return plans

def generate_design_docs():
    """Generate design documentation"""
    return {
        "design": {
            "principles": [
                "Agent-first architecture",
                "Modular and extensible",
                "Test-driven development",
                "Continuous integration"
            ],
            "patterns": [
                "Repository pattern",
                "Service layer",
                "Event-driven communication"
            ]
        }
    }

def generate_product_specs():
    """Generate product specifications"""
    return {
        "product_specs": {
            "features": [
                {
                    "name": "Agent-First Harness",
                    "description": "Unified repository harness for AI agents",
                    "priority": "high"
                },
                {
                    "name": "Knowledge Index",
                    "description": "Automated knowledge base generation",
                    "priority": "high"
                },
                {
                    "name": "Smoke Testing",
                    "description": "Playwright-based smoke tests",
                    "priority": "medium"
                }
            ]
        }
    }

def generate_references():
    """Generate reference documentation"""
    return {
        "references": {
            "standards": [
                "PEP 8 - Python Style Guide",
                "Semantic Versioning 2.0.0",
                "Conventional Commits 1.0.0"
            ],
            "tools": [
                "Playwright for E2E testing",
                "Pytest for unit testing",
                "Black for code formatting"
            ]
        }
    }

def generate_inventory():
    """Generate repository inventory"""
    inventory = {
        "inventory": {
            "directories": [],
            "files": [],
            "total_size": 0
        }
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        rel_path = Path(root).relative_to(REPO_ROOT)

        # Skip hidden directories and __pycache__
        if any(part.startswith('.') or part == '__pycache__' for part in rel_path.parts):
            continue

        inventory["inventory"]["directories"].append(str(rel_path))

        for f in files:
            file_path = rel_path / f
            file_size = os.path.getsize(os.path.join(root, f))
            inventory["inventory"]["files"].append({
                "path": str(file_path),
                "size": file_size,
                "extension": Path(f).suffix
            })
            inventory["inventory"]["total_size"] += file_size

    return inventory

def main():
    """Main execution function"""
    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Generate all documentation
    docs = {
        "architecture": generate_architecture_docs(),
        "plans": generate_plans(),
        "design": generate_design_docs(),
        "product_specs": generate_product_specs(),
        "references": generate_references(),
        "inventory": generate_inventory()
    }

    # Write documentation files
    for doc_type, content in docs.items():
        doc_path = docs_dir / f"{doc_type}.json"
        with open(doc_path, 'w') as f:
            json.dump(content, f, indent=2)
        print(f"Generated: {doc_path}")

    # Generate index file
    index = {
        "generated_at": __import__('datetime').datetime.now().isoformat(),
        "documentation": list(docs.keys()),
        "total_docs": len(docs)
    }

    with open(docs_dir / "index.json", 'w') as f:
        json.dump(index, f, indent=2)

    print("Documentation generation complete!")

if __name__ == "__main__":
    main()
