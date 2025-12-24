-- Create a table to track scraping jobs
create table public.scrape_jobs (
  id uuid default gen_random_uuid() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  
  -- Job Parameters
  course_category text,
  specialization text,
  city text,
  university text,
  
  -- Job Options
  engine text default 'playwright',
  headless boolean default true,
  
  -- Results
  result_summary text,
  error_message text,
  output_files jsonb -- Store paths or URLs of generated files
);

-- Enable Row Level Security (RLS)
alter table public.scrape_jobs enable row level security;

-- Create policies (Adjust based on your auth setup, here allowing public access for simplicity of the worker)
-- In production, you should restrict this to authenticated users and service roles.

-- Allow anyone to read jobs (for the worker and UI)
create policy "Enable read access for all users" on public.scrape_jobs
  for select using (true);

-- Allow anyone to insert jobs (for the UI)
create policy "Enable insert access for all users" on public.scrape_jobs
  for insert with check (true);

-- Allow anyone to update jobs (for the worker)
create policy "Enable update access for all users" on public.scrape_jobs
  for update using (true);
