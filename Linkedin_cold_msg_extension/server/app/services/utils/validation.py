from .text_utils import normalize_key


def _contains_normalized(haystack: str, needle: str) -> bool:
    nh = normalize_key(haystack)
    nn = normalize_key(needle)
    if not nn:
        return True
    return nn in nh


def _has_token_overlap(haystack: str, snippet: str, minimum_hits: int = 3) -> bool:
    hay_tokens = set(normalize_key(haystack).split())
    snippet_tokens = [tok for tok in normalize_key(snippet).split() if len(tok) >= 4]
    if not snippet_tokens:
        return True
    unique_tokens = set(snippet_tokens)
    hits = len([tok for tok in unique_tokens if tok in hay_tokens])
    threshold = min(minimum_hits, max(1, len(unique_tokens) // 2))
    return hits >= threshold


def validate_variant_text(text: str, plan: dict[str, str], banlist: list[str]) -> list[str]:
    violations: list[str] = []
    if not text:
        violations.append("empty text")
        return violations

    if len(text) > 300:
        violations.append("length > 300")

    target_fact = plan.get("target_fact", "")
    hook_text = plan.get("hook_text", "")
    proof_point = plan.get("proof_point", "")
    cta = plan.get("cta", "")
    required_token = plan.get("required_token", "")

    if target_fact and not (
        _contains_normalized(text, target_fact) or _has_token_overlap(text, target_fact, minimum_hits=2)
    ):
        violations.append("missing target_fact")
    if hook_text and not (
        _contains_normalized(text, hook_text) or _has_token_overlap(text, hook_text, minimum_hits=2)
    ):
        violations.append("missing hook_text")
    if proof_point and not _has_token_overlap(text, proof_point):
        violations.append("missing proof_point")
    if cta and not _contains_normalized(text, cta):
        violations.append("missing CTA")
    if required_token and not _contains_normalized(text, required_token):
        violations.append("missing required_token")

    lowered = text.lower()
    for phrase in banlist:
        if phrase and phrase.lower() in lowered:
            violations.append("contains banned phrase")
            break

    return violations
