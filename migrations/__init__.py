"""
Database Migration System for BTHome Listener

This module provides a simple migration framework for managing database schema changes.
It tracks applied migrations in a schema_migrations table to ensure migrations are only
applied once, even across application restarts.

Usage:
    from migrations import MigrationManager
    
    # Initialize and run migrations
    manager = MigrationManager(db_path="bthome_data.db")
    manager.run_migrations()
"""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import importlib
import sys

logger = logging.getLogger(__name__)

# Define all migrations in this module
# Each migration file in the migrations directory should define a MIGRATIONS list
# This list contains dictionaries with the following keys:
#   - version: Unique version identifier (string)
#   - description: Human-readable description
#   - sql: SQL statements to execute (string or list of strings)
#   - python: Optional Python function to execute (takes conn, cursor)
#   - checksum: Optional checksum for verification

# Import all migration modules to collect their MIGRATIONS
_MIGRATIONS = []

# Get the migrations directory
_migrations_dir = Path(__file__).parent

# Import all Python files in the migrations directory
for py_file in sorted(_migrations_dir.glob("*.py")):
    if py_file.name.startswith("_"):
        continue
    
    try:
        module_name = f"migrations.{py_file.stem}"
        module = importlib.import_module(module_name)
        if hasattr(module, 'MIGRATIONS'):
            _MIGRATIONS.extend(module.MIGRATIONS)
    except ImportError as e:
        logger.warning(f"Could not import migration module {module_name}: {e}")

# Sort migrations by version
_MIGRATIONS.sort(key=lambda x: x.get('version', ''))


class MigrationManager:
    """
    Manages database migrations for the BTHome Listener.
    
    The migration system:
    - Tracks applied migrations in a schema_migrations table
    - Applies pending migrations in order
    - Supports both Python-based and SQL-based migrations
    - Preserves existing data during schema changes
    """
    
    MIGRATIONS_MODULE = "migrations"
    
    def __init__(self, db_path: str):
        """
        Initialize the migration manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._connection = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection
    
    def close(self):
        """Close the database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    def _ensure_schema_migrations_table(self):
        """Create the schema_migrations table if it doesn't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
                checksum TEXT
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_schema_migrations_version 
            ON schema_migrations(version)
        """)
        
        conn.commit()
    
    def _get_applied_migrations(self) -> List[str]:
        """Get list of already applied migration versions"""
        self._ensure_schema_migrations_table()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [row["version"] for row in cursor.fetchall()]
    
    def _get_available_migrations(self) -> List[dict]:
        """
        Get list of available migrations.
        
        Returns the migrations that were collected at module import time.
        """
        return _MIGRATIONS
    
    def _record_migration(self, version: str, description: str, checksum: Optional[str] = None):
        """Record that a migration has been applied"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute(
            """INSERT INTO schema_migrations (version, description, applied_at, checksum) 
               VALUES (?, ?, ?, ?)""",
            (version, description, now, checksum)
        )
        conn.commit()
        logger.info(f"Recorded migration {version}: {description}")
    
    def _apply_migration(self, migration: dict) -> bool:
        """
        Apply a single migration.
        
        Args:
            migration: Migration definition dictionary with keys:
                - version: Migration version string
                - description: Description of the migration
                - sql: Optional SQL statements to execute
                - python: Optional Python function to execute
                - checksum: Optional checksum for verification
        
        Returns:
            True if migration was applied successfully, False otherwise
        """
        version = migration.get('version', 'unknown')
        description = migration.get('description', '')
        sql = migration.get('sql', '')
        python_func = migration.get('python')
        checksum = migration.get('checksum')
        
        logger.info(f"Applying migration {version}: {description}")
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Execute SQL if provided
            if sql:
                if isinstance(sql, str):
                    cursor.executescript(sql)
                elif isinstance(sql, list):
                    for stmt in sql:
                        cursor.execute(stmt)
            
            # Execute Python function if provided
            if python_func:
                python_func(conn, cursor)
            
            conn.commit()
            
            # Record the migration
            self._record_migration(version, description, checksum)
            
            logger.info(f"Successfully applied migration {version}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to apply migration {version}: {e}")
            raise
    
    def run_migrations(self) -> int:
        """
        Run all pending migrations.
        
        Returns:
            Number of migrations applied
        """
        self._ensure_schema_migrations_table()
        
        applied = self._get_applied_migrations()
        available = self._get_available_migrations()
        
        applied_set = set(applied)
        count = 0
        
        for migration in available:
            version = migration.get('version', '')
            if version not in applied_set:
                try:
                    self._apply_migration(migration)
                    count += 1
                    applied_set.add(version)
                except Exception as e:
                    logger.error(f"Migration {version} failed, stopping migration process: {e}")
                    raise
        
        logger.info(f"Applied {count} migration(s)")
        return count
    
    def get_migration_status(self) -> dict:
        """
        Get the current migration status.
        
        Returns:
            Dictionary with migration status information
        """
        self._ensure_schema_migrations_table()
        
        applied = self._get_applied_migrations()
        available = self._get_available_migrations()
        
        applied_versions = set(applied)
        available_versions = {m.get('version', '') for m in available}
        
        pending = available_versions - applied_versions
        
        return {
            'applied_count': len(applied),
            'available_count': len(available),
            'pending_count': len(pending),
            'applied_versions': sorted(applied),
            'pending_versions': sorted(pending),
            'migrations_table_exists': True
        }
    
    def reset_migrations(self):
        """
        Reset the migration tracking (DANGEROUS - use only for development).
        
        This removes all records from the schema_migrations table, causing
        all migrations to be re-applied on the next run.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM schema_migrations")
        conn.commit()
        logger.warning("Migration tracking has been reset")
