"""
Career Refinement Service (Simplified)

A streamlined service to:
1. Fetch career data from Supabase staging DB
2. Generate self-discovery questions using Gemini
3. Push updates back to Supabase staging DB
"""
import json
import time
import argparse
import logging
from typing import Optional, List, Dict, Any

import google.generativeai as genai
from supabase import create_client, Client
from json_repair import repair_json

# Import configuration
from config import (
    GEMINI_API_KEY, 
    GEMINI_MODEL, 
    SUPABASE_URL, 
    SUPABASE_KEY,
    NUM_QUESTIONS,
    DEFAULT_BATCH_SIZE
)

# --- Setup Logging ---
# Configure logging to write to both file (DEBUG) and console (INFO)
logger = logging.getLogger("CareerRefinement")
logger.setLevel(logging.DEBUG)

# Console Handler
c_handler = logging.StreamHandler()
c_handler.setLevel(logging.INFO)
c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
c_handler.setFormatter(c_format)

# File Handler
f_handler = logging.FileHandler('career_refinement.log', encoding='utf-8')
f_handler.setLevel(logging.DEBUG)
f_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
f_handler.setFormatter(f_format)

# Add handlers
if not logger.handlers:
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

# --- Service: Database (Supabase) ---
_supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    """Singleton to get Supabase client."""
    global _supabase_client
    if _supabase_client:
        return _supabase_client
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials missing. DB sync disabled.")
        return None
        
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase_client
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        return None

def fetch_all_careers() -> List[Dict]:
    """Fetch all careers from staging DB."""
    client = get_supabase()
    if not client:
        return []
    try:
        # Fetch all rows (Supabase default limit is usually 1000)
        response = client.table("career_paths_staging").select("*").execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to fetch careers: {e}")
        return []

def fetch_career_by_path(career_path: str) -> Optional[Dict]:
    """Fetch a single career by career_path."""
    client = get_supabase()
    if not client:
        return None
    try:
        response = client.table("career_paths_staging").select("*").eq("career_path", career_path).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to fetch career '{career_path}': {e}")
        return None

def push_to_staging(career_data: Dict) -> bool:
    """Push career data to 'career_paths_staging' table."""
    client = get_supabase()
    if not client:
        return False

    try:
        # Prepare data
        career_path = career_data.get("career_path") or career_data.get("name")
        if not career_path:
            return False
            
        # Use existing slug if available, else generate
        slug = career_data.get("slug")
        if not slug:
            slug = career_path.lower().replace(" ", "-").replace(",", "").replace("--", "-")
        
        # Map JSON fields to DB columns
        row_data = {
            "slug": slug,
            "career_path": career_path,
            "exploration_questions": career_data.get("exploration_questions"),
            "description": career_data.get("desc`ription"),
            "refined_description": career_data.get("refined_description"),
            "role_responsibilities": career_data.get("role_responsibilities"),
            "key_skills_required": career_data.get("key_skills_required"),
            "career_options": career_data.get("career_options"),
            "salary_demand": career_data.get("salary_demand"),
            "education_required": career_data.get("education_required"),
            "best_colleges": career_data.get("best_colleges"),
        }
        
        # Clean None values
        row_data = {k: v for k, v in row_data.items() if v is not None}

        # Upsert
        client.table("career_paths_staging").upsert(row_data, on_conflict="slug").execute()
        logger.info(f"  ✓ Pushed to DB: {slug}")
        return True
    except Exception as e:
        logger.error(f"  ✗ DB Push Failed: {e}")
        return False

# --- Service: AI (Gemini) ---
def generate_content(career_data: Dict) -> Optional[Dict]:
    """Generate self-discovery questions AND refined description using Gemini."""
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY missing.")
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    # Extract context
    name = career_data.get("career_path") or career_data.get("name", "Unknown")
    desc = str(career_data.get("description", ""))[:800]
    skills = str(career_data.get("key_skills_required", ""))[:300]

    # Prompt
    prompt = f"""You are an expert career counselor for Indian students (Grade 9-12).

Task 1: Generate 3 SELF-DISCOVERY questions for: {name}
- Start with "Do you" or "Are you"
- Focus on personality fit and interests
- Keep under 120 chars

Task 2: Write a REFINED DESCRIPTION for: {name}
- Target Audience: Indian teenagers. Tone should be inspiring, clear, and relatable.
- Structure:
  1. The Hook: Start with a relatable scenario or question that connects to the career.
  2. The Reality: Explain what they actually DO day-to-day. Solve problems? Create things? Help people? (Avoid textbook definitions).
  3. The Impact: Why does this career matter? How does it change the world or help society?
- Length: 2-3 paragraphs.

Context:
Original Description: {desc}
Skills: {skills}

Return ONLY valid JSON:
{{
    "exploration_questions": ["Question 1?", "Question 2?", "Question 3?"],
    "refined_description": "Paragraph 1... Paragraph 2..."
}}"""

    try:
        logger.debug(f"Sending prompt to Gemini for: {name}")
        response = model.generate_content(
            prompt, 
            generation_config={"temperature": 0.7, "top_p": 0.9}
        )
        
        if not response.text:
            logger.warning("Gemini returned empty response")
            return None

        # Log raw response for debugging
        logger.debug(f"Raw Gemini Response for {name}:\n{response.text}")

        # Parse JSON
        cleaned = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(cleaned)
        
        return data

    except Exception as e:
        logger.error(f"  ✗ AI Generation Failed: {e}")
        return None

# --- Core Logic: Record Processing ---
def process_record(data: Dict, force: bool = False) -> bool:
    """Process a single DB record: Check -> Generate -> Push."""
    slug = data.get("slug")
    name = data.get("career_path")
    logger.info(f"Processing: {name} ({slug})")

    try:
        # Check if we need to generate
        existing_questions = data.get("exploration_questions")
        existing_refined_desc = data.get("refined_description")
        
        needs_generation = not existing_questions or not existing_refined_desc or force

        if needs_generation:
            logger.info(f"  Generating content...")
            generated_data = generate_content(data)
            
            if generated_data:
                # Update local dict
                if generated_data.get("exploration_questions"):
                    data["exploration_questions"] = generated_data["exploration_questions"][:NUM_QUESTIONS]
                
                if generated_data.get("refined_description"):
                    data["refined_description"] = generated_data["refined_description"]
                
                # Push update to DB
                return push_to_staging(data)
            else:
                logger.warning("  ⚠ Failed to generate content")
                return False
        else:
            logger.info("  Content already exists (skipping)")
            return True

    except Exception as e:
        logger.error(f"Error processing {slug}: {e}")
        return False

# --- CLI Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Career Refinement Service")
    parser.add_argument("--career-path", help="Single career path name to process (e.g. 'Fashion Designing')")
    parser.add_argument("--all", action="store_true", help="Process all careers from DB")
    parser.add_argument("--force", action="store_true", help="Regenerate existing content")
    args = parser.parse_args()

    if args.career_path:
        logger.info(f"Fetching career: {args.career_path}")
        record = fetch_career_by_path(args.career_path)
        if record:
            process_record(record, args.force)
        else:
            logger.error(f"Career not found: {args.career_path}")
    
    elif args.all:
        logger.info("Fetching all careers from DB...")
        records = fetch_all_careers()
        logger.info(f"Found {len(records)} records")
        
        for i, record in enumerate(records, 1):
            process_record(record, args.force)
            if i % DEFAULT_BATCH_SIZE == 0:
                time.sleep(1) # Rate limiting pause
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
