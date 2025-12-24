"""
Utility functions for data processing and CSV/JSON export
"""
import csv
import pandas as pd
import json
import os
from typing import List, Dict, Set, Optional, Any, Tuple
from supabase import create_client, Client
from src.config import SUPABASE_URL, SUPABASE_KEY
from src.logger import setup_logger

logger = setup_logger()

# Cache of lowercase college names per CSV path to avoid rereading the file
_CSV_NAME_CACHE: Dict[str, Set[str]] = {}

def _read_college_names_from_csv(filepath: str) -> Set[str]:
    """Parse CSV rows defensively and return normalized college names."""
    names: Set[str] = set()

    try:
        with open(filepath, newline='', encoding='utf-8') as csv_file:
            reader = csv.reader(csv_file)
            header = next(reader, None)
            if not header:
                return names

            normalized_header = [col.strip() for col in header]
            if "College Name" not in normalized_header:
                return names

            expected_columns = len(normalized_header)
            name_index = normalized_header.index("College Name")

            for row in reader:
                if not row:
                    continue

                # Skip malformed rows that don't match the header length.
                if len(row) != expected_columns:
                    continue

                name = row[name_index].strip()
                if name:
                    names.add(name.lower())
    except Exception as exc:
        logger.warning(f"Failed to read college names from CSV {filepath}: {exc}")

    return names

def _get_csv_name_cache(filepath: str) -> Set[str]:
    """Lazy-load and cache college names already present in a CSV."""
    if filepath in _CSV_NAME_CACHE:
        return _CSV_NAME_CACHE[filepath]

    names: Set[str] = set()
    if os.path.exists(filepath):
        names = _read_college_names_from_csv(filepath)

    _CSV_NAME_CACHE[filepath] = names
    return names

def deduplicate_colleges(colleges: List[Dict]) -> List[Dict]:
    """Remove duplicate colleges based on college name"""
    seen = {}
    
    for college in colleges:
        # Handle both old format ("College Name") and new format ("name")
        college_name = college.get('College Name', college.get('name', '')).strip().lower()
        
        if not college_name:
            continue
        
        # If we haven't seen this college, or if this entry has more data, keep it
        if college_name not in seen:
            seen[college_name] = college
        else:
            # Compare data richness - keep the one with more fields
            existing = seen[college_name]
            existing_fields = sum(1 for v in existing.values() if v and str(v).strip())
            new_fields = sum(1 for v in college.values() if v and str(v).strip())
            
            if new_fields > existing_fields:
                seen[college_name] = college
    
    return list(seen.values())


def transform_college_data(colleges: List[Dict]) -> List[Dict]:
    """
    Transform extracted college data to the target JSON format
    
    Converts from:
    - "College Name" -> "name"
    - "Location" -> "city" (extract city from location string)
    - "College Type" -> "type"
    - "Course Category" -> "course_category"
    - "Total Courses" -> "total_courses"
    - "Match Percentage" -> "match_percentage"
    - "Match Level" -> "match_level"
    - "Has Website Link" -> "has_website_link"
    - "College ID" -> "college_id"
    - "Courses" -> "courses" (transform each course)
    """
    transformed = []
    
    for college in colleges:
        # Extract city from Location (format: "City" or "City, State")
        location = college.get('Location', '').strip()
        city = location.split(',')[0].strip() if location else ""
        
        # Transform college data
        transformed_college = {
            "city": city,
            "name": college.get('College Name', ''),
            "type": college.get('College Type', ''),
            "course_category": college.get('Course Category', ''),
            "total_courses": college.get('Total Courses', ''),
            "match_percentage": college.get('Match Percentage', ''),
            "match_level": college.get('Match Level', ''),
            "has_website_link": college.get('Has Website Link', ''),
            "college_id": college.get('College ID', ''),
            "courses": []
        }
        
        # Transform courses
        courses = college.get('Courses', [])
        for course in courses:
            # Convert entrance_exams to array of strings
            entrance_exams_raw = course.get('Entrance Exams', '')
            if isinstance(entrance_exams_raw, list):
                # Already a list, use it as is
                entrance_exams = [str(exam).strip() for exam in entrance_exams_raw if exam and str(exam).strip()]
            elif isinstance(entrance_exams_raw, str):
                # Split by comma if multiple exams, otherwise single item array
                if entrance_exams_raw.strip():
                    entrance_exams = [exam.strip() for exam in entrance_exams_raw.split(',') if exam.strip()]
                else:
                    entrance_exams = []
            else:
                entrance_exams = []
            
            transformed_course = {
                "name": course.get('Course Name', ''),
                "annual_fees": course.get('Fees', ''),
                "duration": course.get('Duration', ''),
                "degree_level": course.get('Degree Type', ''),
                "entrance_exams": entrance_exams
            }
            transformed_college["courses"].append(transformed_course)
        
        transformed.append(transformed_college)
    
    return transformed


def save_to_supabase(
    json_data: Dict,
    career_path: Optional[str],
    specialization: Optional[str],
    location: Optional[str],
    university: Optional[str],
    job_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Save or update data in Supabase search_criteria table
    
    Args:
        json_data: The JSON data to save (should have 'colleges' key)
        career_path: Career path filter (e.g., 'Engineering')
        specialization: Specialization filter (e.g., 'Science') or None
        location: Location filter (e.g., 'Delhi') or None
        university: University filter or None
        job_id: Optional Job ID to update status
    
    Returns:
        Tuple[bool, str]: Success flag and status message
    """
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            msg = "Supabase credentials not found. Skipping Supabase save."
            logger.warning(msg)
            return False, msg

        # Initialize Supabase client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        def _update_job_status(success: bool, message: str):
            if job_id:
                try:
                    logger.info(f"Updating job {job_id} save status -> success={success}")
                    # Update the job record (don't chain .select() - not supported in this version)
                    supabase.table("scrape_jobs").update({
                        "save_success": success,
                        "save_message": message
                    }).eq("id", job_id).execute()
                    
                    logger.info(f"Updated job {job_id} save status to {success} with message: {message}")
                except Exception as e:
                    logger.error(f"Failed to update job status for {job_id}: {e}")

        location_value = (location or "").strip()
        if not location_value:
            msg = "Location is required to save data to Supabase."
            logger.error(msg)
            _update_job_status(False, msg)
            return False, msg
        
        # Prepare the data for search_criteria table
        # Format location as "city, state" if available, or just city
        location_str = location_value
        
        # Ensure we pass a dict for the jsonb column. Use the provided `json_data`.
        if isinstance(json_data, dict):
            llm_json = json_data
        else:
            try:
                llm_json = json.loads(json_data)
            except Exception:
                llm_json = {"colleges": json_data}

        # Prepare the record data (include location so upsert conflict keys match)
        normalized_career_path = career_path.strip() if career_path else None
        normalized_specialization = specialization.strip() if specialization else None
        normalized_university = university.strip() if university else None

        def _normalize_case(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            cleaned = value.strip()
            if not cleaned:
                return None
            return cleaned[:1].upper() + cleaned[1:]

        normalized_career_path = _normalize_case(normalized_career_path)
        normalized_specialization = _normalize_case(normalized_specialization)
        normalized_university = _normalize_case(normalized_university)
        normalized_location = _normalize_case(location_str)

        record_data = {
            "career_path": normalized_career_path,
            "specialization": normalized_specialization,
            "university": normalized_university,
            "location": normalized_location,
            "llm_json": llm_json
        }
        
        def _apply_filter(query_obj, column: str, value: Optional[str]):
            if value is None:
                return query_obj.filter(column, "is", "null")
            return query_obj.eq(column, value)

        # First try to find an existing record that matches the four key columns
        # If found -> update the existing record. Otherwise -> insert a new record.
        try:
            query = supabase.table("search_criteria").select("*")

            query = _apply_filter(query, "career_path", normalized_career_path)
            query = _apply_filter(query, "specialization", normalized_specialization)
            query = _apply_filter(query, "university", normalized_university)
            query = _apply_filter(query, "location", normalized_location)

            existing = query.limit(1).execute()

            if getattr(existing, "data", None) and len(existing.data) > 0:
                # Update the first matching record
                record_id = existing.data[0].get("id")
                if record_id:
                    supabase.table("search_criteria").update(record_data).eq("id", record_id).execute()
                    msg = f"Updated existing record in Supabase (ID: {record_id})"
                    logger.info(msg)
                    _update_job_status(True, msg)
                    return True, msg

            # No matching record found -> insert a new one
            response = supabase.table("search_criteria").insert(record_data).execute()
            if getattr(response, "data", None) and len(response.data) > 0:
                msg = f"Inserted new record in Supabase (ID: {response.data[0].get('id', 'N/A')})"
                logger.info(msg)
                _update_job_status(True, msg)
                return True, msg
            else:
                msg = "Supabase insert returned no data"
                logger.warning(msg)
                _update_job_status(False, msg)
                return False, msg
        except Exception as e:
            logger.error(f"Supabase operation failed: {e}")
            raise
            
    except Exception as e:
        msg = f"Error saving to Supabase: {e}"
        logger.error(msg)
        try:
            if 'supabase' in locals() and supabase and job_id:
                 supabase.table("scrape_jobs").update({
                     "save_success": False,
                     "save_message": msg
                 }).eq("id", job_id).execute()
        except:
            pass
        return False, msg


def save_to_csv(data: List[Dict], output_dir: str, filename: str):
    """Save data to CSV file"""
    os.makedirs(output_dir, exist_ok=True)
    
    if data:
        logger.info(f"Removing duplicates from {len(data)} records...")
        data = deduplicate_colleges(data)
        logger.info(f"After deduplication: {len(data)} unique records")
        
        df = pd.DataFrame(data)
        filepath = os.path.join(output_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8')
        logger.info(f"CSV saved to {filepath}")
        logger.info(f"Total unique records: {len(data)}")
        return filepath
    else:
        logger.warning("No data to save")
        return None


def save_to_json(
    data: List[Dict], 
    output_dir: str, 
    filename: str,
    push_to_supabase: bool = False,
    career_path: Optional[str] = None,
    specialization: Optional[str] = None,
    location: Optional[str] = None,
    university: Optional[str] = None,
    job_id: Optional[str] = None
):
    """
    Save data to JSON file and optionally to Supabase
    
    Args:
        data: List of college dictionaries
        output_dir: Directory to save the file
        filename: Name of the file
        push_to_supabase: If True, also save to Supabase
        career_path: Career path filter for Supabase
        specialization: Specialization filter for Supabase
        location: Location filter for Supabase
        university: University filter for Supabase
        job_id: Supabase Job ID to update with save status
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if data:
        logger.info(f"Removing duplicates from {len(data)} records...")
        data = deduplicate_colleges(data)
        logger.info(f"After deduplication: {len(data)} unique records")
        
        # Transform data to target format
        logger.info(f"Transforming data to target format...")
        transformed_data = transform_college_data(data)
        
        # Prepare JSON structure with 'colleges' key
        json_data = {"colleges": transformed_data}
        
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON saved to {filepath}")
        logger.info(f"Total unique records: {len(transformed_data)}")
        
        # Save to Supabase when explicitly requested
        if push_to_supabase:
            logger.info("Saving to Supabase...")
            success, supabase_msg = save_to_supabase(
                json_data=json_data,
                career_path=career_path,
                specialization=specialization,
                location=location,
                university=university,
                job_id=job_id
            )
            if success:
                logger.info(supabase_msg)
            else:
                logger.error(supabase_msg)
        
        return filepath
    else:
        logger.warning("No data to save")
        return None


def save_data(
    data: List[Dict], 
    output_dir: str, 
    base_filename: str, 
    formats: List[str] = ['csv'],
    push_to_supabase: bool = False,
    career_path: Optional[str] = None,
    specialization: Optional[str] = None,
    location: Optional[str] = None,
    university: Optional[str] = None,
    job_id: Optional[str] = None
 ):
    """
    Save data in multiple formats
    
    Args:
        data: List of dictionaries containing college data
        output_dir: Directory to save files
        base_filename: Base filename without extension
        formats: List of formats to save ('csv', 'json', or both)
        push_to_supabase: If True, also save to Supabase when saving JSON
        career_path: Career path filter for Supabase
        specialization: Specialization filter for Supabase
        location: Location filter for Supabase
        university: University filter for Supabase
        job_id: Supabase Job ID to update with save status
    
    Returns:
        Dictionary mapping format to filepath
    """
    saved_files = {}
    
    for fmt in formats:
        if fmt.lower() == 'csv':
            filename = f"{base_filename}.csv" if not base_filename.endswith('.csv') else base_filename
            filepath = save_to_csv(data, output_dir, filename)
            if filepath:
                saved_files['csv'] = filepath
        
        elif fmt.lower() == 'json':
            filename = f"{base_filename}.json" if not base_filename.endswith('.json') else base_filename
            # Remove .csv extension if present
            filename = filename.replace('.csv', '.json')
            filepath = save_to_json(
                data, 
                output_dir, 
                filename,
                push_to_supabase=push_to_supabase,
                career_path=career_path,
                specialization=specialization,
                location=location,
                university=university,
                job_id=job_id
            )
            if filepath:
                saved_files['json'] = filepath
    
    return saved_files


def clean_text(text: str) -> str:
    """Clean and normalize text data"""
    if not text:
        return ""

    # Remove extra whitespace and newlines
    text = ' '.join(text.split())
    return text.strip()


def append_to_csv(data: Dict, output_dir: str, filename: str):
    """
    Append a single record to CSV file.
    Creates file with header if it doesn't exist.
    Checks for duplicates based on College Name before appending.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    
    try:
        new_name = data.get('College Name', '').strip().lower()
        name_cache = None
        if new_name:
            name_cache = _get_csv_name_cache(filepath)
            if new_name in name_cache:
                return True

        df = pd.DataFrame([data])
        
        # Check if file exists to determine if we need to write header
        header = not os.path.exists(filepath)
        
        df.to_csv(filepath, mode='a', header=header, index=False, encoding='utf-8')
        if new_name and name_cache is not None:
            name_cache.add(new_name)
        return True
    except Exception as e:
        logger.error(f"Failed to append to CSV: {e}")
        return False


def append_to_jsonl(data: Dict, output_dir: str, filename: str):
    """
    Append a single record to a JSONL file (one JSON object per line).
    Efficient O(1) append, crash-safe.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    
    try:
        # Note: We don't check for duplicates here to keep it O(1).
        # Deduplication relies on the scraper checking `processed_colleges` before calling this.
        
        with open(filepath, 'a', encoding='utf-8') as f:
            json_line = json.dumps(data, ensure_ascii=False)
            f.write(json_line + '\n')
            
        return True
    except Exception as e:
        logger.error(f"Failed to append to JSONL: {e}")
        return False


def load_existing_colleges(
    output_dir: str,
    base_filename: str,
    formats: Optional[List[str]] = None
) -> Dict[str, Set[str]]:
    """Load already-scraped college names grouped per requested format.

    Returning a mapping lets callers decide whether a college must exist in all
    requested formats before it gets skipped. This enables scenarios like
    regenerating a missing CSV row even when the JSON export still contains the
    record.

    Args:
        output_dir: Directory containing export files.
        base_filename: Base filename without extension.
        formats: Restricts which file types to inspect (e.g. ['csv'], ['json']).
                 Defaults to checking both CSV and JSONL for backward compatibility.
    """

    default_formats = ['csv', 'json'] if formats is None else formats
    formats_lower = [fmt.lower() for fmt in default_formats]
    existing: Dict[str, Set[str]] = {fmt: set() for fmt in formats_lower}

    if 'csv' in formats_lower:
        csv_path = os.path.join(output_dir, f"{base_filename}.csv")
        if os.path.exists(csv_path):
            names = _read_college_names_from_csv(csv_path)
            existing['csv'].update(names)
            logger.info(f"Loaded {len(names)} existing records from CSV")

    if 'json' in formats_lower:
        jsonl_path = os.path.join(output_dir, f"{base_filename}.jsonl")
        if os.path.exists(jsonl_path):
            try:
                count = 0
                with open(jsonl_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            name = data.get('College Name', '').strip().lower()
                            if name:
                                existing['json'].add(name)
                                count += 1
                        except json.JSONDecodeError:
                            continue
                logger.info(f"Loaded {count} existing records from JSONL")
            except Exception as e:
                logger.warning(f"Failed to read existing JSONL for resumability: {e}")

    return existing