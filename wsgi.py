#!/usr/bin/env python3
"""
WSGI Entry Point for BTHome Web Server

This module provides the WSGI application entry point for running the
BTHome web server with production WSGI servers like Gunicorn or uWSGI.

Configuration is done via environment variables:
    BTHOME_DATABASE: Path to SQLite database (default: bthome_data.db)
    BTHOME_ENV: Environment mode (development, dev, production, prod) (default: production)

Usage with Gunicorn:
    gunicorn --bind 0.0.0.0:5000 --workers 4 --threads 2 wsgi:application

Or using the convenience script:
    ./run_gunicorn.sh
"""

import os
import logging
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from web_server import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration from environment
DB_PATH = os.environ.get('BTHOME_DATABASE', 'bthome_data.db')
ENV = os.environ.get('BTHOME_ENV', 'production')
APP_MOUNT_PATH = os.environ.get('APP_MOUNT_PATH', '/watering')

# Validate environment
VALID_ENVS = ['development', 'dev', 'production', 'prod']
if ENV not in VALID_ENVS:
    logger.warning(f"Invalid BTHOME_ENV value: {ENV}. Using 'production' as fallback.")
    ENV = 'production'

# Create the Flask application
flask_app = create_app(db_path=DB_PATH, env=ENV)

# Mount the Flask app at the specified path using DispatcherMiddleware
# This ensures Flask receives the correct SCRIPT_NAME for URL generation
application = DispatcherMiddleware(None, {
    APP_MOUNT_PATH: flask_app
})

logger.info(f"WSGI application created")
logger.info(f"Database: {DB_PATH}")
logger.info(f"Environment: {ENV}")
logger.info(f"Mount path: {APP_MOUNT_PATH}")
