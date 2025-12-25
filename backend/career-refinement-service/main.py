"""
Career Refinement Service

A streamlined service to:
1. Fetch career data from Supabase career_path table
2. Generate self-discovery questions using Gemini
3. Push updates back to Supabase career_path table

Generates Lovable UI fields:
- ask_yourself: 3 self-reflection questions (JSONB array)
- role_description: One-sentence career description
- impact_sentence: Motivational impact statement
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
    """Fetch all careers from career_path table."""
    client = get_supabase()
    if not client:
        return []
    try:
        # Fetch all rows (Supabase default limit is usually 1000)
        response = client.table("career_path").select("*").execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to fetch careers: {e}")
        return []

def fetch_career_by_name(career_name: str) -> Optional[Dict]:
    """Fetch a single career by name."""
    client = get_supabase()
    if not client:
        return None
    try:
        response = client.table("career_path").select("*").eq("name", career_name).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to fetch career '{career_name}': {e}")
        return None

def fetch_career_by_slug(slug: str) -> Optional[Dict]:
    """Fetch a single career by slug."""
    client = get_supabase()
    if not client:
        return None
    try:
        response = client.table("career_path").select("*").eq("slug", slug).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to fetch career with slug '{slug}': {e}")
        return None

def update_career(career_data: Dict) -> bool:
    """Update career data in 'career_path' table with Lovable fields."""
    client = get_supabase()
    if not client:
        return False

    try:
        # Get the career ID (required for update)
        career_id = career_data.get("id")
        slug = career_data.get("slug")
        
        if not career_id:
            logger.error("Career ID missing - cannot update")
            return False
        
        # Map to Lovable UI field names
        row_data = {
            "ask_yourself": career_data.get("ask_yourself"),
            "role_description": career_data.get("role_description"),
            "impact_sentence": career_data.get("impact_sentence"),
        }
        
        # Clean None values
        row_data = {k: v for k, v in row_data.items() if v is not None}

        # Update by ID
        client.table("career_path").update(row_data).eq("id", career_id).execute()
        logger.info(f"  ✓ Updated career: {slug}")
        return True
    except Exception as e:
        logger.error(f"  ✗ DB Update Failed: {e}")
        return False

# --- Service: AI (Gemini) ---
def generate_content(career_data: Dict) -> Optional[Dict]:
    """Generate Lovable UI fields: ask_yourself, role_description, impact_sentence."""
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY missing.")
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    # Extract context from career_path table columns
    name = career_data.get("name", "Unknown")
    desc = career_data.get("description", {})
    if isinstance(desc, dict):
        desc = desc.get("overview", str(desc))[:800]
    else:
        desc = str(desc)[:800]
    skills = str(career_data.get("key_skills_required", ""))[:300]

    # Prompt for Lovable UI fields
    prompt = f"""You are an expert career counselor for Indian students (Grade 9-12).

Generate content for the career: {name}

Task 1: Generate 3 SELF-DISCOVERY questions (ask_yourself)
- Start with "Do you" or "Are you"
- Focus on personality fit and interests
- Help students determine if this career suits them
- Keep each question under 100 characters

Task 2: Write a ROLE DESCRIPTION (role_description)
- 2-3 engaging sentences describing what this professional does day-to-day
- Target audience: Indian teenagers - make it relatable and clear
- Cover: What problems do they solve? What do they create or work on?
- Avoid textbook definitions - be conversational and real

Task 3: Write an IMPACT STATEMENT (impact_sentence)
- 2-3 inspiring sentences about the career's impact on society
- Why does this career matter? How does it change lives or improve the world?
- Make it motivational - help students feel excited about this path

Context:
Original Description: {desc}
Skills: {skills}

Return ONLY valid JSON:
{{
    "ask_yourself": ["Question 1?", "Question 2?", "Question 3?"],
    "role_description": "2-3 sentences describing what they do day-to-day.",
    "impact_sentence": "2-3 sentences about their impact on society."
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

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error, attempting repair: {e}")
        try:
            repaired = repair_json(cleaned)
            return json.loads(repaired)
        except Exception as repair_error:
            logger.error(f"  ✗ JSON Repair Failed: {repair_error}")
            return None
    except Exception as e:
        logger.error(f"  ✗ AI Generation Failed: {e}")
        return None

# --- Core Logic: Record Processing ---
def process_record(data: Dict, force: bool = False) -> bool:
    """Process a single DB record: Check -> Generate -> Update."""
    slug = data.get("slug")
    name = data.get("name")
    logger.info(f"Processing: {name} ({slug})")

    try:
        # Check if we need to generate (using Lovable field names)
        existing_questions = data.get("ask_yourself")
        existing_role_desc = data.get("role_description")
        existing_impact = data.get("impact_sentence")
        
        needs_generation = not existing_questions or not existing_role_desc or not existing_impact or force

        if needs_generation:
            logger.info(f"  Generating content...")
            generated_data = generate_content(data)
            
            if generated_data:
                # Update local dict with Lovable field names
                if generated_data.get("ask_yourself"):
                    data["ask_yourself"] = generated_data["ask_yourself"][:NUM_QUESTIONS]
                
                if generated_data.get("role_description"):
                    data["role_description"] = generated_data["role_description"]
                
                if generated_data.get("impact_sentence"):
                    data["impact_sentence"] = generated_data["impact_sentence"]
                
                # Update career in DB
                return update_career(data)
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
    parser = argparse.ArgumentParser(description="Career Refinement Service - Generate Lovable UI fields")
    parser.add_argument("--name", help="Single career name to process (e.g. 'Civil Engineer')")
    parser.add_argument("--slug", help="Single career slug to process (e.g. 'civil-engineer')")
    parser.add_argument("--all", action="store_true", help="Process all careers from DB")
    parser.add_argument("--force", action="store_true", help="Regenerate existing content")
    args = parser.parse_args()

    if args.name:
        logger.info(f"Fetching career by name: {args.name}")
        record = fetch_career_by_name(args.name)
        if record:
            process_record(record, args.force)
        else:
            logger.error(f"Career not found: {args.name}")
    
    elif args.slug:
        logger.info(f"Fetching career by slug: {args.slug}")
        record = fetch_career_by_slug(args.slug)
        if record:
            process_record(record, args.force)
        else:
            logger.error(f"Career not found with slug: {args.slug}")
    
    elif args.all:
        logger.info("Fetching all careers from career_path table...")
        records = fetch_all_careers()
        logger.info(f"Found {len(records)} records")
        
        for i, record in enumerate(records, 1):
            process_record(record, args.force)
            if i % DEFAULT_BATCH_SIZE == 0:
                time.sleep(1)  # Rate limiting pause
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
