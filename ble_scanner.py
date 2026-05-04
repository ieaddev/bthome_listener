"""
Bleak-based BLE Scanner for BTHome advertisements

This module provides a scanner that listens for BLE advertisements
and filters for BTHome v2 data.
"""

import asyncio
import logging
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from bleak import BleakScanner, BleakClient, BLEDevice
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from bthome_decoder import BTHomeDecoder, BTHomeData

logger = logging.getLogger(__name__)


@dataclass
class BTHomeDevice:
    """Represents a BTHome device with its current state"""
    address: str
    name: Optional[str] = None
    rssi: Optional[int] = None
    last_seen: Optional[datetime] = None
    bthome_data: Optional[BTHomeData] = None
    advertisement_count: int = 0
    
    # Track sensor values by name for display
    sensor_values: Dict[str, Any] = field(default_factory=dict)
    binary_sensor_values: Dict[str, bool] = field(default_factory=dict)
    events: list = field(default_factory=list)
    
    def update_from_advertisement(self, advertisement_data: AdvertisementData, rssi: int):
        """Update device state from a new advertisement"""
        self.rssi = rssi
        self.last_seen = datetime.now()
        self.advertisement_count += 1
        
        # Try to decode BTHome data
        raw_data = bytes(advertisement_data.manufacturer_data.values()) if advertisement_data.manufacturer_data else b''
        if not raw_data:
            # Try service data
            for uuid, data in advertisement_data.service_data.items():
                raw_data = data
                break
        
        if raw_data:
            # Convert to bytes if needed
            if isinstance(raw_data, (list, tuple)):
                raw_data = bytes(raw_data)
            
            # Try to decode
            decoded = BTHomeDecoder.decode_advertisement(raw_data)
            if decoded:
                self.bthome_data = decoded
                self._update_sensor_values()
        
        # Update name from advertisement if available
        if advertisement_data.local_name:
            self.name = advertisement_data.local_name
    
    def _update_sensor_values(self):
        """Update sensor value tracking from decoded BTHome data"""
        if not self.bthome_data:
            return
        
        # Update sensor values
        for sensor in self.bthome_data.sensors:
            self.sensor_values[sensor.name] = sensor.value
        
        # Update binary sensor values
        for binary in self.bthome_data.binary_sensors:
            self.binary_sensor_values[binary.name] = binary.value
        
        # Track events
        self.events.extend(self.bthome_data.events)
        # Keep only last 10 events
        if len(self.events) > 10:
            self.events = self.events[-10:]
    
    def get_display_name(self) -> str:
        """Get a display name for the device"""
        if self.name:
            return self.name
        return f"Device_{self.address.replace(':', '')}"
    
    def __str__(self):
        lines = [
            f"Device: {self.get_display_name()}",
            f"  Address: {self.address}",
            f"  RSSI: {self.rssi} dBm" if self.rssi else "  RSSI: N/A",
            f"  Last seen: {self.last_seen}" if self.last_seen else "  Last seen: Never",
            f"  Advertisements: {self.advertisement_count}",
        ]
        
        if self.bthome_data:
            lines.append(f"  BTHome v{self.bthome_data.version}")
            if self.bthome_data.device_info.device_type_id:
                lines.append(f"  Device Type: {self.bthome_data.device_info.device_type_id}")
            if self.bthome_data.device_info.firmware_version:
                lines.append(f"  Firmware: {self.bthome_data.device_info.firmware_version}")
            
            # Display sensor values
            if self.sensor_values:
                lines.append("  Sensor Values:")
                for name, value in self.sensor_values.items():
                    if isinstance(value, float):
                        lines.append(f"    {name}: {value:.2f}")
                    else:
                        lines.append(f"    {name}: {value}")
            
            # Display binary sensor values
            if self.binary_sensor_values:
                lines.append("  Binary Sensors:")
                for name, value in self.binary_sensor_values.items():
                    lines.append(f"    {name}: {'ON' if value else 'OFF'}")
            
            # Display recent events
            if self.events:
                lines.append("  Recent Events:")
                for event in self.events[-5:]:  # Last 5 events
                    lines.append(f"    {event}")
        
        return "\n".join(lines)


class BTHomeScanner:
    """
    Scanner for BTHome BLE advertisements using Bleak.
    
    This scanner continuously listens for BLE advertisements and filters
    for those containing BTHome v2 data.
    """
    
    def __init__(self, 
                 device_filter: Optional[Callable[[BLEDevice, AdvertisementData], bool]] = None,
                 detection_callback: Optional[Callable[[BTHomeDevice], None]] = None):
        """
        Initialize the BTHome scanner.
        
        Args:
            device_filter: Optional function to filter which devices to track.
                          Receives (BLEDevice, AdvertisementData) and returns bool.
            detection_callback: Optional callback called when a BTHome device is detected.
                               Receives BTHomeDevice object.
        """
        self.device_filter = device_filter
        self.detection_callback = detection_callback
        self.devices: Dict[str, BTHomeDevice] = {}
        self._scanner: Optional[BleakScanner] = None
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.total_advertisements = 0
        self.bthome_advertisements = 0
        self.start_time: Optional[datetime] = None
    
    def _default_filter(self, device: BLEDevice, advertisement_data: AdvertisementData) -> bool:
        """Default filter: accept all devices with BTHome data"""
        # Check for BTHome UUID in service data
        for uuid in advertisement_data.service_uuids:
            if uuid.lower() == "fc00" or uuid.lower() == "0000fc00-0000-1000-8000-00805f9b34fb":
                return True
        
        # Check manufacturer data for BTHome
        for manufacturer_id, data in advertisement_data.manufacturer_data.items():
            # BTHome uses manufacturer ID 0x0522 (Shelly) or others
            # But we'll check the data itself
            if isinstance(data, (bytes, bytearray)):
                bthome_data = BTHomeDecoder.extract_bthome_data(data)
                if bthome_data is not None:
                    return True
        
        # Check service data
        for uuid, data in advertisement_data.service_data.items():
            if isinstance(data, (bytes, bytearray)):
                bthome_data = BTHomeDecoder.extract_bthome_data(data)
                if bthome_data is not None:
                    return True
        
        return False
    
    def _get_filter(self) -> Callable[[BLEDevice, AdvertisementData], bool]:
        """Get the effective filter function"""
        if self.device_filter:
            return self.device_filter
        return self._default_filter
    
    def _process_advertisement(self, device: BLEDevice, advertisement_data: AdvertisementData):
        """Process a BLE advertisement"""
        self.total_advertisements += 1
        
        # Apply filter
        if not self._get_filter()(device, advertisement_data):
            return
        
        # Get or create device tracking
        address = device.address
        if address not in self.devices:
            self.devices[address] = BTHomeDevice(address=address, name=device.name)
            logger.info(f"New BTHome device detected: {address} ({device.name})")
        
        device_obj = self.devices[address]
        
        # Update device from advertisement
        rssi = advertisement_data.rssi if advertisement_data.rssi is not None else 0
        device_obj.update_from_advertisement(advertisement_data, rssi)
        
        # Check if this advertisement contains BTHome data
        if device_obj.bthome_data:
            self.bthome_advertisements += 1
            logger.debug(f"BTHome data from {address}: {device_obj.bthome_data}")
            
            # Call detection callback if set
            if self.detection_callback:
                try:
                    self.detection_callback(device_obj)
                except Exception as e:
                    logger.error(f"Error in detection callback: {e}")
    
    async def start(self, scan_interval: float = 1.0, scan_window: float = 0.5):
        """
        Start scanning for BTHome devices.
        
        Args:
            scan_interval: Time between scan cycles in seconds
            scan_window: Duration of each scan window in seconds
        """
        if self._running:
            logger.warning("Scanner is already running")
            return
        
        self._running = True
        self.start_time = datetime.now()
        self._scanner = BleakScanner(
            detection_callback=self._process_advertisement,
            scanning_mode="passive"
        )
        
        logger.info("Starting BTHome scanner...")
        
        async def scan_loop():
            while self._running:
                try:
                    await self._scanner.start()
                    await asyncio.sleep(scan_window)
                    await self._scanner.stop()
                    await asyncio.sleep(scan_interval - scan_window)
                except Exception as e:
                    logger.error(f"Scan error: {e}")
                    await asyncio.sleep(1.0)
        
        self._scan_task = asyncio.create_task(scan_loop())
    
    async def stop(self):
        """Stop the scanner"""
        if not self._running:
            return
        
        self._running = False
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._scanner:
            await self._scanner.stop()
            self._scanner = None
        
        logger.info("BTHome scanner stopped")
    
    def get_devices(self) -> Dict[str, BTHomeDevice]:
        """Get all tracked devices"""
        return self.devices.copy()
    
    def get_device(self, address: str) -> Optional[BTHomeDevice]:
        """Get a specific device by address"""
        return self.devices.get(address)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scanner statistics"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "total_advertisements": self.total_advertisements,
            "bthome_advertisements": self.bthome_advertisements,
            "tracked_devices": len(self.devices),
        }
    
    def clear_devices(self):
        """Clear all tracked devices"""
        self.devices.clear()
        logger.info("Cleared all tracked devices")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        asyncio.run(self.stop())
