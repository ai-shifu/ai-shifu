import os


def load_prompt_template(template_name: str) -> str:
    """
    Load the specified prompt template file

    Args:
        template_name: Template file name (without .md extension)

    Returns:
        Template file content

    Raises:
        FileNotFoundError: When template file does not exist
    """
    # Get the directory of current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Build prompts directory path
    prompts_dir = os.path.join(current_dir, "../../prompts")

    # Ensure filename has .md extension
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"

    # Build complete file path
    template_path = os.path.join(prompts_dir, template_name)

    # Check if file exists
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Prompt template file not found: {template_path}")

    # Read file content
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"Failed to read prompt template file {template_path}: {str(e)}")
