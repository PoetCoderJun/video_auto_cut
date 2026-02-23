from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(get_settings().db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_files (
                job_id TEXT PRIMARY KEY,
                video_path TEXT,
                srt_path TEXT,
                optimized_srt_path TEXT,
                final_step1_srt_path TEXT,
                topics_path TEXT,
                final_topics_path TEXT,
                final_video_path TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_step1_lines (
                job_id TEXT NOT NULL,
                line_id INTEGER NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                original_text TEXT NOT NULL,
                optimized_text TEXT NOT NULL,
                ai_suggest_remove INTEGER NOT NULL,
                user_final_remove INTEGER NOT NULL,
                PRIMARY KEY(job_id, line_id),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_step2_chapters (
                job_id TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                line_ids_json TEXT NOT NULL,
                PRIMARY KEY(job_id, chapter_id),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE INDEX IF NOT EXISTS idx_job_tasks_status ON job_tasks(status, task_id);
            CREATE INDEX IF NOT EXISTS idx_job_tasks_job_id ON job_tasks(job_id, status);
            """
        )
        conn.commit()
