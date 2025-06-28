# scripts/utils/config.py
"""
Configuration management for the Mariupol Toponyms Database
Loads settings from environment variables and provides defaults
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging
from datetime import datetime

# Load environment variables from .env file
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
load_dotenv(env_path)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'mariupol_toponyms'),
    'user': os.getenv('DB_USER', 'mariupol_researcher'),
    'password': os.getenv('DB_PASSWORD', 'change_me_please!')
}

# Project paths
PROJECT_ROOT = project_root
DATA_DIR = PROJECT_ROOT / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / 'processed'
BACKUP_DIR = DATA_DIR / 'backups'
LOG_DIR = PROJECT_ROOT / 'logs'
SQL_DIR = PROJECT_ROOT / 'sql'

# Create directories if they don't exist
for directory in [RAW_DATA_DIR, PROCESSED_DATA_DIR, BACKUP_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def setup_logging(name: str) -> logging.Logger:
    """
    Set up logging for a module
    
    Args:
        name: Logger name (usually __name__ from the calling module)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)
    
    # File handler (one log file per day)
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}_toponyms.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)
    
    return logger

# API endpoints
OVERPASS_API_URL = os.getenv('OVERPASS_API_URL', 'https://overpass-api.de/api/interpreter')
# Important geographical settings
MARIUPOL_BBOX = "47.0002828,37.2942822,47.2294948,37.7554739" # Exact BBOX from Overpass XML for Hromada
# Important dates for the project
INVASION_DATE = '2022-02-24'  # Date of Russian invasion
PRE_WAR_DATE = '2022-02-23'   # Last day before invasion

# Common settings
DEFAULT_LANGUAGE = 'uk'  # Ukrainian
SUPPORTED_LANGUAGES = ['uk', 'ru', 'en']