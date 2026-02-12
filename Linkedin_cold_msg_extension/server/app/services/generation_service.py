import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import MODEL_NAME
from ..logging_utils import append_ndjson, utc_now_iso
from ..models import GenerateRequest, GenerateResponse, Variant
from .openai_client import OpenAIResponsesClient
from .render.prompt_render import build_prompt_context
from .response_parsing import extract_response_text, normalize_variants, parse_json_content
from .utils.constants import BASE_BANLIST
from .utils.payload import as_plain_dict
from .utils.validation import validate_variant_text


@dataclass(frozen=True)
class AttemptSettings:
    temperature: float


DEFAULT_ATTEMPTS = (
    AttemptSettings(temperature=0.6),
    AttemptSettings(temperature=0.2),
)


def trim_to_limit_preserving_cta(text: str, cta: str, limit: int = 300) -> str:
    if not text:
        return text

    cta = cta or ""
    if cta and not text.endswith(cta):
        if cta in text:
            text = text[: text.rfind(cta) + len(cta)]
        else:
            text = text.rstrip(" .") + " " + cta

    if len(text) <= limit:
        return text

    if not cta:
        return text[:limit].rstrip()

    ellipsis = " ... "
    max_prefix = limit - len(cta) - len(ellipsis)
    if max_prefix <= 0:
        return cta[:limit]

    prefix = text[:max_prefix].rstrip()
    return f"{prefix}{ellipsis}{cta}"


def validate_variant_text_extended(text: str, plan: dict[str, str], banlist: list[str]) -> list[str]:
    violations = validate_variant_text(text, plan, banlist)
    cta = plan.get("cta", "")
    if cta and not text.endswith(cta):
        violations.append("missing CTA end")
    if len(text) > 300:
        violations.append("length > 300")
    return list(dict.fromkeys(violations))


class GenerationService:
    def __init__(
        self,
        client: OpenAIResponsesClient | None = None,
        attempts: tuple[AttemptSettings, ...] = DEFAULT_ATTEMPTS,
        model_name: str = MODEL_NAME,
        log_path: Path | None = None,
    ) -> None:
        self.client = client or OpenAIResponsesClient(model_name=model_name)
        self.attempts = attempts
        self.model_name = model_name
        self.log_path = log_path or Path(__file__).resolve().parents[3] / "logs" / "requests.ndjson"

    async def generate(self, payload: GenerateRequest) -> GenerateResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

        start_time = time.perf_counter()
        request_id = uuid.uuid4().hex
        now = utc_now_iso()
        log_record: dict[str, Any] = {
            "ts": now,
            "timestamp": now,
            "request_id": request_id,
            "event": "generate",
            "model_name": self.model_name,
            "attempts": [],
        }

        final_variants: list[Variant] | None = None
        final_messages: list[dict[str, str]] | None = None
        final_bridge_plan: dict[str, dict[str, Any]] | None = None
        final_banlist: list[str] | None = None
        final_debug: dict[str, Any] | None = None
        final_validations: list[dict[str, Any]] | None = None
        final_openai_status: int | None = None
        final_openai_fallback_status: int | None = None
        final_content = ""

        for idx, settings in enumerate(self.attempts, start=1):
            try:
                messages, debug_log = build_prompt_context(
                    payload,
                    request_id=request_id,
                    model_name=self.model_name,
                )
            except Exception as exc:
                log_record["error"] = {
                    "stage": "planning",
                    "type": type(exc).__name__,
                    "msg": str(exc),
                }
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise

            bridge_plan = debug_log.get("bridge_plan", {}) if isinstance(debug_log, dict) else {}
            banlist = self._build_banlist(payload)

            try:
                result = await self.client.generate_structured_notes(
                    api_key=api_key,
                    messages=messages,
                    temperature=settings.temperature,
                )
            except Exception as exc:
                log_record["error"] = {
                    "stage": "openai_request",
                    "type": type(exc).__name__,
                    "msg": str(exc),
                }
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise

            if result.status_code >= 400:
                log_record["error"] = {
                    "stage": "openai_call",
                    "status": result.status_code,
                    "body_preview": result.body_text[:2000],
                }
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise HTTPException(status_code=result.status_code, detail=result.body_text)

            data = result.data or {}
            content, refusal = extract_response_text(data)
            if refusal:
                log_record["error"] = {"stage": "openai_refusal", "msg": refusal}
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise HTTPException(status_code=502, detail=refusal)

            if not content:
                content = data.get("output_text", "")
            if not content:
                log_record["error"] = {"stage": "openai_empty", "msg": "Empty response"}
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise HTTPException(status_code=502, detail="Empty response from model")

            raw = parse_json_content(content)
            if raw is None:
                log_record["error"] = {"stage": "parse_json", "msg": "Model did not return JSON"}
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise HTTPException(status_code=502, detail="Model did not return JSON")

            variants = normalize_variants(raw)
            if not variants:
                log_record["error"] = {"stage": "normalize_variants", "msg": "No variants returned"}
                log_record["status"] = "error"
                append_ndjson(self.log_path, log_record)
                raise HTTPException(status_code=502, detail="No variants returned")

            validations = []
            trimmed_variants: list[Variant] = []
            for variant in variants:
                plan = bridge_plan.get(variant.label, {})
                cta = plan.get("cta", "")
                variant.text = trim_to_limit_preserving_cta(variant.text, cta, 300)
                variant.char_count = len(variant.text)
                violations = validate_variant_text_extended(variant.text, plan, banlist)
                validations.append({"label": variant.label, "violations": violations})
                trimmed_variants.append(variant)

            attempt_log = {
                "attempt": idx,
                "temperature": settings.temperature,
                "openai_http": {"status": result.status_code},
                "openai_http_fallback": {"status": result.fallback_status_code}
                if result.fallback_status_code is not None
                else None,
                "plan": debug_log,
                "messages": messages,
                "validations": validations,
                "final_texts": [
                    {"label": variant.label, "text": variant.text, "char_count": variant.char_count}
                    for variant in trimmed_variants
                ],
            }
            log_record["attempts"].append(attempt_log)

            any_violations = any(item["violations"] for item in validations)
            final_variants = trimmed_variants
            final_messages = messages
            final_bridge_plan = bridge_plan
            final_banlist = banlist
            final_debug = debug_log
            final_validations = validations
            final_openai_status = result.status_code
            final_openai_fallback_status = result.fallback_status_code
            final_content = content

            if not any_violations:
                break

        if final_variants is None:
            log_record["error"] = {"stage": "finalize", "msg": "No variants produced"}
            log_record["status"] = "error"
            append_ndjson(self.log_path, log_record)
            raise HTTPException(status_code=502, detail="No variants produced")

        log_record["model_output_preview"] = final_content[:1200]
        log_record["final_messages"] = final_messages
        log_record["final_variant_plan"] = final_bridge_plan
        log_record["final_banlist"] = final_banlist
        log_record["debug"] = final_debug
        log_record["messages"] = final_messages
        log_record["variants"] = [
            {"label": variant.label, "char_count": variant.char_count, "text": variant.text}
            for variant in final_variants
        ]
        log_record["validations"] = final_validations or []
        if final_openai_status is not None:
            log_record["openai_http"] = {"status": final_openai_status}
        if final_openai_fallback_status is not None:
            log_record["openai_http_fallback"] = {"status": final_openai_fallback_status}
        log_record["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        log_record["status"] = "ok"
        append_ndjson(self.log_path, log_record)

        return GenerateResponse(variants=final_variants)

    @staticmethod
    def _build_banlist(payload: GenerateRequest) -> list[str]:
        if isinstance(payload, dict):
            my_profile = as_plain_dict(payload.get("my_profile", {}))
        else:
            my_profile = as_plain_dict(getattr(payload, "my_profile", {}))

        do_not_say = (my_profile.get("do_not_say") or [])[:12]
        combined = BASE_BANLIST + do_not_say
        return [item.strip() for item in combined if item and item.strip()]
