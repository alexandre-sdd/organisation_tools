import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import MODEL_NAME, OPENAI_API_URL
    from .logging_utils import append_ndjson, utc_now_iso
    from .models import GenerateRequest, GenerateResponse
    from .services.prompting import (
        BASE_BANLIST,
        RESPONSE_SCHEMA,
        build_prompt_context,
        validate_variant_text,
    )
    from .services.response_parsing import (
        extract_response_text,
        normalize_variants,
        parse_json_content,
    )
except ImportError:  # pragma: no cover - supports running as `uvicorn main:app`
    from config import MODEL_NAME, OPENAI_API_URL
    from logging_utils import append_ndjson, utc_now_iso
    from models import GenerateRequest, GenerateResponse
    from services.prompting import (
        BASE_BANLIST,
        RESPONSE_SCHEMA,
        build_prompt_context,
        validate_variant_text,
    )
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

    request_id = uuid.uuid4().hex
    # Persist logs alongside the extension artifacts for easy inspection.
    # Path: Linkedin_cold_msg_extension/logs/requests.ndjson
    log_path = Path(__file__).resolve().parents[2] / "logs" / "requests.ndjson"
    log_record: dict[str, object] = {
        "ts": utc_now_iso(),
        "request_id": request_id,
        "event": "generate",
        "model_name": MODEL_NAME,
    }

    messages: list[dict[str, str]]
    debug_log: dict[str, object]
    try:
        messages, debug_log = build_prompt_context(
            payload, request_id=request_id, model_name=MODEL_NAME
        )
        log_record["debug"] = debug_log
        # Persist exactly what the model saw (system + user).
        log_record["messages"] = messages
        if os.getenv("PROMPT_DEBUG", "0") == "1":
            print(json.dumps(debug_log, ensure_ascii=True))
    except Exception as e:
        log_record["error"] = {
            "stage": "build_prompt_context",
            "type": type(e).__name__,
            "msg": str(e),
        }
        append_ndjson(log_path, log_record)
        raise
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

    try:
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
            log_record["openai_http"] = {"status": resp.status_code}

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
                log_record["openai_http_fallback"] = {"status": resp.status_code}
    except Exception as e:
        log_record["error"] = {
            "stage": "openai_request",
            "type": type(e).__name__,
            "msg": str(e),
        }
        append_ndjson(log_path, log_record)
        raise

    if resp.status_code >= 400:
        log_record["error"] = {
            "stage": "openai_call",
            "status": resp.status_code,
            "body_preview": resp.text[:2000],
        }
        append_ndjson(log_path, log_record)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    content, refusal = extract_response_text(data)
    if refusal:
        log_record["error"] = {"stage": "openai_refusal", "msg": refusal}
        append_ndjson(log_path, log_record)
        raise HTTPException(status_code=502, detail=refusal)
    if not content:
        content = data.get("output_text", "")
    if not content:
        log_record["error"] = {"stage": "openai_empty", "msg": "Empty response from model"}
        append_ndjson(log_path, log_record)
        raise HTTPException(status_code=502, detail="Empty response from model")

    log_record["model_output_preview"] = content[:1200]
    raw = parse_json_content(content)
    if raw is None:
        if os.getenv("OPENAI_DEBUG", os.getenv("GROQ_DEBUG", "0")) == "1":
            print("Model raw content:", content)
        log_record["error"] = {"stage": "parse_json", "msg": "Model did not return JSON"}
        append_ndjson(log_path, log_record)
        raise HTTPException(status_code=502, detail="Model did not return JSON")

    variants = normalize_variants(raw)
    if not variants:
        log_record["error"] = {"stage": "normalize_variants", "msg": "No variants returned"}
        append_ndjson(log_path, log_record)
        raise HTTPException(status_code=502, detail="No variants returned")

    validations = []
    bridge_plan = {}
    banlist = BASE_BANLIST
    if isinstance(debug_log, dict):
        bridge_plan = debug_log.get("bridge_plan", {})  # type: ignore[assignment]
        compact = debug_log.get("compact_my_profile", {})  # type: ignore[assignment]
        do_not_say = []
        if isinstance(compact, dict):
            do_not_say = compact.get("do_not_say", []) or []
        if isinstance(do_not_say, list):
            banlist = BASE_BANLIST + [str(x) for x in do_not_say if x]

    for v in variants:
        per_plan = {}
        if isinstance(bridge_plan, dict) and isinstance(bridge_plan.get(v.label), dict):
            per_plan = bridge_plan.get(v.label, {})
        violations = validate_variant_text(v.text, per_plan, banlist) if per_plan else []
        validations.append({"label": v.label, "violations": violations})

    log_record["variants"] = [
        {"label": v.label, "char_count": v.char_count, "text": v.text} for v in variants
    ]
    log_record["validations"] = validations
    append_ndjson(log_path, log_record)

    return GenerateResponse(variants=variants)
