# BTHome Web Server

A simple Flask-based web interface for viewing BTHome sensor data stored in the SQLite database.

## Features

- **Device Selection**: View all detected BTHome devices
- **Advertisement Browser**: Select and view individual advertisements from each device
- **Data Visualization**: View sensor readings, binary sensor states, and events with their positions
- **REST API**: JSON API endpoints for programmatic access
- **Responsive Design**: Works on desktop and mobile devices

## Quick Start

### Prerequisites

- Python 3.7+
- Flask (`pip install Flask`)
- Existing SQLite database from bthome_listener

### Running the Web Server

```bash
# Install dependencies
pip install -r requirements_web.txt

# Run the web server (default: port 5000)
python web_server.py

# With custom database path
python web_server.py --database /path/to/bthome_data.db

# With custom host and port
python web_server.py --host 0.0.0.0 --port 8080
```

Then open your browser to: `http://localhost:5000`

## Usage

1. **Select a Device**: Choose from the dropdown list of detected BTHome devices
2. **View Available Positions**: See all sensor positions for that device with their names and units
3. **Select a Position**: Click on any position to view its time series data
4. **View Data**: See all readings for that position, with optional time range filtering
5. **Apply Time Filters**: Optionally filter the data by start and end timestamps

## API Endpoints

The web server provides the following REST API endpoints:

### GET /api/devices
Returns a list of all devices.

**Response:**
```json
[
  {
    "id": 1,
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Device Name",
    "first_seen": "2024-01-01T12:00:00",
    "last_seen": "2024-01-02T12:00:00",
    "advertisement_count": 42
  }
]
```

### GET /api/device/<device_address>/positions
Returns all available sensor positions for a specific device with their metadata.

**Response:**
```json
[
  {
    "position": 0,
    "name": "temperature",
    "unit": "°C",
    "sensor_type": "sensor",
    "device_id": 1,
    "device_address": "AA:BB:CC:DD:EE:FF"
  },
  {
    "position": 1,
    "name": "humidity",
    "unit": "%",
    "sensor_type": "sensor",
    "device_id": 1,
    "device_address": "AA:BB:CC:DD:EE:FF"
  }
]
```

### GET /api/sensor/<device_id>/<position>
Returns sensor data for a specific device and position.

**Path Parameters:**
- `device_id`: The device ID (integer)
- `position`: The position in the advertisement (integer)

**Query Parameters:**
- `start_time` (optional): Filter by start timestamp (ISO 8601 format, e.g., `2024-01-01T12:00:00`)
- `end_time` (optional): Filter by end timestamp (ISO 8601 format)

**Response:**
```json
[
  {
    "id": 1,
    "advertisement_id": 123,
    "device_id": 1,
    "position": 0,
    "object_id": 2,
    "name": "temperature",
    "value": 22.5,
    "value_text": null,
    "unit": "°C",
    "timestamp": "2024-01-01T12:00:00",
    "address": "AA:BB:CC:DD:EE:FF",
    "device_name": "Device Name"
  },
  {
    "id": 2,
    "advertisement_id": 124,
    "device_id": 1,
    "position": 0,
    "object_id": 2,
    "name": "temperature",
    "value": 23.0,
    "value_text": null,
    "unit": "°C",
    "timestamp": "2024-01-01T12:05:00",
    "address": "AA:BB:CC:DD:EE:FF",
    "device_name": "Device Name"
  }
]
```

### GET /api/statistics
Returns database statistics.

**Response:**
```json
{
  "device_count": 5,
  "advertisement_count": 1000,
  "sensor_reading_count": 5000,
  "binary_sensor_reading_count": 1000,
  "event_count": 500,
  "database_size_bytes": 1048576
}
```

## Deployment Options

### Local Development
Run directly as shown above. Access at `http://localhost:5000`.

### Production with Gunicorn
For better performance in production:

```bash
pip install gunicorn
 gunicorn -w 4 -b 0.0.0.0:8000 web_server:app
```

### Behind Nginx (Recommended for Production)

Configure Nginx as a reverse proxy:

```nginx
server {
    listen 80;
    server_name bthome.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### With Basic Authentication

Use Nginx basic auth:

```nginx
location / {
    auth_basic "BTHome Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:5000;
    # ... other proxy settings
}
```

Create password file:
```bash
htpasswd -c /etc/nginx/.htpasswd username
```

Or use Flask basic auth (for development only):

```python
from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    return username == 'admin' and password == 'secret'

@app.route('/')
@auth.login_required
ndef index():
    # ... existing code
```

### As a Systemd Service

Create `/etc/systemd/system/bthome-web.service`:

```ini
[Unit]
Description=BTHome Web Server
After=network.target

[Service]
User=appuser
WorkingDirectory=/path/to/bthome_listener
ExecStart=/usr/bin/python3 /path/to/bthome_listener/web_server.py --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bthome-web
sudo systemctl start bthome-web
```

## Configuration

The web server can be configured via command-line arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `--database` | `bthome_data.db` | Path to SQLite database file |
| `--host` | `0.0.0.0` | Host to bind to |
| `--port` | `5000` | Port to listen on |
| `--debug` | `False` | Enable debug mode |

## Database Access

The web server uses the same SQLite database as the bthome_listener. Thanks to SQLite's WAL (Write-Ahead Logging) mode:

- ✅ Multiple processes can read simultaneously
- ✅ The listener can write while the web server reads
- ✅ No locking issues for read-heavy workloads

The database is opened in read-only mode for queries, so there's no risk of corruption from concurrent access.

## Customization

### Changing the Look and Feel

The HTML template is embedded in the `web_server.py` file. You can modify the `HTML_TEMPLATE` string to change:
- Colors and styling
- Layout
- What data is displayed
- How data is formatted

### Adding New Pages

Add new routes to the Flask app:

```python
@app.route('/new-page')
def new_page():
    return "My new page"
```

### Adding New API Endpoints

Add new API endpoints following the existing pattern:

```python
@app.route('/api/new-endpoint')
def new_endpoint():
    data = db.some_method()
    return jsonify(data)
```

## Troubleshooting

### Database Not Found
Make sure the database file exists at the specified path and the web server has read permissions.

### Port Already in Use
Change the port with `--port` argument, or stop the existing process.

### No Devices Showing
The database might be empty. Make sure the bthome_listener has been running and receiving advertisements.

### Slow Performance
For large databases, consider:
- Adding more indexes
- Limiting the number of results returned
- Using pagination

## Security Considerations

1. **Do NOT expose to the internet** without proper security
2. **Use HTTPS** in production (via Nginx or other reverse proxy)
3. **Enable authentication** (basic auth or better)
4. **Keep Flask updated** to latest version
5. **Run as non-root user** in production
6. **Use a firewall** to restrict access to your local network

## License

This software is provided as-is under the same license as the bthome_listener project.
