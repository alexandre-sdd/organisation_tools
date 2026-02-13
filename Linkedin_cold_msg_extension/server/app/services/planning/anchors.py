import re
from typing import Any

from ..utils.constants import VARIANT_LABELS
from ..utils.text_utils import compact_role_title, is_nyc, match_entity, normalize_key
from .target_analysis import is_likely_metadata_company, score_hook


def _school_tokens(value: str, school_stop: set[str]) -> list[str]:
    return [tok for tok in normalize_key(value).split() if tok and tok not in school_stop]


def _school_min_overlap(a: str, b: str, school_stop: set[str]) -> int:
    a_tokens = _school_tokens(a, school_stop)
    b_tokens = _school_tokens(b, school_stop)
    if not a_tokens or not b_tokens:
        return 1
    if len(a_tokens) <= 1 or len(b_tokens) <= 1:
        return 1
    return 2


def _clean_school_name(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    return text or value.strip()


def build_anchor_candidates(
    my_profile: dict[str, Any],
    target_profile: dict[str, Any],
    hooks: list[str],
    derived_hooks: list[str],
    target_tags: set[str],
    my_tags: set[str] | None = None,
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    school_stop = {"university", "college", "school", "institute", "faculty"}
    company_stop = {"group", "inc", "corp", "ltd", "llc", "company", "technologies", "tech"}

    my_schools = my_profile.get("schools") or []
    target_schools = [edu.get("school", "") for edu in target_profile.get("education") or []]
    target_headline = target_profile.get("headline", "")
    my_location = my_profile.get("location", "")
    target_location = target_profile.get("location", "")
    my_tags = my_tags or set()

    headline_has_school_hint = bool(
        re.search(
            r"\b(university|college|school|institute|ecole|supelec|polytechnique|alum)\b",
            normalize_key(target_headline),
        )
    )
    if target_headline:
        normalized_headline = normalize_key(target_headline)
        for my_school in my_schools:
            cleaned_my_school = _clean_school_name(my_school)
            normalized_school = normalize_key(cleaned_my_school)
            has_explicit_school_text = bool(
                normalized_school and normalized_school in normalized_headline
            )
            if not (headline_has_school_hint or has_explicit_school_text):
                continue
            required = _school_min_overlap(cleaned_my_school, target_headline, school_stop)
            if match_entity(
                cleaned_my_school,
                target_headline,
                school_stop,
                min_token_overlap=required,
            ):
                target_schools.append(cleaned_my_school)

    for my_school in my_schools:
        cleaned_my_school = _clean_school_name(my_school)
        for target_school in target_schools:
            required = _school_min_overlap(cleaned_my_school, target_school, school_stop)
            if match_entity(
                cleaned_my_school,
                target_school,
                school_stop,
                min_token_overlap=required,
            ):
                base = 12
                text = f"{target_school} alum"
                if is_nyc(my_location) and is_nyc(target_location):
                    base += 4
                    text = f"{target_school} alum in NYC"
                anchors.append(
                    {
                        "type": "school",
                        "text": text,
                        "score": base,
                        "evidence": f"{my_school} + {target_school} + {target_location}",
                    }
                )

    my_experiences = my_profile.get("experiences") or []
    for exp in target_profile.get("top_experiences") or []:
        company = exp.get("company", "")
        title = compact_role_title(exp.get("title", ""))
        if company and not is_likely_metadata_company(company):
            for my_exp in my_experiences:
                if match_entity(my_exp, company, company_stop):
                    anchors.append(
                        {
                            "type": "company",
                            "text": f"Both have experience at {company}",
                            "score": 9,
                            "evidence": f"{my_exp} + {company}",
                        }
                    )
        if company and title and not is_likely_metadata_company(company):
            anchors.append(
                {
                    "type": "role",
                    "text": f"{title} at {company}",
                    "score": 6,
                    "evidence": f"{title} + {company}",
                }
            )
        elif title:
            anchors.append(
                {
                    "type": "role",
                    "text": title,
                    "score": 5,
                    "evidence": f"{title}",
                }
            )

    if is_nyc(my_location) and is_nyc(target_location):
        anchors.append(
            {
                "type": "location",
                "text": "Both based in NYC",
                "score": 6,
                "evidence": f"{my_location} + {target_location}",
            }
        )

    shared_tags = sorted(list(target_tags.intersection(my_tags)))
    for tag in shared_tags:
        tag_label = {
            "analytics": "analytics/data",
            "product": "product",
            "cv": "computer vision",
            "community": "community",
            "finance": "finance",
        }.get(tag, tag)
        anchors.append(
            {
                "type": "industry",
                "text": f"Shared background in {tag_label}",
                "score": 10,
                "evidence": f"shared_tags={tag}",
            }
        )

    # Keep a low-priority domain fallback even without explicit overlap.
    if "cv" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared focus on computer vision",
                "score": 4,
                "evidence": "target_tags=cv",
            }
        )
    if "analytics" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared focus on analytics/data",
                "score": 4,
                "evidence": "target_tags=analytics",
            }
        )
    if "product" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared product/analytics focus",
                "score": 4,
                "evidence": "target_tags=product",
            }
        )

    for hook in hooks:
        anchors.append(
            {
                "type": "hook",
                "text": hook,
                "score": 4 + score_hook(hook, target_profile),
                "evidence": "extension hook",
            }
        )

    for hook in derived_hooks:
        anchors.append(
            {
                "type": "derived",
                "text": hook,
                "score": 3 + score_hook(hook, target_profile),
                "evidence": "derived hook",
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for anchor in anchors:
        key = normalize_key(anchor["text"])
        if not key:
            continue
        if key not in deduped or anchor["score"] > deduped[key]["score"]:
            deduped[key] = anchor

    return sorted(deduped.values(), key=lambda a: a["score"], reverse=True)


def _pick_rotated(candidates: list[dict[str, Any]], cycle_index: int) -> dict[str, Any] | None:
    if not candidates:
        return None
    return candidates[cycle_index % len(candidates)]


def select_anchor_plan(
    anchors: list[dict[str, Any]],
    cycle_index: int = 0,
) -> dict[str, dict[str, Any]]:
    plan: dict[str, dict[str, Any]] = {}
    used_types: set[str] = set()
    used_texts: set[str] = set()
    variants = VARIANT_LABELS
    cycle = max(0, int(cycle_index or 0))

    def anchor_type(anchor: dict[str, Any]) -> str:
        return (anchor.get("type") or "").strip().lower()

    required_types: list[str] = []
    if any(anchor_type(anchor) == "school" for anchor in anchors):
        required_types.append("school")
    if any(anchor_type(anchor) == "industry" for anchor in anchors):
        required_types.append("industry")

    seeded_variants = variants[: len(required_types)]
    for variant, req_type in zip(seeded_variants, required_types):
        matches: list[dict[str, Any]] = []
        for anchor in anchors:
            text_key = normalize_key(anchor.get("text", ""))
            if (
                anchor_type(anchor) == req_type
                and text_key
                and text_key not in used_texts
            ):
                matches.append(anchor)
        chosen = _pick_rotated(matches, cycle)
        if chosen:
            plan[variant] = chosen
            used_types.add(anchor_type(chosen))
            used_texts.add(normalize_key(chosen.get("text", "")))

    for variant in variants:
        if variant in plan:
            continue
        chosen: dict[str, Any] | None = None

        primary_candidates: list[dict[str, Any]] = []
        for anchor in anchors:
            kind = anchor_type(anchor)
            text_key = normalize_key(anchor.get("text", ""))
            if text_key and text_key not in used_texts and kind not in used_types:
                primary_candidates.append(anchor)
        chosen = _pick_rotated(primary_candidates, cycle)

        if not chosen:
            secondary_candidates: list[dict[str, Any]] = []
            for anchor in anchors:
                text_key = normalize_key(anchor.get("text", ""))
                if text_key and text_key not in used_texts:
                    secondary_candidates.append(anchor)
            chosen = _pick_rotated(secondary_candidates, cycle)

        if not chosen:
            tertiary_candidates: list[dict[str, Any]] = []
            for anchor in anchors:
                kind = (anchor.get("type") or "").strip().lower()
                if kind not in used_types:
                    tertiary_candidates.append(anchor)
            chosen = _pick_rotated(tertiary_candidates, cycle)

        if not chosen and anchors:
            chosen = _pick_rotated(anchors, cycle)

        if chosen:
            plan[variant] = chosen
            used_types.add(anchor_type(chosen))
            text_key = normalize_key(chosen.get("text", ""))
            if text_key:
                used_texts.add(text_key)

    return plan


def classify_anchor_type(anchor: dict[str, Any]) -> str:
    anchor_type = (anchor.get("type") or "").strip().lower()
    allowed = {"school", "industry", "company", "role", "location", "domain", "hook", "derived"}
    if anchor_type in allowed:
        return anchor_type
    return "other"
