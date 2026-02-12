# Backend Logic and Prompting Details

This document explains how the backend is structured, how requests are processed, and how prompts are constructed for the model.

## High-Level Flow

1. The extension sends a POST to `/generate` with:
   - `my_profile` (your info)
   - `target_profile` (LinkedIn profile info)
   - `hooks` (overlap signals from the extension)
2. The FastAPI handler builds a prompt with:
   - compacted profiles
   - ranked hooks and proof points
   - anchor plan (one hook per variant)
   - strict JSON schema instructions
3. The OpenAI Responses API is called using:
   - `instructions` (system message)
   - `input` (user content)
   - `text.format` JSON schema
4. The response is parsed and normalized into `variants`:
   - 3 variants: `short`, `direct`, `warm`
   - each includes `label`, `text`, `char_count`

## File/Module Responsibilities

- `server/app/main.py`
  - FastAPI app factory
  - CORS middleware configuration
  - Router registration

- `server/app/api/routes/generate.py`
  - `/generate` endpoint
  - Delegates to the generation service

- `server/app/services/generation_service.py`
  - End-to-end orchestration for `/generate`
  - Build prompt context, call model, parse/normalize output
  - Trim/validate variants and emit request traces

- `server/app/services/openai_client.py`
  - OpenAI Responses API adapter
  - Handles schema fallback (`json_schema` -> `json_object`)

- `server/app/config.py`
  - Loads `.env` from `server/.env`
  - Defines model constants:
    - `MODEL_NAME`
    - `OPENAI_API_URL`

- `server/app/models.py`
  - Pydantic models:
    - `GenerateRequest`
    - `GenerateResponse`
    - `Variant`

- `server/app/services/prompting.py`
  - **Core prompting logic**
  - Hook scoring, tagging, anchor selection
  - Prompt assembly and schema

- `server/app/services/response_parsing.py`
  - Extracts and parses model output
  - Normalizes variants to match API response

## Prompting Logic (Detailed)

### 1) Input Normalization
`build_prompt(payload)` in `services/prompting.py` reduces raw profiles to compact, predictable fields:

- `my_profile` becomes:
  - `headline`
  - `location`
  - `schools` (max 3)
  - `experiences` (max 3)
  - `proof_points` (max 6, fallback to defaults)
  - `focus_areas` (max 6)
  - `internship_goal`
  - `do_not_say` (banlist)
  - `tone_preference`

- `target_profile` becomes:
  - `name`
  - `headline`
  - `location`
  - `about`
  - `top_experiences` (max 2)
  - `education` (max 1)

This keeps the prompt small and stable while preserving the most important signals.

### 2) Hooks and Derivations
The extension can pass hooks directly. We also derive hooks from the target profile:

- From experience:
  - `"{title} at {company}"`
  - or `"{company} experience"`
- From education:
  - `"{school} alum"`
- From headline:
  - headline string as hook

Each hook is scored based on:
- overlap with target profile text
- explicit mentions of company/title/school/location
- length and keyword overlap

### 3) Target Classification (Tags)
`classify_target()` applies keyword regex to tag the target profile:

- `analytics`
- `product`
- `cv`
- `community`
- `finance`

These tags later influence which proof points are ranked highest.

### 4) Proof Point Ranking
Each proof point is scored based on the target tags:

- analytics: boosts points mentioning pipelines, dashboards, pandas, SQL
- cv: boosts mentions of YOLO/OpenCV/vision
- product: boosts product + decision-support
- community: boosts outreach/partnership/events
- finance: boosts accounting/commercial/performance

Top-ranked points are shown in the prompt and referenced by the model.

### 5) Anchor Candidates and Anchor Plan
Anchors define the **one hook per variant** rule. The system builds candidates from:

- Shared schools (strongest anchor)
- Shared companies
- Target role title
- Shared domain tag (analytics/product/cv)
- Shared location (NYC)
- Extension hooks and derived hooks

Each anchor is scored, deduplicated, and sorted. Then:

- The first 3 variants are assigned different anchor types when possible
- A fallback ensures each variant always has a hook

This is displayed to the model explicitly as:

```
ANCHOR_PLAN (use exactly as hook):
- short: ...
- direct: ...
- warm: ...
```

### 6) System Prompt Rules
The system message forces strict output:

- Exactly 3 variants (`short`, `direct`, `warm`)
- Each <= 300 chars
- Each has:
  - exactly one hook (from anchor plan)
  - exactly one proof point
  - ends with a soft CTA question
- No markdown, no prose, JSON only

A full JSON schema is provided to reduce parsing failures.

### 7) Response Parsing
The response handler does:

- Extracts `output_text` from Responses API JSON
- Parses JSON (supports raw JSON or fenced blocks)
- Normalizes each variant:
  - enforces `label` values
  - trims to 300 chars
  - computes `char_count`

If anything fails, the endpoint returns a 502 with a useful message.

## Why This Structure

The folder layout mirrors the logic:

- `app/main.py` = app factory + middleware + router registration
- `app/api/routes/generate.py` = HTTP endpoint layer
- `app/services/generation_service.py` = generation orchestration
- `app/config.py` = environment + configuration
- `app/services/*` = prompt planning, model client, parsing, validation
- `app/models.py` = shared request/response shapes

This keeps endpoint code thin, isolates model I/O from business logic, and makes planning/parsing easier to maintain independently.
