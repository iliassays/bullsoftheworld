"""Move database-owner credentials out of the runtime environment on first RLS deployment.

This is a one-time release bootstrap. It reads the existing owner ``DATABASE_URL`` from the repo
``.env``, writes owner/runtime secrets to a deployment-only file with mode 0600, and atomically
replaces the runtime URL with a newly generated ``bulls_app`` credential. It never prints secrets.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

_RUNTIME_ROLE = "bulls_app"


def _env_value(lines: list[str], key: str) -> str:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value
    raise RuntimeError(f"{key} is missing from the runtime environment")


def _replace_env_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{prefix}{value}\n")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        raise RuntimeError(f"{key} is missing from the runtime environment")
    return output


def _runtime_url(owner_url: str, password: str) -> str:
    parsed = urlsplit(owner_url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    owner = unquote(parsed.username or "")
    if not owner or not parsed.password or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must include owner username, password, and host")
    if owner == _RUNTIME_ROLE:
        raise RuntimeError("runtime role is already configured but migration credentials are missing")

    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    host = f"{hostname}:{parsed.port}" if parsed.port else hostname
    netloc = f"{quote(_RUNTIME_ROLE)}:{quote(password, safe='')}@{host}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def bootstrap(env_path: Path, migration_env_path: Path) -> None:
    """Create the deployment-only secret file and replace the runtime URL exactly once."""

    if migration_env_path.exists():
        raise RuntimeError(f"refusing to overwrite existing {migration_env_path}")
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    owner_url = _env_value(lines, "DATABASE_URL")
    runtime_password = secrets.token_urlsafe(48)
    runtime_url = _runtime_url(owner_url, runtime_password)
    updated_lines = _replace_env_value(lines, "DATABASE_URL", runtime_url)

    migration_env_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(migration_env_path.parent, 0o700)
    fd = os.open(migration_env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(f"MIGRATION_DATABASE_URL={owner_url}\n")
            output.write(f"APP_DATABASE_PASSWORD={runtime_password}\n")
        os.chmod(migration_env_path, 0o600)

        temporary = env_path.with_name(f".{env_path.name}.runtime-role.tmp")
        temporary.write_text("".join(updated_lines), encoding="utf-8")
        os.chmod(temporary, env_path.stat().st_mode & 0o777)
        os.replace(temporary, env_path)
    except Exception:
        migration_env_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    runtime_environment = repository / ".env"
    deployment_environment = Path("/home/ubuntu/.config/bulls/migration.env")
    bootstrap(runtime_environment, deployment_environment)
    print(
        "Configured restricted bulls_app runtime credentials; owner credentials are now "
        f"isolated in {deployment_environment}"
    )
