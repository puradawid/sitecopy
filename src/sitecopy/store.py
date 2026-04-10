from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        self.conn.executescript(
            """
            create table if not exists resources (
              canonical_url text primary key,
              original_url text,
              final_url text,
              kind text,
              status_code integer,
              content_type text,
              content_length integer,
              checksum text,
              local_path text,
              fetch_timestamp text,
              error_reason text
            );
            create table if not exists referrers (
              source_canonical_url text,
              target_original_url text,
              target_canonical_url text,
              context text
            );
            create table if not exists redirects (
              source_canonical_url text primary key,
              final_canonical_url text,
              chain_json text
            );
            create table if not exists collisions (
              canonical_url text,
              requested_path text,
              resolved_path text,
              reason text
            );
            create table if not exists skips (
              url text,
              reason text,
              referrer text
            );
            """
        )
        self.conn.commit()

    def upsert_resource(self, **values: Any) -> None:
        keys = list(values)
        placeholders = ", ".join("?" for _ in keys)
        updates = ", ".join(f"{k}=excluded.{k}" for k in keys if k != "canonical_url")
        self.conn.execute(
            f"insert into resources ({', '.join(keys)}) values ({placeholders}) on conflict(canonical_url) do update set {updates}",
            [values[k] for k in keys],
        )
        self.conn.commit()

    def get_resource(self, canonical_url: str) -> sqlite3.Row | None:
        return self.conn.execute("select * from resources where canonical_url = ?", (canonical_url,)).fetchone()

    def resources(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("select * from resources order by canonical_url"))

    def downloaded_map(self) -> dict[str, str]:
        rows = self.conn.execute("select canonical_url, local_path from resources where local_path is not null and error_reason is null").fetchall()
        mapping = {r["canonical_url"]: r["local_path"] for r in rows}
        redirects = self.conn.execute("select source_canonical_url, final_canonical_url from redirects").fetchall()
        for redirect in redirects:
            target = mapping.get(redirect["final_canonical_url"])
            if target:
                mapping[redirect["source_canonical_url"]] = target
        return mapping

    def add_referrer(self, source: str, target_original: str, target_canonical: str, context: str) -> None:
        self.conn.execute("insert into referrers values (?, ?, ?, ?)", (source, target_original, target_canonical, context))
        self.conn.commit()

    def add_skip(self, url: str, reason: str, referrer: str | None = None) -> None:
        self.conn.execute("insert into skips values (?, ?, ?)", (url, reason, referrer))
        self.conn.commit()

    def add_redirect(self, source: str, final: str, chain: list[str]) -> None:
        self.conn.execute(
            "insert into redirects values (?, ?, ?) on conflict(source_canonical_url) do update set final_canonical_url=excluded.final_canonical_url, chain_json=excluded.chain_json",
            (source, final, json.dumps(chain)),
        )
        self.conn.commit()

    def add_collision(self, item: dict[str, str]) -> None:
        self.conn.execute("insert into collisions values (?, ?, ?, ?)", (item["canonical_url"], item["requested_path"], item["resolved_path"], item["reason"]))
        self.conn.commit()

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"select count(*) from {table}").fetchone()[0])

    def close(self) -> None:
        self.conn.close()
