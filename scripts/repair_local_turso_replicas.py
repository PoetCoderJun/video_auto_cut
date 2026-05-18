#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

try:
    import libsql  # type: ignore
except Exception as exc:  # pragma: no cover - depends on local environment
    raise SystemExit(
        "libsql is required. Run with the same Python environment as start_web_mvp.sh."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def repo_resolved_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def default_auth_replica_path(shared_replica_path: Path) -> Path:
    suffix = shared_replica_path.suffix or ".db"
    return shared_replica_path.with_name(f"{shared_replica_path.stem}.auth{suffix}")


def replica_related_paths(replica_path: Path) -> list[Path]:
    return [
        replica_path,
        replica_path.with_name(replica_path.name + "-wal"),
        replica_path.with_name(replica_path.name + "-shm"),
        replica_path.with_name(replica_path.name + "-info"),
    ]


def has_replica_metadata(replica_path: Path) -> bool:
    return replica_path.with_name(replica_path.name + "-info").exists()


def has_invalid_local_state(replica_path: Path) -> bool:
    return not replica_path.exists() or not has_replica_metadata(replica_path)


def remove_related(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def table_names(conn: object) -> set[str]:
    rows = conn.execute(  # type: ignore[attr-defined]
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return {str(row[0]) for row in rows}


def table_count(conn: object, table_name: str) -> int | None:
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()  # type: ignore[attr-defined]
    except Exception:
        return None
    return int(row[0])


def sync_to_temp_replica(
    *,
    name: str,
    target_path: Path,
    turso_url: str,
    auth_token: str,
    required_tables: set[str],
) -> dict[str, int | None]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.repair-{os.getpid()}")
    remove_related(replica_related_paths(tmp_path))
    try:
        conn = libsql.connect(str(tmp_path), sync_url=turso_url, auth_token=auth_token)
        try:
            conn.sync()
            tables = table_names(conn)
            missing = sorted(required_tables - tables)
            if missing:
                raise RuntimeError(f"{name} replica is missing required tables: {', '.join(missing)}")
            counts = {
                table_name: table_count(conn, table_name)
                for table_name in sorted(required_tables)
            }
        finally:
            conn.close()

        remove_related(replica_related_paths(target_path))
        for src, dst in zip(replica_related_paths(tmp_path), replica_related_paths(target_path)):
            if src.exists():
                src.replace(dst)
        return counts
    finally:
        remove_related(replica_related_paths(tmp_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild local Turso replica files from the configured online Turso database.",
    )
    parser.add_argument(
        "--target",
        choices=("business", "auth", "all"),
        default="all",
        help="Which local replica to rebuild.",
    )
    parser.add_argument(
        "--only-if-invalid-local-state",
        action="store_true",
        help="Skip replicas that already have libsql metadata.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    turso_url = (os.getenv("TURSO_DATABASE_URL") or "").strip()
    auth_token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    if not turso_url or not auth_token:
        raise SystemExit("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required to repair local replicas.")

    work_dir = repo_resolved_path(os.getenv("WORK_DIR") or "workdir")
    shared_raw = (
        os.getenv("API_TURSO_LOCAL_REPLICA_PATH")
        or os.getenv("TURSO_LOCAL_REPLICA_PATH")
        or str(work_dir / "web_api_turso_replica.db")
    )
    business_path = repo_resolved_path(shared_raw)
    auth_raw = os.getenv("BETTER_AUTH_TURSO_LOCAL_REPLICA_PATH")
    auth_path = repo_resolved_path(auth_raw) if auth_raw else default_auth_replica_path(business_path)

    targets: list[tuple[str, Path, set[str]]] = []
    if args.target in {"business", "all"}:
        targets.append(
            (
                "business",
                business_path,
                {"users", "credit_ledger", "coupon_codes", "public_invite_settings", "guest_sessions"},
            )
        )
    if args.target in {"auth", "all"}:
        targets.append(("auth", auth_path, {"user", "account", "session", "jwks"}))

    for name, path, required_tables in targets:
        if args.only_if_invalid_local_state and not has_invalid_local_state(path):
            print(f"[repair_local_turso_replicas] {name} replica already has metadata: {path}")
            continue
        counts = sync_to_temp_replica(
            name=name,
            target_path=path,
            turso_url=turso_url,
            auth_token=auth_token,
            required_tables=required_tables,
        )
        count_text = ", ".join(f"{table}={count}" for table, count in counts.items())
        print(f"[repair_local_turso_replicas] rebuilt {name} replica: {path}")
        print(f"[repair_local_turso_replicas] verified tables: {count_text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
