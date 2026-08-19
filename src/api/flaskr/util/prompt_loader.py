from pathlib import Path


def load_prompt_template(template_name: str) -> str:
    """Load the specified prompt template file

    Args:
        template_name: Template file name (without .md extension)

    Returns:
        Template file content

    Raises:
        FileNotFoundError: When template file does not exist

    """
    # Get the directory of current file
    current_dir = str(Path(__file__).resolve().parent)
    # Build prompts directory path
    prompts_dir = str(Path(current_dir) / "../../prompts")

    # Ensure filename has .md extension
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"

    # Build complete file path
    template_path = str(Path(prompts_dir) / template_name)

    # Check if file exists
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Prompt template file not found: {template_path}")

    # Read file content
    try:
        with Path(template_path).open(encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise OSError(
            f"Failed to read prompt template file {template_path}: {e!s}"
        ) from e
