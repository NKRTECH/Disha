"""
Configuration file for login credentials and URLs
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Get the project root directory (parent of src/)
project_root = Path(__file__).parent.parent

# Load environment variables from .env file in project root
load_dotenv(dotenv_path=project_root / '.env')

# Login credentials
LOGIN_EMAIL = os.getenv("LOGIN_EMAIL", "kundu.ansh@yahoo.com")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "anshk05")

# URLs
MAIN_URL = "https://careerzoom.edumilestones.com/"
COLLEGE_SEARCH_URL = "https://careertest.edumilestones.com/india-colleges/"

# Browser settings
HEADLESS = False  # Set to True to run browser in background
WAIT_TIMEOUT = 10  # Timeout in seconds for element waits

# Output settings
OUTPUT_DIR = "data"
CSV_FILENAME = "colleges_data.csv"

# Deployment mode - set SERVERLESS_MODE=true for read-only file systems (Leapcell, AWS Lambda, etc.)
SERVERLESS_MODE = os.getenv("SERVERLESS_MODE", "false").lower() in ("true", "1", "yes")

# Scraping settings
MAX_SCROLLS = 50  # Maximum number of scrolls to load all colleges
MAX_PAGES = 10    # Maximum number of pages to scrape (pagination)
SCROLL_PAUSE_TIME = 2  # Seconds to wait between scrolls

# Supabase settings
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")