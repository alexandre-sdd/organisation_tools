from typing import Any

from ..planning.anchors import build_anchor_candidates, classify_anchor_type, select_anchor_plan
from ..planning.bridge_plan import build_bridge_plan, build_target_facts
from ..planning.proof_points import proof_point_strength_score, score_proof_point
from ..planning.target_analysis import classify_target, derive_hooks, score_hook
from ..utils.constants import BASE_BANLIST, FALLBACK_PROOF_POINTS, MAX_PROOF_POINTS, RESPONSE_SCHEMA
from ..utils.debug import build_debug_log
from ..utils.payload import as_plain_dict


def build_prompt_context(
    payload: Any,
    request_id: str = "",
    model_name: str = "",
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if isinstance(payload, dict):
        my_profile = as_plain_dict(payload.get("my_profile", {}))
        target_profile = as_plain_dict(payload.get("target_profile", {}))
        raw_hooks = payload.get("hooks") or []
    else:
        my_profile = as_plain_dict(getattr(payload, "my_profile", {}))
        target_profile = as_plain_dict(getattr(payload, "target_profile", {}))
        raw_hooks = getattr(payload, "hooks", None) or []

    hooks = [hook for hook in raw_hooks if hook][:3]

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
        "You write tailored LinkedIn connection notes under a hard 300-character limit. "
        "Return strict JSON only (no markdown, no prose). "
        "Do NOT fabricate details. Use ONLY BRIDGE_PLAN facts. "
        "Write exactly 3 variants labeled short, direct, warm. "
        "Constraints per variant: "
        "(1) <= 300 characters. "
        "(2) Mention TARGET_FACT and HOOK_TEXT (exact wording preferred but light rephrasing is allowed). "
        "(3) Include one concrete detail from PROOF_POINT. "
        "(4) Include INTENT naturally (exact wording not required). "
        "(5) Must include CTA verbatim at the very end. "
        "(6) If REQUIRED_TOKEN is present, include it verbatim once. "
        "(7) Avoid robotic style: do NOT start every variant with the same template and do NOT mechanically repeat field names. "
        "(8) Keep tone human, concise, and specific; 1-2 sentences max. "
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

    bridge_lines: list[str] = ["BRIDGE_PLAN (facts to include, no fabrication):"]
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
            "STYLE:",
            "- Keep variants distinct in wording and rhythm.",
            "- Avoid overusing parentheses and rigid connector phrases.",
            "- Keep one strong bridge between target fact and sender proof point.",
            "- Do not add extra sender facts beyond PROOF_POINT.",
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
