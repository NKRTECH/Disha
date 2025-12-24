-- Add save_message and save_success columns to scrape_jobs table
alter table public.scrape_jobs 
add column if not exists save_message text,
add column if not exists save_success boolean;
