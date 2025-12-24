import time
import sys
import os
import subprocess
import json
import traceback
import argparse
from typing import Optional, Dict, Any
from supabase import create_client, Client

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.config import SUPABASE_URL, SUPABASE_KEY
from src.logger import setup_logger

logger = setup_logger("worker")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_pending_job() -> Optional[Dict[str, Any]]:
    """Fetch the oldest pending job."""
    try:
        response = supabase.table("scrape_jobs") \
            .select("*") \
            .eq("status", "pending") \
            .order("created_at", desc=False) \
            .limit(1) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        return None

def check_any_running_job() -> bool:
    """Check if any job is currently in 'processing' state."""
    try:
        response = supabase.table("scrape_jobs") \
            .select("id") \
            .eq("status", "processing") \
            .limit(1) \
            .execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking running jobs: {e}")
        return False

def update_job_status(job_id: str, status: str, error_message: str = None, result_summary: str = None):
    """Update the status of a job."""
    try:
        data = {
            "status": status,
            "updated_at": "now()"
        }
        if error_message:
            data["error_message"] = error_message
        if result_summary:
            data["result_summary"] = result_summary
            
        supabase.table("scrape_jobs").update(data).eq("id", job_id).execute()
        logger.info(f"Job {job_id} updated to {status}")
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")

def run_scraper_process(job: Dict[str, Any]):
    """Run the scraper as a subprocess."""
    job_id = job["id"]
    logger.info(f"Starting job {job_id}")
    
    # Extract parameters
    course_category = job.get("course_category")
    specialization = job.get("specialization")
    city = job.get("city")
    university = job.get("university")
    engine = job.get("engine", "playwright")
    headless = job.get("headless", True)
    save_to_supabase = job.get("save_to_supabase", False)
    
    # Construct command
    cmd = [sys.executable, "main.py"]
    
    # Handle 'null' inputs for the CLI
    cmd.append(course_category if course_category else "null")
    cmd.append(specialization if specialization else "null")
    cmd.append(city if city else "null")
    cmd.append(university if university else "null")
    
    # Add flags
    if engine:
        cmd.extend(["--engine", engine])
    
    if headless:
        cmd.append("--headless")
        
    if save_to_supabase:
        cmd.append("--save")

    # Pass the job ID so the scraper can update the job status with save results
    cmd.extend(["--job-id", str(job_id)])

    # Ensure we get both JSON (for UI) and CSV (for download)
    cmd.extend(["--format", "both"])
    
    logger.info(f"Executing command: {' '.join(cmd)}")
    
    try:
        # Run the process
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=current_dir,
            env=os.environ.copy(),  # Explicitly pass environment variables to subprocess
            check=False # Don't raise exception immediately, check return code
        )
        
        if process.returncode == 0:
            logger.info(f"Job {job_id} completed successfully.")
            update_job_status(job_id, "completed", result_summary=process.stdout[-500:]) # Save last 500 chars of log
        else:
            logger.error(f"Job {job_id} failed with code {process.returncode}")
            error_msg = f"Process failed with code {process.returncode}.\nStderr: {process.stderr}"
            update_job_status(job_id, "failed", error_message=error_msg)
            
    except Exception as e:
        logger.error(f"Exception running job {job_id}: {e}")
        update_job_status(job_id, "failed", error_message=str(e))

def main():
    logger.info("Worker started (Cron Mode).")
    
    # 1. Check if another worker is already running a job
    if check_any_running_job():
        logger.info("Another job is currently processing. Exiting to maintain sequential order.")
        return

    # 2. Process jobs until queue is empty
    jobs_processed = 0
    while True:
        job = fetch_pending_job()
        if not job:
            logger.info(f"No more pending jobs. Exiting after processing {jobs_processed} jobs.")
            break
        
        job_id = job["id"]
        try:
            update_job_status(job_id, "processing")
            run_scraper_process(job)
            jobs_processed += 1
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            # If we crash on one job, continue to the next one to clear the queue
            time.sleep(1)

if __name__ == "__main__":
    main()
