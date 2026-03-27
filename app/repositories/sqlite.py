"""SQLite implementation of the repository interface."""

import aiosqlite
import json
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from .base import BaseRepository


class SQLiteRepository(BaseRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
        return self._db

    async def initialize(self) -> None:
        db = await self._get_db()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                analysis_hints TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT '',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                profile_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (profile_id) REFERENCES profiles(id)
            );

            CREATE TABLE IF NOT EXISTS baseline_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER NOT NULL UNIQUE,
                outline_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (transcript_id) REFERENCES transcripts(id)
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER NOT NULL,
                analysis_type TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (transcript_id) REFERENCES transcripts(id),
                UNIQUE(transcript_id, analysis_type)
            );

            CREATE TABLE IF NOT EXISTS channel_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL UNIQUE,
                profile_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (profile_id) REFERENCES profiles(id)
            );

            CREATE TABLE IF NOT EXISTS profile_grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_profile_id INTEGER NOT NULL,
                auto_selected_profile_id INTEGER NOT NULL,
                user_grade INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (channel_profile_id) REFERENCES channel_profiles(id),
                FOREIGN KEY (auto_selected_profile_id) REFERENCES profiles(id)
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE
            );

            CREATE TABLE IF NOT EXISTS cross_analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_type TEXT NOT NULL,
                transcript_ids TEXT NOT NULL DEFAULT '[]',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transcript_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'user',
                accepted INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (transcript_id) REFERENCES transcripts(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id),
                UNIQUE(transcript_id, tag_id)
            );
        """)
        await db.commit()

        # Migrations: add columns if missing
        for migration in [
            "ALTER TABLE transcripts ADD COLUMN processing_stats TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE transcripts ADD COLUMN upload_date TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE transcripts ADD COLUMN watch_later INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE transcript_tags ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass  # column already exists

        # Seed default profiles
        default_profiles = [
            ("podcast", "Long-form conversational content with multiple speakers", "Look for topic transitions, guest introductions, ad breaks, and conversational segments. Podcasts often have intro/outro segments and sponsor reads."),
            ("tutorial", "Educational content teaching a specific skill or concept", "Look for introduction of concepts, step-by-step instructions, demonstrations, and recap/summary sections. Tutorials often have prerequisites and follow a logical progression."),
            ("lecture", "Academic or professional presentation on a topic", "Look for thesis statements, main arguments, supporting evidence, examples, and conclusions. Lectures often have a formal structure with clear sections."),
            ("interview", "Question-and-answer format between interviewer and subject", "Look for question-answer pairs, topic shifts, follow-up questions, and key revelations. Interviews often have an introduction of the guest and closing remarks."),
        ]
        for name, desc, hints in default_profiles:
            await db.execute(
                "INSERT OR IGNORE INTO profiles (name, description, analysis_hints) VALUES (?, ?, ?)",
                (name, desc, hints),
            )
        await db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # --- Profiles ---
    async def get_profiles(self) -> list[dict]:
        db = await self._get_db()
        cursor = await db.execute("SELECT * FROM profiles ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_profile(self, profile_id: int) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_profile(self, name: str, description: str, analysis_hints: str = "") -> int:
        db = await self._get_db()
        cursor = await db.execute(
            "INSERT INTO profiles (name, description, analysis_hints) VALUES (?, ?, ?)",
            (name, description, analysis_hints),
        )
        await db.commit()
        return cursor.lastrowid

    async def delete_profile(self, profile_id: int) -> bool:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM transcripts WHERE profile_id = ?",
            (profile_id,),
        )
        row = await cursor.fetchone()
        if row["cnt"] > 0:
            return False
        await db.execute("DELETE FROM channel_profiles WHERE profile_id = ?", (profile_id,))
        await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        await db.commit()
        return True

    # --- Transcripts ---
    async def create_transcript(self, video_url: str, profile_id: int) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            "INSERT INTO transcripts (video_url, profile_id, status) VALUES (?, ?, 'pending')",
            (video_url, profile_id),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_transcript(self, transcript_id: int) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT t.*, p.name as profile_name
               FROM transcripts t
               JOIN profiles p ON t.profile_id = p.id
               WHERE t.id = ?""",
            (transcript_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_transcripts(self, channel: str | None = None, profile_id: int | None = None, tag: str | None = None, watch_later: bool | None = None, limit: int | None = None) -> list[dict]:
        db = await self._get_db()
        query = """SELECT t.*, p.name as profile_name,
                      CASE WHEN b.id IS NOT NULL THEN 1 ELSE 0 END as has_baseline
               FROM transcripts t
               JOIN profiles p ON t.profile_id = p.id
               LEFT JOIN baseline_analysis b ON t.id = b.transcript_id"""
        conditions = []
        params = []
        if channel:
            conditions.append("t.channel = ?")
            params.append(channel)
        if profile_id is not None:
            conditions.append("t.profile_id = ?")
            params.append(profile_id)
        if tag:
            query += " JOIN transcript_tags tt ON t.id = tt.transcript_id JOIN tags tg ON tt.tag_id = tg.id"
            conditions.append("tg.name = ? AND tt.accepted = 1")
            params.append(tag)
        if watch_later is not None:
            conditions.append("t.watch_later = ?")
            params.append(1 if watch_later else 0)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY t.created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Get completed analyses for this transcript
            ar_cursor = await db.execute(
                "SELECT analysis_type FROM analysis_results WHERE transcript_id = ?",
                (d["id"],),
            )
            ar_rows = await ar_cursor.fetchall()
            d["completed_analyses"] = [r["analysis_type"] for r in ar_rows]
            # Get accepted tags
            tag_cursor = await db.execute(
                """SELECT tg.name, tt.source, tt.confirmed FROM tags tg JOIN transcript_tags tt ON tg.id = tt.tag_id
                   WHERE tt.transcript_id = ? AND tt.accepted = 1""",
                (d["id"],),
            )
            d["tags"] = [{"name": r["name"], "source": r["source"], "confirmed": r["confirmed"]} for r in await tag_cursor.fetchall()]
            results.append(d)
        return results

    async def get_channels(self) -> list[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT channel, COUNT(*) as transcript_count
               FROM transcripts WHERE channel != ''
               GROUP BY channel ORDER BY channel"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_transcript(self, transcript_id: int, **kwargs) -> None:
        if not kwargs:
            return
        db = await self._get_db()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [transcript_id]
        await db.execute(
            f"UPDATE transcripts SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

    # --- Baseline Analysis ---
    async def save_baseline_analysis(self, transcript_id: int, outline_json: str, summary: str) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            """INSERT OR REPLACE INTO baseline_analysis (transcript_id, outline_json, summary)
               VALUES (?, ?, ?)""",
            (transcript_id, outline_json, summary),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_baseline_analysis(self, transcript_id: int) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM baseline_analysis WHERE transcript_id = ?",
            (transcript_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # --- Analysis Results ---
    async def save_analysis_result(self, transcript_id: int, analysis_type: str, result_json: str) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            """INSERT OR REPLACE INTO analysis_results (transcript_id, analysis_type, result_json)
               VALUES (?, ?, ?)""",
            (transcript_id, analysis_type, result_json),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_analysis_result(self, transcript_id: int, analysis_type: str) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM analysis_results WHERE transcript_id = ? AND analysis_type = ?",
            (transcript_id, analysis_type),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_analysis_results_for_transcript(self, transcript_id: int) -> list[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM analysis_results WHERE transcript_id = ? ORDER BY created_at DESC",
            (transcript_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Channel Profiles ---
    async def set_channel_profile(self, channel_name: str, profile_id: int) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            """INSERT INTO channel_profiles (channel_name, profile_id)
               VALUES (?, ?)
               ON CONFLICT(channel_name) DO UPDATE SET profile_id = excluded.profile_id""",
            (channel_name, profile_id),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_channel_profile(self, channel_name: str) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM channel_profiles WHERE channel_name = ?",
            (channel_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # --- Profile Grades ---
    async def save_profile_grade(self, channel_profile_id: int, auto_selected_profile_id: int, user_grade: int) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            "INSERT INTO profile_grades (channel_profile_id, auto_selected_profile_id, user_grade) VALUES (?, ?, ?)",
            (channel_profile_id, auto_selected_profile_id, user_grade),
        )
        await db.commit()
        return cursor.lastrowid

    # --- Tags ---
    async def get_tags_for_transcript(self, transcript_id: int) -> list[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT t.id, t.name, tt.source, tt.accepted, tt.confirmed
               FROM tags t JOIN transcript_tags tt ON t.id = tt.tag_id
               WHERE tt.transcript_id = ?
               ORDER BY t.name""",
            (transcript_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def add_tag_to_transcript(self, transcript_id: int, tag_name: str, source: str = "user") -> dict:
        db = await self._get_db()
        # Upsert tag
        await db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name.strip().lower(),))
        cursor = await db.execute("SELECT id, name FROM tags WHERE name = ?", (tag_name.strip().lower(),))
        tag = dict(await cursor.fetchone())
        # Link to transcript
        await db.execute(
            """INSERT OR IGNORE INTO transcript_tags (transcript_id, tag_id, source)
               VALUES (?, ?, ?)""",
            (transcript_id, tag["id"], source),
        )
        await db.commit()
        return tag

    async def remove_tag_from_transcript(self, transcript_id: int, tag_id: int) -> None:
        db = await self._get_db()
        await db.execute(
            "DELETE FROM transcript_tags WHERE transcript_id = ? AND tag_id = ?",
            (transcript_id, tag_id),
        )
        await db.commit()

    async def reject_auto_tag(self, transcript_id: int, tag_id: int) -> None:
        db = await self._get_db()
        await db.execute(
            "UPDATE transcript_tags SET accepted = 0 WHERE transcript_id = ? AND tag_id = ?",
            (transcript_id, tag_id),
        )
        await db.commit()

    async def confirm_auto_tag(self, transcript_id: int, tag_id: int) -> None:
        db = await self._get_db()
        await db.execute(
            "UPDATE transcript_tags SET confirmed = 1 WHERE transcript_id = ? AND tag_id = ?",
            (transcript_id, tag_id),
        )
        await db.commit()

    async def get_confirmed_tags_for_channel(self, channel: str) -> list[str]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT DISTINCT tg.name FROM tags tg
               JOIN transcript_tags tt ON tg.id = tt.tag_id
               JOIN transcripts tr ON tt.transcript_id = tr.id
               WHERE tr.channel = ? AND tt.confirmed = 1""",
            (channel,),
        )
        return [r["name"] for r in await cursor.fetchall()]

    async def get_all_tags(self) -> list[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT t.name, COUNT(tt.id) as usage_count
               FROM tags t LEFT JOIN transcript_tags tt ON t.id = tt.tag_id AND tt.accepted = 1
               GROUP BY t.id ORDER BY usage_count DESC, t.name"""
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def get_rejected_tags_for_channel(self, channel: str) -> list[str]:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT DISTINCT tg.name FROM tags tg
               JOIN transcript_tags tt ON tg.id = tt.tag_id
               JOIN transcripts tr ON tt.transcript_id = tr.id
               WHERE tr.channel = ? AND tt.accepted = 0""",
            (channel,),
        )
        return [r["name"] for r in await cursor.fetchall()]

    # --- URL Lookup ---
    async def get_transcripts_by_urls(self, urls: list[str]) -> list[dict]:
        if not urls:
            return []
        db = await self._get_db()
        placeholders = ",".join("?" for _ in urls)
        cursor = await db.execute(
            f"SELECT id, video_url, title, status FROM transcripts WHERE video_url IN ({placeholders})",
            urls,
        )
        return [dict(r) for r in await cursor.fetchall()]

    # --- Cross-Analysis ---
    async def save_cross_analysis(self, analysis_type: str, transcript_ids: list[int], result_json: str) -> int:
        db = await self._get_db()
        cursor = await db.execute(
            """INSERT INTO cross_analysis_results (analysis_type, transcript_ids, result_json)
               VALUES (?, ?, ?)""",
            (analysis_type, json.dumps(transcript_ids), result_json),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_cross_analysis(self, cross_analysis_id: int) -> Optional[dict]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM cross_analysis_results WHERE id = ?",
            (cross_analysis_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_cross_analysis_result(self, cross_analysis_id: int, result_json: str) -> None:
        db = await self._get_db()
        await db.execute(
            "UPDATE cross_analysis_results SET result_json = ? WHERE id = ?",
            (result_json, cross_analysis_id),
        )
        await db.commit()

    async def get_all_cross_analyses(self, limit: int | None = None) -> list[dict]:
        db = await self._get_db()
        query = "SELECT * FROM cross_analysis_results ORDER BY created_at DESC"
        params: list = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]
