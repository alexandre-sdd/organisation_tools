from typing import Any


def as_plain_dict(value: Any) -> dict[str, Any]:
    """Convert Pydantic models and mappings into plain dictionaries."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}
