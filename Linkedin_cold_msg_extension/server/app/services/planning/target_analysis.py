import re
from typing import Any

from ..utils.constants import ROLE_KEYWORD_MIN_LEN
from ..utils.text_utils import normalize_key, tokenize


def build_target_text(target_profile: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(
        [
            target_profile.get("name", ""),
            target_profile.get("headline", ""),
            target_profile.get("location", ""),
            target_profile.get("about", ""),
        ]
    )
    for exp in target_profile.get("top_experiences") or []:
        parts.append(exp.get("title", ""))
        parts.append(exp.get("company", ""))
    for edu in target_profile.get("education") or []:
        parts.append(edu.get("school", ""))
    return " ".join([part for part in parts if part]).strip()


def score_hook(hook: str, target_profile: dict[str, Any]) -> int:
    if not hook:
        return 0
    score = 0
    hook_lower = hook.lower()
    target_text = build_target_text(target_profile).lower()
    overlap = set(tokenize(hook)).intersection(tokenize(target_text))
    score += min(len(hook), 80) // 20
    score += min(len(overlap), 3)

    for exp in target_profile.get("top_experiences") or []:
        company = (exp.get("company") or "").lower()
        title = (exp.get("title") or "").lower()
        if company and company in hook_lower:
            score += 3
        if title and title in hook_lower:
            score += 2

    for edu in target_profile.get("education") or []:
        school = (edu.get("school") or "").lower()
        if school and school in hook_lower:
            score += 3

    location = (target_profile.get("location") or "").lower()
    if location and location in hook_lower:
        score += 1

    return score


def derive_hooks(target_profile: dict[str, Any]) -> list[str]:
    hooks: list[str] = []
    for exp in target_profile.get("top_experiences") or []:
        title = exp.get("title", "")
        company = exp.get("company", "")
        if title and company:
            hooks.append(f"{title} at {company}")
        elif company:
            hooks.append(f"{company} experience")
    for edu in target_profile.get("education") or []:
        school = edu.get("school", "")
        if school:
            hooks.append(f"{school} alum")
    headline = target_profile.get("headline", "")
    if headline:
        hooks.append(f"{headline}")
    return hooks[:5]


def classify_target(target_profile: dict[str, Any]) -> set[str]:
    text = build_target_text(target_profile).lower()
    tags: set[str] = set()
    if re.search(
        r"(data|analytics|ml|machine learning|sql|python|bi|business intelligence|stats|statistic|quant|ai)",
        text,
    ):
        tags.add("analytics")
    if re.search(r"(product|pm|product management|growth|roadmap)", text):
        tags.add("product")
    if re.search(
        r"(computer vision|vision|opencv|yolo|camera|radar|perception|imaging)",
        text,
    ):
        tags.add("cv")
    if re.search(r"(community|partnership|outreach|events|club|association)", text):
        tags.add("community")
    if re.search(r"(finance|trading|investment|bank|equity)", text):
        tags.add("finance")
    return tags


def extract_role_keyword(target_profile: dict[str, Any]) -> str:
    top_experiences = target_profile.get("top_experiences") or []
    if not top_experiences:
        return ""
    title = (top_experiences[0] or {}).get("title", "")
    if not title:
        return ""
    stop = {
        "data",
        "senior",
        "lead",
        "principal",
        "staff",
        "junior",
        "global",
        "payments",
        "usds",
        "jv",
    }
    words = title.split()
    candidates: list[str] = []
    for word in words:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", word)
        if len(cleaned) >= ROLE_KEYWORD_MIN_LEN:
            candidates.append(cleaned)
    for cand in candidates:
        if cand.lower() not in stop:
            return cand
    return candidates[-1] if candidates else ""


def extract_headline_keyword(headline: str) -> str:
    if not headline:
        return ""
    patterns = [
        r"computer vision",
        r"vision",
        r"opencv",
        r"yolo",
        r"product",
        r"growth",
        r"analytics",
        r"data",
        r"machine learning",
        r"ml",
        r"sql",
        r"python",
        r"ai",
        r"finance",
        r"trading",
        r"investment",
        r"community",
        r"outreach",
        r"partnership",
    ]
    for pattern in patterns:
        match = re.search(pattern, headline, re.IGNORECASE)
        if match:
            return headline[match.start() : match.end()]
    return ""


def extract_company_from_fact(target_fact: str) -> str:
    if " at " in target_fact:
        return target_fact.split(" at ", 1)[1].strip()
    if target_fact.endswith(" alum"):
        return target_fact[: -len(" alum")].strip()
    return target_fact


def is_domain_fact(token: str) -> bool:
    return normalize_key(token) in {
        "nyc",
        "analytics",
        "product",
        "computer vision",
        "finance",
        "community",
    }
