import json
import re
from typing import Any

try:
    from ..models import Variant
    from .utils.constants import VARIANT_LABELS
except ImportError:  # pragma: no cover
    from models import Variant
    from services.utils.constants import VARIANT_LABELS


def normalize_variants(raw: dict[str, Any]) -> list[Variant]:
    desired_labels = VARIANT_LABELS
    variants = []
    items = raw.get("variants", [])
    for index, item in enumerate(items):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if len(text) > 300:
            text = text[:297].rstrip() + "..."
        label = (item.get("label") or "").strip().lower()
        if label not in desired_labels:
            label = desired_labels[index] if index < len(desired_labels) else "variant"
        variants.append(Variant(label=label, text=text, char_count=len(text)))
    return variants


def parse_json_content(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    candidate = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", candidate, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def extract_response_text(data: dict[str, Any]) -> tuple[str, str]:
    output = data.get("output", [])
    texts: list[str] = []
    refusals: list[str] = []
    for item in output:
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                elif part.get("type") == "refusal":
                    refusals.append(part.get("refusal", ""))
        elif item.get("type") == "refusal":
            refusals.append(item.get("refusal", ""))
    return "\n".join([t for t in texts if t]).strip(), "\n".join(
        [r for r in refusals if r]
    ).strip()
