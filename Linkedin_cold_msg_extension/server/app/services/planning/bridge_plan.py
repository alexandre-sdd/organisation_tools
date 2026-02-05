import re
from typing import Any

from ..utils.constants import CTA_BY_VARIANT, DOMAIN_FACTS
from .proof_points import select_proof_point_for_variant
from .target_analysis import (
    extract_company_from_fact,
    extract_headline_keyword,
    extract_role_keyword,
    is_domain_fact,
)
from ..utils.text_utils import compact_role_title, is_nyc, match_entity, normalize_key


def build_target_facts(target_profile: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    top_experiences = target_profile.get("top_experiences") or []

    if top_experiences:
        first = top_experiences[0] or {}
        title = compact_role_title(first.get("title", ""))
        company = first.get("company", "")
        if title and company:
            facts.append(
                {"type": "role_company", "text": f"{title} at {company}", "score": 12}
            )

    for exp in top_experiences:
        company = exp.get("company", "")
        if company:
            facts.append({"type": "company", "text": company, "score": 10})

    education = target_profile.get("education") or []
    if education:
        school = (education[0] or {}).get("school", "")
        if school:
            facts.append({"type": "school", "text": f"{school} alum", "score": 9})

    headline = target_profile.get("headline", "")
    about = target_profile.get("about", "")
    domain_text = f"{headline} {about}".lower().strip()
    domain_tags: set[str] = set()
    if re.search(
        r"(data|analytics|ml|machine learning|sql|python|bi|business intelligence|stats|statistic|quant|ai)",
        domain_text,
    ):
        domain_tags.add("analytics")
    if re.search(r"(product|pm|product management|growth|roadmap)", domain_text):
        domain_tags.add("product")
    if re.search(
        r"(computer vision|vision|opencv|yolo|camera|radar|perception|imaging)",
        domain_text,
    ):
        domain_tags.add("cv")
    if re.search(r"(community|partnership|outreach|events|club|association)", domain_text):
        domain_tags.add("community")
    if re.search(r"(finance|trading|investment|bank|equity)", domain_text):
        domain_tags.add("finance")

    for tag, phrase in DOMAIN_FACTS:
        if tag in domain_tags:
            facts.append({"type": "domain", "text": phrase, "score": 6})

    if headline:
        if len(headline) <= 60:
            text = headline
        else:
            text = headline[:57].rstrip() + "..."
        if text:
            facts.append({"type": "headline", "text": text, "score": 4})

    location = target_profile.get("location", "")
    if location and is_nyc(location):
        facts.append({"type": "location", "text": "NYC", "score": 3})

    deduped: dict[str, dict[str, Any]] = {}
    for fact in facts:
        key = normalize_key(fact["text"])
        if not key:
            continue
        if key not in deduped or fact["score"] > deduped[key]["score"]:
            deduped[key] = fact

    return sorted(deduped.values(), key=lambda f: f["score"], reverse=True)


def boost_school_facts(my_profile: dict[str, Any], target_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    school_stop = {"university", "college", "school", "institute", "faculty"}
    my_schools = my_profile.get("schools") or []
    boosted: list[dict[str, Any]] = []
    for fact in target_facts:
        score = fact.get("score", 0)
        if fact.get("type") == "school" and my_schools:
            school_text = fact.get("text", "").replace(" alum", "").strip()
            for my_school in my_schools:
                if match_entity(my_school, school_text, school_stop):
                    score += 2
                    break
        boosted.append({"type": fact.get("type"), "text": fact.get("text", ""), "score": score})
    return sorted(boosted, key=lambda f: f.get("score", 0), reverse=True)


def select_required_token(my_profile: dict[str, Any], target_profile: dict[str, Any]) -> str:
    top_experiences = target_profile.get("top_experiences") or []
    if top_experiences:
        company = (top_experiences[0] or {}).get("company", "")
        if company:
            return company

    education = target_profile.get("education") or []
    if education:
        school = (education[0] or {}).get("school", "")
        if school:
            school_stop = {"university", "college", "school", "institute", "faculty"}
            for my_school in (my_profile.get("schools") or []):
                if match_entity(my_school, school, school_stop):
                    return school

    headline = target_profile.get("headline", "")
    return extract_headline_keyword(headline)


def build_intent(tags: set[str], target_fact: str, target_profile: dict[str, Any]) -> str:
    top_experiences = target_profile.get("top_experiences") or []
    company_or_role = ""
    if top_experiences:
        company_or_role = (top_experiences[0] or {}).get("company", "")

    if not company_or_role:
        if not is_domain_fact(target_fact):
            company_or_role = extract_company_from_fact(target_fact)

    if not company_or_role:
        headline = target_profile.get("headline", "")
        if headline and len(headline) <= 60:
            company_or_role = headline

    if not company_or_role:
        company_or_role = "your work"

    if "cv" in tags:
        intent = f"Curious what you're building in vision at {company_or_role}"
    elif "finance" in tags:
        intent = f"Curious what you focus on in {company_or_role}"
    elif "product" in tags:
        intent = f"Curious how you think about product/growth at {company_or_role}"
    elif "analytics" in tags:
        intent = f"Curious how you apply analytics at {company_or_role}"
    elif "community" in tags:
        intent = f"Curious about your outreach/community work at {company_or_role}"
    else:
        intent = f"Curious about your path at {company_or_role}"

    if len(intent) > 80:
        intent = intent[:77].rstrip() + "..."
    return intent


def build_bridge_plan(
    my_profile: dict[str, Any],
    target_profile: dict[str, Any],
    target_tags: set[str],
    anchors: list[dict[str, Any]],
    anchor_plan: dict[str, dict[str, Any]],
    ranked_proof_points: list[dict[str, Any]],
    target_facts: list[dict[str, Any]],
    proof_points: list[str],
    classify_anchor_type_fn,
) -> dict[str, dict[str, str]]:
    variants = ["short", "direct", "warm"]

    boosted_facts = boost_school_facts(my_profile, target_facts)
    high_signal_fact = None
    for fact in boosted_facts:
        if fact.get("type") in {"role_company", "company", "school"}:
            high_signal_fact = fact
            break

    used_keys: set[str] = set()
    selected_facts: dict[str, dict[str, Any]] = {}
    for variant in variants:
        chosen = None
        for fact in boosted_facts:
            key = normalize_key(fact.get("text", ""))
            if key and key not in used_keys:
                chosen = fact
                used_keys.add(key)
                break
        if not chosen and boosted_facts:
            chosen = boosted_facts[0]
        if not chosen:
            chosen = {"type": "other", "text": "", "score": 0}
        selected_facts[variant] = chosen

    required_base = select_required_token(my_profile, target_profile)
    role_keyword = extract_role_keyword(target_profile)

    plan: dict[str, dict[str, str]] = {}
    for variant in variants:
        anchor = anchor_plan.get(variant, {}) or {}
        anchor_type = classify_anchor_type_fn(anchor)
        anchor_score = anchor.get("score", 0)
        hook_text = anchor.get("text", "")
        target_fact = selected_facts[variant].get("text", "")

        if anchor_type in {"domain", "location"} and anchor_score < 7 and high_signal_fact:
            hook_text = target_fact or high_signal_fact.get("text", "")

        proof_point = select_proof_point_for_variant(
            target_tags, anchor_type, proof_points, ranked_proof_points
        )
        intent = build_intent(target_tags, target_fact, target_profile)
        cta = CTA_BY_VARIANT[variant]

        required_token = required_base
        if required_token and normalize_key(required_token) == normalize_key(target_fact):
            if role_keyword:
                required_token = role_keyword

        plan[variant] = {
            "target_fact": target_fact,
            "hook_text": hook_text,
            "proof_point": proof_point,
            "intent": intent,
            "cta": cta,
            "required_token": required_token,
        }

    return plan
