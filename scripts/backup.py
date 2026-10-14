#!/usr/bin/env python3
"""
Small Software Cloud - Automated Backup Utility
Dumps PostgreSQL database, computes SHA256 checksum, writes metadata manifest,
and manages backup retention.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_backup(target_dir: Path, container_name: str = "smallcloud_postgres", keep: int = 7) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"smallcloud_backup_{timestamp}.sql.gz"
    meta_file = target_dir / f"smallcloud_backup_{timestamp}.json"

    print(f"[*] Initiating backup for container: {container_name}")
    print(f"[*] Destination: {backup_file}")

    # Run pg_dumpall or pg_dump via docker exec smallcloud_postgres
    cmd = [
        "docker", "exec", container_name,
        "pg_dump", "-U", "smallcloud", "-d", "smallcloud", "-Z", "9"
    ]

    try:
        with open(backup_file, "wb") as f_out:
            proc = subprocess.run(cmd, stdout=f_out, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as exc:
        err_msg = exc.stderr.decode("utf-8", errors="replace")
        print(f"[ERROR] pg_dump failed: {err_msg}", file=sys.stderr)
        if backup_file.exists():
            backup_file.unlink()
        sys.exit(1)
    except FileNotFoundError:
        print("[ERROR] 'docker' CLI not found on PATH. Ensure Docker is running.", file=sys.stderr)
        sys.exit(1)

    file_size = backup_file.stat().st_size
    sha256_hash = compute_sha256(backup_file)

    manifest = {
        "timestamp": timestamp,
        "backup_file": backup_file.name,
        "file_size_bytes": file_size,
        "sha256": sha256_hash,
        "container": container_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(meta_file, "w", encoding="utf-8") as f_meta:
        json.dump(manifest, f_meta, indent=2)

    print(f"[SUCCESS] Backup created: {backup_file.name} ({file_size} bytes)")
    print(f"[*] Checksum (SHA256): {sha256_hash}")

    # Retention management
    existing_backups = sorted(target_dir.glob("smallcloud_backup_*.sql.gz"))
    if len(existing_backups) > keep:
        to_delete = existing_backups[:-keep]
        for old_file in to_delete:
            old_meta = old_file.with_suffix("").with_suffix(".json")
            print(f"[*] Pruning old backup: {old_file.name}")
            old_file.unlink(missing_ok=True)
            old_meta.unlink(missing_ok=True)

    return backup_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Small Software Cloud Database Backup")
    parser.add_argument("--dir", default="./backups", help="Directory to store backup files")
    parser.add_argument("--container", default="smallcloud_postgres", help="PostgreSQL Docker container name")
    parser.add_argument("--keep", type=int, default=7, help="Number of recent backups to retain")
    args = parser.parse_args()

    run_backup(Path(args.dir), args.container, args.keep)
