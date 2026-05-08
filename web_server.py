#!/usr/bin/env python3
"""
Flask Web Server for BTHome Listener

This module provides a simple web interface to view BTHome sensor data
stored in the SQLite database. Users can:
- Select a device
- Select an advertisement from that device
- View the time series data for that advertisement

Usage:
    python web_server.py [--database PATH] [--host HOST] [--port PORT]

Options:
    --database PATH    Path to SQLite database (default: bthome_data.db)
    --host HOST        Host to bind to (default: 0.0.0.0)
    --port PORT        Port to listen on (default: 5000)
"""

import argparse
from flask import Flask, render_template_string, request, jsonify
from database import BTHomeDatabase
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global database instance (will be initialized after parsing args)
db: Optional[BTHomeDatabase] = None


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTHome Sensor Data Viewer</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        .card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #555;
        }
        select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .data-table th, .data-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .data-table th {
            background-color: #4CAF50;
            color: white;
        }
        .data-table tr:hover {
            background-color: #f5f5f5;
        }
        .sensor-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .sensor-card {
            background: #f9f9f9;
            border-radius: 4px;
            padding: 15px;
            border-left: 4px solid #4CAF50;
        }
        .sensor-card .name {
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }
        .sensor-card .value {
            font-size: 24px;
            color: #4CAF50;
        }
        .sensor-card .unit {
            color: #666;
            font-size: 14px;
        }
        .timestamp {
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }
        .empty-state {
            color: #666;
            font-style: italic;
            text-align: center;
            padding: 40px;
        }
        .advertisement-list {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .advertisement-item {
            padding: 10px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
        }
        .advertisement-item:hover {
            background-color: #f5f5f5;
        }
        .advertisement-item.selected {
            background-color: #e8f5e9;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>BTHome Sensor Data Viewer</h1>
        
        <div class="card">
            <h2>Select Device</h2>
            <form id="deviceForm">
                <div class="form-group">
                    <label for="deviceSelect">Device:</label>
                    <select id="deviceSelect" name="device" required>
                        <option value="">-- Select a device --</option>
                        {% for device in devices %}
                        <option value="{{ device.address }}">{{ device.name or device.address }}</option>
                        {% endfor %}
                    </select>
                </div>
                <button type="submit">Load Advertisements</button>
            </form>
        </div>
        
        <div class="card" id="advertisementsCard" style="display: none;">
            <h2>Select Advertisement</h2>
            <div id="advertisementsList" class="advertisement-list"></div>
        </div>
        
        <div class="card" id="dataCard" style="display: none;">
            <h2>Advertisement Data</h2>
            <div id="advertisementInfo"></div>
            <div id="sensorData"></div>
        </div>
    </div>
    
    <script>
        const deviceForm = document.getElementById('deviceForm');
        const advertisementsCard = document.getElementById('advertisementsCard');
        const dataCard = document.getElementById('dataCard');
        const advertisementsList = document.getElementById('advertisementsList');
        const advertisementInfo = document.getElementById('advertisementInfo');
        const sensorData = document.getElementById('sensorData');
        
        let currentDevice = null;
        let currentAdvertisement = null;
        
        // Load advertisements for selected device
        deviceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            currentDevice = document.getElementById('deviceSelect').value;
            
            if (!currentDevice) return;
            
            const response = await fetch(`/api/device/${encodeURIComponent(currentDevice)}/advertisements`);
            const ads = await response.json();
            
            if (ads.length === 0) {
                advertisementsList.innerHTML = '<div class="empty-state">No advertisements found for this device</div>';
                advertisementsCard.style.display = 'block';
                dataCard.style.display = 'none';
                return;
            }
            
            advertisementsList.innerHTML = ads.map(ad => `
                <div class="advertisement-item" data-id="${ad.id}" data-timestamp="${ad.timestamp}">
                    <strong>Ad #${ad.id}</strong> - ${new Date(ad.timestamp).toLocaleString()}
                    ${ad.bthome_version ? `<br>BTHome v${ad.bthome_version}` : ''}
                    ${ad.packet_id !== null ? `<br>Packet ID: ${ad.packet_id}` : ''}
                </div>
            `).join('');
            
            advertisementsCard.style.display = 'block';
            dataCard.style.display = 'none';
            
            // Add click handlers
            document.querySelectorAll('.advertisement-item').forEach(item => {
                item.addEventListener('click', () => {
                    document.querySelectorAll('.advertisement-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    loadAdvertisementData(item.dataset.id);
                });
            });
        });
        
        async function loadAdvertisementData(advertisementId) {
            currentAdvertisement = advertisementId;
            
            const response = await fetch(`/api/advertisement/${advertisementId}`);
            const data = await response.json();
            
            // Display advertisement info
            advertisementInfo.innerHTML = `
                <div class="sensor-grid">
                    <div class="sensor-card">
                        <div class="name">Advertisement ID</div>
                        <div class="value">${data.advertisement.id}</div>
                    </div>
                    <div class="sensor-card">
                        <div class="name">Timestamp</div>
                        <div class="value">${new Date(data.advertisement.timestamp).toLocaleString()}</div>
                    </div>
                    <div class="sensor-card">
                        <div class="name">BTHome Version</div>
                        <div class="value">${data.advertisement.bthome_version || 'N/A'}</div>
                    </div>
                    <div class="sensor-card">
                        <div class="name">Device</div>
                        <div class="value">${data.advertisement.device_name || data.advertisement.address}</div>
                    </div>
                </div>
            `;
            
            // Display sensor data
            let sensorHtml = '<h3>Sensor Readings</h3>';
            if (data.sensors.length > 0) {
                sensorHtml += '<div class="sensor-grid">';
                data.sensors.forEach(sensor => {
                    const value = sensor.value !== null ? sensor.value : sensor.value_text;
                    sensorHtml += `
                        <div class="sensor-card">
                            <div class="name">${sensor.name} (Pos: ${sensor.position})</div>
                            <div class="value">${value}</div>
                            ${sensor.unit ? `<div class="unit">${sensor.unit}</div>` : ''}
                        </div>
                    `;
                });
                sensorHtml += '</div>';
            } else {
                sensorHtml += '<div class="empty-state">No sensor readings in this advertisement</div>';
            }
            
            sensorHtml += '<h3>Binary Sensor Readings</h3>';
            if (data.binary_sensors.length > 0) {
                sensorHtml += '<div class="sensor-grid">';
                data.binary_sensors.forEach(sensor => {
                    const value = sensor.value === 1 ? 'ON' : 'OFF';
                    sensorHtml += `
                        <div class="sensor-card">
                            <div class="name">${sensor.name} (Pos: ${sensor.position})</div>
                            <div class="value">${value}</div>
                        </div>
                    `;
                });
                sensorHtml += '</div>';
            } else {
                sensorHtml += '<div class="empty-state">No binary sensor readings in this advertisement</div>';
            }
            
            sensorHtml += '<h3>Events</h3>';
            if (data.events.length > 0) {
                sensorHtml += '<div class="sensor-grid">';
                data.events.forEach(event => {
                    sensorHtml += `
                        <div class="sensor-card">
                            <div class="name">${event.device_type}: ${event.event_type} (Pos: ${event.position})</div>
                            ${event.event_property ? `<div class="value">${event.event_property}</div>` : ''}
                        </div>
                    `;
                });
                sensorHtml += '</div>';
            } else {
                sensorHtml += '<div class="empty-state">No events in this advertisement</div>';
            }
            
            sensorData.innerHTML = sensorHtml;
            dataCard.style.display = 'block';
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Main page - show device list"""
    devices = db.get_devices()
    return render_template_string(HTML_TEMPLATE, devices=devices)


@app.route('/api/devices')
def api_devices():
    """API endpoint: get all devices"""
    devices = db.get_devices()
    return jsonify(devices)


@app.route('/api/device/<device_address>/advertisements')
def api_device_advertisements(device_address):
    """API endpoint: get advertisements for a specific device"""
    advertisements = db.get_advertisements(device_address=device_address)
    return jsonify(advertisements)


@app.route('/api/advertisement/<int:advertisement_id>')
def api_advertisement(advertisement_id):
    """API endpoint: get all data for a specific advertisement"""
    data = db.get_advertisement_data(advertisement_id)
    if data is None:
        return jsonify({"error": "Advertisement not found"}), 404
    return jsonify(data)


@app.route('/api/sensor/<sensor_name>/history')
def api_sensor_history(sensor_name):
    """API endpoint: get history for a specific sensor"""
    device_address = request.args.get('device')
    limit = request.args.get('limit', type=int)
    
    history = db.get_sensor_history(
        device_address=device_address,
        sensor_name=sensor_name,
        limit=limit
    )
    return jsonify(history)


@app.route('/api/statistics')
def api_statistics():
    """API endpoint: get database statistics"""
    stats = db.get_statistics()
    return jsonify(stats)


def main():
    """Main entry point"""
    global db
    
    parser = argparse.ArgumentParser(
        description='BTHome Web Server - View sensor data from SQLite database'
    )
    parser.add_argument(
        '--database',
        type=str,
        default='bthome_data.db',
        help='Path to SQLite database file (default: bthome_data.db)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to listen on (default: 5000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = BTHomeDatabase(db_path=args.database)
    db.initialize()
    
    logger.info(f"Starting BTHome Web Server on {args.host}:{args.port}")
    logger.info(f"Using database: {args.database}")
    
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
