import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import MODEL_NAME, OPENAI_API_URL
    from .models import GenerateRequest, GenerateResponse
    from .services.prompting import RESPONSE_SCHEMA, build_prompt
    from .services.response_parsing import (
        extract_response_text,
        normalize_variants,
        parse_json_content,
    )
except ImportError:  # pragma: no cover - supports running as `uvicorn main:app`
    from config import MODEL_NAME, OPENAI_API_URL
    from models import GenerateRequest, GenerateResponse
    from services.prompting import RESPONSE_SCHEMA, build_prompt
    from services.response_parsing import (
        extract_response_text,
        normalize_variants,
        parse_json_content,
    )

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    messages = build_prompt(payload)
    system_msg = ""
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_msg = msg.get("content", "")
        elif msg.get("role") == "user":
            user_msg = msg.get("content", "")

    input_items = []
    if user_msg:
        input_items.append({"role": "user", "content": user_msg})
    else:
        input_items = [
            {"role": msg.get("role"), "content": msg.get("content", "")}
            for msg in messages
            if msg.get("role") != "system"
        ]
        if not input_items:
            input_items = [{"role": "user", "content": ""}]

    async with httpx.AsyncClient(timeout=30) as client:
        request_body = {
            "model": MODEL_NAME,
            "input": input_items,
            "instructions": system_msg,
            "temperature": 0.6,
            "max_output_tokens": 350,
            "text": {"format": RESPONSE_SCHEMA},
        }
        resp = await client.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )

        if resp.status_code >= 400 and (
            "response_format" in resp.text or "json_schema" in resp.text
        ):
            request_body["text"] = {"format": {"type": "json_object"}}
            resp = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    content, refusal = extract_response_text(data)
    if refusal:
        raise HTTPException(status_code=502, detail=refusal)
    if not content:
        content = data.get("output_text", "")
    if not content:
        raise HTTPException(status_code=502, detail="Empty response from model")

    raw = parse_json_content(content)
    if raw is None:
        if os.getenv("OPENAI_DEBUG", os.getenv("GROQ_DEBUG", "0")) == "1":
            print("Model raw content:", content)
        raise HTTPException(status_code=502, detail="Model did not return JSON")

    variants = normalize_variants(raw)
    if not variants:
        raise HTTPException(status_code=502, detail="No variants returned")

    return GenerateResponse(variants=variants)
