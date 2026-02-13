# LinkedIn Note Copilot

Minimal Chrome Extension + FastAPI backend for drafting LinkedIn connection notes.

## Extension (Chrome)

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select `Linkedin_cold_msg_extension/extension`.
4. Open a LinkedIn profile page like `https://www.linkedin.com/in/...`.
5. Click **Draft connection note**.
6. Configure your profile data in the extension **Options** page.
   - `headline`, `location`, `schools`, `experiences`
   - `proof_points` (up to 6), `focus_areas`, `internship_goal`
   - `do_not_say` phrases and `tone_preference`

## Backend (FastAPI)

1. Create a virtual environment and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```

2. Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your_key_here"
```

3. Run the server:

```bash
uvicorn server.main:app --reload --port 8000
```

The extension will call `http://localhost:8000/generate`.

### Backend layout (refactored)

- `server/app/main.py`: FastAPI app factory + middleware + router wiring
- `server/app/api/routes/generate.py`: `/generate` HTTP route only
- `server/app/services/generation_service.py`: orchestration (planning -> model call -> parsing -> validation -> logging)
- `server/app/services/openai_client.py`: OpenAI Responses API client
- `server/app/services/planning/*` + `server/app/services/render/*`: deterministic bridge-plan construction and prompt rendering

## Notes

- The extension only operates on the currently open profile page.
- No automatic clicking is performed.
- Use **Copy** if the connect modal is not open.
