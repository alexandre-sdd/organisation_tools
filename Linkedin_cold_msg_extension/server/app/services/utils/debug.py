from typing import Any


def build_debug_log(
    request_id: str,
    model_name: str,
    compact_my_profile: dict[str, Any],
    compact_target_profile: dict[str, Any],
    hooks_in: list[str],
    derived_hooks: list[str],
    hook_scores_sorted: list[dict[str, Any]],
    derived_scores: list[dict[str, Any]],
    target_tags: set[str],
    ranked_proof_points: list[dict[str, Any]],
    anchor_candidates: list[dict[str, Any]],
    anchor_plan: dict[str, dict[str, Any]],
    target_facts: list[dict[str, Any]],
    bridge_plan: dict[str, dict[str, str]],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "model_name": model_name,
        "compact_my_profile": compact_my_profile,
        "compact_target_profile": compact_target_profile,
        "hooks_in": hooks_in,
        "derived_hooks": derived_hooks,
        "hook_scores_sorted": hook_scores_sorted,
        "derived_scores": derived_scores,
        "target_tags": sorted(list(target_tags)),
        "ranked_proof_points": ranked_proof_points[:5],
        "anchor_candidates": anchor_candidates[:10],
        "anchor_plan": anchor_plan,
        "target_facts": target_facts[:5],
        "bridge_plan": bridge_plan,
    }
