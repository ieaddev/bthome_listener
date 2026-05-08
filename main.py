#!/usr/bin/env python3
"""
BTHome Listener - Main Application

This application listens for BLE advertisements containing BTHome v2 data,
decodes them, and displays the information grouped by device.

Usage:
    python main.py [options]

Options:
    --scan-interval SECONDS    Interval between scan cycles (default: 1.0)
    --scan-window SECONDS      Duration of each scan window (default: 0.5)
    --verbose, -v              Enable verbose logging
    --help, -h                Show this help message
"""

import argparse
import asyncio
import logging
import sys
import signal
from datetime import datetime
from typing import Dict, List, Optional

from ble_scanner import BTHomeScanner, BTHomeDevice
from bthome_decoder import BTHomeData

# Configure logging - default to WARNING to avoid flashing output
# Users can enable verbose logging with -v flag
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class BTHomeListener:
    """
    Main application class for listening to BTHome advertisements.
    
    This class manages the BLE scanner, tracks devices, and displays
    the decoded BTHome data grouped by device.
    """
    
    def __init__(self, scan_interval: float = 1.0, scan_window: float = 0.5):
        """
        Initialize the BTHome listener.
        
        Args:
            scan_interval: Time between scan cycles in seconds
            scan_window: Duration of each scan window in seconds
        """
        self.scan_interval = scan_interval
        self.scan_window = scan_window
        self.scanner = BTHomeScanner(detection_callback=self._on_device_detected)
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Display settings
        self.last_display_time = datetime.now()
        self.display_interval = 5.0  # Update display every 5 seconds
    
    def _on_device_detected(self, device: BTHomeDevice):
        """Callback when a BTHome device is detected"""
        logger.debug(f"Device detected: {device.address}")
        
        # If we have decoded data, log it at debug level
        if device.bthome_data:
            logger.debug(f"BTHome data from {device.get_display_name()}: {device.bthome_data}")
    
    def _clear_screen(self):
        """Clear the console screen"""
        # ANSI escape code to clear screen and move cursor to top
        print("\033[2J\033[H", end="")
    
    def _format_sensor_value(self, value: any, unit: str = "") -> str:
        """Format a sensor value for display"""
        if isinstance(value, float):
            return f"{value:.2f} {unit}" if unit else f"{value:.2f}"
        return f"{value} {unit}" if unit else str(value)
    
    def _display_devices(self):
        """Display all tracked devices and their data"""
        devices = self.scanner.get_devices()
        
        if not devices:
            print("No BTHome devices detected yet...")
            print(f"Scanning for {self.scanner.get_statistics()['uptime_seconds']:.1f} seconds")
            print(f"Total advertisements: {self.scanner.total_advertisements}")
            print(f"BTHome advertisements: {self.scanner.bthome_advertisements}")
            return
        
        # Get statistics
        stats = self.scanner.get_statistics()
        
        # Header
        print("=" * 80)
        print("BTHome Listener - Detected Devices")
        print("=" * 80)
        print(f"Uptime: {stats['uptime_seconds']:.1f}s | "
              f"Devices: {stats['tracked_devices']} | "
              f"BTHome ads: {stats['bthome_advertisements']}")
        print("-" * 80)
        
        # Sort devices by last seen (most recent first)
        sorted_devices = sorted(
            devices.values(),
            key=lambda d: d.last_seen if d.last_seen else datetime.min,
            reverse=True
        )
        
        for i, device in enumerate(sorted_devices, 1):
            print(f"\n[{i}] {device.get_display_name()}")
            print(f"    Address: {device.address}")
            print(f"    RSSI: {device.rssi} dBm" if device.rssi else "    RSSI: N/A")
            print(f"    Last seen: {device.last_seen.strftime('%H:%M:%S') if device.last_seen else 'Never'}")
            print(f"    Advertisements: {device.advertisement_count}")
            
            if device.bthome_data:
                bthome = device.bthome_data
                print(f"    BTHome v{bthome.version} | "
                      f"Encrypted: {bthome.is_encrypted} | "
                      f"Trigger-based: {bthome.is_trigger_based}")
                
                if bthome.device_info.device_type_id:
                    print(f"    Device Type ID: {bthome.device_info.device_type_id}")
                if bthome.device_info.firmware_version:
                    print(f"    Firmware: {bthome.device_info.firmware_version}")
                if bthome.packet_id is not None:
                    print(f"    Packet ID: {bthome.packet_id}")
                
                # Display sensor values
                if device.sensor_values:
                    print("    Sensors:")
                    for sensor in bthome.sensors:
                        value_str = self._format_sensor_value(sensor.value, sensor.unit)
                        print(f"      {sensor.name}: {value_str}")
                
                # Display binary sensor values
                if device.binary_sensor_values:
                    print("    Binary Sensors:")
                    for name, value in device.binary_sensor_values.items():
                        print(f"      {name}: {'ON' if value else 'OFF'}")
                
                # Display recent events
                if device.events:
                    print("    Recent Events:")
                    for event in device.events[-5:]:
                        print(f"      {event}")
        
        print("\n" + "=" * 80)
        print("Press Ctrl+C to exit")
        print("=" * 80)
    
    async def _display_loop(self):
        """Periodically update the display"""
        while not self._shutdown_event.is_set():
            try:
                self._clear_screen()
                self._display_devices()
                await asyncio.sleep(self.display_interval)
            except Exception as e:
                logger.error(f"Display error: {e}")
                await asyncio.sleep(1.0)
    
    async def start(self):
        """Start the listener"""
        if self._running:
            logger.warning("Listener is already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        logger.info("Starting BTHome Listener...")
        logger.info(f"Scan interval: {self.scan_interval}s, Scan window: {self.scan_window}s")
        
        # Start the scanner
        await self.scanner.start(self.scan_interval, self.scan_window)
        
        # Start display loop
        display_task = asyncio.create_task(self._display_loop())
        
        # Wait for shutdown
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            display_task.cancel()
            try:
                await display_task
            except asyncio.CancelledError:
                pass
            
            await self.scanner.stop()
            self._running = False
    
    async def stop(self):
        """Stop the listener"""
        if not self._running:
            return
        
        logger.info("Stopping BTHome Listener...")
        self._shutdown_event.set()
        await self.scanner.stop()
        self._running = False
    
    def get_device_count(self) -> int:
        """Get the number of tracked devices"""
        return len(self.scanner.get_devices())
    
    def get_statistics(self) -> Dict:
        """Get listener statistics"""
        return self.scanner.get_statistics()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="BTHome Listener - Listen for BLE advertisements with BTHome v2 data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Start with default settings
  python main.py --scan-interval 2.0      # Scan every 2 seconds
  python main.py -v                       # Enable verbose logging
        """
    )
    
    parser.add_argument(
        '--scan-interval',
        type=float,
        default=1.0,
        help='Interval between scan cycles in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '--scan-window',
        type=float,
        default=0.5,
        help='Duration of each scan window in seconds (default: 0.5)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--no-clear',
        action='store_true',
        help='Disable screen clearing'
    )
    
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    
    # Configure logging level
    # basicConfig already set root logger to WARNING by default
    if args.verbose:
        # Enable verbose logging - show DEBUG and above
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('bleak').setLevel(logging.DEBUG)
    else:
        # Default: only show WARNING and above
        logging.getLogger().setLevel(logging.WARNING)
        logging.getLogger('bleak').setLevel(logging.WARNING)
    
    # Create listener
    listener = BTHomeListener(
        scan_interval=args.scan_interval,
        scan_window=args.scan_window
    )
    
    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def shutdown_handler(signame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received {signame}, shutting down...")
        await listener.stop()
    
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(
            getattr(signal, signame),
            lambda s=signame: asyncio.create_task(shutdown_handler(s))
        )
    
    try:
        # Run the listener
        loop.run_until_complete(listener.start())
    except KeyboardInterrupt:
        # This is handled by the signal handler above, but just in case
        logger.info("Keyboard interrupt, shutting down...")
        loop.run_until_complete(listener.stop())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure clean shutdown
        loop.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
