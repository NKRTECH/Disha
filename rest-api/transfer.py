from supabase import create_client, Client
import json

# --- Setup (Replace with your actual keys) ---
SUPABASE_URL = 'https://czqyykcerlzhmrsfdfmq.supabase.co';
SUPABASE_PUBLISHABLE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cXl5a2Nlcmx6aG1yc2ZkZm1xIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAyMDg5NjgsImV4cCI6MjA3NTc4NDk2OH0.2QOLg_5_gHsHlEkLjgFmLoxfQGeHK4Iuo13am5qZB3Y'

supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
# ---------------------------------------------

# 1. Fetch data from the source table
try:
    source_table = 'st_career_path'
    response = supabase.table(source_table).select('json_data').execute()
    source_data = response.data

except Exception as e:
    print(f"? Error fetching data: {e}")
    exit()

# 2. Process the data and prepare for insertion
new_records = []
for record in source_data:
    print("Processing...", record)
    # Ensure the 'json' field is present and not null
    json_data = record.get('json_data')
    if not json_data:
        continue

    try:
        # Navigate the JSON object to get the description
        # Assuming the structure is: {"details": {"description": "..."}}
        description = json_data.get('description')
        name=json_data.get('career_path')
        role_responsibilities=json_data.get('role_responsibilities')
        education_required=json_data.get('education_required')
        salary_demand=json_data.get('salary_demand')
        career_options=json_data.get('career_options')
        key_skills_required=json_data.get('key_skills_required')

        if description:
            new_records.append({"description": description, "name": name, "role_responsibilities": role_responsibilities,"education_required":education_required, "salary_demand":salary_demand,"career_options":career_options, "key_skills_required":key_skills_required})
            
    except Exception as e:
        print(f"Warning: Failed to parse JSON for a record. Error: {e}")
        
print(f"Prepared {len(new_records)} records for insertion.")

# 3. Insert the processed data into the destination table
if new_records:
    try:
        destination_table = 'career_path1'
        insert_response = supabase.table(destination_table).insert(new_records).execute()
        
        print(f"? Successfully inserted {len(new_records)} descriptions into '{destination_table}'.")
        
    except Exception as e:
        print(f"? Error inserting data: {e}")