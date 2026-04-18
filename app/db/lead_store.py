from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict


class LeadRepository:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    company TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def insert_lead(self, lead_data: Dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO leads (full_name, email, company)
                VALUES (?, ?, ?)
                """,
                (
                    lead_data["full_name"],
                    lead_data["email"],
                    lead_data["company"],
                ),
            )
            conn.commit()
