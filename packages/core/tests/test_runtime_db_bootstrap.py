from __future__ import annotations

import importlib.util
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "bootstrap_runtime_db_credentials.py"
_SPEC = importlib.util.spec_from_file_location("bootstrap_runtime_db_credentials", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
bootstrap = _MODULE.bootstrap


def test_bootstrap_separates_owner_and_runtime_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    migration_path = tmp_path / "private" / "migration.env"
    owner_url = "postgresql+asyncpg://bulls:owner-secret@127.0.0.1:5432/bulls?ssl=disable"
    env_path.write_text(f"ENV=prod\nDATABASE_URL={owner_url}\nREDIS_URL=redis://local\n")
    env_path.chmod(0o640)
    monkeypatch.setattr(_MODULE.secrets, "token_urlsafe", lambda _length: "runtime_secret_-123")

    bootstrap(env_path, migration_path)

    runtime_line = next(
        line for line in env_path.read_text().splitlines() if line.startswith("DATABASE_URL=")
    )
    runtime_url = urlsplit(runtime_line.split("=", 1)[1])
    assert runtime_url.username == "bulls_app"
    assert unquote(runtime_url.password or "") == "runtime_secret_-123"
    assert runtime_url.hostname == "127.0.0.1"
    assert runtime_url.port == 5432
    assert runtime_url.query == "ssl=disable"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o640

    migration_values = migration_path.read_text()
    assert f"MIGRATION_DATABASE_URL={owner_url}" in migration_values
    assert "APP_DATABASE_PASSWORD=runtime_secret_-123" in migration_values
    assert stat.S_IMODE(migration_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(migration_path.parent.stat().st_mode) == 0o700


def test_bootstrap_refuses_to_overwrite_existing_secret_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    migration_path = tmp_path / "migration.env"
    env_path.write_text("DATABASE_URL=postgresql://owner:secret@localhost/db\n")
    migration_path.write_text("existing\n")

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        bootstrap(env_path, migration_path)

    assert migration_path.read_text() == "existing\n"
