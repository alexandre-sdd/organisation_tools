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

    if target_fact and target_fact not in text:
        violations.append("missing target_fact")
    if hook_text and hook_text not in text:
        violations.append("missing hook_text")
    if proof_point and proof_point not in text:
        violations.append("missing proof_point")
    if cta and cta not in text:
        violations.append("missing CTA")
    if required_token and required_token not in text:
        violations.append("missing required_token")

    lowered = text.lower()
    for phrase in banlist:
        if phrase and phrase.lower() in lowered:
            violations.append("contains banned phrase")
            break

    return violations
