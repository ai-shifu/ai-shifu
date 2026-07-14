"""Flask CLI entrypoints for offline shifu repair work."""

from __future__ import annotations

import json

import click

from .repair import repair_shifu_outline_structure


def register_shifu_commands(console, app) -> None:
    @console.group(name="shifu")
    def shifu_group() -> None:
        """Shifu maintenance commands for offline repair work."""

    @shifu_group.command(name="repair-outline-structure")
    @click.option(
        "--shifu-bid",
        "shifu_bids",
        multiple=True,
        help="Restrict repair to one or more shifu business identifiers.",
    )
    @click.option(
        "--user-bid",
        default=None,
        help="Operator user bid recorded on appended repair rows.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Preview the repair payload without writing data.",
    )
    def repair_outline_structure_command(
        shifu_bids: tuple[str, ...],
        user_bid: str | None,
        dry_run: bool,
    ) -> None:
        """Repair broken draft outline parent/position state and rebuild struct."""
        if not dry_run and not user_bid:
            raise click.ClickException(
                "Pass --user-bid for non-dry-run outline repair."
            )

        payload = repair_shifu_outline_structure(
            app,
            user_bid=user_bid,
            shifu_bids=list(shifu_bids) or None,
            dry_run=dry_run,
        ).to_payload()
        click.echo(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
