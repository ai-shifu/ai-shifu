"""Build the pre-raw host prompt shape for historical-session regressions."""

from typing import Any

from markdownflow.engine.script import (
    ScriptBundle,
    collected_names,
    render_memory_section,
    substitute_variables,
)


def expanded_initial_prompt(
    bundle: ScriptBundle, memory: dict[str, Any], *, memory_limit: int | None = None
) -> str:
    """Reproduce the prior prompt writer without depending on the current writer."""
    collected = collected_names(bundle.script)
    sections = [
        render_memory_section(bundle, memory, limit=memory_limit)[0],
        "<script>\n"
        + substitute_variables(
            bundle.script, memory, collected=collected, unavailable=True
        )
        + "\n</script>",
    ]
    if bundle.constraints:
        sections.append(
            "<constraints>\n"
            + substitute_variables(
                bundle.constraints, memory, collected=collected, unavailable=True
            )
            + "\n</constraints>"
        )
    sections.extend(
        f'<extra name="{name}">\n{body}\n</extra>'
        for name, body in bundle.extras.items()
    )
    return "\n\n".join(sections)
