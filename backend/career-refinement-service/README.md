# Career Refinement Service

This service uses LLM (Gemini) to automatically generate Lovable UI fields for career paths:
- **ask_yourself**: 3 self-reflection questions (JSONB array) to help students determine career fit
- **role_description**: One concise sentence describing what the professional does
- **impact_sentence**: One motivational sentence about the career's impact on society

## Setup

```bash
cd backend/career-refinement-service
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file:

```bash
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash-lite
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Usage

### Process a Single Career (by Name)
```bash
python main.py --name "Civil Engineer"
```

### Process a Single Career (by Slug)
```bash
python main.py --slug "civil-engineer"
```

### Process All Careers
Iterates through all records in the `career_path` table.

```bash
python main.py --all
```

### Force Regenerate
Regenerate content even if it already exists.

```bash
python main.py --name "Civil Engineer" --force
python main.py --all --force
```

## How it Works

1. **Fetch**: Retrieves career data from Supabase `career_path` table
2. **Check**: Checks if `ask_yourself`, `role_description`, or `impact_sentence` are missing
3. **Generate**: If missing (or `--force` is used), calls Gemini to generate:
   - `ask_yourself`: 3 self-discovery questions starting with "Do you" or "Are you"
   - `role_description`: One sentence describing what they do
   - `impact_sentence`: One sentence about their societal impact
4. **Update**: Updates the record in Supabase `career_path` table

## Database Fields (Lovable UI)

| Field | Type | Description |
|-------|------|-------------|
| `ask_yourself` | JSONB | Array of 3 self-reflection questions |
| `role_description` | TEXT | One-sentence career description |
| `impact_sentence` | TEXT | Motivational impact statement |

## File Structure

```
career-refinement-service/
├── main.py                    # Main service logic
├── config.py                  # Configuration settings
├── requirements.txt           # Dependencies
├── .env                       # Environment variables
└── README.md                  # Documentation
```
