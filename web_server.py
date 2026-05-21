#!/usr/bin/env python3
"""
Flask Web Server for BTHome Listener

This module provides a simple web interface to view BTHome sensor data
stored in the SQLite database. Users can:
- Select a device
- Select an advertisement from that device
- View the time series data for that advertisement

Usage (Development):
    python web_server.py [--database PATH] [--host HOST] [--port PORT] [--env ENVIRONMENT] [--debug] [--threaded]

Usage (Production with Gunicorn):
    gunicorn --bind 0.0.0.0:5000 --workers 4 wsgi:app
    # Or use the convenience script:
    ./run_gunicorn.sh

Options:
    --database PATH    Path to SQLite database (default: bthome_data.db)
    --host HOST        Host to bind to (default: 0.0.0.0)
    --port PORT        Port to listen on (default: 5000)
    --env ENVIRONMENT  Environment mode: development, dev, production, prod (default: production)
    --debug            Enable debug mode (deprecated: use --env development instead)
    --threaded         Enable threaded mode for production

Environment Variables (for WSGI):
    BTHOME_DATABASE    Path to SQLite database (default: bthome_data.db)
    BTHOME_ENV          Environment mode: development, dev, production, prod (default: production)
"""

import argparse
import os
from flask import Flask, render_template_string, request, jsonify
from database import BTHomeDatabase
from typing import List, Dict, Any, Optional, Tuple
import logging
import math
from datetime import datetime, timedelta
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global database instance (will be initialized after parsing args or via create_app)
db: Optional[BTHomeDatabase] = None


def calculate_quartiles(values: List[float]) -> Tuple[float, float, float, float, float]:
    """
    Calculate box plot statistics from a list of values.
    
    Returns: (min, q1, median, q3, max)
    """
    if not values:
        return (0, 0, 0, 0, 0)
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    min_val = sorted_values[0]
    max_val = sorted_values[-1]
    
    def get_quartile(pos):
        """Get value at a specific position using linear interpolation"""
        if n == 0:
            return 0
        integer_pos = int(pos)
        fractional = pos - integer_pos
        if integer_pos + 1 < n:
            return sorted_values[integer_pos] + fractional * (sorted_values[integer_pos + 1] - sorted_values[integer_pos])
        return sorted_values[integer_pos]
    
    q1 = get_quartile((n - 1) * 0.25)
    median = get_quartile((n - 1) * 0.5)
    q3 = get_quartile((n - 1) * 0.75)
    
    return (min_val, q1, median, q3, max_val)


def aggregate_readings(readings: List[Dict[str, Any]], time_range_seconds: float) -> Tuple[List[Dict[str, Any]], str]:
    """
    Aggregate sensor readings based on the time range.
    
    Args:
        readings: List of sensor reading dictionaries with 'timestamp' and 'value' keys
        time_range_seconds: The total time range in seconds
    
    Returns:
        Tuple of (aggregated_data, aggregation_label)
        where aggregated_data is a list of dicts with box plot stats for each interval
    """
    if not readings:
        return [], ""
    
    # Determine aggregation interval based on time range
    if time_range_seconds <= 24 * 60 * 60:  # <= 1 day
        interval_seconds = 60 * 60  # 1 hour
        label = "hourly"
    elif time_range_seconds <= 7 * 24 * 60 * 60:  # <= 1 week
        interval_seconds = 6 * 60 * 60  # 6 hours
        label = "6-hourly"
    elif time_range_seconds <= 30 * 24 * 60 * 60:  # <= 1 month
        interval_seconds = 24 * 60 * 60  # 1 day
        label = "daily"
    else:
        interval_seconds = 7 * 24 * 60 * 60  # 1 week
        label = "weekly"
    
    # Group readings by interval
    intervals = defaultdict(list)
    
    for reading in readings:
        timestamp = reading['timestamp']
        # Parse timestamp (assuming ISO 8601 format)
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        
        # Calculate interval start
        epoch = datetime(1970, 1, 1)
        timestamp_seconds = (dt - epoch).total_seconds()
        interval_start_seconds = (timestamp_seconds // interval_seconds) * interval_seconds
        interval_start = epoch + timedelta(seconds=interval_start_seconds)
        
        intervals[interval_start].append(reading['value'])
    
    # Calculate box plot stats for each interval
    aggregated = []
    for interval_start, values in sorted(intervals.items()):
        # Filter out None values
        valid_values = [v for v in values if v is not None]
        
        if valid_values:
            min_val, q1, median, q3, max_val = calculate_quartiles(valid_values)
            interval_str = interval_start.strftime('%Y-%m-%d %H:%M:%S')
            
            aggregated.append({
                'timestamp': interval_str,
                'min': min_val,
                'q1': q1,
                'median': median,
                'q3': q3,
                'max': max_val,
                'count': len(valid_values),
                'values': valid_values
            })
    
    return aggregated, label


def create_app(db_path: str = 'bthome_data.db', env: str = 'production', 
               host: str = '0.0.0.0', port: int = 5000) -> Flask:
    """
    Factory function to create and configure the Flask application.
    
    This allows the app to be used with WSGI servers like Gunicorn.
    
    Args:
        db_path: Path to SQLite database file
        env: Environment mode (development, dev, production, prod)
        host: Host to bind to
        port: Port to listen on
        
    Returns:
        Configured Flask application
    """
    global db
    
    # Validate environment
    valid_envs = ['development', 'dev', 'production', 'prod']
    if env not in valid_envs:
        logger.warning(f"Invalid environment: {env}. Using 'production' as fallback.")
        env = 'production'
    
    # Determine debug mode
    debug_mode = env in ['development', 'dev']
    
    # Log mode
    if debug_mode:
        logger.warning("Running in DEVELOPMENT mode - do not use in production!")
    else:
        logger.info("Running in PRODUCTION mode")
    
    # Initialize database
    db = BTHomeDatabase(db_path=db_path)
    db.initialize()
    
    logger.info(f"Using database: {db_path}")
    
    return app


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTHome Sensor Data Viewer</title>
    <script src="{{ base_url }}/static/js/luxon.min.js"></script>
    <script src="{{ base_url }}/static/js/chart.umd.min.js"></script>
    <script src="{{ base_url }}/static/js/chartjs-adapter-luxon.min.js"></script>
    <script src="{{ base_url }}/static/js/chartjs-chart-box-and-violin-plot.min.js"></script>
    <script>
        // Register luxon adapter for time axis
        Chart.register(ChartjsAdapterLuxon);
        // Register box plot plugin with required scales
        Chart.register(BoxPlotController, BoxAndWiskers, Chart.CategoryScale, Chart.LinearScale);
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
            <div style="margin-bottom: 15px;">
                <label style="display: inline-block; margin-right: 10px;">Display Mode:</label>
                <select id="displayMode" style="display: inline-block; width: auto; padding: 5px;">
                    <option value="line">Line Chart</option>
                    <option value="boxplot">Box Plot</option>
                </select>
            </div>
            <div class="chart-container">
                <canvas id="sensorChart"></canvas>
            </div>
            <div id="sensorDataInfo"></div>
        </div>
    </div>
    
    <script>
        // Base URL for API requests - respects reverse proxy mount path
        const baseUrl = '{{ base_url }}';
        
        // Helper function to parse timestamp strings and convert to local DateTime
        function parseTimestamp(ts) {
            // If timestamp is already a string with timezone info, parse it
            // The database stores timestamps in UTC ISO format (e.g., "2024-01-01T12:00:00+00:00")
            // Luxon will parse this correctly and we can convert to local timezone
            if (typeof ts === 'string') {
                return luxon.DateTime.fromISO(ts).toLocal();
            }
            // If it's already a Date object
            if (ts instanceof Date) {
                return luxon.DateTime.fromJSDate(ts).toLocal();
            }
            // Fallback
            return luxon.DateTime.fromJSDate(new Date(ts)).toLocal();
        }
        
        const deviceForm = document.getElementById('deviceForm');
        const positionsCard = document.getElementById('positionsCard');
        const sensorDataCard = document.getElementById('sensorDataCard');
        const timeFilterCard = document.getElementById('timeFilterCard');
        const positionsList = document.getElementById('positionsList');
        const sensorDataInfo = document.getElementById('sensorDataInfo');
        const displayModeSelect = document.getElementById('displayMode');
        
        let currentDevice = null;
        let currentDeviceId = null;
        let currentPosition = null;
        let sensorChart = null;
        let currentDisplayMode = 'line';
        let currentRawData = null;
        
        // Time range filter elements
        const timeRangeSelect = document.getElementById('timeRange');
        const customRangeContainer = document.getElementById('customRangeContainer');
        
        // Populate device dropdown on page load
        async function populateDeviceDropdown() {
            try {
                const response = await fetch(`${baseUrl}/api/devices`);
                const devices = await response.json();
                
                const deviceSelect = document.getElementById('deviceSelect');
                // Clear existing options except the default one
                while (deviceSelect.options.length > 1) {
                    deviceSelect.remove(1);
                }
                
                // Add devices to dropdown
                devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.address;
                    option.textContent = device.name || device.address;
                    deviceSelect.appendChild(option);
                });
            } catch (error) {
                console.error('Error loading devices:', error);
            }
        }
        
        // Load devices when page loads
        document.addEventListener('DOMContentLoaded', populateDeviceDropdown);
        
        // Load positions for selected device
        deviceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            currentDevice = document.getElementById('deviceSelect').value;
            
            if (!currentDevice) return;
            
            // Get device ID
            const deviceResponse = await fetch(`${baseUrl}/api/devices`);
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
            
            // Display mode change handler
            if (displayModeSelect) {
                displayModeSelect.addEventListener('change', function() {
                    currentDisplayMode = this.value;
                    if (currentDeviceId && currentPosition) {
                        loadPositionData(currentDeviceId, currentPosition);
                    }
                });
            }
            
            const response = await fetch(`${baseUrl}/api/device/${encodeURIComponent(currentDeviceId)}/positions`);
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
            
            // Helper to convert local datetime string to UTC ISO string
            function localToUTC(localDateTimeStr) {
                if (!localDateTimeStr) return null;
                // Parse the local datetime string (format: "YYYY-MM-DDTHH:mm:ss")
                // This is in the browser's local timezone
                const localDate = new Date(localDateTimeStr);
                // Convert to UTC ISO string
                return localDate.toISOString().slice(0, 19);
            }
            
            if (range === 'custom') {
                const startInput = document.getElementById('startTime')?.value;
                const endInput = document.getElementById('endTime')?.value;
                
                if (startInput) {
                    startTime = localToUTC(startInput);
                } else {
                    startTime = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString().slice(0, 19);
                }
                
                if (endInput) {
                    endTime = localToUTC(endInput);
                } else {
                    endTime = now.toISOString().slice(0, 19);
                }
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
            
            // Get current display mode
            currentDisplayMode = displayModeSelect?.value || 'line';
            
            if (currentDisplayMode === 'boxplot') {
                // Load box plot data
                let url = `${baseUrl}/api/sensor/${encodeURIComponent(deviceId)}/${position}/boxplot?`;
                if (startTime) url += `start_time=${encodeURIComponent(startTime)}&`;
                if (endTime) url += `end_time=${encodeURIComponent(endTime)}&`;
                
                const response = await fetch(url);
                const result = await response.json();
                
                if (!result.data || result.data.length === 0) {
                    sensorDataInfo.innerHTML = '<div class="empty-state">No data found for this position with the specified filters</div>';
                    sensorDataCard.style.display = 'block';
                    return;
                }
                
                // Prepare box plot chart data - parse timestamps and convert to local timezone
                const timestamps = result.data.map(r => parseTimestamp(r.timestamp));
                const minValues = result.data.map(r => r.min);
                const q1Values = result.data.map(r => r.q1);
                const medianValues = result.data.map(r => r.median);
                const q3Values = result.data.map(r => r.q3);
                const maxValues = result.data.map(r => r.max);
                
                // Destroy existing chart if it exists
                if (sensorChart) {
                    sensorChart.destroy();
                }
                
                const ctx = document.getElementById('sensorChart').getContext('2d');
                
                // Prepare data for box plot chart using the boxplot plugin
                // The plugin expects data with: min, q1, median, q3, max
                const boxplotData = timestamps.map((timestamp, i) => ({
                    min: minValues[i],
                    q1: q1Values[i],
                    median: medianValues[i],
                    q3: q3Values[i],
                    max: maxValues[i]
                }));
                
                // Create box plot chart using the boxplot plugin
                sensorChart = new Chart(ctx, {
                    type: 'boxplot',
                    data: {
                        labels: timestamps.map((t, i) => i),
                        datasets: [{
                            label: `${sensorName}${unit ? ` (${unit})` : ''}`,
                            data: boxplotData,
                            backgroundColor: 'rgba(76, 175, 80, 0.2)',
                            borderColor: '#4CAF50',
                            borderWidth: 1,
                            outlierColor: '#FF0000',
                            padding: 10,
                            itemStyle: 'normal'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                type: 'category',
                                position: 'bottom',
                                title: {
                                    display: true,
                                    text: 'Time Intervals'
                                },
                                ticks: {
                                    callback: function(value, index, values) {
                                        if (index >= timestamps.length) return '';
                                        // Format based on aggregation level using Luxon
                                        const dt = timestamps[index];
                                        if (result.aggregation === 'hourly') {
                                            return dt.toLocaleString({hour: '2-digit', minute: '2-digit'});
                                        } else if (result.aggregation === '6-hourly') {
                                            return dt.toLocaleString({month: 'short', day: 'numeric', hour: '2-digit'});
                                        } else if (result.aggregation === 'daily') {
                                            return dt.toLocaleString({month: 'short', day: 'numeric'});
                                        } else {
                                            return dt.toLocaleString({month: 'short', day: 'numeric'});
                                        }
                                    },
                                    maxRotation: 45,
                                    minRotation: 45
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: `${sensorName}${unit ? ` (${unit})` : ''}`
                                },
                                beginAtZero: false
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const dataPoint = result.data[context.dataIndex];
                                        return [
                                            `Min: ${dataPoint.min.toFixed(2)} ${unit}`,
                                            `Q1: ${dataPoint.q1.toFixed(2)} ${unit}`,
                                            `Median: ${dataPoint.median.toFixed(2)} ${unit}`,
                                            `Q3: ${dataPoint.q3.toFixed(2)} ${unit}`,
                                            `Max: ${dataPoint.max.toFixed(2)} ${unit}`,
                                            `Count: ${dataPoint.count} readings`
                                        ];
                                    }
                                }
                            },
                            legend: {
                                display: true,
                                position: 'top'
                            }
                        }
                    }
                });
                
                // Show info
                sensorDataInfo.innerHTML = `<p>Showing box plot for ${sensorName} (${result.aggregation} aggregation) with ${result.data.reduce((sum, d) => sum + d.count, 0)} total readings</p>`;
                sensorDataCard.style.display = 'block';
            } else {
                // Load raw data for line chart
                let url = `${baseUrl}/api/sensor/${encodeURIComponent(deviceId)}/${position}?`;
                if (startTime) url += `start_time=${encodeURIComponent(startTime)}&`;
                if (endTime) url += `end_time=${encodeURIComponent(endTime)}&`;
                
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.length === 0) {
                    sensorDataInfo.innerHTML = '<div class="empty-state">No data found for this position with the specified filters</div>';
                    sensorDataCard.style.display = 'block';
                    return;
                }
                
                // Store raw data for potential future use
                currentRawData = data;
                
                // Prepare chart data - parse timestamps and convert to local timezone
                const timestamps = data.map(r => parseTimestamp(r.timestamp));
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
                                        hour: 'HH:mm',
                                        day: 'MMM d',
                                        week: 'MMM d',
                                        month: 'MMM yyyy'
                                    },
                                    // Use local timezone for display
                                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
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
                                        return `Time: ${timestamp.toLocaleString(luxon.DateTime.DATETIME_FULL)}`;
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
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Main page - show device list"""
    return render_template_string(HTML_TEMPLATE, base_url=request.script_root)


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


@app.route('/api/sensor/<int:device_id>/<int:position>/boxplot')
def api_sensor_boxplot(device_id, position):
    """API endpoint: get box plot data for a specific device and position
    
    Returns aggregated box plot statistics based on the time range:
    - Per 1 hour if time frame <= 1 day
    - Per 6 hours if time frame <= 1 week
    - Per 1 day if time frame <= 1 month
    - Per week otherwise
    
    Required query parameters:
    - start_time: Filter by start timestamp (ISO 8601 format)
    - end_time: Filter by end timestamp (ISO 8601 format)
    """
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    # Validate required parameters
    if not start_time or not end_time:
        return jsonify({'error': 'Both start_time and end_time query parameters are required'}), 400
    
    # Parse time range to calculate duration
    try:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    except:
        try:
            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            return jsonify({'error': f'Invalid timestamp format: {str(e)}'}), 400
    
    time_range_seconds = (end_dt - start_dt).total_seconds()
    
    # Get all sensor readings for this device and position
    all_readings = db.get_sensor_readings(device_address=None)
    
    # Filter by device_id and position
    filtered = [r for r in all_readings if r['device_id'] == device_id and r['position'] == position]
    
    # Apply mandatory time filters
    filtered = [r for r in filtered if r['timestamp'] >= start_time and r['timestamp'] <= end_time]
    
    # Sort by timestamp
    filtered.sort(key=lambda x: x['timestamp'])
    
    # Aggregate readings
    aggregated, aggregation_label = aggregate_readings(filtered, time_range_seconds)
    
    return jsonify({
        'aggregation': aggregation_label,
        'data': aggregated
    })


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
        help='Enable debug mode (deprecated: use --env development instead)'
    )
    parser.add_argument(
        '--env',
        type=str,
        default='production',
        choices=['development', 'dev', 'production', 'prod'],
        help='Environment mode: development, dev, production, prod (default: production)'
    )
    parser.add_argument(
        '--threaded',
        action='store_true',
        help='Enable threaded mode for production'
    )
    
    args = parser.parse_args()
    
    # Determine debug mode based on environment and deprecated --debug flag
    debug_mode = args.debug or args.env in ['development', 'dev']
    
    if args.debug:
        logger.warning("--debug flag is deprecated, use --env development instead")
    
    # Log mode
    if debug_mode:
        logger.warning("Running in DEVELOPMENT mode - do not use in production!")
    else:
        logger.info("Running in PRODUCTION mode")
    
    # Create app using factory - this initializes the database
    app = create_app(db_path=args.database, env=args.env)
    
    logger.info(f"Starting BTHome Web Server on {args.host}:{args.port}")
    logger.info(f"Using database: {args.database}")
    
    app.run(host=args.host, port=args.port, debug=debug_mode, threaded=args.threaded)


if __name__ == '__main__':
    main()
