"""Reject the retired markdown-flow package in application code."""

import markdown_flow.escaping


def legacy_escaping() -> object:
    return markdown_flow.escaping
