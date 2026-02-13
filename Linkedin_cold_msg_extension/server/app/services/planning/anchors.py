from typing import Any

from ..utils.text_utils import compact_role_title, is_nyc, match_entity, normalize_key
from .target_analysis import is_likely_metadata_company, score_hook


def build_anchor_candidates(
    my_profile: dict[str, Any],
    target_profile: dict[str, Any],
    hooks: list[str],
    derived_hooks: list[str],
    target_tags: set[str],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    school_stop = {"university", "college", "school", "institute", "faculty"}
    company_stop = {"group", "inc", "corp", "ltd", "llc", "company", "technologies", "tech"}

    my_schools = my_profile.get("schools") or []
    target_schools = [edu.get("school", "") for edu in target_profile.get("education") or []]
    my_location = my_profile.get("location", "")
    target_location = target_profile.get("location", "")

    for my_school in my_schools:
        for target_school in target_schools:
            if match_entity(my_school, target_school, school_stop, min_token_overlap=2):
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

    if "cv" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared focus on computer vision",
                "score": 6,
                "evidence": "target_tags=cv",
            }
        )
    if "analytics" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared focus on analytics/data",
                "score": 6,
                "evidence": "target_tags=analytics",
            }
        )
    if "product" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared product/analytics focus",
                "score": 5,
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


def select_anchor_plan(anchors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    preferred_order = ["school", "company", "role", "domain", "location", "hook", "derived"]
    plan: dict[str, dict[str, Any]] = {}
    used_types: set[str] = set()
    variants = ["short", "direct", "warm"]

    for variant in variants:
        for anchor in anchors:
            if anchor["type"] not in used_types:
                plan[variant] = anchor
                used_types.add(anchor["type"])
                break
        if variant not in plan and anchors:
            plan[variant] = anchors[0]

    if anchors:
        for variant in variants:
            if variant not in plan:
                for anchor in anchors:
                    if anchor["type"] in preferred_order:
                        plan[variant] = anchor
                        break
    return plan


def classify_anchor_type(anchor: dict[str, Any]) -> str:
    anchor_type = (anchor.get("type") or "").strip().lower()
    allowed = {"school", "company", "role", "location", "domain", "hook", "derived"}
    if anchor_type in allowed:
        return anchor_type
    return "other"
