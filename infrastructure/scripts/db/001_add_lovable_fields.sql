-- ============================================================================
-- Migration: Add Lovable UI Fields to career_path Table
-- Date: 2025-12-24
-- Purpose: Add 3 new fields from Lovable to support complete UI merge
-- Guide: Based on LOVABLE_MERGE_GUIDE v2.1 and Phase 2.6 verification
-- ============================================================================

-- Migration Version
-- Version: 001
-- Description: Add ask_yourself, role_description, and impact_sentence fields

-- ============================================================================
-- BACKUP RECOMMENDATION
-- ============================================================================
-- Before running this migration, backup the career_path table:
-- pg_dump -h <host> -U <user> -d <database> -t career_path > backup_career_path_$(date +%Y%m%d).sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Add new columns to career_path table
-- ============================================================================

-- Add ask_yourself field (JSONB array of 3 self-reflection questions)
ALTER TABLE career_path
ADD COLUMN IF NOT EXISTS ask_yourself JSONB
DEFAULT NULL;

-- Add role_description field (one-sentence career description)
ALTER TABLE career_path
ADD COLUMN IF NOT EXISTS role_description TEXT
DEFAULT NULL;

-- Add impact_sentence field (career impact statement)
ALTER TABLE career_path
ADD COLUMN IF NOT EXISTS impact_sentence TEXT
DEFAULT NULL;

-- ============================================================================
-- 2. Add column comments for documentation
-- ============================================================================

COMMENT ON COLUMN career_path.ask_yourself IS
'Array of 3 self-reflection questions for students to determine career fit.
Format: JSONB array of strings, e.g., ["Question 1?", "Question 2?", "Question 3?"]
Source: Lovable CareerDetails.tsx - displayed as 3 boxes in hero section
Example: ["Do you enjoy solving problems using math and physics?", "Are you curious about how buildings are made?", "Do you want to create things that help communities?"]';

COMMENT ON COLUMN career_path.role_description IS
'One-sentence description of the career role. Concise summary of what the professional does.
Source: Lovable CareerDetails.tsx - displayed in hero section
Example: "Civil engineers design and build infrastructure like roads, bridges, and buildings that shape cities."';

COMMENT ON COLUMN career_path.impact_sentence IS
'Statement describing the career''s impact on society/individuals. Motivational sentence.
Source: Lovable CareerDetails.tsx - displayed in hero section
Example: "They create structures that improve everyday life and last for generations."';

-- ============================================================================
-- 3. Create indexes if needed (optional - for query performance)
-- ============================================================================

-- GIN index for ask_yourself JSONB field (if we need to search within questions)
-- Uncomment if you plan to search/filter by questions
-- CREATE INDEX IF NOT EXISTS idx_career_path_ask_yourself
-- ON career_path USING GIN (ask_yourself);

-- ============================================================================
-- 4. Validation queries
-- ============================================================================

-- Verify columns were added
DO $$
DECLARE
  ask_yourself_exists BOOLEAN;
  role_description_exists BOOLEAN;
  impact_sentence_exists BOOLEAN;
BEGIN
  -- Check if ask_yourself column exists
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'career_path'
    AND column_name = 'ask_yourself'
  ) INTO ask_yourself_exists;

  -- Check if role_description column exists
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'career_path'
    AND column_name = 'role_description'
  ) INTO role_description_exists;

  -- Check if impact_sentence column exists
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'career_path'
    AND column_name = 'impact_sentence'
  ) INTO impact_sentence_exists;

  -- Raise notice with results
  IF ask_yourself_exists AND role_description_exists AND impact_sentence_exists THEN
    RAISE NOTICE '✅ All columns added successfully!';
    RAISE NOTICE '   - ask_yourself (JSONB)';
    RAISE NOTICE '   - role_description (TEXT)';
    RAISE NOTICE '   - impact_sentence (TEXT)';
  ELSE
    RAISE EXCEPTION '❌ Migration failed - not all columns were added';
  END IF;
END $$;

-- ============================================================================
-- 5. Display updated schema
-- ============================================================================

-- Show new column definitions
SELECT
  column_name,
  data_type,
  is_nullable,
  column_default
FROM information_schema.columns
WHERE table_name = 'career_path'
  AND column_name IN ('ask_yourself', 'role_description', 'impact_sentence')
ORDER BY ordinal_position;

COMMIT;

-- ============================================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================================
--
-- If you need to rollback this migration, run:
--
-- BEGIN;
--
-- ALTER TABLE career_path DROP COLUMN IF EXISTS ask_yourself;
-- ALTER TABLE career_path DROP COLUMN IF EXISTS role_description;
-- ALTER TABLE career_path DROP COLUMN IF EXISTS impact_sentence;
--
-- COMMIT;
--
-- ============================================================================

-- ============================================================================
-- SAMPLE DATA INSERT (for testing)
-- ============================================================================
--
-- After migration, you can test with sample data:
--
-- UPDATE career_path
-- SET
--   ask_yourself = '["Do you enjoy solving problems?", "Are you curious about technology?", "Do you want to build things?"]'::jsonb,
--   role_description = 'Software developers create applications and systems that power modern technology.',
--   impact_sentence = 'They build tools that millions of people use every day to work, learn, and connect.'
-- WHERE slug = 'software-developer';
--
-- ============================================================================

-- ============================================================================
-- NOTES FOR DEVELOPERS
-- ============================================================================
--
-- 1. These fields are from Lovable's CareerDetails.tsx and ARE displayed in UI
-- 2. ask_yourself should always be an array of exactly 3 questions
-- 3. role_description should be one concise sentence
-- 4. impact_sentence should be one motivational sentence
-- 5. All three fields are optional (can be NULL)
-- 6. Update TypeScript interfaces in: frontend/src/integrations/supabase/index.ts
--
-- TypeScript interface update needed:
--
-- export interface CareerPath {
--   // ... existing fields ...
--   ask_yourself?: string[]; // JSONB array
--   role_description?: string;
--   impact_sentence?: string;
-- }
--
-- ============================================================================

-- Migration complete!
-- Version: 001
-- Status: SUCCESS (if no errors above)
