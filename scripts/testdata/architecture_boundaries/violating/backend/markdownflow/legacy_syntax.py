"""Reject the retired markdown-flow package inside the engine library."""

from markdown_flow import InteractionParser


def legacy_parser() -> object:
    return InteractionParser()
