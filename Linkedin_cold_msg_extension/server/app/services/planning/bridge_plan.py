from typing import Any

from ..utils.constants import CTA_BY_VARIANT, DOMAIN_FACTS, VARIANT_LABELS
from .proof_points import select_proof_point_for_variant
from .target_analysis import (
    classify_target,
    extract_company_from_fact,
    extract_headline_keyword,
    is_domain_fact,
    is_likely_metadata_company,
)
from ..utils.text_utils import compact_role_title, is_nyc, match_entity, normalize_key


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


def build_target_facts(target_profile: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    top_experiences = target_profile.get("top_experiences") or []

    first_valid_pair = None
    for exp in top_experiences:
        title = compact_role_title((exp or {}).get("title", ""))
        company = (exp or {}).get("company", "")
        if title and company and not is_likely_metadata_company(company):
            first_valid_pair = {"title": title, "company": company}
            break
    if first_valid_pair:
        facts.append(
            {
                "type": "role_company",
                "text": f"{first_valid_pair['title']} at {first_valid_pair['company']}",
                "score": 12,
            }
        )

    for exp in top_experiences:
        company = (exp or {}).get("company", "")
        title = compact_role_title((exp or {}).get("title", ""))
        if company and not is_likely_metadata_company(company):
            facts.append({"type": "company", "text": company, "score": 10})
        elif title and not is_likely_metadata_company(title):
            facts.append({"type": "company", "text": title, "score": 9})

    education = target_profile.get("education") or []
    if education:
        school = (education[0] or {}).get("school", "")
        if school:
            facts.append({"type": "school", "text": f"{school} alum", "score": 9})

    headline = target_profile.get("headline", "")
    about = target_profile.get("about", "")
    domain_tags = classify_target(
        {
            "name": "",
            "headline": headline,
            "location": "",
            "about": about,
            "top_experiences": [],
            "education": [],
        }
    )

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
                required = _school_min_overlap(my_school, school_text, school_stop)
                if match_entity(my_school, school_text, school_stop, min_token_overlap=required):
                    score += 2
                    break
        boosted.append({"type": fact.get("type"), "text": fact.get("text", ""), "score": score})
    return sorted(boosted, key=lambda f: f.get("score", 0), reverse=True)


def select_required_token(my_profile: dict[str, Any], target_profile: dict[str, Any]) -> str:
    top_experiences = target_profile.get("top_experiences") or []
    for exp in top_experiences:
        company = (exp or {}).get("company", "")
        if company and not is_likely_metadata_company(company):
            return company

    education = target_profile.get("education") or []
    if education:
        school = (education[0] or {}).get("school", "")
        if school:
            school_stop = {"university", "college", "school", "institute", "faculty"}
            for my_school in (my_profile.get("schools") or []):
                required = _school_min_overlap(my_school, school, school_stop)
                if match_entity(my_school, school, school_stop, min_token_overlap=required):
                    return school

    headline = target_profile.get("headline", "")
    return extract_headline_keyword(headline)


def build_intent(tags: set[str], target_fact: str, target_profile: dict[str, Any]) -> str:
    top_experiences = target_profile.get("top_experiences") or []
    company_or_role = ""
    for exp in top_experiences:
        company = (exp or {}).get("company", "")
        if company and not is_likely_metadata_company(company):
            company_or_role = company
            break

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
    variants = VARIANT_LABELS

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

    plan: dict[str, dict[str, str]] = {}
    used_hook_keys: set[str] = set()
    for variant in variants:
        anchor = anchor_plan.get(variant, {}) or {}
        anchor_type = classify_anchor_type_fn(anchor)
        anchor_score = anchor.get("score", 0)
        hook_text = anchor.get("text", "")
        target_fact = selected_facts[variant].get("text", "")

        if anchor_type in {"domain", "location"} and anchor_score < 7 and high_signal_fact:
            hook_text = target_fact or high_signal_fact.get("text", "")
        hook_text = compact_hook_text(hook_text, target_fact)
        hook_text = choose_unique_hook_text(
            hook_text,
            target_fact,
            anchors,
            boosted_facts,
            used_hook_keys,
        )
        hook_key = normalize_key(hook_text)
        if hook_key:
            used_hook_keys.add(hook_key)

        proof_point = select_proof_point_for_variant(
            target_tags, anchor_type, proof_points, ranked_proof_points
        )
        intent = build_intent(target_tags, target_fact, target_profile)
        cta = CTA_BY_VARIANT[variant]

        # Required token is intentionally disabled to avoid unnatural forced insertions.
        required_token = ""

        plan[variant] = {
            "target_fact": target_fact,
            "hook_text": hook_text,
            "proof_point": proof_point,
            "intent": intent,
            "cta": cta,
            "required_token": required_token,
        }

    return plan


def compact_hook_text(hook_text: str, target_fact: str) -> str:
    text = " ".join((hook_text or "").split()).strip()
    if not text:
        return target_fact or ""
    if len(text) <= 70:
        return text
    if target_fact and len(target_fact) <= 70:
        return target_fact
    return text[:67].rstrip() + "..."


def choose_unique_hook_text(
    primary_hook: str,
    target_fact: str,
    anchors: list[dict[str, Any]],
    boosted_facts: list[dict[str, Any]],
    used_hook_keys: set[str],
) -> str:
    candidates = [primary_hook, target_fact]
    candidates.extend((anchor or {}).get("text", "") for anchor in anchors)
    candidates.extend((fact or {}).get("text", "") for fact in boosted_facts)

    for candidate in candidates:
        text = " ".join((candidate or "").split()).strip()
        if not text:
            continue
        key = normalize_key(text)
        if not key or key in used_hook_keys:
            continue
        if is_likely_metadata_company(text):
            continue
        return text

    fallback = " ".join((primary_hook or target_fact or "").split()).strip()
    if fallback and not is_likely_metadata_company(fallback):
        return fallback
    return "your work"
