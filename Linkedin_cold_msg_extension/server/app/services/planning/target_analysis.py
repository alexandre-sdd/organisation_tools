import re
from typing import Any

from ..utils.constants import ROLE_KEYWORD_MIN_LEN
from ..utils.text_utils import normalize_key, tokenize

SHORT_EMPLOYMENT_TYPES = {
    "full time",
    "part time",
    "contract",
    "temporary",
    "freelance",
    "internship",
    "apprenticeship",
    "self employed",
    "seasonal",
}

TAG_PATTERNS = {
    "analytics": r"(\bdata\b|\banalytics\b|\bml\b|\bmachine learning\b|\bsql\b|\bpython\b|\bbi\b|business intelligence|\bstats?\b|\bstatistic\w*\b|\bquant\w*\b|\bai\b)",
    "product": r"(\bproduct\b|\bpm\b|product management|\bgrowth\b|\broadmap\b)",
    "cv": r"(computer vision|vision|opencv|yolo|camera|radar|perception|imaging)",
    "community": r"(community|partnership|outreach|events|club|association)",
    "finance": r"(finance|trading|investment|bank|equity)",
}


def is_likely_metadata_company(value: str) -> bool:
    normalized = normalize_key(value)
    if not normalized:
        return True
    if normalized in SHORT_EMPLOYMENT_TYPES:
        return True
    if re.search(r"\b\d+\s*(yrs?|years?|mos?|months?)\b", normalized):
        return True
    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", normalized):
        return True
    if "present" in normalized and re.search(r"\b\d{4}\b", normalized):
        return True
    return False


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


def build_my_profile_text(my_profile: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(
        [
            my_profile.get("headline", ""),
            my_profile.get("location", ""),
            my_profile.get("internship_goal", ""),
        ]
    )
    parts.extend(my_profile.get("experiences") or [])
    parts.extend(my_profile.get("focus_areas") or [])
    parts.extend(my_profile.get("proof_points") or [])
    return " ".join([part for part in parts if part]).strip()


def classify_text_tags(text: str) -> set[str]:
    lowered = (text or "").lower()
    tags: set[str] = set()
    for tag, pattern in TAG_PATTERNS.items():
        if re.search(pattern, lowered):
            tags.add(tag)
    return tags


def classify_my_profile(my_profile: dict[str, Any]) -> set[str]:
    return classify_text_tags(build_my_profile_text(my_profile))


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
        if title and company and not is_likely_metadata_company(company):
            hooks.append(f"{title} at {company}")
        elif company and not is_likely_metadata_company(company):
            hooks.append(f"{company} experience")
        elif title:
            hooks.append(title)
    for edu in target_profile.get("education") or []:
        school = edu.get("school", "")
        if school:
            hooks.append(f"{school} alum")
    headline = target_profile.get("headline", "")
    if headline:
        hooks.append(f"{headline}")
    return hooks[:5]


def classify_target(target_profile: dict[str, Any]) -> set[str]:
    return classify_text_tags(build_target_text(target_profile))


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
        company = target_fact.split(" at ", 1)[1].strip()
        return "" if is_likely_metadata_company(company) else company
    if target_fact.endswith(" alum"):
        return target_fact[: -len(" alum")].strip()
    return "" if is_likely_metadata_company(target_fact) else target_fact


def is_domain_fact(token: str) -> bool:
    return normalize_key(token) in {
        "nyc",
        "analytics",
        "product",
        "computer vision",
        "finance",
        "community",
    }
