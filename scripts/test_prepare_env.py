# ruff: noqa: INP001 -- These tests exercise a standalone repository script.
"""Exercise first-install persistence and failure recovery without real secrets."""

from __future__ import annotations

import concurrent.futures
import contextlib
import io
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import prepare_env
import pytest


@pytest.fixture
def installation(tmp_path: Path) -> tuple[Path, Path]:
    template = tmp_path / "template"
    template.write_text('# First installation\nSECRET_KEY=""\nOTHER="unchanged"\n')
    return tmp_path / ".env", template


def _run_installer(output: Path, template: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("SECRET_KEY", None)
    return subprocess.run(
        [
            sys.executable,
            str(Path(prepare_env.__file__)),
            "--output",
            str(output),
            "--template",
            str(template),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_new_installations_use_independent_private_secure_keys(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    assert prepare_env.prepare_env(output, template, environ={})
    _, key = prepare_env._key_assignment(output.read_text())
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", key)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_text().endswith('OTHER="unchanged"\n')
    second = output.with_name("second.env")
    assert prepare_env.prepare_env(second, template, environ={})
    assert prepare_env._key_assignment(second.read_text())[1] != key


def test_generation_requests_32_cryptographically_random_bytes(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    output, template = installation
    requested = []

    def token_urlsafe(size: int) -> str:
        requested.append(size)
        return "fixture-generated-value"

    monkeypatch.setattr(prepare_env.secrets, "token_urlsafe", token_urlsafe)
    prepare_env.prepare_env(output, template, environ={})
    assert requested == [32]


def test_unsupported_platform_fails_before_creating_configuration(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    output, template = installation
    with monkeypatch.context() as platform:
        platform.setattr(prepare_env.os, "name", "nt")
        with pytest.raises(prepare_env.PreparationError, match="POSIX host"):
            prepare_env.prepare_env(output, template, environ={})
    assert not output.exists()


def test_private_config_remains_owner_readable_under_restrictive_umask(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    previous_umask = os.umask(0o777)
    try:
        prepare_env.prepare_env(output, template, environ={})
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert prepare_env._key_assignment(output.read_text())[1]


def test_restart_and_upgrade_reuse_original_file(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    first = _run_installer(output, template)
    assert first.returncode == 0, first.stderr
    original = output.read_bytes()
    original_mode = output.stat().st_mode
    # Simulate a changed or absent template during an upgrade.
    template.unlink()
    second = _run_installer(output, template)
    assert second.returncode == 0, second.stderr
    assert output.read_bytes() == original
    assert output.stat().st_mode == original_mode
    key = prepare_env._key_assignment(original.decode())[1]
    assert key not in first.stdout + first.stderr + second.stdout + second.stderr


@pytest.mark.parametrize(
    "key", ["my-explicit-key", "!@#$%^&*()_+-=[]{}|;:,.<>?/~`", "quoted'key"]
)
def test_explicit_environment_value_wins_without_generation(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    output, template = installation

    def unexpected_random(_size: int) -> str:
        pytest.fail("An explicit key must not be replaced with a random key")

    monkeypatch.setattr(prepare_env.secrets, "token_urlsafe", unexpected_random)
    prepare_env.prepare_env(output, template, environ={"SECRET_KEY": f"  {key}  "})
    assert prepare_env._key_assignment(output.read_text())[1] == key


@pytest.mark.parametrize(
    "key", ["", "   ", "${MISSING}", "line\nbreak", "line\rbreak", "back\\slash"]
)
def test_invalid_explicit_environment_fails_without_output_or_disclosure(
    installation: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
) -> None:
    output, template = installation
    monkeypatch.setenv("SECRET_KEY", key)
    assert prepare_env.main(["--output", str(output), "--template", str(template)]) == 1
    captured = capsys.readouterr()
    if key.strip():
        assert key not in captured.out + captured.err
    assert not output.exists()
    assert not list(output.parent.glob(".*.init-*.tmp"))


@pytest.mark.parametrize(
    "assignment",
    [
        'SECRET_KEY="ai-shifu"',
        "SECRET_KEY=existing-value # retained comment",
        "export SECRET_KEY = 'existing # value' # comment",
        'SECRET_KEY="existing\\"quote"',
        "SECRET_KEY='existing\\'quote'",
        "SECRET_KEY = existing-value-with-#-hash",
    ],
)
def test_existing_explicit_and_legacy_values_never_rotate(
    installation: tuple[Path, Path], assignment: str
) -> None:
    output, template = installation
    original = f"# Custom settings\n{assignment}\nOTHER=retained\n".encode()
    output.write_bytes(original)
    output.chmod(0o400)
    assert not prepare_env.prepare_env(
        output, template, environ={"SECRET_KEY": "different-value"}
    )
    assert output.read_bytes() == original
    assert stat.S_IMODE(output.stat().st_mode) == 0o400


@pytest.mark.parametrize(
    "content",
    [
        "OTHER=value\n",
        "SECRET_KEY=\n",
        'SECRET_KEY="   "\n',
        "SECRET_KEY=one\nSECRET_KEY=two\n",
        "SECRET_KEY\n",
        'SECRET_KEY="unfinished\n',
        "SECRET_KEY='secret-value' trailing\n",
        "SECRET_KEY=${LOST_ORIGINAL_KEY}\n",
        "SECRET_KEY=secret'broken\n",
    ],
)
def test_invalid_existing_configuration_is_never_repaired_or_overwritten(
    installation: tuple[Path, Path], content: str
) -> None:
    output, template = installation
    output.write_text(content)
    with pytest.raises(prepare_env.PreparationError):
        prepare_env.prepare_env(output, template, environ={})
    assert output.read_text() == content
    assert not list(output.parent.glob(".*.init-*.tmp"))


@pytest.mark.parametrize(
    "content",
    ["OTHER=value\n", "SECRET_KEY=public-default\n", "SECRET_KEY=\nSECRET_KEY=\n"],
)
def test_template_must_have_exactly_one_blank_key(
    installation: tuple[Path, Path], content: str
) -> None:
    output, template = installation
    template.write_text(content)
    with pytest.raises(prepare_env.PreparationError):
        prepare_env.prepare_env(output, template, environ={})
    assert not output.exists()


def test_multiple_processes_publish_one_complete_shared_configuration(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = list(
            executor.map(lambda _: _run_installer(output, template), range(24))
        )
    assert all(result.returncode == 0 for result in results)
    assert sum("Created private" in result.stdout for result in results) == 1
    original = output.read_bytes()
    key = prepare_env._key_assignment(original.decode())[1]
    assert len(key) == 43
    assert original.endswith(b'OTHER="unchanged"\n')
    assert all(key not in result.stdout + result.stderr for result in results)
    assert not list(output.parent.glob(".*.init-*.tmp"))


@pytest.mark.parametrize("dangling", [False, True])
def test_symlinks_are_never_followed(
    installation: tuple[Path, Path], dangling: bool
) -> None:
    output, template = installation
    target = output.with_name("linked.env")
    if not dangling:
        target.write_text("SECRET_KEY=original\n")
    output.symlink_to(target)
    with pytest.raises(prepare_env.PreparationError, match="symbolic link"):
        prepare_env.prepare_env(output, template, environ={})
    assert output.is_symlink()
    if not dangling:
        assert target.read_text() == "SECRET_KEY=original\n"


def test_nonregular_file_is_rejected_without_hanging(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    os.mkfifo(output)
    with pytest.raises(prepare_env.PreparationError, match="regular file"):
        prepare_env.prepare_env(output, template, environ={})
    assert stat.S_ISFIFO(output.stat().st_mode)


def test_missing_output_directory_is_not_created(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    output = output.parent / "missing" / ".env"
    with pytest.raises(prepare_env.PreparationError, match="permissions"):
        prepare_env.prepare_env(output, template, environ={})
    assert not output.parent.exists()


def test_readonly_directory_fails_without_publishing(
    installation: tuple[Path, Path],
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")
    output, template = installation
    output.parent.chmod(0o500)
    try:
        with pytest.raises(prepare_env.PreparationError, match="permissions"):
            prepare_env.prepare_env(output, template, environ={})
        assert not output.exists()
    finally:
        output.parent.chmod(0o700)


def test_unreadable_existing_file_is_not_replaced(
    installation: tuple[Path, Path],
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses file permissions")
    output, template = installation
    output.write_text("SECRET_KEY=original\n")
    output.chmod(0)
    try:
        with pytest.raises(prepare_env.PreparationError, match="permissions"):
            prepare_env.prepare_env(output, template, environ={})
    finally:
        output.chmod(0o600)
    assert output.read_text() == "SECRET_KEY=original\n"


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_failure_before_publication_leaves_no_partial_configuration(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    output, template = installation

    def failure(*_args: object, **_kwargs: object) -> None:
        message = "failure containing confidential-fixture-data"
        raise OSError(message)

    with monkeypatch.context() as patch:
        patch.setattr(prepare_env.os, operation, failure)
        with pytest.raises(
            prepare_env.PreparationError, match="retry against the same path"
        ) as caught:
            prepare_env.prepare_env(output, template, environ={})
        assert "confidential-fixture-data" not in str(caught.value)
    assert not output.exists()
    assert not list(output.parent.glob(".*.init-*.tmp"))
    assert prepare_env.prepare_env(output, template, environ={})


def test_directory_sync_failure_preserves_published_key_for_recovery(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    output, template = installation

    def failure(_directory: Path) -> None:
        message = "cannot sync directory"
        raise OSError(message)

    with monkeypatch.context() as patch:
        patch.setattr(prepare_env, "_sync_directory", failure)
        with pytest.raises(prepare_env.PreparationError, match="do not delete"):
            prepare_env.prepare_env(output, template, environ={})
    original = output.read_bytes()
    assert not prepare_env.prepare_env(output, template, environ={})
    assert output.read_bytes() == original


def test_crash_before_publication_recovers_without_using_partial_file(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    code = """
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[3])))
import prepare_env
def crash(*args, **kwargs):
    os._exit(19)
prepare_env.os.link = crash
prepare_env.prepare_env(Path(sys.argv[1]), Path(sys.argv[2]), environ={})
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(output),
            str(template),
            str(Path(prepare_env.__file__).parent),
        ],
        check=False,
    )
    assert crashed.returncode == 19
    assert not output.exists()
    leftovers = list(output.parent.glob(".*.init-*.tmp"))
    assert len(leftovers) == 1
    assert stat.S_IMODE(leftovers[0].stat().st_mode) == 0o600
    assert prepare_env.prepare_env(output, template, environ={})
    assert prepare_env._key_assignment(output.read_text())[1]


def test_crash_after_publication_keeps_key_on_restart(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    code = """
import os
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
import prepare_env
def crash(directory):
    os._exit(19)
prepare_env._sync_directory = crash
prepare_env.prepare_env(Path(sys.argv[1]), Path(sys.argv[2]), environ={})
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(output),
            str(template),
            str(Path(prepare_env.__file__).parent),
        ],
        check=False,
    )
    assert crashed.returncode == 19
    original = output.read_bytes()
    assert prepare_env._key_assignment(original.decode())[1]
    assert not prepare_env.prepare_env(output, template, environ={})
    assert output.read_bytes() == original


def test_durable_publication_syncs_contents_before_link_and_directory_after(
    installation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    output, template = installation
    operations = []
    original_fsync = os.fsync
    original_link = os.link

    def track_fsync(descriptor: int) -> None:
        operations.append(
            "directory_sync"
            if stat.S_ISDIR(os.fstat(descriptor).st_mode)
            else "file_sync"
        )
        original_fsync(descriptor)

    def track_link(source: Path, destination: Path) -> None:
        operations.append("publish")
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        assert prepare_env._key_assignment(source.read_text())[1]
        assert not destination.exists()
        original_link(source, destination)

    monkeypatch.setattr(prepare_env.os, "fsync", track_fsync)
    monkeypatch.setattr(prepare_env.os, "link", track_link)
    prepare_env.prepare_env(output, template, environ={})
    assert operations == ["file_sync", "publish", "directory_sync"]


def test_cli_errors_do_not_echo_existing_secret(
    installation: tuple[Path, Path],
) -> None:
    output, template = installation
    output.write_text("SECRET_KEY=confidential-value\nSECRET_KEY=other-value\n")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        assert (
            prepare_env.main(["--output", str(output), "--template", str(template)])
            == 1
        )
    assert "confidential-value" not in stderr.getvalue()
    assert "other-value" not in stderr.getvalue()
