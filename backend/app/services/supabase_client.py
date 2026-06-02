import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid
from app.config import settings

logger = logging.getLogger("supabase_client")

# Attempt to import Supabase, otherwise mock it
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase SDK python package not installed. Running in mock DB mode.")

class MockDatabase:
    """An in-memory database fallback to allow the system to run without credentials."""
    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            "agent_registry": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "CorrelationAgent",
                    "role": "Correlated Pairs & News Analyst",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                },
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "NewsAgent",
                    "role": "XAUUSD News & Impact Analyst",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                },
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "name": "TradingAgent",
                    "role": "Price Reaction Observer & Signal Generator",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                },
                {
                    "id": "44444444-4444-4444-4444-444444444444",
                    "name": "QAAgent",
                    "role": "Quality Assurance & Improvement Analyst",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                },
                {
                    "id": "55555555-5555-5555-5555-555555555555",
                    "name": "PerformanceAgent",
                    "role": "Trade Observability & Accuracy Tracker",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                },
                {
                    "id": "66666666-6666-6666-6666-666666666666",
                    "name": "SupervisorAgent",
                    "role": "Chief AI Officer — System Supervisor",
                    "status": "active",
                    "config": {},
                    "lessons_learned": [],
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "avg_response_time_ms": 0.0,
                    "accuracy_score": 1.0,
                    "total_tasks_completed": 0,
                    "total_errors": 0,
                }
            ],
            "analysis_cycles": [],
            "correlation_reports": [],
            "gold_news_reports": [],
            "trade_signals": [],
            "qa_reports": [],
            "performance_reports": [],
            "supervisor_reports": [],
            "notifications": [],
            "audit_log": []
        }

    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if table not in self.tables:
            self.tables[table] = []
        
        row = data.copy()
        if "id" not in row:
            row["id"] = str(uuid.uuid4())
        if "created_at" not in row:
            row["created_at"] = datetime.utcnow().isoformat()
            
        self.tables[table].append(row)
        return row

    def select(self, table: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        rows = self.tables.get(table, [])
        if not filters:
            return rows
        
        filtered = []
        for row in rows:
            match = True
            for k, v in filters.items():
                if row.get(k) != v:
                    match = False
                    break
            if match:
                filtered.append(row)
        return filtered

    def update(self, table: str, filters: Dict[str, Any], data: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = self.tables.get(table, [])
        updated_rows = []
        for row in rows:
            match = True
            for k, v in filters.items():
                if row.get(k) != v:
                    match = False
                    break
            if match:
                for k, v in data.items():
                    row[k] = v
                updated_rows.append(row)
        return updated_rows

class DatabaseService:
    def __init__(self):
        self.client: Optional[Client] = None
        self.use_mock = True
        self.mock_db = MockDatabase()
        
        if settings.is_supabase_configured and SUPABASE_AVAILABLE:
            try:
                self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
                self.use_mock = False
                logger.info("Successfully connected to Supabase Database.")
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}. Falling back to Mock DB.")
        else:
            logger.info("Supabase credentials missing or invalid. Running in Mock DB mode.")

    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_mock:
            return self.mock_db.insert(table, data)
        try:
            res = self.client.table(table).insert(data).execute()
            return res.data[0] if res.data else data
        except Exception as e:
            logger.error(f"Error inserting into {table}: {e}")
            # Degrade gracefully to mock
            return self.mock_db.insert(table, data)

    def select(self, table: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self.use_mock:
            return self.mock_db.select(table, filters)
        try:
            query = self.client.table(table).select("*")
            if filters:
                for k, v in filters.items():
                    query = query.eq(k, v)
            res = query.execute()
            return res.data
        except Exception as e:
            logger.error(f"Error selecting from {table}: {e}")
            return self.mock_db.select(table, filters)

    def update(self, table: str, filters: Dict[str, Any], data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.use_mock:
            return self.mock_db.update(table, filters, data)
        try:
            query = self.client.table(table).update(data)
            for k, v in filters.items():
                query = query.eq(k, v)
            res = query.execute()
            return res.data
        except Exception as e:
            logger.error(f"Error updating table {table}: {e}")
            return self.mock_db.update(table, filters, data)

    def update_agent_status(self, agent_name: str, status: str, errors_delta: int = 0, tasks_delta: int = 0, response_time_ms: float = 0.0):
        # Update heartbeat, status, error increments, response times
        filters = {"name": agent_name}
        agents = self.select("agent_registry", filters)
        if not agents:
            # Create a mock agent first
            self.insert("agent_registry", {"name": agent_name, "role": "Worker Agent", "status": status})
            agents = self.select("agent_registry", filters)
            
        agent = agents[0]
        new_errors = agent.get("total_errors", 0) + errors_delta
        new_tasks = agent.get("total_tasks_completed", 0) + tasks_delta
        
        # Simple rolling average for response time
        curr_avg = agent.get("avg_response_time_ms", 0.0)
        curr_tasks = agent.get("total_tasks_completed", 0)
        if response_time_ms > 0:
            if curr_tasks > 0:
                new_avg = ((curr_avg * curr_tasks) + response_time_ms) / (curr_tasks + 1)
            else:
                new_avg = response_time_ms
        else:
            new_avg = curr_avg
            
        data = {
            "status": status,
            "last_heartbeat": datetime.utcnow().isoformat(),
            "total_errors": new_errors,
            "total_tasks_completed": new_tasks,
            "avg_response_time_ms": new_avg
        }
        self.update("agent_registry", filters, data)

    def save_lesson(self, agent_name: str, mistake: str, correction: str, lesson: str):
        filters = {"name": agent_name}
        agents = self.select("agent_registry", filters)
        if not agents:
            return
            
        agent = agents[0]
        lessons = agent.get("lessons_learned", [])
        if not isinstance(lessons, list):
            lessons = []
            
        lessons.append({
            "timestamp": datetime.utcnow().isoformat(),
            "mistake": mistake,
            "correction": correction,
            "lesson": lesson
        })
        
        # Calculate new accuracy score based on corrections
        # Formula: Accuracy goes down as mistakes accumulate unless we clear them
        error_count = len(lessons)
        new_accuracy = max(0.2, 1.0 - (error_count * 0.1))
        
        self.update("agent_registry", filters, {
            "lessons_learned": lessons,
            "accuracy_score": new_accuracy
        })

# Global db service client
db_service = DatabaseService()
