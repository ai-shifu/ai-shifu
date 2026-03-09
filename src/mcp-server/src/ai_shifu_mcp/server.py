"""AI-Shifu MCP Server — manage courses from Claude.

Exposes AI-Shifu's course-authoring REST API as MCP tools so that
Claude Code / Claude Desktop users can create, edit, and publish
interactive AI courses through natural language.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ai_shifu_mcp.api_client import AiShifuClient


# ── Lifespan ─────────────────────────────────────────


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize the shared HTTP client on startup, close on shutdown."""
    client = AiShifuClient()
    await client.start()
    yield {"client": client}
    await client.close()


mcp = FastMCP(
    "AI-Shifu",
    instructions=(
        "AI-Shifu course management server. Use these tools to create, "
        "edit, and publish interactive AI courses. Every course is identified "
        "by a 'bid' (business identifier) returned on creation. Outlines "
        "form a tree: chapters contain sections (lessons). MDFlow is the "
        "Markdown-based format used for lesson content."
    ),
    lifespan=lifespan,
)


def _client(ctx: Context) -> AiShifuClient:
    """Shortcut to retrieve the shared HTTP client from lifespan context."""
    return ctx.lifespan_context["client"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Course Management (4 tools)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool
async def list_courses(
    ctx: Context,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List all courses owned by the current user.

    Returns a paginated list with course name, description, and bid
    (business identifier) for each course. Use the bid in subsequent
    tool calls to operate on a specific course.

    Args:
        page: Page number (starts from 1).
        page_size: Number of courses per page (max 100).
    """
    return await _client(ctx).get(
        "/api/shifu/shifus",
        params={
            "page_index": page,
            "page_size": page_size,
            "is_favorite": False,
        },
    )


@mcp.tool
async def create_course(
    ctx: Context,
    name: str,
    description: str = "",
) -> dict:
    """Create a new course.

    Returns the created course object including its bid, which is needed
    for all subsequent operations (outlines, content, publishing).

    Args:
        name: Course name (max 100 characters).
        description: Optional course description.
    """
    return await _client(ctx).put(
        "/api/shifu/shifus",
        json={"name": name, "description": description},
    )


@mcp.tool
async def get_course_detail(
    ctx: Context,
    course_bid: str,
) -> dict:
    """Get complete details of a course.

    Returns the full course configuration including name, description,
    system prompt, model settings (model name, temperature), TTS settings,
    and publishing status.

    Args:
        course_bid: The business identifier of the course.
    """
    return await _client(ctx).get(f"/api/shifu/shifus/{course_bid}/detail")


@mcp.tool
async def update_course_detail(
    ctx: Context,
    course_bid: str,
    name: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """Update course settings.

    Only the provided fields will be updated; omitted fields remain
    unchanged. To clear a field, pass an empty string.

    Args:
        course_bid: The business identifier of the course.
        name: New course name.
        description: New course description.
        system_prompt: System prompt that guides the AI's behavior.
        model: LLM model identifier (e.g. "gpt-4", "deepseek-chat").
        temperature: Model temperature (0.0 - 2.0).
        keywords: List of keywords/tags for the course.
    """
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if model is not None:
        payload["model"] = model
    if temperature is not None:
        payload["temperature"] = temperature
    if keywords is not None:
        payload["keywords"] = keywords
    return await _client(ctx).post(
        f"/api/shifu/shifus/{course_bid}/detail",
        json=payload,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Outline Management (5 tools)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool
async def get_outlines(
    ctx: Context,
    course_bid: str,
) -> list:
    """Get the full chapter/section tree of a course.

    Returns a hierarchical list where each node has a bid, name,
    position, type, and children array. Top-level nodes are chapters;
    their children are sections (lessons).

    Args:
        course_bid: The business identifier of the course.
    """
    return await _client(ctx).get(f"/api/shifu/shifus/{course_bid}/outlines")


@mcp.tool
async def create_outline(
    ctx: Context,
    course_bid: str,
    name: str,
    parent_bid: str | None = None,
    description: str = "",
    outline_type: str = "guest",
    system_prompt: str | None = None,
    is_hidden: bool = False,
    index: int | None = None,
) -> dict:
    """Create a new chapter or section in a course.

    To create a top-level chapter, omit parent_bid.
    To create a section under a chapter, provide the chapter's bid
    as parent_bid.

    Args:
        course_bid: The business identifier of the course.
        name: Title of the chapter or section.
        parent_bid: Bid of the parent chapter (omit for top-level).
        description: Optional description.
        outline_type: Access type — "guest" (default), "trial", or "normal".
        system_prompt: Optional system prompt override for this section.
        is_hidden: Whether this section is hidden from learners.
        index: Position index (0-based). Appended to end if omitted.
    """
    payload: dict[str, Any] = {"name": name}
    if parent_bid is not None:
        payload["parent_bid"] = parent_bid
    if description:
        payload["description"] = description
    if outline_type != "guest":
        payload["type"] = outline_type
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if is_hidden:
        payload["is_hidden"] = is_hidden
    if index is not None:
        payload["index"] = index
    return await _client(ctx).put(
        f"/api/shifu/shifus/{course_bid}/outlines",
        json=payload,
    )


@mcp.tool
async def update_outline(
    ctx: Context,
    course_bid: str,
    outline_bid: str,
    name: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    outline_type: str | None = None,
    is_hidden: bool | None = None,
    index: int | None = None,
) -> dict:
    """Update an existing chapter or section.

    Only the provided fields will be updated.

    Args:
        course_bid: The business identifier of the course.
        outline_bid: The business identifier of the outline node.
        name: New title.
        description: New description.
        system_prompt: New system prompt override.
        outline_type: New access type — "guest", "trial", or "normal".
        is_hidden: Whether to hide this section from learners.
        index: New position index.
    """
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if outline_type is not None:
        payload["type"] = outline_type
    if is_hidden is not None:
        payload["is_hidden"] = is_hidden
    if index is not None:
        payload["index"] = index
    return await _client(ctx).post(
        f"/api/shifu/shifus/{course_bid}/outlines/{outline_bid}",
        json=payload,
    )


@mcp.tool
async def delete_outline(
    ctx: Context,
    course_bid: str,
    outline_bid: str,
) -> Any:
    """Delete a chapter or section from a course.

    Warning: This also deletes all child sections and their content.
    This action cannot be undone.

    Args:
        course_bid: The business identifier of the course.
        outline_bid: The business identifier of the outline to delete.
    """
    return await _client(ctx).delete(
        f"/api/shifu/shifus/{course_bid}/outlines/{outline_bid}",
    )


@mcp.tool
async def reorder_outlines(
    ctx: Context,
    course_bid: str,
    outlines: list[dict],
) -> list:
    """Reorder chapters and sections within a course.

    Provide the full ordering as a list of objects, each containing
    the outline bid and its new position string.

    Args:
        course_bid: The business identifier of the course.
        outlines: List of {"bid": "...", "position": "01"} objects
            defining the new order. Position strings are zero-padded
            two-digit numbers (e.g. "01", "02").
    """
    return await _client(ctx).patch(
        f"/api/shifu/shifus/{course_bid}/outlines/reorder",
        json={"outlines": outlines},
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Content Management (2 tools)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool
async def get_lesson_content(
    ctx: Context,
    course_bid: str,
    outline_bid: str,
) -> Any:
    """Get the MDFlow content of a lesson (section).

    Returns the raw MDFlow (Markdown Flow) string that defines the
    interactive teaching content for this section.

    Args:
        course_bid: The business identifier of the course.
        outline_bid: The business identifier of the section.
    """
    return await _client(ctx).get(
        f"/api/shifu/shifus/{course_bid}/outlines/{outline_bid}/mdflow",
    )


@mcp.tool
async def save_lesson_content(
    ctx: Context,
    course_bid: str,
    outline_bid: str,
    content: str,
) -> Any:
    """Save MDFlow content for a lesson (section).

    Overwrites the existing content with the provided MDFlow string.
    MDFlow is a Markdown-based format that supports interactive blocks
    like buttons, inputs, options, and AI-generated content sections.

    Args:
        course_bid: The business identifier of the course.
        outline_bid: The business identifier of the section.
        content: The MDFlow content string to save.
    """
    return await _client(ctx).post(
        f"/api/shifu/shifus/{course_bid}/outlines/{outline_bid}/mdflow",
        json={"data": content},
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Preview & Publish (2 tools)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool
async def preview_course(
    ctx: Context,
    course_bid: str,
) -> Any:
    """Generate a preview link for a course.

    Returns a URL that can be opened in a browser to preview the
    course as a learner would experience it.

    Args:
        course_bid: The business identifier of the course.
    """
    return await _client(ctx).post(
        f"/api/shifu/shifus/{course_bid}/preview",
        json={},
    )


@mcp.tool
async def publish_course(
    ctx: Context,
    course_bid: str,
) -> Any:
    """Publish a course to make it available to learners.

    Once published, the course becomes accessible via its public URL.
    Returns the published URL.

    Args:
        course_bid: The business identifier of the course.
    """
    return await _client(ctx).post(f"/api/shifu/shifus/{course_bid}/publish")
