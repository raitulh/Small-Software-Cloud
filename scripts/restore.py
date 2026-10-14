#!/usr/bin/env python3
"""
Small Software Cloud - Database Restore Utility
Verifies SHA256 checksum against metadata manifest and restores database via psql.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_restore(backup_file: Path, container_name: str = "smallcloud_postgres", skip_verify: bool = False):
    if not backup_file.exists():
        print(f"[ERROR] Backup file '{backup_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    meta_file = backup_file.with_suffix("").with_suffix(".json")
    if meta_file.exists() and not skip_verify:
        with open(meta_file, "r", encoding="utf-8") as f_meta:
            manifest = json.load(f_meta)
        expected_sha = manifest.get("sha256")
        if expected_sha:
            print("[*] Verifying backup checksum...")
            actual_sha = compute_sha256(backup_file)
            if actual_sha != expected_sha:
                print(f"[ERROR] Checksum mismatch! Expected {expected_sha}, got {actual_sha}", file=sys.stderr)
                sys.exit(1)
            print("[✓] Checksum matches manifest.")

    print(f"[*] Restoring database from '{backup_file.name}' into container '{container_name}'...")

    cmd = [
        "docker", "exec", "-i", container_name,
        "psql", "-U", "smallcloud", "-d", "smallcloud"
    ]

    try:
        # Read gzipped dump and pipe to psql
        with gzip.open(backup_file, "rb") as f_in:
            dump_data = f_in.read()

        proc = subprocess.run(cmd, input=dump_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print("[SUCCESS] Database restored successfully!")
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode("utf-8", errors="replace")
        print(f"[ERROR] Database restore failed: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Small Software Cloud Database Restore")
    parser.add_argument("backup_file", help="Path to the .sql.gz backup file to restore")
    parser.add_argument("--container", default="smallcloud_postgres", help="PostgreSQL Docker container name")
    parser.add_argument("--skip-verify", action="store_true", help="Skip checksum verification")
    args = parser.parse_args()

    run_restore(Path(args.backup_file), args.container, args.skip_verify)
