"""
Tests for the database migration system.
"""

import sqlite3
import os
import tempfile
import pytest
from pathlib import Path

# Add the project directory to the path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from migrations import MigrationManager
from database import BTHomeDatabase


class TestMigrationManager:
    """Tests for the MigrationManager class"""
    
    def test_create_schema_migrations_table(self):
        """Test that schema_migrations table is created"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            manager._ensure_schema_migrations_table()
            
            # Verify table exists
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
            result = cursor.fetchone()
            conn.close()
            
            assert result is not None
            assert result[0] == 'schema_migrations'
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_create_index(self):
        """Test that index on schema_migrations is created"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            manager._ensure_schema_migrations_table()
            
            # Verify index exists
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_schema_migrations_version'")
            result = cursor.fetchone()
            conn.close()
            
            assert result is not None
            assert result[0] == 'idx_schema_migrations_version'
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_record_migration(self):
        """Test recording a migration"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            manager._ensure_schema_migrations_table()
            
            manager._record_migration('001', 'Test migration', 'abc123')
            
            # Verify migration was recorded
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT version, description, checksum FROM schema_migrations WHERE version='001'")
            result = cursor.fetchone()
            conn.close()
            
            assert result is not None
            assert result[0] == '001'
            assert result[1] == 'Test migration'
            assert result[2] == 'abc123'
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_get_applied_migrations(self):
        """Test getting list of applied migrations"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            manager._ensure_schema_migrations_table()
            
            # Record some migrations
            manager._record_migration('001', 'Migration 1')
            manager._record_migration('002', 'Migration 2')
            
            applied = manager._get_applied_migrations()
            
            assert len(applied) == 2
            assert '001' in applied
            assert '002' in applied
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_get_available_migrations(self):
        """Test getting available migrations from files"""
        manager = MigrationManager(':memory:')
        available = manager._get_available_migrations()
        
        # Should find at least the initial migration
        assert len(available) >= 1
        
        # Check that migrations have required fields
        for migration in available:
            assert 'version' in migration
            assert 'description' in migration
        
        manager.close()
    
    def test_run_migrations(self):
        """Test running all migrations"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            count = manager.run_migrations()
            
            # Should have applied at least one migration
            assert count >= 1
            
            # Verify migrations were recorded
            applied = manager._get_applied_migrations()
            assert len(applied) >= 1
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_get_migration_status(self):
        """Test getting migration status"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            
            # Run migrations
            manager.run_migrations()
            
            # Get status
            status = manager.get_migration_status()
            
            assert 'applied_count' in status
            assert 'available_count' in status
            assert 'pending_count' in status
            assert 'applied_versions' in status
            assert 'pending_versions' in status
            
            # After running migrations, pending should be 0 or less than available
            assert status['pending_count'] <= status['available_count']
            assert status['applied_count'] >= 1
            
            manager.close()
        finally:
            os.unlink(db_path)
    
    def test_idempotent_migrations(self):
        """Test that migrations are only applied once"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # First run
            manager1 = MigrationManager(db_path)
            count1 = manager1.run_migrations()
            manager1.close()
            
            # Second run should apply fewer migrations
            manager2 = MigrationManager(db_path)
            count2 = manager2.run_migrations()
            manager2.close()
            
            # Second run should apply 0 migrations (all already applied)
            assert count2 == 0
            
        finally:
            os.unlink(db_path)


class TestDatabaseIntegration:
    """Test migration integration with BTHomeDatabase"""
    
    def test_database_initialization_creates_migrations_table(self):
        """Test that database initialization creates schema_migrations table"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            db = BTHomeDatabase(db_path)
            db.initialize()
            
            # Verify schema_migrations table exists
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
            result = cursor.fetchone()
            conn.close()
            
            assert result is not None
            assert result[0] == 'schema_migrations'
            
            db.close()
        finally:
            os.unlink(db_path)
    
    def test_database_get_migration_status(self):
        """Test getting migration status from database"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            db = BTHomeDatabase(db_path)
            db.initialize()
            
            status = db.get_migration_status()
            
            assert 'applied_count' in status
            assert 'available_count' in status
            assert status['migrations_table_exists'] == True
            
            db.close()
        finally:
            os.unlink(db_path)
    
    def test_database_preserves_existing_data(self):
        """Test that database initialization preserves existing data"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create initial database with some data
            db1 = BTHomeDatabase(db_path)
            db1.initialize()
            
            # Insert test data
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO devices (address, name, first_seen, last_seen, advertisement_count) VALUES (?, ?, ?, ?, ?)",
                ('AA:BB:CC:DD:EE:FF', 'Test Device', '2024-01-01T00:00:00', '2024-01-01T00:00:00', 1)
            )
            conn.commit()
            conn.close()
            
            db1.close()
            
            # Reinitialize database (simulating app restart)
            db2 = BTHomeDatabase(db_path)
            db2.initialize()
            
            # Verify data still exists
            device = db2.get_device('AA:BB:CC:DD:EE:FF')
            assert device is not None
            assert device['address'] == 'AA:BB:CC:DD:EE:FF'
            assert device['name'] == 'Test Device'
            
            db2.close()
        finally:
            os.unlink(db_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
