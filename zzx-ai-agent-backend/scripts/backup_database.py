"""Create a compressed logical backup without putting the password in argv."""
from __future__ import annotations

import argparse
import gzip
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    cfg = dict(dotenv_values(Path(__file__).resolve().parents[1] / ".env"))
    cfg.update(os.environ)
    database = cfg.get("MYSQL_DB", "zzx_agent_db")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / f"{database}-{timestamp}.sql.gz"
    command = [
        "mysqldump",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--set-gtid-purged=OFF",
        "-h", cfg.get("MYSQL_HOST", "127.0.0.1"),
        "-P", str(cfg.get("MYSQL_PORT", "3306")),
        "-u", cfg["MYSQL_USER"],
        database,
    ]
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = cfg["MYSQL_PASSWORD"]
    with gzip.open(target, "wb") as output:
        subprocess.run(command, env=environment, stdout=output, check=True)
    print(f"Database backup written to {target}")


if __name__ == "__main__":
    main()
