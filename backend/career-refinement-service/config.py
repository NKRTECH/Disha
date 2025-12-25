"""Configuration for Career Refinement Service"""
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Processing Configuration
DEFAULT_BATCH_SIZE = 10
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Question Generation Settings
NUM_QUESTIONS = 3
QUESTION_MAX_LENGTH = 100
