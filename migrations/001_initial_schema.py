"""
Migration 001: Initial Schema Migration

This is the base migration that creates the schema_migrations table.
This table is used to track which migrations have been applied to the database.

Note: The actual database tables (devices, advertisements, sensor_readings, etc.)
are created by the database.py module's initialize() method. This migration
only creates the migration tracking infrastructure.
"""

# List of migrations in this file
MIGRATIONS = [
    {
        'version': '001',
        'description': 'Create schema_migrations table for tracking database migrations',
        'sql': """
            -- Create the schema_migrations table to track applied migrations
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
                checksum TEXT
            );
            
            -- Create index for faster lookups by version
            CREATE INDEX IF NOT EXISTS idx_schema_migrations_version 
            ON schema_migrations(version);
        """,
        'checksum': 'a1b2c3d4e5f6'
    }
]
