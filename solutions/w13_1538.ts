# scripts/generate_ai_collab_docs.py
#!/usr/bin/env python3
"""Generate AI collaboration documentation from repository structure."""

import os
import json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent

STRUCTURE = {
    "architecture": ["system_overview.md", "data_flow.md", "component_diagram.md"],
    "plans": ["sprint_plan.md", "roadmap.md", "milestones.md"],
    "design_docs": ["api_design.md", "database_schema.md", "ui_design.md"],
    "product_specs": ["requirements.md", "user_stories.md", "acceptance_criteria.md"],
    "references": ["glossary.md", "links.md", "standards.md"],
    "generated_inventory": ["component_inventory.json", "dependency_graph.json"],
    "exec_plans": ["implementation_plan.md", "testing_strategy.md", "deployment_plan.md"]
}

def create_directory_structure():
    """Create the directory structure for AI collaboration docs."""
    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    for category, files in STRUCTURE.items():
        category_dir = docs_dir / category
        category_dir.mkdir(exist_ok=True)
        
        for file_name in files:
            file_path = category_dir / file_name
            if not file_path.exists():
                file_path.write_text(f"# {file_name.replace('_', ' ').replace('.md', '').title()}\n\n*Auto-generated on {datetime.now().isoformat()}*\n")
    
    return docs_dir

def generate_manifest():
    """Generate a manifest file for the documentation structure."""
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "version": "1.0.0",
        "structure": STRUCTURE
    }
    
    manifest_path = REPO_ROOT / "docs" / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return manifest_path

def main():
    print("Generating AI collaboration documentation...")
    docs_dir = create_directory_structure()
    manifest_path = generate_manifest()
    print(f"Documentation structure created at: {docs_dir}")
    print(f"Manifest generated at: {manifest_path}")
    print("Done!")

if __name__ == "__main__":
    main()
