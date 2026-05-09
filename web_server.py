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
    <script src="/static/js/luxon.min.js"></script>
    <script src="/static/js/chart.umd.min.js"></script>
    <script src="/static/js/chartjs-adapter-luxon.min.js"></script>
    <script>
        // Register luxon adapter for time axis
        Chart.register(ChartjsAdapterLuxon);
    </script>
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
        .chart-container {
            position: relative;
            height: 500px;
            margin: 20px 0;
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
                <button type="submit">Load Positions</button>
            </form>
        </div>
        
        <div class="card" id="timeFilterCard" style="display: none;">
            <h2>Time Range Filter (Optional)</h2>
            <div class="form-group">
                <label for="timeRange">Time Range:</label>
                <select id="timeRange" name="timeRange">
                    <option value="lastDay" selected>Last Day</option>
                    <option value="lastWeek">Last Week</option>
                    <option value="lastMonth">Last Month</option>
                    <option value="custom">Custom Range</option>
                </select>
            </div>
            <div id="customRangeContainer" style="display: none; margin-top: 15px;">
                <div class="sensor-grid">
                    <div class="sensor-card">
                        <label for="startTime">From:</label>
                        <input type="datetime-local" id="startTime">
                    </div>
                    <div class="sensor-card">
                        <label for="endTime">Until:</label>
                        <input type="datetime-local" id="endTime">
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card" id="positionsCard" style="display: none;">
            <h2>Available Sensor Positions</h2>
            <div id="positionsList"></div>
        </div>
        
        <div class="card" id="sensorDataCard" style="display: none;">
            <h2>Sensor Data</h2>
            <div class="chart-container">
                <canvas id="sensorChart"></canvas>
            </div>
            <div id="sensorDataInfo"></div>
        </div>
    </div>
    
    <script>
        const deviceForm = document.getElementById('deviceForm');
        const positionsCard = document.getElementById('positionsCard');
        const sensorDataCard = document.getElementById('sensorDataCard');
        const timeFilterCard = document.getElementById('timeFilterCard');
        const positionsList = document.getElementById('positionsList');
        const sensorDataInfo = document.getElementById('sensorDataInfo');
        
        let currentDevice = null;
        let currentDeviceId = null;
        let currentPosition = null;
        let sensorChart = null;
        
        // Time range filter elements
        const timeRangeSelect = document.getElementById('timeRange');
        const customRangeContainer = document.getElementById('customRangeContainer');
        
        // Load positions for selected device
        deviceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            currentDevice = document.getElementById('deviceSelect').value;
            
            if (!currentDevice) return;
            
            // Get device ID
            const deviceResponse = await fetch(`/api/devices`);
            const devices = await deviceResponse.json();
            const device = devices.find(d => d.address === currentDevice);
            currentDeviceId = device ? device.id : null;
            
            if (!currentDeviceId) {
                positionsList.innerHTML = '<div class="empty-state">Device not found</div>';
                positionsCard.style.display = 'block';
                return;
            }
            
            // Show time filter card
            timeFilterCard.style.display = 'block';
            
            // Setup time range filter
            if (timeRangeSelect) {
                timeRangeSelect.addEventListener('change', function() {
                    if (this.value === 'custom') {
                        customRangeContainer.style.display = 'block';
                    } else {
                        customRangeContainer.style.display = 'none';
                        // Clear custom values when switching away from custom
                        document.getElementById('startTime').value = '';
                        document.getElementById('endTime').value = '';
                    }
                });
            }
            
            const response = await fetch(`/api/device/${encodeURIComponent(currentDeviceId)}/positions`);
            const positions = await response.json();
            
            if (positions.length === 0) {
                positionsList.innerHTML = '<div class="empty-state">No sensor positions found for this device</div>';
                positionsCard.style.display = 'block';
                sensorDataCard.style.display = 'none';
                return;
            }
            
            positionsList.innerHTML = positions.map(pos => `
                <div class="advertisement-item" data-position="${pos.position}" data-device-id="${pos.device_id}" data-name="${pos.name || ''}" data-unit="${pos.unit || ''}">
                    <strong>Position ${pos.position}</strong> - ${pos.name}
                    ${pos.unit ? `<br><span class="unit">Unit: ${pos.unit}</span>` : ''}
                    <br><span class="timestamp">${pos.sensor_type} sensor</span>
                </div>
            `).join('');
            
            positionsCard.style.display = 'block';
            sensorDataCard.style.display = 'none';
            
            // Add click handlers
            document.querySelectorAll('.advertisement-item').forEach(item => {
                item.addEventListener('click', () => {
                    document.querySelectorAll('.advertisement-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    loadPositionData(currentDeviceId, item.dataset.position);
                });
            });
        });
        
        function getTimeRange() {
            const range = timeRangeSelect?.value || 'lastDay';
            const now = new Date();
            let startTime = null;
            let endTime = null;
            
            if (range === 'custom') {
                startTime = document.getElementById('startTime')?.value || new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString().slice(0, 19);
                endTime = document.getElementById('endTime')?.value || now.toISOString().slice(0, 19);
            } else if (range === 'lastDay') {
                startTime = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString().slice(0, 19);
                endTime = now.toISOString().slice(0, 19);
            } else if (range === 'lastWeek') {
                startTime = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 19);
                endTime = now.toISOString().slice(0, 19);
            } else if (range === 'lastMonth') {
                startTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 19);
                endTime = now.toISOString().slice(0, 19);
            }
            
            return { startTime, endTime };
        }
        
        async function loadPositionData(deviceId, position) {
            currentPosition = position;
            
            // Get sensor name and unit from the selected position item
            const selectedItem = document.querySelector('.advertisement-item.selected');
            const sensorName = selectedItem?.dataset.name || `Position ${position}`;
            const unit = selectedItem?.dataset.unit || '';
            
            // Get time range based on selection
            const { startTime, endTime } = getTimeRange();
            
            let url = `/api/sensor/${encodeURIComponent(deviceId)}/${position}?`;
            if (startTime) url += `start_time=${encodeURIComponent(startTime)}&`;
            if (endTime) url += `end_time=${encodeURIComponent(endTime)}&`;
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.length === 0) {
                sensorDataInfo.innerHTML = '<div class="empty-state">No data found for this position with the specified filters</div>';
                sensorDataCard.style.display = 'block';
                return;
            }
            
            // Prepare chart data
            const timestamps = data.map(r => new Date(r.timestamp));
            const values = data.map(r => r.value !== null ? r.value : (r.value_text ? parseFloat(r.value_text) || 0 : 0));
            
            // Destroy existing chart if it exists
            if (sensorChart) {
                sensorChart.destroy();
            }
            
            const ctx = document.getElementById('sensorChart').getContext('2d');
            sensorChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: timestamps,
                    datasets: [{
                        label: `${sensorName}${unit ? ` (${unit})` : ''}`,
                        data: values,
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'minute',
                                displayFormats: {
                                    minute: 'HH:mm',
                                    hour: 'HH:mm'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Time'
                            },
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: `${sensorName}${unit ? ` (${unit})` : ''}`
                            }
                        }
                    },
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return `${sensorName}: ${context.raw} ${unit}`;
                                },
                                afterLabel: function(context) {
                                    const timestamp = timestamps[context.dataIndex];
                                    return `Time: ${timestamp.toLocaleString()}`;
                                }
                            }
                        }
                    }
                }
            });
            
            // Show info
            sensorDataInfo.innerHTML = `<p>Showing ${data.length} readings for ${sensorName}</p>`;
            sensorDataCard.style.display = 'block';
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


@app.route('/api/device/<int:device_id>/positions')
def api_device_positions(device_id):
    """API endpoint: get available sensor positions for a device
    
    Returns a list of unique positions with their metadata (name, unit, sensor type)
    
    Args:
        device_id: The database ID of the device
    """
    # Verify device exists
    device = db.get_device_by_id(device_id)
    if device is None:
        return jsonify({"error": "Device not found"}), 404
    
    device_address = device['address']
    
    # Get all sensor readings for this device
    readings = db.get_sensor_readings(device_address=device_address)
    
    # Get all binary sensor readings for this device
    binary_readings = db.get_binary_sensor_readings(device_address=device_address)
    
    # Build a map of position -> info
    positions = {}
    
    for reading in readings:
        pos = reading['position']
        if pos not in positions:
            positions[pos] = {
                'position': pos,
                'name': reading['name'],
                'unit': reading['unit'],
                'sensor_type': 'sensor',
                'device_id': device_id,
                'device_address': device_address
            }
    
    for reading in binary_readings:
        pos = reading['position']
        if pos not in positions:
            positions[pos] = {
                'position': pos,
                'name': reading['name'],
                'unit': '',
                'sensor_type': 'binary_sensor',
                'device_id': device_id,
                'device_address': device_address
            }
    
    # Convert to list and sort by position
    result = sorted(positions.values(), key=lambda x: x['position'])
    
    return jsonify(result)


@app.route('/api/sensor/<int:device_id>/<int:position>')
def api_sensor_data(device_id, position):
    """API endpoint: get sensor data for a specific device and position
    
    Required parameters:
    - device_id: The device ID
    - position: The position in the advertisement
    
    Required query parameters:
    - start_time: Filter by start timestamp (ISO 8601 format)
    - end_time: Filter by end timestamp (ISO 8601 format)
    """
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    # Validate required parameters
    if not start_time or not end_time:
        return jsonify({'error': 'Both start_time and end_time query parameters are required'}), 400
    
    # Get all sensor readings for this device and position
    all_readings = db.get_sensor_readings(device_address=None)
    
    # Filter by device_id and position
    filtered = [r for r in all_readings if r['device_id'] == device_id and r['position'] == position]
    
    # Apply mandatory time filters
    filtered = [r for r in filtered if r['timestamp'] >= start_time and r['timestamp'] <= end_time]
    
    # Sort by timestamp
    filtered.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Simplify response: only include necessary fields
    simplified = [{
        'id': r['id'],
        'advertisement_id': r['advertisement_id'],
        'timestamp': r['timestamp'],
        'value': r['value'],
        'value_text': r['value_text']
    } for r in filtered]
    
    return jsonify(simplified)


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
