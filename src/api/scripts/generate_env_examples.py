#!/usr/bin/env python3
"""
Generate the .env.example.full file for AI-Shifu configuration.

Usage:
    python scripts/generate_env_examples.py

The generated file will be created in the docker directory.
"""

import sys
from pathlib import Path

# Add parent directory to path to import from flaskr
sys.path.insert(0, str(Path(__file__).parent.parent))

from flaskr.common.config import ENV_VARS, EnhancedConfig  # noqa: E402


def generate_env_examples():
    """Generate the .env.example.full file."""
    # Create EnhancedConfig instance
    config = EnhancedConfig(ENV_VARS)

    # Get the output directory (docker directory)
    # Script is in src/api/scripts, docker is in docker/
    script_dir = Path(__file__).parent  # src/api/scripts
    api_dir = script_dir.parent  # src/api
    src_dir = api_dir.parent  # src
    root_dir = src_dir.parent  # project root
    output_dir = root_dir / "docker"  # docker directory

    # Make sure docker directory exists
    output_dir.mkdir(exist_ok=True)

    # Generate full configuration (all variables)
    full_file = output_dir / ".env.example.full"
    full_content = config.export_env_example_filtered(filter_type="all")

    # Write full configuration
    with open(full_file, "w", encoding="utf-8") as f:
        f.write(full_content)
    print(f"✅ Generated full configuration: {full_file}")

    # Print summary
    print("\n📊 Summary:")

    # Count variables
    required_count = sum(1 for env_var in ENV_VARS.values() if env_var.required)
    total_count = len(ENV_VARS)
    optional_count = total_count - required_count

    print(f"  - Total variables: {total_count}")
    print(f"  - Required variables: {required_count}")
    print(f"  - Optional variables: {optional_count}")

    # List required variables
    print("\n📌 Required variables that must be configured:")
    required_vars = sorted(
        [(name, var) for name, var in ENV_VARS.items() if var.required],
        key=lambda x: (x[1].group, x[0]),
    )

    current_group = None
    for var_name, env_var in required_vars:
        if env_var.group != current_group:
            current_group = env_var.group
            print(f"\n  [{current_group.upper()}]")
        print(f"    - {var_name}")
        if env_var.description:
            # Print first line of description
            desc_lines = env_var.description.strip().split("\n")
            print(f"      {desc_lines[0]}")

    print("\n📝 Instructions:")
    print(
        "  1. Copy docker/.env.example.full to docker/.env (or the root .env you prefer)"
    )
    print("  2. Configure at least one LLM API key and other required secrets")
    print("  3. Keep .env files out of version control")

    print("\n✨ Environment configuration files generated successfully!")


if __name__ == "__main__":
    try:
        generate_env_examples()
    except Exception as e:
        print(f"❌ Error generating environment examples: {e}", file=sys.stderr)
        sys.exit(1)
