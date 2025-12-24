-- Add save_to_supabase column to scrape_jobs table
alter table public.scrape_jobs 
add column save_to_supabase boolean default false;
