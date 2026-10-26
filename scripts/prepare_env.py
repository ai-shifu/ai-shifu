# ruff: noqa: INP001 -- This installer is run as a standalone repository script.
"""Create a private installation .env once, without rotating an existing key.

This installer uses only the Python standard library. Run it before Compose or
the manual backend; application workers never generate their own secret keys.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class PreparationError(Exception):
    """A safe, actionable installation error which contains no secret values."""


_KEY_LINE = re.compile(r"^\s*(?:export\s+)?SECRET_KEY\b")
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?SECRET_KEY\s*=\s*(.*)$")
_ROOT = Path(__file__).resolve().parent.parent


def _literal_value(raw: str) -> str:
    """Read a single-line dotenv literal without performing interpolation."""
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] not in {"'", '"'}:
        if "'" in raw or '"' in raw:
            message = (
                "SECRET_KEY has malformed quoting. Restore its original configuration."
            )
            raise PreparationError(message)
        value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    else:
        quote = raw[0]
        decoded: list[str] = []
        index = 1
        escapes = {"\\": "\\", "'": "'"}
        if quote == '"':
            escapes.update(
                {
                    '"': '"',
                    "a": "\a",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    "v": "\v",
                }
            )
        while index < len(raw):
            character = raw[index]
            if character == quote:
                trailing = raw[index + 1 :].strip()
                if trailing and not trailing.startswith("#"):
                    break
                value = "".join(decoded).strip()
                break
            if character == "\\" and index + 1 < len(raw):
                following = raw[index + 1]
                if following in escapes:
                    decoded.append(escapes[following])
                    index += 2
                    continue
            decoded.append(character)
            index += 1
        else:
            message = (
                "SECRET_KEY has malformed quoting. Restore its original configuration."
            )
            raise PreparationError(message)
        if character != quote or (trailing and not trailing.startswith("#")):
            message = (
                "SECRET_KEY has malformed quoting. Restore its original configuration."
            )
            raise PreparationError(message)
    if "${" in value:
        message = "SECRET_KEY must be a literal value, without variable interpolation. Restore its original configuration."
        raise PreparationError(message)
    return value


def _key_assignment(content: str) -> tuple[int, str]:
    """Locate exactly one unambiguous SECRET_KEY assignment."""
    found = []
    for index, line in enumerate(content.splitlines()):
        if not _KEY_LINE.match(line):
            continue
        assignment = _ASSIGNMENT.fullmatch(line)
        if assignment is None:
            message = "SECRET_KEY has a malformed assignment. Restore its original configuration."
            raise PreparationError(message)
        found.append((index, _literal_value(assignment[1])))
    if len(found) != 1:
        message = "The configuration must contain exactly one SECRET_KEY assignment. Restore its original configuration."
        raise PreparationError(message)
    return found[0]


def _read_existing(output: Path) -> bool:
    """Validate an existing regular file without changing it or following links."""
    try:
        if output.is_symlink():
            message = (
                "The configuration path must be a regular file, not a symbolic link."
            )
            raise PreparationError(message)
        descriptor = os.open(
            output,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except FileNotFoundError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            message = "The configuration path must be a regular file."
            raise PreparationError(message)
        with os.fdopen(descriptor, encoding="utf-8") as source:
            descriptor = -1
            _, key = _key_assignment(source.read())
        if not key:
            message = "Existing SECRET_KEY is empty. Restore the original key; the installer will not replace existing configuration."
            raise PreparationError(message)
    finally:
        if descriptor != -1:
            os.close(descriptor)
    return True


def _sync_directory(directory: Path) -> None:
    """Persist directory entries before reporting successful installation."""
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _new_content(template: Path, environ: Mapping[str, str]) -> str:
    content = template.read_text(encoding="utf-8")
    index, template_key = _key_assignment(content)
    if template_key:
        message = "The installation template must leave SECRET_KEY empty; refusing to reuse a template key."
        raise PreparationError(message)
    if "SECRET_KEY" in environ:
        key = environ["SECRET_KEY"].strip()
        if not key:
            message = "Explicit SECRET_KEY is empty. Set a nonempty key or unset it before initializing a new installation."
            raise PreparationError(message)
        if "${" in key or any(character in key for character in "\\\r\n\x00"):
            message = "Explicit SECRET_KEY must be a single-line literal without backslashes or variable interpolation."
            raise PreparationError(message)
    else:
        key = secrets.token_urlsafe(32)
    # Single quotes prevent Compose's $ interpolation. Both readers support \\'
    # but disagree about \\\\, so fresh explicit values cannot contain backslashes.
    escaped = key.replace("'", "\\'")
    lines = content.splitlines(keepends=True)
    lines[index] = f"SECRET_KEY='{escaped}'\n"
    return "".join(lines)


def prepare_env(
    output: Path,
    template: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Create a durable private config, or retain an existing config unchanged.

    Return whether this invocation created the file. Never overwrite any target,
    even when another installer wins a race or the existing file is invalid.
    A publication error may leave a complete file: rerun against that same path.
    """
    if os.name != "posix":
        message = "Configuration provisioning requires a POSIX host, such as Linux, macOS, or WSL."
        raise PreparationError(message)
    temporary: Path | None = None
    try:
        if _read_existing(output):
            _sync_directory(output.parent)
            return False
        content = _new_content(template, os.environ if environ is None else environ)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.init-", suffix=".tmp", dir=output.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as destination:
            os.fchmod(destination.fileno(), 0o600)
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        try:
            # link is atomic and refuses an existing destination, unlike replace.
            os.link(temporary, output)
        except FileExistsError:
            if not _read_existing(output):
                message = "Configuration changed during installation. Retry against the same path."
                raise PreparationError(message) from None
            _sync_directory(output.parent)
            return False
        _sync_directory(output.parent)
    except (OSError, UnicodeError):
        message = (
            "Could not prepare the configuration securely. Check file and directory permissions "
            "and filesystem support for atomic hard links and fsync, then retry against the same path. "
            "A complete configuration may already exist; do not delete or replace it."
        )
        raise PreparationError(message) from None
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink()
    return True


def main(argv: list[str] | None = None) -> int:
    """Run the installation helper without disclosing configuration values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_ROOT / "docker" / ".env")
    parser.add_argument(
        "--template", type=Path, default=_ROOT / "docker" / ".env.example.full"
    )
    arguments = parser.parse_args(argv)
    try:
        created = prepare_env(arguments.output, arguments.template)
    except PreparationError as exc:
        print(f"Configuration preparation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Created private configuration. Configure the provider and model settings before startup."
        if created
        else "Existing configuration preserved. SECRET_KEY was not changed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
