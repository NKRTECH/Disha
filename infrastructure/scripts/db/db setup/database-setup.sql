-- Run this SQL in your Supabase SQL Editor to set up the database

-- Create cluster table

CREATE TABLE public.career_cluster (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT career_cluster_pkey PRIMARY KEY (id)
);

-- Create stream table
CREATE TABLE public.stream (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT stream_pkey PRIMARY KEY (id)
);

-- Create subject table
CREATE TABLE public.subject (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT subject_pkey PRIMARY KEY (id)
);

-- Create skill table
CREATE TABLE public.skill (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  category text CHECK (category = ANY (ARRAY['technical'::text, 'soft'::text, NULL::text])),
  description text,
  CONSTRAINT skill_pkey PRIMARY KEY (id)
);

-- Create entrance_exam table
CREATE TABLE public.entrance_exam (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  eligibility text,
  exam_pattern text,
  difficulty_level text CHECK (difficulty_level = ANY (ARRAY['Easy'::text, 'Medium'::text, 'Hard'::text, 'Very Hard'::text, NULL::text])),
  exam_dates text,
  official_website text,
  CONSTRAINT entrance_exam_pkey PRIMARY KEY (id)
);
-- Create colleges table
CREATE TABLE public.college (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text NOT NULL,
  address text NOT NULL,
  city text NOT NULL,
  state text NOT NULL,
  zip_code text NOT NULL,
  website text NOT NULL,
  email text NOT NULL,
  phone text NOT NULL,
  scholarshipdetails text NOT NULL,
  rating numeric NOT NULL,
  type text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT college_pkey PRIMARY KEY (id)
);

-- Create career path table
CREATE TABLE public.career_path (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  description jsonb,
  name character varying,
  role_responsibilities jsonb,
  education_required jsonb,
  salary_demand jsonb,
  career_options jsonb,
  key_skills_required jsonb,
  career_cluster_id uuid,
  career_stream_id uuid,
  slug text NOT NULL UNIQUE,
  subjects jsonb,
  tags jsonb DEFAULT '[]'::jsonb,
  CONSTRAINT career_path_pkey PRIMARY KEY (id),
  CONSTRAINT career_path_career_cluster_id_fkey FOREIGN KEY (career_cluster_id) REFERENCES public.career_cluster(id),
  CONSTRAINT career_path_career_stream_id_fkey FOREIGN KEY (career_stream_id) REFERENCES public.stream(id)
);


-- Create courses table
CREATE TABLE public.course (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text NOT NULL,
  duration text NOT NULL,
  degree_level text,
  seats integer,
  annual_fees text,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT course_pkey PRIMARY KEY (id)
);


-- Table for CourseEntranceExams
CREATE TABLE public.course_entrance_exams(
    id uuid default gen_random_uuid() primary key,
    course_id uuid NOT NULL,
    entranceexam_id uuid NOT NULL,
    FOREIGN KEY (entranceexam_id) REFERENCES public.entrance_exam(id),
	FOREIGN KEY (course_id) REFERENCES public.course(id)
);

-- Table for Staging College data
CREATE TABLE public.st_college (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text NOT NULL,
  address text,
  city text,
  state text,
  zip_code text,
  website text,
  email text,
  phone text,
  scholarshipdetails text,
  rating numeric,
  type text,
  confidence numeric,
  confidence_level text,
  evidence_status text,
  evidence_urls text,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT st_college_pkey PRIMARY KEY (id)
);

-- Table for Staging Course data
CREATE TABLE public.st_course (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  duration text,
  degree_level text,
  seats integer,
  annual_fees text,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT st_course_pkey PRIMARY KEY (id)
);

-- Table for Staging College and Course many to many data
CREATE TABLE public.st_college_courses (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  college_id uuid NOT NULL,
  course_id uuid NOT NULL,
  CONSTRAINT st_college_courses_pkey PRIMARY KEY (id),
  CONSTRAINT st_college_courses_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.st_college(id),
  CONSTRAINT st_college_courses_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.st_course(id)
);

-- Table for data scrapped career path
CREATE TABLE public.st_career_path (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  career_path text,
  json_data jsonb,
  CONSTRAINT st_career_path_pkey PRIMARY KEY (id)
);
-- Table for course and career path many to many 
CREATE TABLE public.careerpath_courses (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  careerpath_id uuid NOT NULL,
  course_id uuid NOT NULL,
  is_primary boolean DEFAULT false,
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT careerpath_courses_pkey PRIMARY KEY (id),
  CONSTRAINT careerpath_courses_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.course(id),
  CONSTRAINT careerpath_courses_careerpath_id_fkey FOREIGN KEY (careerpath_id) REFERENCES public.career_path(id)
);

--Many to many relationship between college and courses
CREATE TABLE public.college_courses (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  college_id uuid NOT NULL,
  course_id uuid NOT NULL,
  annual_fees text,
  total_fees text,
  seats text,
  duration_override text,
  admission_process text,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT college_courses_pkey PRIMARY KEY (id),
  CONSTRAINT college_courses_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id),
  CONSTRAINT college_courses_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.course(id)
);


-- job table for scraping data from the site
CREATE TABLE public.scrape_jobs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text])),
  course_category text,
  specialization text,
  city text,
  university text,
  engine text DEFAULT 'playwright'::text,
  headless boolean DEFAULT true,
  result_summary text,
  error_message text,
  output_files jsonb,
  save_to_supabase boolean DEFAULT false,
  save_message text,
  save_success boolean,
  CONSTRAINT scrape_jobs_pkey PRIMARY KEY (id)
);

-- search criteria
CREATE TABLE public.search_criteria (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  location text NOT NULL,
  career_path text,
  specialization text,
  university text,
  llm_json jsonb NOT NULL,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT search_criteria_pkey PRIMARY KEY (id)
);
