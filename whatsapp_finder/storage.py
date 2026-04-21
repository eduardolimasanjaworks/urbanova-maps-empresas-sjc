from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set


@dataclass
class GroupLink:
    url: str
    source_url: str
    engine: str
    query: str
    first_seen_at: str


class ResultStore:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_file = self.output_dir / "groups_raw.jsonl"
        self.unique_json = self.output_dir / "groups_unique.json"
        self.unique_csv = self.output_dir / "groups_unique.csv"
        self.summary_json = self.output_dir / "run_summary.json"
        self.checkpoint_json = self.output_dir / "checkpoint.json"

        self.unique_links: Dict[str, GroupLink] = {}
        self.visited_pages: Set[str] = set()
        self.done_queries: Set[str] = set()
        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        if not self.checkpoint_json.exists():
            return
        data = json.loads(self.checkpoint_json.read_text(encoding="utf-8"))
        for row in data.get("unique_links", []):
            gl = GroupLink(**row)
            self.unique_links[gl.url] = gl
        self.visited_pages = set(data.get("visited_pages", []))
        self.done_queries = set(data.get("done_queries", []))

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_links(self, links: Iterable[str], source_url: str, engine: str, query: str) -> int:
        now = self._utcnow()
        added = 0
        with self.raw_file.open("a", encoding="utf-8") as handle:
            for link in links:
                payload = {
                    "url": link,
                    "source_url": source_url,
                    "engine": engine,
                    "query": query,
                    "seen_at": now,
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                if link not in self.unique_links:
                    self.unique_links[link] = GroupLink(
                        url=link,
                        source_url=source_url,
                        engine=engine,
                        query=query,
                        first_seen_at=now,
                    )
                    added += 1
        return added

    def mark_page_visited(self, url: str) -> None:
        self.visited_pages.add(url)

    def mark_query_done(self, engine: str, query: str) -> None:
        self.done_queries.add(f"{engine}::{query}")

    def is_query_done(self, engine: str, query: str) -> bool:
        return f"{engine}::{query}" in self.done_queries

    def save_checkpoint(self) -> None:
        data = {
            "unique_links": [vars(x) for x in self.unique_links.values()],
            "visited_pages": sorted(self.visited_pages),
            "done_queries": sorted(self.done_queries),
            "checkpoint_at": self._utcnow(),
        }
        self.checkpoint_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def export_unique(self, run_summary: dict) -> None:
        unique_rows = [vars(row) for row in self.unique_links.values()]
        self.unique_json.write_text(
            json.dumps(unique_rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.unique_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["url", "source_url", "engine", "query", "first_seen_at"],
            )
            writer.writeheader()
            for row in unique_rows:
                writer.writerow(row)

        self.summary_json.write_text(
            json.dumps(run_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

