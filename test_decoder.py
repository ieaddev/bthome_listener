#!/usr/bin/env python3
"""
Test script for BTHome v2 decoder.

This script tests the decoder with example payloads from the BTHome specification.
"""

import sys
sys.path.insert(0, '/workspace/bthome_listener')

from bthome_decoder import BTHomeDecoder, BTHomeData


def test_basic_example():
    """Test the basic example from the BTHome specification"""
    print("Testing basic example from BTHome spec...")
    
    # Example from https://bthome.io/format/
    # Advertising payload: 020106 0B094449592D73656E736F72 0A16D2FC4002C40903BF13
    # Service data part: 0A16D2FC4002C40903BF13
    # BTHome data: D2FC4002C40903BF13
    
    # Construct the full advertisement payload
    advertisement = bytes.fromhex("020106 0B094449592D73656E736F72 0A16D2FC4002C40903BF13")
    
    # Decode
    result = BTHomeDecoder.decode_advertisement(advertisement)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    print(f"  UUID: 0x{result.uuid:04X}")
    print(f"  Version: {result.version}")
    print(f"  Encrypted: {result.is_encrypted}")
    print(f"  Trigger-based: {result.is_trigger_based}")
    
    # Check values
    assert result.uuid == 0xFCD2, f"Expected UUID 0xFCD2, got 0x{result.uuid:04X}"
    assert result.version == 2, f"Expected version 2, got {result.version}"
    assert not result.is_encrypted, "Expected unencrypted"
    assert not result.is_trigger_based, "Expected not trigger-based"
    
    # Check sensors
    assert len(result.sensors) == 2, f"Expected 2 sensors, got {len(result.sensors)}"
    
    # Temperature sensor (0x02)
    temp_sensor = result.sensors[0]
    assert temp_sensor.object_id == 0x02, f"Expected temperature object ID 0x02, got {temp_sensor.object_id:02X}"
    assert temp_sensor.name == "temperature", f"Expected name 'temperature', got '{temp_sensor.name}'"
    assert abs(temp_sensor.value - 25.00) < 0.01, f"Expected temperature ~25.00°C, got {temp_sensor.value}"
    assert temp_sensor.unit == "°C", f"Expected unit '°C', got '{temp_sensor.unit}'"
    
    # Humidity sensor (0x03)
    humidity_sensor = result.sensors[1]
    assert humidity_sensor.object_id == 0x03, f"Expected humidity object ID 0x03, got {humidity_sensor.object_id:02X}"
    assert humidity_sensor.name == "humidity", f"Expected name 'humidity', got '{humidity_sensor.name}'"
    assert abs(humidity_sensor.value - 50.55) < 0.01, f"Expected humidity ~50.55%, got {humidity_sensor.value}"
    assert humidity_sensor.unit == "%", f"Expected unit '%', got '{humidity_sensor.unit}'"
    
    print("  PASSED: All checks passed")
    print(f"  Decoded data:\n{result}")
    return True


def test_device_info():
    """Test device info fields"""
    print("\nTesting device info fields...")
    
    # Create a payload with device info
    # Device info byte: 0x40 (version 2, unencrypted, not trigger-based)
    # Device type ID: 0xF0 01 00 (device type 1)
    # Firmware version: 0xF1 00 01 02 04 (version 4.2.1.0)
    # Temperature: 0x02 CA 09 (25.06°C)
    
    bthome_data = bytes.fromhex("40 F00100 F100010204 02CA09")
    
    # Test direct decoding (bypassing advertisement parsing)
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert result.device_info.device_type_id == 1, f"Expected device type 1, got {result.device_info.device_type_id}"
    assert result.device_info.firmware_version == "4.2.1.0", f"Expected firmware 4.2.1.0, got {result.device_info.firmware_version}"
    
    print("  PASSED: Device info decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_binary_sensor():
    """Test binary sensor decoding"""
    print("\nTesting binary sensor...")
    
    # Device info byte: 0x40
    # Door sensor (0x1A) = 1 (open)
    bthome_data = bytes.fromhex("40 1A01")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert len(result.binary_sensors) == 1, f"Expected 1 binary sensor, got {len(result.binary_sensors)}"
    
    door_sensor = result.binary_sensors[0]
    assert door_sensor.object_id == 0x1A, f"Expected door sensor object ID 0x1A, got {door_sensor.object_id:02X}"
    assert door_sensor.name == "Door", f"Expected name 'Door', got '{door_sensor.name}'"
    assert door_sensor.value is True, f"Expected door to be open (True), got {door_sensor.value}"
    
    print("  PASSED: Binary sensor decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_event():
    """Test event decoding"""
    print("\nTesting event decoding...")
    
    # Device info byte: 0x40
    # Button press event (0x3A 0x01)
    bthome_data = bytes.fromhex("40 3A01")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert len(result.events) == 1, f"Expected 1 event, got {len(result.events)}"
    
    event = result.events[0]
    assert event.device_type == "button", f"Expected device type 'button', got '{event.device_type}'"
    assert event.event_type == "press", f"Expected event type 'press', got '{event.event_type}'"
    
    print("  PASSED: Event decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_packet_id():
    """Test packet ID"""
    print("\nTesting packet ID...")
    
    # Device info byte: 0x40
    # Packet ID: 0x00 0x09
    # Temperature: 0x02 CA 09
    bthome_data = bytes.fromhex("40 0009 02CA09")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert result.packet_id == 9, f"Expected packet ID 9, got {result.packet_id}"
    
    print("  PASSED: Packet ID decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_multiple_sensors():
    """Test multiple sensors of the same type"""
    print("\nTesting multiple sensors of same type...")
    
    # Device info byte: 0x40
    # Temperature 1: 0x02 CA 09 (25.06°C)
    # Temperature 2: 0x02 90 06 (15.36°C)
    bthome_data = bytes.fromhex("40 02CA09 029006")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert len(result.sensors) == 2, f"Expected 2 sensors, got {len(result.sensors)}"
    
    # Both should be temperature sensors
    for sensor in result.sensors:
        assert sensor.name == "temperature", f"Expected temperature sensor, got '{sensor.name}'"
    
    print("  PASSED: Multiple sensors decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_encrypted_data():
    """Test encrypted data detection"""
    print("\nTesting encrypted data detection...")
    
    # Device info byte: 0x41 (version 2, encrypted, not trigger-based)
    # Some encrypted data
    bthome_data = bytes.fromhex("41 AA BB CC DD")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert result.is_encrypted, "Expected encrypted flag to be True"
    assert len(result.sensors) == 0, "Encrypted data should not decode sensors"
    
    print("  PASSED: Encrypted data detected correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_trigger_based():
    """Test trigger-based device detection"""
    print("\nTesting trigger-based device detection...")
    
    # Device info byte: 0x44 (version 2, unencrypted, trigger-based)
    # Button press
    bthome_data = bytes.fromhex("44 3A01")
    
    # Test direct decoding
    result = BTHomeDecoder.decode_bthome_data(bthome_data)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    assert result.is_trigger_based, "Expected trigger-based flag to be True"
    
    print("  PASSED: Trigger-based device detected correctly")
    print(f"  Decoded data:\n{result}")
    return True


def test_advertisement_with_additional_data():
    """Test advertisement with BTHome data plus additional AD structures (flags, local name)"""
    print("\nTesting advertisement with additional data (flags + local name)...")
    
    # Raw advertisement data from user:
    # 02 01 06 - Flags (LE General Discovery)
    # 05 09 69 65 61 64 - Complete Local Name: "iead"
    # 0a 16 d2 fc 40 02 c4 09 03 bf 00 - Service Data with BTHome UUID
    # BTHome data: 40 02 c4 09 03 bf 00
    #   - 40: device info (version 2, unencrypted, not trigger-based)
    #   - 02 c4 09: temperature (0x09C4 = 2500 * 0.01 = 25.00°C)
    #   - 03 bf 00: humidity (0x00BF = 191 * 0.01 = 1.91%)
    
    advertisement = bytes.fromhex("02 01 06 05 09 69 65 61 64 0a 16 d2 fc 40 02 c4 09 03 bf 00")
    
    # Decode
    result = BTHomeDecoder.decode_advertisement(advertisement)
    
    if result is None:
        print("  FAILED: Could not decode advertisement")
        return False
    
    # Check BTHome header
    assert result.uuid == 0xFCD2, f"Expected UUID 0xFCD2, got 0x{result.uuid:04X}"
    assert result.version == 2, f"Expected version 2, got {result.version}"
    assert not result.is_encrypted, "Expected unencrypted"
    assert not result.is_trigger_based, "Expected not trigger-based"
    
    # Check sensors
    assert len(result.sensors) == 2, f"Expected 2 sensors, got {len(result.sensors)}"
    
    # Temperature sensor (0x02)
    temp_sensor = result.sensors[0]
    assert temp_sensor.object_id == 0x02, f"Expected temperature object ID 0x02, got {temp_sensor.object_id:02X}"
    assert temp_sensor.name == "temperature", f"Expected name 'temperature', got '{temp_sensor.name}'"
    assert abs(temp_sensor.value - 25.00) < 0.01, f"Expected temperature ~25.00°C, got {temp_sensor.value}"
    assert temp_sensor.unit == "°C", f"Expected unit '°C', got '{temp_sensor.unit}'"
    
    # Humidity sensor (0x03)
    humidity_sensor = result.sensors[1]
    assert humidity_sensor.object_id == 0x03, f"Expected humidity object ID 0x03, got {humidity_sensor.object_id:02X}"
    assert humidity_sensor.name == "humidity", f"Expected name 'humidity', got '{humidity_sensor.name}'"
    assert abs(humidity_sensor.value - 1.91) < 0.01, f"Expected humidity ~1.91%, got {humidity_sensor.value}"
    assert humidity_sensor.unit == "%", f"Expected unit '%', got '{humidity_sensor.unit}'"
    
    print("  PASSED: Advertisement with additional data decoded correctly")
    print(f"  Decoded data:\n{result}")
    return True


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("BTHome v2 Decoder Tests")
    print("=" * 60)
    
    tests = [
        test_basic_example,
        test_device_info,
        test_binary_sensor,
        test_event,
        test_packet_id,
        test_multiple_sensors,
        test_encrypted_data,
        test_trigger_based,
        test_advertisement_with_additional_data,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
