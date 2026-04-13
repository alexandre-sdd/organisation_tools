from dataclasses import dataclass
from typing import Any

import httpx

from ..config import MODEL_NAME, OPENAI_API_URL
from .utils.constants import RESPONSE_SCHEMA


@dataclass
class OpenAIResponsesResult:
    status_code: int
    body_text: str
    data: dict[str, Any] | None
    fallback_status_code: int | None = None


class OpenAIResponsesClient:
    def __init__(
        self,
        api_url: str = OPENAI_API_URL,
        model_name: str = MODEL_NAME,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_url = api_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate_structured_notes(
        self,
        *,
        api_key: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_output_tokens: int = 350,
    ) -> OpenAIResponsesResult:
        system_msg, user_msg = _split_messages(messages)
        input_items = _build_input_items(messages, user_msg)

        request_body = {
            "model": self.model_name,
            "input": input_items,
            "instructions": system_msg,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "text": {"format": RESPONSE_SCHEMA},
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

            fallback_status_code = None
            if response.status_code >= 400 and (
                "response_format" in response.text or "json_schema" in response.text
            ):
                request_body["text"] = {"format": {"type": "json_object"}}
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
                fallback_status_code = response.status_code

        data: dict[str, Any] | None = None
        try:
            data = response.json()
        except Exception:
            data = None

        return OpenAIResponsesResult(
            status_code=response.status_code,
            body_text=response.text,
            data=data,
            fallback_status_code=fallback_status_code,
        )


def _split_messages(messages: list[dict[str, str]]) -> tuple[str, str]:
    system_msg = ""
    user_msg = ""
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_msg = msg.get("content", "")
        elif role == "user":
            user_msg = msg.get("content", "")
    return system_msg, user_msg


def _build_input_items(messages: list[dict[str, str]], user_msg: str) -> list[dict[str, str]]:
    if user_msg:
        return [{"role": "user", "content": user_msg}]

    non_system = [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in messages
        if msg.get("role") != "system"
    ]
    return non_system or [{"role": "user", "content": ""}]
