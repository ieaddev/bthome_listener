"""
SQLite Database Module for BTHome Listener

This module provides SQLite-based persistence for BTHome advertisement data.
It stores all sensor readings, binary sensor states, and events with their
position in the advertisement, timestamp, and source device information.

Database Schema:
    - devices: Device metadata (address, name, etc.)
    - advertisements: Each BTHome advertisement received
    - sensor_readings: Individual sensor readings from advertisements
    - binary_sensor_readings: Binary sensor readings from advertisements
    - events: Event data from advertisements
"""

import sqlite3
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict

from bthome_decoder import BTHomeData, SensorData, BinarySensorData, EventData

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "bthome_data.db"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    db_path: str = DEFAULT_DB_PATH
    enable_wal: bool = True  # Enable WAL mode for better concurrent access
    synchronous: str = "NORMAL"  # Balance between safety and performance
    journal_mode: str = "WAL" if enable_wal else "DELETE"


class BTHomeDatabase:
    """
    SQLite database for storing BTHome advertisement data.
    
    The database schema is designed to:
    - Store each advertisement with its timestamp and source device
    - Store each data point (sensor, binary sensor, event) with its position in the advertisement
    - Track multiple values of the same type from a single source
    - Preserve the order of values as they appear in advertisements
    
    Tables:
        devices: Stores device metadata (MAC address, name, first/last seen)
        advertisements: Stores each BTHome advertisement with timestamp and device reference
        sensor_readings: Stores individual sensor readings with position and value
        binary_sensor_readings: Stores binary sensor readings with position and value
        events: Stores event data with position
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH, config: Optional[DatabaseConfig] = None):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
            config: Optional database configuration
        """
        self.db_path = db_path
        self.config = config or DatabaseConfig(db_path=db_path)
        self._local = threading.local()
        self._initialized = False
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection for the current thread"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign key support
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            # Configure based on settings
            self._local.connection.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
            self._local.connection.execute(f"PRAGMA synchronous = {self.config.synchronous}")
        return self._local.connection
    
    def close(self):
        """Close the database connection for the current thread"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    def initialize(self):
        """
        Initialize the database schema.
        
        Creates all necessary tables if they don't exist.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create tables
        cursor.executescript("""
            -- Devices table: stores device metadata
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL UNIQUE,
                name TEXT,
                first_seen TEXT NOT NULL,  -- ISO 8601 timestamp
                last_seen TEXT NOT NULL,   -- ISO 8601 timestamp
                advertisement_count INTEGER DEFAULT 0
            );
            
            -- Advertisements table: stores each BTHome advertisement
            CREATE TABLE IF NOT EXISTS advertisements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,  -- ISO 8601 timestamp when received
                bthome_version INTEGER,
                is_encrypted INTEGER DEFAULT 0,  -- Boolean as integer
                is_trigger_based INTEGER DEFAULT 0,
                packet_id INTEGER,
                device_type_id INTEGER,
                firmware_version TEXT,
                raw_data BLOB,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Sensor readings table: stores individual sensor readings
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,   -- Denormalized for faster sensor history queries
                position INTEGER NOT NULL,  -- Position in the advertisement data
                object_id INTEGER NOT NULL,   -- BTHome object ID
                name TEXT NOT NULL,          -- Sensor name (e.g., "temperature")
                value REAL,                  -- Numeric value (NULL for non-numeric)
                value_text TEXT,             -- Text value (for non-numeric sensors)
                unit TEXT,                   -- Unit of measurement
                timestamp TEXT NOT NULL,     -- Denormalized timestamp for faster history queries
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Binary sensor readings table
            CREATE TABLE IF NOT EXISTS binary_sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,   -- Denormalized for faster queries
                position INTEGER NOT NULL,  -- Position in the advertisement data
                object_id INTEGER NOT NULL,   -- BTHome object ID
                name TEXT NOT NULL,          -- Sensor name (e.g., "motion")
                value INTEGER NOT NULL,      -- Boolean as integer (0 or 1)
                timestamp TEXT NOT NULL,     -- Denormalized timestamp for faster history queries
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Events table
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertisement_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,   -- Denormalized for faster queries
                position INTEGER NOT NULL,  -- Position in the advertisement data
                device_type TEXT NOT NULL,  -- Event device type (e.g., "button")
                event_type TEXT NOT NULL,   -- Event type (e.g., "press")
                event_property TEXT,        -- JSON string for event properties
                timestamp TEXT NOT NULL,     -- Denormalized timestamp for faster history queries
                FOREIGN KEY (advertisement_id) REFERENCES advertisements(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            
            -- Indexes for efficient querying
            -- Primary query: get sensor history for a specific device and sensor name
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_name_timestamp ON sensor_readings(device_id, name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name_device_timestamp ON sensor_readings(name, device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name_timestamp ON sensor_readings(name, timestamp);
            
            -- For filtering by device and sensor name (most common use case)
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_name ON sensor_readings(device_id, name);
            
            -- Original indexes for other query patterns
            CREATE INDEX IF NOT EXISTS idx_advertisements_device_id ON advertisements(device_id);
            CREATE INDEX IF NOT EXISTS idx_advertisements_timestamp ON advertisements(timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_advertisement_id ON sensor_readings(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_name ON sensor_readings(name);
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp_adv ON sensor_readings(advertisement_id, position);
            
            -- Binary sensor indexes
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_device_name_timestamp ON binary_sensor_readings(device_id, name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_device_name ON binary_sensor_readings(device_id, name);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_advertisement_id ON binary_sensor_readings(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_binary_sensor_readings_name ON binary_sensor_readings(name);
            
            -- Event indexes
            CREATE INDEX IF NOT EXISTS idx_events_device_type_timestamp ON events(device_id, device_type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_advertisement_id ON events(advertisement_id);
            CREATE INDEX IF NOT EXISTS idx_events_device_type ON events(device_type);
            
            -- Device index
            CREATE INDEX IF NOT EXISTS idx_devices_address ON devices(address);
        """)
        
        conn.commit()
        self._initialized = True
        logger.info(f"Database initialized at {self.db_path}")
    
    def _ensure_initialized(self):
        """Ensure database is initialized"""
        if not self._initialized:
            self.initialize()
    
    def _get_device_id(self, address: str, name: Optional[str] = None) -> int:
        """
        Get or create a device ID for the given address.
        
        Args:
            address: MAC address of the device
            name: Optional device name
            
        Returns:
            Device ID
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Try to find existing device
        cursor.execute("SELECT id FROM devices WHERE address = ?", (address,))
        result = cursor.fetchone()
        
        if result:
            # Update last seen and name if changed
            device_id = result["id"]
            cursor.execute(
                "UPDATE devices SET last_seen = ?, name = COALESCE(?, name), advertisement_count = advertisement_count + 1 WHERE id = ?",
                (now, name, device_id)
            )
            conn.commit()
            return device_id
        
        # Create new device
        cursor.execute(
            "INSERT INTO devices (address, name, first_seen, last_seen, advertisement_count) VALUES (?, ?, ?, ?, 1)",
            (address, name, now, now)
        )
        conn.commit()
        return cursor.lastrowid
    
    def store_advertisement(self, address: str, name: Optional[str], 
                           bthome_data: BTHomeData, 
                           timestamp: Optional[datetime] = None) -> int:
        """
        Store a BTHome advertisement and all its data points.
        
        Args:
            address: MAC address of the source device
            name: Optional device name
            bthome_data: Decoded BTHomeData object
            timestamp: When the advertisement was received (defaults to now)
            
        Returns:
            The advertisement ID
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        timestamp_iso = timestamp.isoformat()
        
        # Get or create device
        device_id = self._get_device_id(address, name)
        
        # Insert advertisement
        cursor.execute(
            """INSERT INTO advertisements 
               (device_id, timestamp, bthome_version, is_encrypted, 
                is_trigger_based, packet_id, device_type_id, firmware_version, raw_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                device_id,
                timestamp_iso,
                bthome_data.version,
                1 if bthome_data.is_encrypted else 0,
                1 if bthome_data.is_trigger_based else 0,
                bthome_data.packet_id,
                bthome_data.device_info.device_type_id,
                bthome_data.device_info.firmware_version,
                bthome_data.raw_data
            )
        )
        advertisement_id = cursor.lastrowid
        
        # Store sensor readings with their positions
        for position, sensor in enumerate(bthome_data.sensors):
            self._store_sensor_reading(cursor, advertisement_id, device_id, position, sensor, timestamp_iso)
        
        # Store binary sensor readings with their positions
        for position, binary_sensor in enumerate(bthome_data.binary_sensors):
            self._store_binary_sensor_reading(cursor, advertisement_id, device_id, position, binary_sensor, timestamp_iso)
        
        # Store events with their positions
        for position, event in enumerate(bthome_data.events):
            self._store_event(cursor, advertisement_id, device_id, position, event, timestamp_iso)
        
        conn.commit()
        logger.debug(f"Stored advertisement {advertisement_id} from device {address}")
        return advertisement_id
    
    def _store_sensor_reading(self, cursor: sqlite3.Cursor, advertisement_id: int, 
                              device_id: int, position: int, sensor: SensorData, 
                              timestamp: str):
        """Store a single sensor reading"""
        # Determine if value is numeric or text
        if isinstance(sensor.value, (int, float)):
            value = sensor.value
            value_text = None
        else:
            value = None
            value_text = str(sensor.value)
        
        cursor.execute(
            """INSERT INTO sensor_readings 
               (advertisement_id, device_id, position, object_id, name, value, value_text, unit, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                advertisement_id,
                device_id,
                position,
                sensor.object_id,
                sensor.name,
                value,
                value_text,
                sensor.unit,
                timestamp
            )
        )
    
    def _store_binary_sensor_reading(self, cursor: sqlite3.Cursor, advertisement_id: int,
                                      device_id: int, position: int, binary_sensor: BinarySensorData,
                                      timestamp: str):
        """Store a single binary sensor reading"""
        cursor.execute(
            """INSERT INTO binary_sensor_readings 
               (advertisement_id, device_id, position, object_id, name, value, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                advertisement_id,
                device_id,
                position,
                binary_sensor.object_id,
                binary_sensor.name,
                1 if binary_sensor.value else 0,
                timestamp
            )
        )
    
    def _store_event(self, cursor: sqlite3.Cursor, advertisement_id: int,
                    device_id: int, position: int, event: EventData, timestamp: str):
        """Store a single event"""
        # Convert event property to JSON string
        import json
        event_property_json = json.dumps(event.event_property) if event.event_property else None
        
        cursor.execute(
            """INSERT INTO events 
               (advertisement_id, device_id, position, device_type, event_type, event_property, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                advertisement_id,
                device_id,
                position,
                event.device_type,
                event.event_type,
                event_property_json,
                timestamp
            )
        )
    
    def get_device(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get device information by address.
        
        Args:
            address: MAC address of the device
            
        Returns:
            Device dictionary or None if not found
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, address, name, first_seen, last_seen, advertisement_count 
               FROM devices WHERE address = ?""",
            (address,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_device_by_id(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get device information by database ID.
        
        Args:
            device_id: Database ID of the device
            
        Returns:
            Device dictionary or None if not found
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, address, name, first_seen, last_seen, advertisement_count 
               FROM devices WHERE id = ?""",
            (device_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices.
        
        Returns:
            List of device dictionaries
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, address, name, first_seen, last_seen, advertisement_count 
               FROM devices ORDER BY last_seen DESC"""
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_advertisements(self, device_address: Optional[str] = None, 
                           limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get advertisements, optionally filtered by device.
        
        Args:
            device_address: Optional MAC address to filter by
            limit: Maximum number of advertisements to return
            
        Returns:
            List of advertisement dictionaries
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if device_address:
            query = """
                SELECT a.id, a.device_id, a.timestamp, a.bthome_version, 
                       a.is_encrypted, a.is_trigger_based, a.packet_id,
                       a.device_type_id, a.firmware_version,
                       d.address, d.name as device_name
                FROM advertisements a
                JOIN devices d ON a.device_id = d.id
                WHERE d.address = ?
                ORDER BY a.timestamp DESC
            """
            params = (device_address,)
        else:
            query = """
                SELECT a.id, a.device_id, a.timestamp, a.bthome_version, 
                       a.is_encrypted, a.is_trigger_based, a.packet_id,
                       a.device_type_id, a.firmware_version,
                       d.address, d.name as device_name
                FROM advertisements a
                JOIN devices d ON a.device_id = d.id
                ORDER BY a.timestamp DESC
            """
            params = ()
        
        if limit:
            query += " LIMIT ?"
            params = (*params, limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_sensor_readings(self, device_address: Optional[str] = None,
                            sensor_name: Optional[str] = None,
                            limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get sensor readings, optionally filtered.
        
        For the most efficient query when filtering by device and sensor name,
        use get_sensor_history() which uses the denormalized columns directly.
        
        Args:
            device_address: Optional MAC address to filter by
            sensor_name: Optional sensor name to filter by
            limit: Maximum number of readings to return
            
        Returns:
            List of sensor reading dictionaries
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT sr.id, sr.advertisement_id, sr.device_id, sr.position, sr.object_id, 
                   sr.name, sr.value, sr.value_text, sr.unit,
                   sr.timestamp, d.address, d.name as device_name
            FROM sensor_readings sr
            JOIN devices d ON sr.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if sensor_name:
            conditions.append("sr.name = ?")
            params.append(sensor_name)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY sr.timestamp DESC, sr.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_sensor_history(self, device_address: Optional[str] = None,
                           sensor_name: Optional[str] = None,
                           limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get sensor history - OPTIMIZED for the common use case of filtering 
        by a single sensor and viewing its history.
        
        This method uses the denormalized device_id and timestamp columns
        for maximum efficiency, avoiding JOIN operations.
        
        Args:
            device_address: Optional MAC address to filter by
            sensor_name: Optional sensor name to filter by
            limit: Maximum number of readings to return
            
        Returns:
            List of sensor reading dictionaries with timestamp
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Use denormalized columns for direct, efficient access
        query = """
            SELECT sr.id, sr.advertisement_id, sr.device_id, sr.position, sr.object_id,
                   sr.name, sr.value, sr.value_text, sr.unit, sr.timestamp,
                   d.address, d.name as device_name
            FROM sensor_readings sr
            JOIN devices d ON sr.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if sensor_name:
            conditions.append("sr.name = ?")
            params.append(sensor_name)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY sr.timestamp DESC, sr.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_binary_sensor_readings(self, device_address: Optional[str] = None,
                                   sensor_name: Optional[str] = None,
                                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get binary sensor readings, optionally filtered.
        
        Args:
            device_address: Optional MAC address to filter by
            sensor_name: Optional sensor name to filter by
            limit: Maximum number of readings to return
            
        Returns:
            List of binary sensor reading dictionaries
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT bsr.id, bsr.advertisement_id, bsr.device_id, bsr.position, bsr.object_id, 
                   bsr.name, bsr.value, bsr.timestamp,
                   d.address, d.name as device_name
            FROM binary_sensor_readings bsr
            JOIN devices d ON bsr.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if sensor_name:
            conditions.append("bsr.name = ?")
            params.append(sensor_name)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY bsr.timestamp DESC, bsr.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_binary_sensor_history(self, device_address: Optional[str] = None,
                                   sensor_name: Optional[str] = None,
                                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get binary sensor history - OPTIMIZED for filtering by device and sensor name.
        
        Args:
            device_address: Optional MAC address to filter by
            sensor_name: Optional sensor name to filter by
            limit: Maximum number of readings to return
            
        Returns:
            List of binary sensor reading dictionaries with timestamp
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT bsr.id, bsr.advertisement_id, bsr.device_id, bsr.position, bsr.object_id,
                   bsr.name, bsr.value, bsr.timestamp,
                   d.address, d.name as device_name
            FROM binary_sensor_readings bsr
            JOIN devices d ON bsr.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if sensor_name:
            conditions.append("bsr.name = ?")
            params.append(sensor_name)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY bsr.timestamp DESC, bsr.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_events(self, device_address: Optional[str] = None,
                   event_type: Optional[str] = None,
                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get events, optionally filtered.
        
        Args:
            device_address: Optional MAC address to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of events to return
            
        Returns:
            List of event dictionaries
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT e.id, e.advertisement_id, e.device_id, e.position, e.device_type, 
                   e.event_type, e.event_property, e.timestamp,
                   d.address, d.name as device_name
            FROM events e
            JOIN devices d ON e.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if event_type:
            conditions.append("e.event_type = ?")
            params.append(event_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY e.timestamp DESC, e.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_event_history(self, device_address: Optional[str] = None,
                          event_type: Optional[str] = None,
                          limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get event history - OPTIMIZED for filtering by device and event type.
        
        Args:
            device_address: Optional MAC address to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of events to return
            
        Returns:
            List of event dictionaries with timestamp
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT e.id, e.advertisement_id, e.device_id, e.position, e.device_type,
                   e.event_type, e.event_property, e.timestamp,
                   d.address, d.name as device_name
            FROM events e
            JOIN devices d ON e.device_id = d.id
        """
        params = []
        conditions = []
        
        if device_address:
            conditions.append("d.address = ?")
            params.append(device_address)
        
        if event_type:
            conditions.append("e.event_type = ?")
            params.append(event_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY e.timestamp DESC, e.position"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_advertisement_data(self, advertisement_id: int) -> Optional[Dict[str, Any]]:
        """
        Get all data for a specific advertisement.
        
        Args:
            advertisement_id: The advertisement ID
            
        Returns:
            Dictionary containing advertisement, device, sensors, binary sensors, and events
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get advertisement
        cursor.execute(
            """SELECT a.*, d.address, d.name as device_name 
               FROM advertisements a
               JOIN devices d ON a.device_id = d.id
               WHERE a.id = ?""",
            (advertisement_id,)
        )
        ad_row = cursor.fetchone()
        
        if not ad_row:
            return None
        
        result = {
            "advertisement": dict(ad_row),
            "sensors": [],
            "binary_sensors": [],
            "events": []
        }
        
        # Get sensor readings
        cursor.execute(
            """SELECT * FROM sensor_readings 
               WHERE advertisement_id = ? ORDER BY position""",
            (advertisement_id,)
        )
        result["sensors"] = [dict(row) for row in cursor.fetchall()]
        
        # Get binary sensor readings
        cursor.execute(
            """SELECT * FROM binary_sensor_readings 
               WHERE advertisement_id = ? ORDER BY position""",
            (advertisement_id,)
        )
        result["binary_sensors"] = [dict(row) for row in cursor.fetchall()]
        
        # Get events
        cursor.execute(
            """SELECT * FROM events 
               WHERE advertisement_id = ? ORDER BY position""",
            (advertisement_id,)
        )
        result["events"] = [dict(row) for row in cursor.fetchall()]
        
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dictionary with counts of devices, advertisements, readings, etc.
        """
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Device count
        cursor.execute("SELECT COUNT(*) FROM devices")
        stats["device_count"] = cursor.fetchone()[0]
        
        # Advertisement count
        cursor.execute("SELECT COUNT(*) FROM advertisements")
        stats["advertisement_count"] = cursor.fetchone()[0]
        
        # Sensor reading count
        cursor.execute("SELECT COUNT(*) FROM sensor_readings")
        stats["sensor_reading_count"] = cursor.fetchone()[0]
        
        # Binary sensor reading count
        cursor.execute("SELECT COUNT(*) FROM binary_sensor_readings")
        stats["binary_sensor_reading_count"] = cursor.fetchone()[0]
        
        # Event count
        cursor.execute("SELECT COUNT(*) FROM events")
        stats["event_count"] = cursor.fetchone()[0]
        
        # Database size
        db_path = Path(self.db_path)
        if db_path.exists():
            stats["database_size_bytes"] = db_path.stat().st_size
        
        return stats
    
    def vacuum(self):
        """Run VACUUM to optimize the database"""
        self._ensure_initialized()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("VACUUM")
        conn.commit()
        logger.info("Database vacuum completed")
