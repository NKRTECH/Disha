import streamlit as st
import sys
import os
import json
import time
import glob
import pandas as pd
from typing import List, Dict, Optional, Tuple
from supabase import create_client, Client

# Add the current directory to sys.path to allow imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.logger import setup_logger
from src.config import SUPABASE_URL, SUPABASE_KEY
from src.utils import save_to_supabase

logger = setup_logger("scraper_ui")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuration
DATA_DIR = os.path.join(current_dir, "data")

st.set_page_config(
    page_title="College Data Scraper",
    page_icon="🕷️",
    layout="wide"
)

# --- Helper Functions ---

def load_latest_data(base_filename: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the most recently created JSON file matching the base filename."""
    # Look for json files in data dir
    pattern = os.path.join(DATA_DIR, f"*{base_filename}*.json")
    files = glob.glob(pattern)
    
    if not files:
        return None, None
        
    # Get latest file
    latest_file = max(files, key=os.path.getctime)
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            return json.load(f), latest_file
    except Exception as e:
        st.error(f"Error reading file {latest_file}: {e}")
        return None, None

def infer_filters_from_payload(json_payload: Dict) -> Dict[str, Optional[str]]:
    """Best-effort extraction of filter metadata from a scrape result."""
    inferred = {
        "career_path": None,
        "specialization": None,
        "location": None,
        "university": None
    }

    if not isinstance(json_payload, dict):
        return inferred

    colleges = json_payload.get("colleges") or []
    if not isinstance(colleges, list) or not colleges:
        return inferred

    def _single_value(values):
        cleaned = [str(v).strip() for v in values if v and str(v).strip()]
        if not cleaned:
            return None
        unique = set(cleaned)
        if len(unique) == 1:
            return cleaned[0]
        return None

    inferred["career_path"] = _single_value([c.get("course_category") for c in colleges])
    inferred["location"] = _single_value([c.get("city") for c in colleges])
    inferred["university"] = _single_value([c.get("university") for c in colleges])

    return inferred

def submit_job(course_category, specialization, city, university, headless, engine, save_to_supabase):
    """Submit a scraping job to Supabase."""
    try:
        job_data = {
            "course_category": course_category,
            "specialization": specialization,
            "city": city,
            "university": university,
            "engine": engine,
            "headless": headless,
            "save_to_supabase": save_to_supabase,
            "status": "pending"
        }
        response = supabase.table("scrape_jobs").insert(job_data).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        st.error(f"Failed to submit job: {e}")
        return None

def get_job_status(job_id):
    """Fetch the current status of a job."""
    try:
        response = supabase.table("scrape_jobs").select("*").eq("id", job_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching job status: {e}")
        return None

# --- UI Layout ---

st.title("🕷️ College Data Scraper (Decoupled)")
st.markdown("""
This interface queues scraping jobs to a database. A separate worker process executes them.
**Note:** File downloads and previews below assume the worker is running on the same machine (sharing the `data/` folder).
""")

with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.subheader("Filters")
    course_category = st.text_input("Course Category", placeholder="e.g. Engineering")
    specialization = st.text_input("Specialization", placeholder="e.g. Computer Science")
    city = st.text_input("City", placeholder="e.g. Bangalore")
    university = st.text_input("University", placeholder="e.g. Bangalore University")
    
    st.markdown("---")
    
    st.subheader("Options")
    engine = st.selectbox("Scraping Engine", ["playwright", "selenium"], index=0)
    headless = st.checkbox("Headless Mode", value=True, help="Run browser in background")
    save_to_supabase = st.checkbox("Save to Supabase", value=False, help="Automatically save scraped data to database")
    
    st.markdown("---")
    
    run_btn = st.button("🚀 Queue Scraper Job", type="primary", use_container_width=True)

# Main Content Area
if run_btn:
    if not any([course_category, specialization, city, university]):
        msg = "⚠️ Please provide at least one filter (Category, Specialization, City, or University)."
        st.error(msg)
    else:
        with st.spinner("Submitting job..."):
            job = submit_job(course_category, specialization, city, university, headless, engine, save_to_supabase)
        
        if job:
            job_id = job['id']
            st.success(f"✅ Job submitted successfully! ID: `{job_id}`")
            
            # Poll for status
            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            
            while True:
                job_info = get_job_status(job_id)
                if not job_info:
                    st.error("Lost connection to job.")
                    break
                
                status = job_info['status']
                status_placeholder.info(f"Current Status: **{status.upper()}**")
                
                if status == 'pending':
                    progress_bar.progress(10)
                elif status == 'processing':
                    progress_bar.progress(50)
                elif status == 'completed':
                    progress_bar.progress(100)
                    st.success("🎉 Job Completed!")
                    
                    if job_info.get('result_summary'):
                        with st.expander("View Logs"):
                            st.code(job_info['result_summary'])
                    
                    # --- Restore Result Visualization ---
                    # Try to find the file generated by this job
                    parts = [p for p in [course_category, specialization, city, university] if p]
                    base_name_guess = "_".join(parts) if parts else "colleges_data"
                    base_name_guess = base_name_guess.replace(" ", "_")
                    
                    data, filepath = load_latest_data(base_name_guess)
                    
                    if data and "colleges" in data:
                        colleges_data = data["colleges"]
                        st.subheader(f"📊 Results ({len(colleges_data)} colleges)")
                        
                        flat_data = []
                        for c in colleges_data:
                            flat_data.append({
                                "Name": c.get("name"),
                                "City": c.get("city"),
                                "Type": c.get("type"),
                                "Courses": len(c.get("courses", [])),
                                "Website": "Yes" if c.get("has_website_link") else "No"
                            })
                        
                        df = pd.DataFrame(flat_data)
                        st.dataframe(df, use_container_width=True)
                        
                        # Download buttons
                        col1, col2 = st.columns(2)
                        with col1:
                            with open(filepath, "r", encoding="utf-8") as f:
                                st.download_button(
                                    label="📥 Download JSON",
                                    data=f,
                                    file_name=os.path.basename(filepath),
                                    mime="application/json"
                                )
                        
                        with col2:
                            csv_path = filepath.replace(".json", ".csv")
                            if os.path.exists(csv_path):
                                with open(csv_path, "r", encoding="utf-8") as f:
                                    st.download_button(
                                        label="📥 Download CSV",
                                        data=f,
                                        file_name=os.path.basename(csv_path),
                                        mime="text/csv"
                                    )
                        
                        st.markdown("---")
                        push_status = st.empty()
                        if st.button("☁️ Push to Supabase", help="Save these results to the Supabase database"):
                            derived_filters = infer_filters_from_payload(data)
                            effective_filters = {
                                "career_path": course_category or derived_filters["career_path"],
                                "specialization": specialization or derived_filters["specialization"],
                                "location": city or derived_filters["location"],
                                "university": university or derived_filters["university"]
                            }

                            if not effective_filters["location"]:
                                push_status.error("Unable to infer a location. Please rerun with the City filter specified.")
                            else:
                                push_status.info("Sending current scrape to Supabase...")
                                with st.spinner("Pushing data to Supabase..."):
                                    success, supabase_msg = save_to_supabase(
                                        json_data=data,
                                        career_path=effective_filters["career_path"],
                                        specialization=effective_filters["specialization"],
                                        location=effective_filters["location"],
                                        university=effective_filters["university"]
                                    )
                                if success:
                                    push_status.success(f"Supabase update completed: {supabase_msg}")
                                else:
                                    push_status.error(f"Supabase push failed: {supabase_msg}")
                    else:
                        st.warning("Job completed, but could not find the generated file locally. (If the worker is on a different machine, this is expected).")
                    
                    break
                elif status == 'failed':
                    progress_bar.progress(100)
                    st.error("❌ Job Failed.")
                    if job_info.get('error_message'):
                        st.error(f"Error: {job_info['error_message']}")
                    break
                
                time.sleep(2)
        else:
            st.error("Could not create job.")

else:
    # Show recent jobs
    st.markdown("### 🕒 Recent Jobs")
    try:
        response = supabase.table("scrape_jobs").select("*").order("created_at", desc=True).limit(10).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            
            # Rename columns for better display if they exist
            column_config = {
                "save_to_supabase": "Auto Save",
                "save_success": "Save Status",
                "save_message": "Save Details"
            }
            
            # Ensure we have the columns we want to show
            desired_cols = ["id", "created_at", "status", "city", "course_category", "save_to_supabase", "save_success", "save_message"]
            available_cols = df.columns.tolist()
            cols_to_show = [c for c in desired_cols if c in available_cols]
            
            # Create a display dataframe
            df_display = df[cols_to_show].copy()
            
            # Format boolean columns if they exist
            if "save_success" in df_display.columns:
                df_display["save_success"] = df_display["save_success"].apply(
                    lambda x: "✅" if x is True else ("❌" if x is False else "—")
                )
            
            if "save_to_supabase" in df_display.columns:
                df_display["save_to_supabase"] = df_display["save_to_supabase"].apply(
                    lambda x: "Yes" if x is True else "No"
                )

            # Rename columns
            df_display = df_display.rename(columns=column_config)
            
            st.dataframe(
                df_display, 
                use_container_width=True,
                column_config={
                    "Save Details": st.column_config.TextColumn(
                        "Save Details",
                        help="Details about the Supabase save operation",
                        width="medium"
                    )
                }
            )
        else:
            st.info("No recent jobs found.")
    except Exception as e:
        st.error(f"Error fetching recent jobs: {e}")

    # --- Restore Recent Files Section ---
    if os.path.exists(DATA_DIR):
        st.markdown("### 📂 Recently Scraped Data (Local)")
        
        tab1, tab2 = st.tabs(["CSV Files", "JSON Files"])
        
        with tab1:
            csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
            if csv_files:
                csv_files.sort(key=os.path.getmtime, reverse=True)
                for f in csv_files[:5]:
                    st.text(f"📄 {os.path.basename(f)}")
            else:
                st.caption("No CSV files found.")
                
        with tab2:
            json_files = glob.glob(os.path.join(DATA_DIR, "*.json"))
            if json_files:
                json_files.sort(key=os.path.getmtime, reverse=True)
                for f in json_files[:5]:
                    col_file, col_btn = st.columns([3, 1])
                    with col_file:
                        st.text(f"📄 {os.path.basename(f)}")
                    with col_btn:
                        push_file_status = st.empty()
                        if st.button("☁️ Push", key=f"push_{f}", help="Push this file to Supabase"):
                            try:
                                push_file_status.info(f"Sending {os.path.basename(f)} to Supabase...")
                                with open(f, 'r', encoding='utf-8') as json_file:
                                    file_data = json.load(json_file)
                                    
                                derived_filters = infer_filters_from_payload(file_data)

                                if not derived_filters["location"]:
                                    push_file_status.error("Unable to infer a unique city from this file. Please rerun the scrape with City specified.")
                                else:
                                    with st.spinner(f"Pushing {os.path.basename(f)}..."):
                                        success, supabase_msg = save_to_supabase(
                                            json_data=file_data,
                                            career_path=derived_filters["career_path"],
                                            specialization=derived_filters["specialization"],
                                            location=derived_filters["location"],
                                            university=derived_filters["university"]
                                        )
                                    if success:
                                        push_file_status.success(f"Supabase update completed: {supabase_msg}")
                                    else:
                                        push_file_status.error(f"Supabase push failed: {supabase_msg}")
                            except Exception as e:
                                push_file_status.error(f"Error: {e}")
            else:
                st.caption("No JSON files found.")
