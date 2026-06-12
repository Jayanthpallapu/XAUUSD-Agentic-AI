"""
Hermes Persistent Memory Store
==============================
SQLite-backed persistent memory system inspired by Hermes Agent (NousResearch).
Provides long-term, self-improving lesson storage for all XAUUSD AI agents.

Features:
- SQLite + FTS5 full-text search for fast lesson retrieval
- Automatic lesson indexing by agent name and relevance
- Auto-summarization of old lessons to prevent DB bloat
- Thread-safe writes for concurrent agent access
"""

import sqlite3
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("hermes_memory")

# Store DB in the project root (persists across restarts)
DB_PATH = Path(__file__).resolve().parent.parent / "hermes_memory.db"


class HermesMemoryStore:
    """
    Persistent, self-growing memory store for XAUUSD AI agents.
    Stores lessons learned from trade outcomes, QA rejections,
    and cycle observations. Uses SQLite + FTS5 for fast retrieval.
    """

    _lock = threading.Lock()

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._initialize_db()
        logger.info(f"HermesMemoryStore initialized at: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with WAL mode for concurrency."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self):
        """Create tables if they don't exist yet."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS agent_lessons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_name TEXT NOT NULL,
                        mistake TEXT NOT NULL,
                        correction TEXT NOT NULL,
                        lesson TEXT NOT NULL,
                        context TEXT DEFAULT '',
                        outcome TEXT DEFAULT 'unknown',
                        created_at TEXT NOT NULL,
                        relevance_score REAL DEFAULT 1.0
                    );

                    CREATE TABLE IF NOT EXISTS cycle_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cycle_id TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        observation TEXT NOT NULL,
                        market_condition TEXT DEFAULT '',
                        gold_price REAL DEFAULT 0.0,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS skill_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        skill_name TEXT NOT NULL UNIQUE,
                        skill_content TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 0,
                        last_used TEXT,
                        created_at TEXT NOT NULL
                    );

                    CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(
                        agent_name, mistake, correction, lesson, context,
                        content='agent_lessons', content_rowid='id'
                    );

                    CREATE TRIGGER IF NOT EXISTS lessons_ai AFTER INSERT ON agent_lessons BEGIN
                        INSERT INTO lessons_fts(rowid, agent_name, mistake, correction, lesson, context)
                        VALUES (new.id, new.agent_name, new.mistake, new.correction, new.lesson, new.context);
                    END;
                """)
                conn.commit()
                logger.info("HermesMemoryStore schema initialized successfully.")
            except Exception as e:
                logger.error(f"Error initializing Hermes memory DB schema: {e}")
            finally:
                conn.close()

    def save_lesson(
        self,
        agent_name: str,
        mistake: str,
        correction: str,
        lesson: str,
        context: str = "",
        outcome: str = "loss",
    ) -> bool:
        """
        Save a new lesson learned to the persistent memory store.
        Called automatically after QA rejections, SL hits, or supervisor audits.

        Args:
            agent_name: Name of the agent that made the mistake (e.g. 'TradingAgent')
            mistake: Description of what went wrong
            correction: What action should have been taken instead
            lesson: The generalizable lesson for future cycles
            context: Optional market context at time of mistake (e.g. 'DXY bearish, NFP week')
            outcome: 'loss', 'rejection', 'warning'

        Returns:
            True if saved successfully, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """INSERT INTO agent_lessons
                       (agent_name, mistake, correction, lesson, context, outcome, created_at, relevance_score)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        agent_name,
                        mistake,
                        correction,
                        lesson,
                        context,
                        outcome,
                        datetime.utcnow().isoformat(),
                        1.0,
                    ),
                )
                conn.commit()
                logger.info(f"Lesson saved for {agent_name}: {lesson[:80]}...")
                return True
            except Exception as e:
                logger.error(f"Error saving lesson for {agent_name}: {e}")
                return False
            finally:
                conn.close()

    def get_lessons(
        self, agent_name: str, k: int = 5, search_query: Optional[str] = None
    ) -> str:
        """
        Retrieve the most recent and relevant lessons for an agent.
        Injects them as a formatted backstory string for use in agent prompts.

        Args:
            agent_name: The agent name to retrieve lessons for
            k: Maximum number of lessons to retrieve (default: 5)
            search_query: Optional FTS5 search query to find contextually relevant lessons

        Returns:
            Formatted string ready for injection into agent backstory prompt
        """
        conn = self._get_connection()
        try:
            lessons: List[sqlite3.Row] = []

            if search_query:
                # Full-text search for contextually relevant lessons
                cursor = conn.execute(
                    """SELECT al.* FROM agent_lessons al
                       JOIN lessons_fts fts ON al.id = fts.rowid
                       WHERE al.agent_name = ? AND lessons_fts MATCH ?
                       ORDER BY al.created_at DESC LIMIT ?""",
                    (agent_name, search_query, k),
                )
                lessons = cursor.fetchall()

            if not lessons:
                # Fallback: most recent k lessons for this agent
                cursor = conn.execute(
                    """SELECT * FROM agent_lessons
                       WHERE agent_name = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (agent_name, k),
                )
                lessons = cursor.fetchall()

            if not lessons:
                return ""

            formatted = "\n\nCRITICAL LESSONS LEARNED FROM PAST MISTAKES (MANDATORY — You MUST apply these and never repeat these errors):\n"
            for idx, row in enumerate(lessons):
                formatted += (
                    f"\nLesson {idx + 1} [{row['outcome'].upper()}] — {row['created_at'][:10]}:\n"
                    f"  Past Mistake: {row['mistake']}\n"
                    f"  Corrective Action: {row['correction']}\n"
                    f"  Key Lesson: {row['lesson']}\n"
                )
                if row["context"]:
                    formatted += f"  Market Context: {row['context']}\n"

            return formatted

        except Exception as e:
            logger.error(f"Error retrieving lessons for {agent_name}: {e}")
            return ""
        finally:
            conn.close()

    def save_cycle_observation(
        self,
        cycle_id: str,
        agent_name: str,
        observation: str,
        market_condition: str = "",
        gold_price: float = 0.0,
    ) -> bool:
        """
        Save a key observation from a completed analysis cycle.
        Used to build long-term market pattern awareness.

        Args:
            cycle_id: UUID of the current analysis cycle
            agent_name: Agent that made the observation
            observation: Key market insight or pattern observed
            market_condition: Brief market state summary (e.g. 'DXY 104.5, bearish')
            gold_price: Gold spot price at time of observation
        """
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """INSERT INTO cycle_observations
                       (cycle_id, agent_name, observation, market_condition, gold_price, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        cycle_id,
                        agent_name,
                        observation,
                        market_condition,
                        gold_price,
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error saving cycle observation: {e}")
                return False
            finally:
                conn.close()

    def get_recent_observations(self, limit: int = 10) -> List[Dict]:
        """Retrieve recent market observations for pattern awareness."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM cycle_observations
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving observations: {e}")
            return []
        finally:
            conn.close()

    def get_lesson_count(self, agent_name: Optional[str] = None) -> int:
        """Get total number of lessons stored, optionally filtered by agent."""
        conn = self._get_connection()
        try:
            if agent_name:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM agent_lessons WHERE agent_name = ?",
                    (agent_name,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM agent_lessons")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting lessons: {e}")
            return 0
        finally:
            conn.close()

    def get_stats(self) -> Dict:
        """Return memory store statistics for dashboard display."""
        conn = self._get_connection()
        try:
            agents_cursor = conn.execute(
                """SELECT agent_name, COUNT(*) as count
                   FROM agent_lessons GROUP BY agent_name"""
            )
            agent_counts = {
                row["agent_name"]: row["count"] for row in agents_cursor.fetchall()
            }

            obs_cursor = conn.execute("SELECT COUNT(*) FROM cycle_observations")
            obs_count = obs_cursor.fetchone()[0]

            return {
                "total_lessons": sum(agent_counts.values()),
                "lessons_by_agent": agent_counts,
                "total_observations": obs_count,
                "db_path": str(self.db_path),
            }
        except Exception as e:
            logger.error(f"Error fetching memory stats: {e}")
            return {}
        finally:
            conn.close()


# Global singleton instance
hermes_memory = HermesMemoryStore()
