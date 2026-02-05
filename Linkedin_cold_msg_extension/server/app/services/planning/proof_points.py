import re
from typing import Any


def score_proof_point(point: str, tags: set[str]) -> int:
    point_lower = point.lower()
    score = 1
    if "cv" in tags and re.search(r"(yolo|opencv|vision|camera|radar|tracking)", point_lower):
        score += 4
    if "analytics" in tags and re.search(
        r"(pipeline|data-quality|analytics|dashboard|pandas|sql|monitoring|accounting)",
        point_lower,
    ):
        score += 4
    if "product" in tags and re.search(r"(product|decision-support|dashboard)", point_lower):
        score += 2
    if "community" in tags and re.search(
        r"(outreach|partnership|club|speaker|events)", point_lower
    ):
        score += 4
    if "finance" in tags and re.search(
        r"(accounting|commercial|performance|forecast|pricing)",
        point_lower,
    ):
        score += 2
    return score


def proof_point_strength_score(point: str) -> int:
    """Heuristic to prefer concrete, credible achievements over generic/background lines."""
    p = (point or "").lower()
    score = 0

    if re.search(r"\b(built|shipped|prototyped|automated|deployed|launched|owned|delivered)\b", p):
        score += 6

    if re.search(r"\b(pipeline|data-quality|monitoring|dashboard|pandas|sql|opencv|yolo|camera|radar)\b", p):
        score += 3

    if re.search(r"\b(targeting|internship|internships)\b", p):
        score -= 8
    if re.search(r"\b(student|dual degree|based in|core stack)\b", p):
        score -= 4

    return score


def select_proof_point_for_variant(
    tags: set[str],
    anchor_type: str,
    proof_points: list[str],
    ranked: list[dict[str, Any]],
) -> str:
    def pick_best(candidates: list[str]) -> str | None:
        if not candidates:
            return None
        scored = [
            (proof_point_strength_score(p), -len(p), p)
            for p in candidates
        ]
        scored.sort(reverse=True)
        return scored[0][2]

    def best_match(pattern: str) -> str | None:
        matches = [p for p in proof_points if re.search(pattern, p.lower())]
        return pick_best(matches)

    def best_non_weak() -> str | None:
        strong = [p for p in proof_points if proof_point_strength_score(p) >= 2]
        if strong:
            return pick_best(strong)
        return pick_best(proof_points)

    if "cv" in tags:
        match = best_match(r"(yolo|opencv|vision|camera|radar|tracking)")
    elif anchor_type == "school" or "community" in tags:
        match = best_match(r"(outreach|partnership|club|speaker|events)")
    elif "product" in tags:
        match = best_match(r"(product management|pm\b|growth|decision-support|dashboard|roadmap)")
    elif "finance" in tags:
        match = best_match(r"(accounting|pricing|performance|forecast)")
    else:
        match = best_match(
            r"(pipeline|data-quality|pandas|sql|monitoring|dashboard|accounting|analytics)"
        )

    if match:
        return match
    if ranked:
        ranked_points = [item.get("point", "") for item in ranked if item.get("point")]
        picked = pick_best([p for p in ranked_points if p])
        if picked:
            return picked
    picked = best_non_weak()
    return picked or ""
