from typing import Any

from ..planning.anchors import build_anchor_candidates, classify_anchor_type, select_anchor_plan
from ..planning.bridge_plan import build_bridge_plan, build_target_facts
from ..planning.proof_points import proof_point_strength_score, score_proof_point
from ..planning.target_analysis import classify_target, derive_hooks, score_hook
from ..utils.constants import BASE_BANLIST, FALLBACK_PROOF_POINTS, MAX_PROOF_POINTS, RESPONSE_SCHEMA
from ..utils.debug import build_debug_log


def build_prompt_context(
    payload: Any,
    request_id: str = "",
    model_name: str = "",
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    my_profile = payload.my_profile or {}
    target_profile = payload.target_profile or {}
    hooks = [hook for hook in (payload.hooks or []) if hook][:3]

    raw_proof_points = [p for p in (my_profile.get("proof_points") or []) if p]
    if not raw_proof_points:
        raw_proof_points = FALLBACK_PROOF_POINTS.copy()

    compact_my_profile = {
        "headline": my_profile.get("headline", ""),
        "location": my_profile.get("location", ""),
        "schools": (my_profile.get("schools") or [])[:3],
        "experiences": (my_profile.get("experiences") or [])[:3],
        "proof_points": raw_proof_points[:MAX_PROOF_POINTS],
        "focus_areas": (my_profile.get("focus_areas") or [])[:6],
        "internship_goal": my_profile.get("internship_goal", ""),
        "do_not_say": (my_profile.get("do_not_say") or [])[:12],
        "tone_preference": my_profile.get("tone_preference", "warm"),
    }

    compact_target_profile = {
        "name": target_profile.get("name", ""),
        "headline": target_profile.get("headline", ""),
        "location": target_profile.get("location", ""),
        "about": target_profile.get("about", ""),
        "top_experiences": (target_profile.get("top_experiences") or [])[:2],
        "education": (target_profile.get("education") or [])[:1],
    }

    derived = derive_hooks(compact_target_profile)
    hook_scores = [
        {"hook": hook, "score": score_hook(hook, compact_target_profile)}
        for hook in hooks
    ]
    if not hook_scores:
        hook_scores = [
            {"hook": hook, "score": score_hook(hook, compact_target_profile)}
            for hook in derived
        ]
    hook_scores_sorted = sorted(hook_scores, key=lambda h: h["score"], reverse=True)
    derived_scores = [
        {"hook": hook, "score": score_hook(hook, compact_target_profile)}
        for hook in derived
    ]

    target_tags = classify_target(compact_target_profile)
    proof_points = raw_proof_points[:MAX_PROOF_POINTS]
    ranked_proof_points = sorted(
        [
            {
                "point": p,
                "score": score_proof_point(p, target_tags) + proof_point_strength_score(p),
            }
            for p in proof_points
        ],
        key=lambda item: item["score"],
        reverse=True,
    )[:6]

    banlist = BASE_BANLIST + (compact_my_profile.get("do_not_say") or [])
    banlist = [item.strip() for item in banlist if item and item.strip()]

    anchor_candidates = build_anchor_candidates(
        compact_my_profile,
        compact_target_profile,
        hooks,
        derived,
        target_tags,
    )
    anchor_plan = select_anchor_plan(anchor_candidates[:8])

    target_facts = build_target_facts(compact_target_profile)
    bridge_plan = build_bridge_plan(
        compact_my_profile,
        compact_target_profile,
        target_tags,
        anchor_candidates,
        anchor_plan,
        ranked_proof_points,
        target_facts,
        proof_points,
        classify_anchor_type,
    )

    system = (
        "You write maximally tailored LinkedIn connection notes under a hard 300-character limit. "
        "Return strict JSON only (no markdown, no prose). "
        "Do NOT fabricate details. Use ONLY the BRIDGE_PLAN strings below. "
        "Write exactly 3 variants labeled short, direct, warm. "
        "Hard constraints per variant: "
        "(1) <= 300 characters. "
        "(2) Must include TARGET_FACT verbatim. "
        "(3) Must include HOOK_TEXT verbatim. "
        "(4) Must include PROOF_POINT verbatim. "
        "(5) Must include INTENT (verbatim or a minimal rephrase with same meaning). "
        "(6) Must include CTA verbatim, and end with CTA. "
        "(7) If REQUIRED_TOKEN is provided, it must appear verbatim AND not as a standalone fragment. "
        "(8) Must include an explicit bridge sentence that contains both TARGET_FACT and PROOF_POINT; "
        "use exactly: 'Seeing {TARGET_FACT}, {PROOF_POINT}.' "
        "You may keep everything else minimal; do not add extra background (no schools/locations/headlines) beyond PROOF_POINT. "
        "Avoid banlist phrases. "
        "Never refuse or explain constraints; always produce JSON."
    )

    fact_lines = [
        f"{idx + 1}. [{item['type']}] {item['text']} (score {item['score']})"
        for idx, item in enumerate(target_facts[:5])
    ]

    def format_bridge_block(label: str, plan: dict[str, str]) -> list[str]:
        lines = [f"{label}:"]
        lines.append(f"  TARGET_FACT={plan.get('target_fact', '')}")
        lines.append(f"  HOOK_TEXT={plan.get('hook_text', '')}")
        lines.append(f"  PROOF_POINT={plan.get('proof_point', '')}")
        lines.append(f"  INTENT={plan.get('intent', '')}")
        lines.append(f"  CTA={plan.get('cta', '')}")
        required_token = plan.get("required_token", "")
        if required_token:
            lines.append(f"  REQUIRED_TOKEN={required_token}")
        return lines

    bridge_lines: list[str] = ["BRIDGE_PLAN (MUST FOLLOW EXACTLY):"]
    for variant in ["short", "direct", "warm"]:
        bridge_lines.extend(format_bridge_block(variant, bridge_plan.get(variant, {})))

    context_text = "\n".join(
        [
            f"TARGET_NAME: {compact_target_profile['name']}",
            "",
            "TARGET_FACTS_RANKED:",
            *([f"- {line}" for line in fact_lines] or ["- (none)"]),
            "",
            *bridge_lines,
            "",
            f"BANLIST: {', '.join(banlist)}",
            "",
            "HARD TEMPLATE (recommended, keep it short):",
            "Hi {TARGET_NAME}, {HOOK_TEXT}. Seeing {TARGET_FACT}, {PROOF_POINT}. {INTENT}. {CTA}",
            "If REQUIRED_TOKEN is present, include it inside the first sentence, e.g. '{HOOK_TEXT} ({REQUIRED_TOKEN})'.",
            "Do not add extra facts about the sender beyond PROOF_POINT.",
            "",
            "OUTPUT_JSON_SCHEMA (shape):",
            "{",
            "  \"variants\": [",
            "    {\"label\": \"short\", \"text\": \"...\", \"char_count\": 123},",
            "    {\"label\": \"direct\", \"text\": \"...\", \"char_count\": 140},",
            "    {\"label\": \"warm\", \"text\": \"...\", \"char_count\": 155}",
            "  ]",
            "}",
        ]
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": context_text},
    ]

    debug_log = build_debug_log(
        request_id=request_id,
        model_name=model_name,
        compact_my_profile=compact_my_profile,
        compact_target_profile=compact_target_profile,
        hooks_in=hooks,
        derived_hooks=derived,
        hook_scores_sorted=hook_scores_sorted,
        derived_scores=derived_scores,
        target_tags=target_tags,
        ranked_proof_points=ranked_proof_points,
        anchor_candidates=anchor_candidates,
        anchor_plan=anchor_plan,
        target_facts=target_facts,
        bridge_plan=bridge_plan,
    )

    return messages, debug_log


def build_prompt(payload: Any) -> list[dict[str, str]]:
    messages, _ = build_prompt_context(payload)
    return messages
