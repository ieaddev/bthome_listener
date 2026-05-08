#!/usr/bin/env python3
"""
Tests for the SQLite database module.

Run with: python -m pytest test_database.py -v
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone
import sqlite3

from bthome_decoder import BTHomeData, SensorData, BinarySensorData, EventData, DeviceInfo
from database import BTHomeDatabase, DatabaseConfig


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def database(temp_db):
    """Create a BTHomeDatabase instance for testing"""
    db = BTHomeDatabase(db_path=temp_db)
    db.initialize()
    return db


class TestDatabaseInitialization:
    """Test database initialization"""
    
    def test_initialize_creates_tables(self, temp_db):
        """Test that initialize creates all required tables"""
        db = BTHomeDatabase(db_path=temp_db)
        db.initialize()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check all tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'devices',
            'advertisements',
            'sensor_readings',
            'binary_sensor_readings',
            'events'
        ]
        
        for table in expected_tables:
            assert table in tables, f"Table {table} not found"
        
        conn.close()
    
    def test_initialize_creates_indexes(self, temp_db):
        """Test that initialize creates all required indexes"""
        db = BTHomeDatabase(db_path=temp_db)
        db.initialize()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check all indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        expected_indexes = [
            'idx_advertisements_device_id',
            'idx_advertisements_timestamp',
            'idx_sensor_readings_advertisement_id',
            'idx_sensor_readings_name',
            'idx_sensor_readings_timestamp_adv',  # Renamed to avoid conflict
            'idx_sensor_readings_device_name_timestamp',  # New optimized index
            'idx_sensor_readings_name_device_timestamp',  # New optimized index
            'idx_sensor_readings_name_timestamp',  # New optimized index
            'idx_sensor_readings_device_name',  # New optimized index
            'idx_binary_sensor_readings_advertisement_id',
            'idx_binary_sensor_readings_name',
            'idx_binary_sensor_readings_device_name_timestamp',  # New optimized index
            'idx_binary_sensor_readings_device_name',  # New optimized index
            'idx_events_advertisement_id',
            'idx_events_device_type',
            'idx_events_device_type_timestamp',  # New optimized index
            'idx_devices_address'
        ]
        
        for index in expected_indexes:
            assert index in indexes, f"Index {index} not found"
        
        conn.close()


class TestDeviceStorage:
    """Test device storage and retrieval"""
    
    def test_store_and_get_device(self, database):
        """Test storing and retrieving a device"""
        # Create a BTHomeData object for testing
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            device_info=DeviceInfo(device_type_id=123, firmware_version="1.0.0")
        )
        
        # Store an advertisement (which will create the device)
        address = "AA:BB:CC:DD:EE:FF"
        name = "Test Device"
        ad_id = database.store_advertisement(
            address=address,
            name=name,
            bthome_data=bthome_data
        )
        
        # Retrieve the device
        device = database.get_device(address)
        
        assert device is not None
        assert device['address'] == address
        assert device['name'] == name
        assert device['advertisement_count'] == 1
        assert device['first_seen'] is not None
        assert device['last_seen'] is not None
    
    def test_get_all_devices(self, database):
        """Test getting all devices"""
        # Store multiple devices
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False
        )
        
        database.store_advertisement(
            address="AA:BB:CC:DD:EE:FF",
            name="Device 1",
            bthome_data=bthome_data
        )
        database.store_advertisement(
            address="11:22:33:44:55:66",
            name="Device 2",
            bthome_data=bthome_data
        )
        
        devices = database.get_devices()
        
        assert len(devices) == 2
        addresses = [d['address'] for d in devices]
        assert "AA:BB:CC:DD:EE:FF" in addresses
        assert "11:22:33:44:55:66" in addresses
    
    def test_device_update_on_new_advertisement(self, database):
        """Test that device is updated when new advertisement is received"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        
        # Store first advertisement
        database.store_advertisement(
            address=address,
            name="Original Name",
            bthome_data=bthome_data
        )
        
        device1 = database.get_device(address)
        assert device1['advertisement_count'] == 1
        assert device1['name'] == "Original Name"
        first_seen = device1['first_seen']
        
        # Store second advertisement with different name
        database.store_advertisement(
            address=address,
            name="Updated Name",
            bthome_data=bthome_data
        )
        
        device2 = database.get_device(address)
        assert device2['advertisement_count'] == 2
        assert device2['name'] == "Updated Name"  # Name should be updated
        assert device2['first_seen'] == first_seen  # First seen should not change
        assert device2['last_seen'] != first_seen  # Last seen should be updated


class TestAdvertisementStorage:
    """Test advertisement storage and retrieval"""
    
    def test_store_advertisement(self, database):
        """Test storing an advertisement"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            packet_id=42,
            device_info=DeviceInfo(device_type_id=123, firmware_version="1.0.0")
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        assert ad_id > 0
        
        # Verify advertisement was stored
        ads = database.get_advertisements(device_address=address)
        assert len(ads) == 1
        assert ads[0]['id'] == ad_id
        assert ads[0]['bthome_version'] == 2
        assert ads[0]['is_encrypted'] == 0
        assert ads[0]['is_trigger_based'] == 0
        assert ads[0]['packet_id'] == 42
        assert ads[0]['device_type_id'] == 123
        assert ads[0]['firmware_version'] == "1.0.0"
    
    def test_store_advertisement_with_sensors(self, database):
        """Test storing advertisement with sensor data"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
                SensorData(object_id=0x03, name="humidity", value=45.0, unit="%"),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get sensor readings
        readings = database.get_sensor_readings(device_address=address)
        
        assert len(readings) == 2
        
        # Check first sensor
        temp_reading = [r for r in readings if r['name'] == 'temperature'][0]
        assert temp_reading['value'] == 22.5
        assert temp_reading['unit'] == "°C"
        assert temp_reading['position'] == 0
        assert temp_reading['object_id'] == 0x02
        
        # Check second sensor
        humidity_reading = [r for r in readings if r['name'] == 'humidity'][0]
        assert humidity_reading['value'] == 45.0
        assert humidity_reading['unit'] == "%"
        assert humidity_reading['position'] == 1
        assert humidity_reading['object_id'] == 0x03
    
    def test_store_advertisement_with_binary_sensors(self, database):
        """Test storing advertisement with binary sensor data"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            binary_sensors=[
                BinarySensorData(object_id=0x11, name="opening", value=True),
                BinarySensorData(object_id=0x21, name="motion", value=False),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get binary sensor readings
        readings = database.get_binary_sensor_readings(device_address=address)
        
        assert len(readings) == 2
        
        # Check first binary sensor
        opening_reading = [r for r in readings if r['name'] == 'opening'][0]
        assert opening_reading['value'] == 1  # True = 1
        assert opening_reading['position'] == 0
        
        # Check second binary sensor
        motion_reading = [r for r in readings if r['name'] == 'motion'][0]
        assert motion_reading['value'] == 0  # False = 0
        assert motion_reading['position'] == 1
    
    def test_store_advertisement_with_events(self, database):
        """Test storing advertisement with event data"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            events=[
                EventData(device_type="button", event_type="press", event_property=None),
                EventData(device_type="button", event_type="double_press", event_property=None),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get events
        events = database.get_events(device_address=address)
        
        assert len(events) == 2
        
        # Check first event
        press_event = [e for e in events if e['event_type'] == 'press'][0]
        assert press_event['device_type'] == 'button'
        assert press_event['position'] == 0
        
        # Check second event
        double_press_event = [e for e in events if e['event_type'] == 'double_press'][0]
        assert double_press_event['device_type'] == 'button'
        assert double_press_event['position'] == 1
    
    def test_store_advertisement_with_event_properties(self, database):
        """Test storing advertisement with event properties"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            events=[
                EventData(
                    device_type="dimmer",
                    event_type="rotate_right",
                    event_property={"steps": 5}
                ),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get events
        events = database.get_events(device_address=address)
        
        assert len(events) == 1
        assert events[0]['event_property'] == '{"steps": 5}'
    
    def test_get_advertisement_data(self, database):
        """Test getting all data for a specific advertisement"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
            ],
            binary_sensors=[
                BinarySensorData(object_id=0x11, name="opening", value=True),
            ],
            events=[
                EventData(device_type="button", event_type="press"),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        ad_id = database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get all data for this advertisement
        ad_data = database.get_advertisement_data(ad_id)
        
        assert ad_data is not None
        assert 'advertisement' in ad_data
        assert 'sensors' in ad_data
        assert 'binary_sensors' in ad_data
        assert 'events' in ad_data
        
        assert len(ad_data['sensors']) == 1
        assert len(ad_data['binary_sensors']) == 1
        assert len(ad_data['events']) == 1


class TestQueryFiltering:
    """Test query filtering capabilities"""
    
    def test_filter_sensor_readings_by_name(self, database):
        """Test filtering sensor readings by sensor name"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
                SensorData(object_id=0x03, name="humidity", value=45.0, unit="%"),
                SensorData(object_id=0x02, name="temperature", value=23.0, unit="°C"),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        # Get only temperature readings
        readings = database.get_sensor_readings(sensor_name="temperature")
        
        assert len(readings) == 2
        assert all(r['name'] == 'temperature' for r in readings)
    
    def test_filter_by_device_and_sensor(self, database):
        """Test filtering by both device and sensor name"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
                SensorData(object_id=0x03, name="humidity", value=45.0, unit="%"),
            ]
        )
        
        # Store for two devices
        database.store_advertisement(
            address="AA:BB:CC:DD:EE:FF",
            name="Device 1",
            bthome_data=bthome_data
        )
        database.store_advertisement(
            address="11:22:33:44:55:66",
            name="Device 2",
            bthome_data=bthome_data
        )
        
        # Get temperature readings from first device only
        readings = database.get_sensor_readings(
            device_address="AA:BB:CC:DD:EE:FF",
            sensor_name="temperature"
        )
        
        assert len(readings) == 1
        assert readings[0]['name'] == 'temperature'
        assert readings[0]['device_name'] == 'Device 1'
    
    def test_limit_results(self, database):
        """Test limiting query results"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        
        # Store multiple advertisements
        for i in range(5):
            database.store_advertisement(
                address=address,
                name="Test Device",
                bthome_data=bthome_data
            )
        
        # Get limited results
        readings = database.get_sensor_readings(device_address=address, limit=3)
        
        assert len(readings) == 3


class TestStatistics:
    """Test database statistics"""
    
    def test_get_statistics(self, database):
        """Test getting database statistics"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
            ],
            binary_sensors=[
                BinarySensorData(object_id=0x11, name="opening", value=True),
            ],
            events=[
                EventData(device_type="button", event_type="press"),
            ]
        )
        
        # Store advertisements for two devices
        database.store_advertisement(
            address="AA:BB:CC:DD:EE:FF",
            name="Device 1",
            bthome_data=bthome_data
        )
        database.store_advertisement(
            address="11:22:33:44:55:66",
            name="Device 2",
            bthome_data=bthome_data
        )
        
        stats = database.get_statistics()
        
        assert stats['device_count'] == 2
        assert stats['advertisement_count'] == 2
        assert stats['sensor_reading_count'] == 2
        assert stats['binary_sensor_reading_count'] == 2
        assert stats['event_count'] == 2
        assert 'database_size_bytes' in stats


class TestDatabaseConfig:
    """Test database configuration"""
    
    def test_custom_config(self, temp_db):
        """Test custom database configuration"""
        config = DatabaseConfig(
            db_path=temp_db,
            enable_wal=False,
            synchronous="FULL",
            journal_mode="DELETE"
        )
        
        db = BTHomeDatabase(config=config)
        db.initialize()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check journal mode (SQLite returns lowercase)
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "delete"
        
        # Check synchronous mode (SQLite returns integer for some modes)
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        # synchronous can be integer (0=OFF, 1=NORMAL, 2=FULL) or string
        if isinstance(synchronous, int):
            # FULL = 2
            assert synchronous == 2
        else:
            assert synchronous.lower() == "full"
        
        conn.close()


class TestContextManager:
    """Test context manager functionality"""
    
    def test_context_manager(self, temp_db):
        """Test using database as context manager"""
        with BTHomeDatabase(db_path=temp_db) as db:
            db.initialize()
            
            bthome_data = BTHomeData(
                uuid=0xFCD2,
                version=2,
                is_encrypted=False,
                is_trigger_based=False
            )
            
            db.store_advertisement(
                address="AA:BB:CC:DD:EE:FF",
                name="Test Device",
                bthome_data=bthome_data
            )
            
            devices = db.get_devices()
            assert len(devices) == 1
        
        # Database should be closed after context exit
        # (We can't directly test this without accessing private members)


class TestTextSensorValues:
    """Test handling of text sensor values"""
    
    def test_store_text_sensor_value(self, database):
        """Test storing text sensor values"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x53, name="text", value="Hello, World!", unit=""),
            ]
        )
        
        address = "AA:BB:CC:DD:EE:FF"
        database.store_advertisement(
            address=address,
            name="Test Device",
            bthome_data=bthome_data
        )
        
        readings = database.get_sensor_readings(device_address=address)
        
        assert len(readings) == 1
        assert readings[0]['value'] is None  # Numeric value should be NULL
        assert readings[0]['value_text'] == "Hello, World!"


class TestOptimizedHistoryQueries:
    """Test optimized history query methods"""
    
    def test_get_sensor_history(self, database):
        """Test optimized sensor history query"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
                SensorData(object_id=0x03, name="humidity", value=45.0, unit="%"),
            ]
        )
        
        # Store multiple advertisements
        for i in range(5):
            database.store_advertisement(
                address="AA:BB:CC:DD:EE:FF",
                name="Device 1",
                bthome_data=bthome_data
            )
        
        # Get temperature history using optimized method
        history = database.get_sensor_history(
            device_address="AA:BB:CC:DD:EE:FF",
            sensor_name="temperature"
        )
        
        assert len(history) == 5
        assert all(h['name'] == 'temperature' for h in history)
        assert all('timestamp' in h for h in history)
        assert all('device_name' in h for h in history)
    
    def test_get_sensor_history_by_name_only(self, database):
        """Test getting sensor history by name only (all devices)"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            sensors=[
                SensorData(object_id=0x02, name="temperature", value=22.5, unit="°C"),
            ]
        )
        
        # Store for two devices
        database.store_advertisement(
            address="AA:BB:CC:DD:EE:FF",
            name="Device 1",
            bthome_data=bthome_data
        )
        database.store_advertisement(
            address="11:22:33:44:55:66",
            name="Device 2",
            bthome_data=bthome_data
        )
        
        # Get all temperature readings
        history = database.get_sensor_history(sensor_name="temperature")
        
        assert len(history) == 2
        assert all(h['name'] == 'temperature' for h in history)
    
    def test_get_binary_sensor_history(self, database):
        """Test optimized binary sensor history query"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            binary_sensors=[
                BinarySensorData(object_id=0x11, name="motion", value=True),
            ]
        )
        
        # Store multiple advertisements
        for i in range(3):
            database.store_advertisement(
                address="AA:BB:CC:DD:EE:FF",
                name="Device 1",
                bthome_data=bthome_data
            )
        
        # Get motion history using optimized method
        history = database.get_binary_sensor_history(
            device_address="AA:BB:CC:DD:EE:FF",
            sensor_name="motion"
        )
        
        assert len(history) == 3
        assert all(h['name'] == 'motion' for h in history)
        assert all('timestamp' in h for h in history)
    
    def test_get_event_history(self, database):
        """Test optimized event history query"""
        bthome_data = BTHomeData(
            uuid=0xFCD2,
            version=2,
            is_encrypted=False,
            is_trigger_based=False,
            events=[
                EventData(device_type="button", event_type="press"),
            ]
        )
        
        # Store multiple advertisements
        for i in range(4):
            database.store_advertisement(
                address="AA:BB:CC:DD:EE:FF",
                name="Device 1",
                bthome_data=bthome_data
            )
        
        # Get button press history using optimized method
        history = database.get_event_history(
            device_address="AA:BB:CC:DD:EE:FF",
            event_type="press"
        )
        
        assert len(history) == 4
        assert all(h['event_type'] == 'press' for h in history)
        assert all('timestamp' in h for h in history)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
