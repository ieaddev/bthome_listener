"""
BTHome v2 Decoder Module

This module decodes BTHome v2 BLE advertisement data according to the specification
at https://bthome.io/format/
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timezone

# BTHome UUID (16-bit, little-endian: 0xFCD2)
BTHOME_UUID = 0xFCD2

# BTHome Device Info flags
BTHOME_ENCRYPTION_FLAG = 0x01
BTHOME_TRIGGER_BASED_FLAG = 0x04
BTHOME_VERSION_MASK = 0xE0  # bits 5-7
BTHOME_VERSION_SHIFT = 5


@dataclass
class SensorData:
    """Represents decoded sensor data from BTHome"""
    object_id: int
    name: str
    value: Union[float, int, str, bool, datetime]
    unit: str = ""
    
    def __str__(self):
        if isinstance(self.value, float):
            return f"{self.name}: {self.value:.2f} {self.unit}" if self.unit else f"{self.name}: {self.value:.2f}"
        return f"{self.name}: {self.value} {self.unit}" if self.unit else f"{self.name}: {self.value}"


@dataclass
class BinarySensorData:
    """Represents decoded binary sensor data from BTHome"""
    object_id: int
    name: str
    value: bool
    
    def __str__(self):
        return f"{self.name}: {'ON' if self.value else 'OFF'}"


@dataclass
class EventData:
    """Represents decoded event data from BTHome"""
    device_type: str
    event_type: str
    event_property: Optional[Dict[str, Any]] = None
    
    def __str__(self):
        if self.event_property:
            return f"{self.device_type}: {self.event_type} ({self.event_property})"
        return f"{self.device_type}: {self.event_type}"


@dataclass
class DeviceInfo:
    """Represents BTHome device information"""
    device_type_id: Optional[int] = None
    firmware_version: Optional[str] = None


@dataclass
class BTHomeData:
    """Represents complete decoded BTHome data"""
    uuid: int
    version: int
    is_encrypted: bool
    is_trigger_based: bool
    packet_id: Optional[int] = None
    device_info: DeviceInfo = field(default_factory=DeviceInfo)
    sensors: List[SensorData] = field(default_factory=list)
    binary_sensors: List[BinarySensorData] = field(default_factory=list)
    events: List[EventData] = field(default_factory=list)
    raw_data: bytes = b''
    
    def __str__(self):
        lines = [
            f"BTHome v{self.version}",
            f"  UUID: 0x{self.uuid:04X}",
            f"  Encrypted: {self.is_encrypted}",
            f"  Trigger-based: {self.is_trigger_based}",
        ]
        if self.packet_id is not None:
            lines.append(f"  Packet ID: {self.packet_id}")
        if self.device_info.device_type_id is not None:
            lines.append(f"  Device Type ID: {self.device_info.device_type_id}")
        if self.device_info.firmware_version:
            lines.append(f"  Firmware: {self.device_info.firmware_version}")
        
        for sensor in self.sensors:
            lines.append(f"  [Sensor] {sensor}")
        for binary in self.binary_sensors:
            lines.append(f"  [Binary] {binary}")
        for event in self.events:
            lines.append(f"  [Event] {event}")
        
        return "\n".join(lines)


# Sensor data type definitions
# Format: (name, data_type, factor, unit)
SENSOR_TYPES = {
    # Temperature
    0x02: ("temperature", "sint16", 0.01, "°C"),
    0x45: ("temperature", "sint16", 0.1, "°C"),
    0x57: ("temperature", "sint8", 1, "°C"),
    0x58: ("temperature", "sint8", 0.35, "°C"),
    
    # Humidity
    0x03: ("humidity", "uint16", 0.01, "%"),
    0x2E: ("humidity", "uint8", 1, "%"),
    
    # Pressure
    0x04: ("pressure", "uint24", 0.01, "hPa"),
    
    # Illuminance
    0x05: ("illuminance", "uint24", 0.01, "lx"),
    
    # Mass
    0x06: ("mass", "uint16", 0.01, "kg"),
    0x07: ("mass", "uint16", 0.01, "lb"),
    
    # Moisture
    0x14: ("moisture", "uint16", 0.01, "%"),
    0x2F: ("moisture", "uint8", 1, "%"),
    
    # Battery
    0x01: ("battery", "uint8", 1, "%"),
    
    # Count
    0x09: ("count", "uint8", 1, ""),
    0x3D: ("count", "uint16", 1, ""),
    0x3E: ("count", "uint32", 1, ""),
    0x59: ("count", "sint8", 1, ""),
    0x5A: ("count", "sint16", 1, ""),
    0x5B: ("count", "sint32", 1, ""),
    
    # Power
    0x0B: ("power", "uint24", 0.01, "W"),
    0x5C: ("power", "sint32", 0.01, "W"),
    
    # Energy
    0x0A: ("energy", "uint24", 0.001, "kWh"),
    0x4D: ("energy", "uint32", 0.001, "kWh"),
    
    # Voltage
    0x0C: ("voltage", "uint16", 0.001, "V"),
    0x4A: ("voltage", "uint16", 0.1, "V"),
    
    # Current
    0x43: ("current", "uint16", 0.001, "A"),
    0x5D: ("current", "sint16", 0.001, "A"),
    
    # CO2
    0x12: ("co2", "uint16", 1, "ppm"),
    
    # TVOC
    0x13: ("tvoc", "uint16", 1, "ug/m3"),
    
    # PM2.5
    0x0D: ("pm2.5", "uint16", 1, "ug/m3"),
    
    # PM10
    0x0E: ("pm10", "uint16", 1, "ug/m3"),
    
    # Dewpoint
    0x08: ("dewpoint", "sint16", 0.01, "°C"),
    
    # Distance
    0x40: ("distance", "uint16", 1, "mm"),
    0x41: ("distance", "uint16", 0.1, "m"),
    
    # Duration
    0x42: ("duration", "uint24", 0.001, "s"),
    
    # Speed
    0x44: ("speed", "uint16", 0.01, "m/s"),
    0x62: ("speed", "sint32", 0.000001, "m/s"),
    
    # Acceleration
    0x51: ("acceleration", "uint16", 0.001, "m/s²"),
    0x63: ("acceleration", "sint32", 0.000001, "m/s²"),
    
    # Gyroscope
    0x52: ("gyroscope", "uint16", 0.001, "°/s"),
    
    # Direction
    0x5E: ("direction", "uint16", 0.01, "°"),
    
    # Rotation
    0x3F: ("rotation", "sint16", 0.1, "°"),
    
    # Rotational speed
    0x61: ("rotational_speed", "uint16", 1, "rpm"),
    
    # Conductivity
    0x56: ("conductivity", "uint16", 1, "µS/cm"),
    
    # Gas
    0x4B: ("gas", "uint24", 0.001, "m3"),
    0x4C: ("gas", "uint32", 0.001, "m3"),
    
    # Volume
    0x47: ("volume", "uint16", 0.1, "L"),
    0x48: ("volume", "uint16", 1, "mL"),
    0x4E: ("volume", "uint32", 0.001, "L"),
    0x49: ("volume_flow_rate", "uint16", 0.001, "m3/hr"),
    0x55: ("volume_storage", "uint32", 0.001, "L"),
    
    # Water
    0x4F: ("water", "uint32", 0.001, "L"),
    
    # Precipitation
    0x5F: ("precipitation", "uint16", 0.1, "mm"),
    
    # UV Index
    0x46: ("uv_index", "uint8", 0.1, ""),
    
    # Light level
    0x64: ("light_level", "uint8", 1, ""),
    
    # Channel
    0x60: ("channel", "uint8", 1, ""),
    
    # Settings revision
    0x65: ("settings_revision", "uint8", 1, ""),
    
    # Timestamp
    0x50: ("timestamp", "uint32", None, ""),
    
    # Text (variable length)
    0x53: ("text", "text", None, ""),
    
    # Raw (variable length)
    0x54: ("raw", "raw", None, ""),
}

# Binary sensor types
BINARY_SENSOR_TYPES = {
    0x0F: ("generic_boolean", "Generic Boolean"),
    0x10: ("power", "Power"),
    0x11: ("opening", "Opening"),
    0x12: ("co2", "CO2"),
    0x13: ("tvoc", "TVOC"),
    0x14: ("moisture", "Moisture"),
    0x15: ("battery", "Battery Low"),
    0x16: ("battery_charging", "Battery Charging"),
    0x17: ("carbon_monoxide", "Carbon Monoxide"),
    0x18: ("cold", "Cold"),
    0x19: ("connectivity", "Connectivity"),
    0x1A: ("door", "Door"),
    0x1B: ("garage_door", "Garage Door"),
    0x1C: ("gas", "Gas"),
    0x1D: ("heat", "Heat"),
    0x1E: ("light", "Light"),
    0x1F: ("lock", "Lock"),
    0x20: ("moisture", "Moisture"),
    0x21: ("motion", "Motion"),
    0x22: ("moving", "Moving"),
    0x23: ("occupancy", "Occupancy"),
    0x24: ("plug", "Plug"),
    0x25: ("presence", "Presence"),
    0x26: ("problem", "Problem"),
    0x27: ("running", "Running"),
    0x28: ("safety", "Safety"),
    0x29: ("smoke", "Smoke"),
    0x2A: ("sound", "Sound"),
    0x2B: ("tamper", "Tamper"),
    0x2C: ("vibration", "Vibration"),
    0x2D: ("window", "Window"),
}

# Event types
EVENT_TYPES = {
    0x3A: {
        "name": "button",
        "events": {
            0x00: ("none", None),
            0x01: ("press", None),
            0x02: ("double_press", None),
            0x03: ("triple_press", None),
            0x04: ("long_press", None),
            0x05: ("long_double_press", None),
            0x06: ("long_triple_press", None),
            0x80: ("hold_press", None),
        }
    },
    0x3B: {
        "name": "command",
        "events": {
            0x00: ("off", None),
            0x01: ("on", None),
            0x02: ("toggle", None),
            0x03: ("step_up", "steps"),
            0x04: ("step_down", "steps"),
        }
    },
    0x3C: {
        "name": "dimmer",
        "events": {
            0x00: ("none", None),
            0x01: ("rotate_left", "steps"),
            0x02: ("rotate_right", "steps"),
        }
    }
}

# Device info types
DEVICE_INFO_TYPES = {
    0xF0: ("device_type_id", "uint16", None),
    0xF1: ("firmware_version", "uint32", None),
    0xF2: ("firmware_version", "uint24", None),
}

# Packet ID
PACKET_ID = 0x00


class BTHomeDecoder:
    """Decoder for BTHome v2 BLE advertisement data"""
    
    @staticmethod
    def extract_bthome_data(advertisement_data: bytes) -> Optional[bytes]:
        """
        Extract BTHome data from BLE advertisement payload.
        
        Args:
            advertisement_data: Raw BLE advertisement payload
            
        Returns:
            BTHome service data if found, None otherwise
        """
        # Parse AD elements
        pos = 0
        while pos < len(advertisement_data):
            if pos + 1 > len(advertisement_data):
                break
            
            length = advertisement_data[pos]
            if length == 0:
                break
            
            # Prevent going beyond the data
            if pos + 1 + length > len(advertisement_data):
                break
            
            ad_type = advertisement_data[pos + 1]
            # ad_data includes everything after the type byte, for the specified length - 1
            ad_data_start = pos + 2
            ad_data_end = pos + 1 + length
            ad_data = advertisement_data[ad_data_start:ad_data_end]
            
            # Check for Service Data (16-bit UUID) - AD type 0x16
            if ad_type == 0x16 and len(ad_data) >= 2:
                # First 2 bytes are the UUID
                uuid = struct.unpack('<H', ad_data[:2])[0]
                if uuid == BTHOME_UUID:
                    # Return the BTHome data (after the UUID)
                    return ad_data[2:]
            
            # Also check for Service Data (128-bit UUID) - AD type 0x20 or 0x21
            if ad_type in (0x20, 0x21) and len(ad_data) >= 16:
                # Check if this contains BTHome UUID (0xFCD2)
                # The 16-bit UUID might be embedded in the 128-bit UUID
                # BTHome uses 0xFCD2 as 16-bit UUID
                # In 128-bit format: 0000FC00-0000-1000-8000-00805F9B34FB
                uuid_128 = ad_data[:16]
                # Check for 0xFC, 0xD2 in the UUID (little-endian)
                if len(uuid_128) >= 4:
                    # Check for 0xD2, 0xFC in the UUID
                    if uuid_128[2] == 0xD2 and uuid_128[3] == 0xFC:
                        # Return the service data
                        return ad_data[16:]
            
            # Also check manufacturer data for BTHome
            # Some devices might use manufacturer data with BTHome UUID
            if ad_type == 0xFF and len(ad_data) >= 2:
                # Check if the manufacturer data starts with BTHome UUID
                uuid = struct.unpack('<H', ad_data[:2])[0]
                if uuid == BTHOME_UUID:
                    return ad_data[2:]
            
            pos += 1 + length
        
        return None
    
    @staticmethod
    def decode_device_info(device_info_byte: int) -> tuple:
        """
        Decode BTHome device info byte.
        
        Returns:
            (version, is_encrypted, is_trigger_based)
        """
        version = (device_info_byte & BTHOME_VERSION_MASK) >> BTHOME_VERSION_SHIFT
        is_encrypted = bool(device_info_byte & BTHOME_ENCRYPTION_FLAG)
        is_trigger_based = bool(device_info_byte & BTHOME_TRIGGER_BASED_FLAG)
        return version, is_encrypted, is_trigger_based
    
    @staticmethod
    def _read_uint8(data: bytes, offset: int) -> tuple:
        """Read uint8 from data at offset"""
        return data[offset], offset + 1
    
    @staticmethod
    def _read_sint8(data: bytes, offset: int) -> tuple:
        """Read sint8 from data at offset"""
        return struct.unpack('<b', data[offset:offset+1])[0], offset + 1
    
    @staticmethod
    def _read_uint16(data: bytes, offset: int) -> tuple:
        """Read uint16 (little-endian) from data at offset"""
        return struct.unpack('<H', data[offset:offset+2])[0], offset + 2
    
    @staticmethod
    def _read_sint16(data: bytes, offset: int) -> tuple:
        """Read sint16 (little-endian) from data at offset"""
        return struct.unpack('<h', data[offset:offset+2])[0], offset + 2
    
    @staticmethod
    def _read_uint24(data: bytes, offset: int) -> tuple:
        """Read uint24 (little-endian) from data at offset"""
        return struct.unpack('<I', data[offset:offset+3] + b'\x00')[0], offset + 3
    
    @staticmethod
    def _read_sint24(data: bytes, offset: int) -> tuple:
        """Read sint24 (little-endian) from data at offset"""
        val = struct.unpack('<I', data[offset:offset+3] + b'\x00')[0]
        if val & 0x00800000:
            val = val | 0xFF000000
        return val, offset + 3
    
    @staticmethod
    def _read_uint32(data: bytes, offset: int) -> tuple:
        """Read uint32 (little-endian) from data at offset"""
        return struct.unpack('<I', data[offset:offset+4])[0], offset + 4
    
    @staticmethod
    def _read_sint32(data: bytes, offset: int) -> tuple:
        """Read sint32 (little-endian) from data at offset"""
        return struct.unpack('<i', data[offset:offset+4])[0], offset + 4
    
    @staticmethod
    def decode_sensor(object_id: int, data: bytes, offset: int) -> tuple:
        """
        Decode a sensor value based on its object_id.
        
        Returns:
            (sensor_data, new_offset)
        """
        if object_id not in SENSOR_TYPES:
            return None, offset
        
        name, data_type, factor, unit = SENSOR_TYPES[object_id]
        
        if data_type == "uint8":
            value, offset = BTHomeDecoder._read_uint8(data, offset)
        elif data_type == "sint8":
            value, offset = BTHomeDecoder._read_sint8(data, offset)
        elif data_type == "uint16":
            value, offset = BTHomeDecoder._read_uint16(data, offset)
        elif data_type == "sint16":
            value, offset = BTHomeDecoder._read_sint16(data, offset)
        elif data_type == "uint24":
            value, offset = BTHomeDecoder._read_uint24(data, offset)
        elif data_type == "sint24":
            value, offset = BTHomeDecoder._read_sint24(data, offset)
        elif data_type == "uint32":
            value, offset = BTHomeDecoder._read_uint32(data, offset)
        elif data_type == "sint32":
            value, offset = BTHomeDecoder._read_sint32(data, offset)
        elif data_type == "text":
            # First byte is length
            text_length, offset = BTHomeDecoder._read_uint8(data, offset)
            text_bytes = data[offset:offset+text_length]
            value = text_bytes.decode('utf-8', errors='replace')
            offset += text_length
            return SensorData(object_id, name, value, unit), offset
        elif data_type == "raw":
            # First byte is length
            raw_length, offset = BTHomeDecoder._read_uint8(data, offset)
            raw_bytes = data[offset:offset+raw_length]
            value = raw_bytes.hex()
            offset += raw_length
            return SensorData(object_id, name, value, unit), offset
        elif data_type == "timestamp":
            value, offset = BTHomeDecoder._read_uint32(data, offset)
            # Convert to datetime
            value = datetime.fromtimestamp(value, tz=timezone.utc)
            return SensorData(object_id, name, value, unit), offset
        else:
            return None, offset
        
        # Apply factor if specified
        if factor is not None:
            value = value * factor
        
        return SensorData(object_id, name, value, unit), offset
    
    @staticmethod
    def decode_binary_sensor(object_id: int, data: bytes, offset: int) -> tuple:
        """
        Decode a binary sensor value.
        
        Returns:
            (binary_sensor_data, new_offset)
        """
        if object_id not in BINARY_SENSOR_TYPES:
            return None, offset
        
        name, display_name = BINARY_SENSOR_TYPES[object_id]
        value, offset = BTHomeDecoder._read_uint8(data, offset)
        
        return BinarySensorData(object_id, display_name, bool(value)), offset
    
    @staticmethod
    def decode_event(object_id: int, data: bytes, offset: int) -> tuple:
        """
        Decode an event.
        
        Returns:
            (event_data, new_offset)
        """
        if object_id not in EVENT_TYPES:
            return None, offset
        
        device_info = EVENT_TYPES[object_id]
        device_type = device_info["name"]
        
        # Read event ID
        event_id, offset = BTHomeDecoder._read_uint8(data, offset)
        
        if event_id not in device_info["events"]:
            return None, offset
        
        event_name, property_name = device_info["events"][event_id]
        
        # Handle events with properties
        event_property = None
        if property_name is not None:
            if property_name == "steps":
                steps, offset = BTHomeDecoder._read_uint8(data, offset)
                event_property = {property_name: steps}
            elif property_name == "step":
                # For command events with step up/down
                if event_id in [0x03, 0x04]:  # step_up, step_down
                    steps, offset = BTHomeDecoder._read_uint8(data, offset)
                    event_property = {property_name: steps}
        
        return EventData(device_type, event_name, event_property), offset
    
    @staticmethod
    def decode_device_info_field(object_id: int, data: bytes, offset: int) -> tuple:
        """
        Decode device info field.
        
        Returns:
            (device_info, new_offset)
        """
        if object_id not in DEVICE_INFO_TYPES:
            return None, offset
        
        field_name, data_type, _ = DEVICE_INFO_TYPES[object_id]
        
        if data_type == "uint16":
            value, offset = BTHomeDecoder._read_uint16(data, offset)
        elif data_type == "uint24":
            value, offset = BTHomeDecoder._read_uint24(data, offset)
        elif data_type == "uint32":
            value, offset = BTHomeDecoder._read_uint32(data, offset)
        else:
            return None, offset
        
        # For firmware version, format it properly
        if field_name == "firmware_version":
            if data_type == "uint32":
                # Format as X.X.X.X
                parts = [
                    (value >> 24) & 0xFF,
                    (value >> 16) & 0xFF,
                    (value >> 8) & 0xFF,
                    value & 0xFF
                ]
                value = ".".join(str(p) for p in parts)
            elif data_type == "uint24":
                # Format as X.X.X
                parts = [
                    (value >> 16) & 0xFF,
                    (value >> 8) & 0xFF,
                    value & 0xFF
                ]
                value = ".".join(str(p) for p in parts)
        
        return (field_name, value), offset
    
    @staticmethod
    def decode_bthome_data(bthome_data: bytes) -> Optional[BTHomeData]:
        """
        Decode BTHome v2 data from service data.
        
        Args:
            bthome_data: Raw BTHome service data (without UUID)
            
        Returns:
            Decoded BTHomeData object or None if decoding fails
        """
        if len(bthome_data) < 1:
            return None
        
        result = BTHomeData(
            uuid=BTHOME_UUID,
            version=0,
            is_encrypted=False,
            is_trigger_based=False,
            raw_data=bthome_data
        )
        
        offset = 0
        
        # First byte should be device info
        if offset >= len(bthome_data):
            return None
        
        device_info_byte = bthome_data[offset]
        offset += 1
        
        version, is_encrypted, is_trigger_based = BTHomeDecoder.decode_device_info(device_info_byte)
        result.version = version
        result.is_encrypted = is_encrypted
        result.is_trigger_based = is_trigger_based
        
        # If encrypted, we can't decode further without the key
        if is_encrypted:
            return result
        
        # Parse remaining data
        while offset < len(bthome_data):
            if offset >= len(bthome_data):
                break
            
            object_id = bthome_data[offset]
            offset += 1
            
            # Handle packet ID
            if object_id == PACKET_ID:
                packet_id, offset = BTHomeDecoder._read_uint8(bthome_data, offset)
                result.packet_id = packet_id
                continue
            
            # Handle device info fields
            if object_id in DEVICE_INFO_TYPES:
                field_info, offset = BTHomeDecoder.decode_device_info_field(
                    object_id, bthome_data, offset
                )
                if field_info:
                    field_name, value = field_info
                    if field_name == "device_type_id":
                        result.device_info.device_type_id = value
                    elif field_name == "firmware_version":
                        result.device_info.firmware_version = value
                continue
            
            # Handle sensor data
            if object_id in SENSOR_TYPES:
                sensor, offset = BTHomeDecoder.decode_sensor(
                    object_id, bthome_data, offset
                )
                if sensor:
                    result.sensors.append(sensor)
                continue
            
            # Handle binary sensor data
            if object_id in BINARY_SENSOR_TYPES:
                binary, offset = BTHomeDecoder.decode_binary_sensor(
                    object_id, bthome_data, offset
                )
                if binary:
                    result.binary_sensors.append(binary)
                continue
            
            # Handle event data
            if object_id in EVENT_TYPES:
                event, offset = BTHomeDecoder.decode_event(
                    object_id, bthome_data, offset
                )
                if event:
                    result.events.append(event)
                continue
            
            # Unknown object ID - skip it
            # According to spec, we should stop parsing here
            break
        
        return result
    
    @staticmethod
    def decode_advertisement(advertisement_data: bytes) -> Optional[BTHomeData]:
        """
        Complete decoding pipeline: extract BTHome data from advertisement and decode it.
        
        Args:
            advertisement_data: Raw BLE advertisement payload
            
        Returns:
            Decoded BTHomeData object or None if not a BTHome advertisement
        """
        bthome_data = BTHomeDecoder.extract_bthome_data(advertisement_data)
        if bthome_data is None:
            return None
        
        return BTHomeDecoder.decode_bthome_data(bthome_data)
