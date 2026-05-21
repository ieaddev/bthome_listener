"""
Migration 001: Initial Schema Migration

This is the base migration that creates all database tables and the schema_migrations
table for tracking which migrations have been applied to the database.

Tables created:
- schema_migrations: Tracks applied database migrations
- devices: Device metadata (address, name, first/last seen, advertisement count)
- advertisements: Each BTHome advertisement received
- sensor_readings: Individual sensor readings from advertisements
- binary_sensor_readings: Binary sensor readings from advertisements
- events: Event data from advertisements

Indexes created for efficient querying as defined in DATABASE_SCHEMA.md.
"""

# List of migrations in this file
MIGRATIONS = [
    {
        'version': '001',
        'description': 'Create all database tables and indexes for BTHome Listener schema',
        'sql': """
            -- Schema migrations tracking table
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
                checksum TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_schema_migrations_version 
            ON schema_migrations(version);
            
            -- Devices table: stores device metadata
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL UNIQUE,
                name TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                advertisement_count INTEGER DEFAULT 0
            );
            
            -- Device index
            CREATE INDEX IF NOT EXISTS idx_devices_address ON devices(address);
            
            -- Advertisements table: stores each BTHome advertisement
            CREATE TABLE IF NOT EXISTS advertisements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                bthome_version INTEGER,
                is_encrypted INTEGER DEFAULT 0,
                is_trigger_based INTEGER DEFAULT 0,
                packet_id INTEGER,
                device_type_id INTEGER,
                firmware_version TEXT,
                raw_data BLOB,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Advertisement indexes
            CREATE INDEX IF NOT EXISTS idx_advertisements_device_id ON advertisements(device_id);
            CREATE INDEX IF NOT EXISTS idx_advertisements_timestamp ON advertisements(timestamp);
            
            -- Sensor readings table: stores individual sensor readings
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                object_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                value REAL,
                value_text TEXT,
                unit TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Sensor readings indexes
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_name_timestamp ON sensor_readings(device_id, name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name_device_timestamp ON sensor_readings(name, device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name_timestamp ON sensor_readings(name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_name ON sensor_readings(device_id, name);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_advertisement_id ON sensor_readings(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name ON sensor_readings(name);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp_adv ON sensor_readings(advertisement_id, position);
            
            -- Binary sensor readings table
            CREATE TABLE IF NOT EXISTS binary_sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                object_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                value INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Binary sensor readings indexes
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_device_name_timestamp ON binary_sensor_readings(device_id, name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_device_name ON binary_sensor_readings(device_id, name);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_advertisement_id ON binary_sensor_readings(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_name ON binary_sensor_readings(name);
            
            -- Events table
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                device_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_property TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Event indexes
            CREATE INDEX IF NOT EXISTS idx_events_device_type_timestamp ON events(device_id, device_type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_advertisement_id ON events(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_events_device_type ON events(device_type);
        """,
        'checksum': 'b5f3a7d9c2e186f45b8a3d7e2c9f1a4b'
    }
]
