import json
import os
import re
import unicodedata
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DEFAULT_MODEL_NAME = "gpt-4o-2024-08-06"
MODEL_NAME = os.getenv("OPENAI_MODEL", DEFAULT_MODEL_NAME)
OPENAI_API_URL = "https://api.openai.com/v1/responses"

FALLBACK_PROOF_POINTS = [
    "Built production-grade pipelines on European accounting data at Chanel; automated data-quality checks in pandas",
    "Shipped analytics tools and monitoring dashboards for commercial performance at Sigma Group",
    "Prototyped vehicle-tracking with camera + radar context at Forvia using YOLO/OpenCV",
    "VP Outreach & Partnerships at Columbia Product Managers Club (speaker outreach + partnerships + events)",
    "Daily stack: Python, pandas, SQL; ML foundations; dashboards and decision-support",
    "Based in NYC; targeting Summer 2026 analytics/product/data internship",
]

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "name": "connection_notes",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "variants": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "enum": ["short", "direct", "warm"],
                        },
                        "text": {
                            "type": "string",
                        },
                        "char_count": {
                            "type": "integer",
                        },
                    },
                    "required": ["label", "text", "char_count"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["variants"],
        "additionalProperties": False,
    },
}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    my_profile: dict[str, Any]
    target_profile: dict[str, Any]
    hooks: list[str]


class Variant(BaseModel):
    label: str
    text: str
    char_count: int


class GenerateResponse(BaseModel):
    variants: list[Variant]


def tokenize(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if len(tok) >= 4]


def normalize_key(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return normalized


def tokens_without_stopwords(text: str, stopwords: set[str]) -> set[str]:
    return {tok for tok in normalize_key(text).split() if tok and tok not in stopwords}


def match_entity(a: str, b: str, stopwords: set[str]) -> bool:
    na = normalize_key(a)
    nb = normalize_key(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    tokens_a = tokens_without_stopwords(a, stopwords)
    tokens_b = tokens_without_stopwords(b, stopwords)
    return len(tokens_a.intersection(tokens_b)) >= 1


def is_nyc(location: str) -> bool:
    loc = normalize_key(location)
    return "new york" in loc or "nyc" in loc or loc.endswith(" ny")


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
            if match_entity(my_school, target_school, school_stop):
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
        title = exp.get("title", "")
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
        if company and title:
            anchors.append(
                {
                    "type": "role",
                    "text": f"{title} at {company}",
                    "score": 6,
                    "evidence": f"{title} + {company}",
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
                "score": 7,
                "evidence": "target_tags=cv",
            }
        )
    if "analytics" in target_tags:
        anchors.append(
            {
                "type": "domain",
                "text": "Shared focus on analytics/data",
                "score": 7,
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

    # Deduplicate by text, keep highest score
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

    # Ensure preferred ordering if we have gaps
    if anchors:
        for variant in variants:
            if variant not in plan:
                for anchor in anchors:
                    if anchor["type"] in preferred_order:
                        plan[variant] = anchor
                        break
    return plan


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
    if re.search(r"(data|analytics|ml|machine learning|sql|python|bi|business intelligence|stats|statistic|quant|ai)", text):
        tags.add("analytics")
    if re.search(r"(product|pm|product management|growth|roadmap)", text):
        tags.add("product")
    if re.search(r"(computer vision|vision|opencv|yolo|camera|radar|perception|imaging)", text):
        tags.add("cv")
    if re.search(r"(community|partnership|outreach|events|club|association)", text):
        tags.add("community")
    if re.search(r"(finance|trading|investment|bank|equity)", text):
        tags.add("finance")
    return tags


def score_proof_point(point: str, tags: set[str]) -> int:
    point_lower = point.lower()
    score = 1
    if "cv" in tags and re.search(r"(yolo|opencv|vision|camera|radar|tracking)", point_lower):
        score += 4
    if "analytics" in tags and re.search(r"(pipeline|data-quality|analytics|dashboard|pandas|sql|monitoring|accounting)", point_lower):
        score += 4
    if "product" in tags and re.search(r"(product|decision-support|dashboard)", point_lower):
        score += 2
    if "community" in tags and re.search(r"(outreach|partnership|club|speaker|events)", point_lower):
        score += 4
    if "finance" in tags and re.search(r"(accounting|commercial|performance|forecast|pricing)", point_lower):
        score += 2
    return score


def build_prompt(payload: GenerateRequest) -> list[dict[str, str]]:
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
        "proof_points": raw_proof_points[:6],
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
    proof_points = raw_proof_points
    ranked_proof_points = sorted(
        [{"point": p, "score": score_proof_point(p, target_tags)} for p in proof_points],
        key=lambda item: item["score"],
        reverse=True,
    )[:6]

    banlist = compact_my_profile.get("do_not_say") or [
        "hope you are well",
        "impressive",
        "pick your brain",
        "leverage synergy",
        "reach out",
        "would love to learn more",
    ]

    anchor_candidates = build_anchor_candidates(
        compact_my_profile,
        compact_target_profile,
        hooks,
        derived,
        target_tags,
    )
    anchor_plan = select_anchor_plan(anchor_candidates[:8])

    system = (
        "You write sharp, non-generic LinkedIn connection notes. "
        "Return strict JSON only (no markdown, no prose). "
        "Do NOT fabricate details. Use only the provided my_profile, target_profile, hooks, and ranked lists. "
        "Write exactly 3 variants labeled short, direct, warm. "
        "Each variant must be <= 300 characters (hard limit). "
        "Each variant must contain exactly one hook, exactly one credibility proof point from my_profile.proof_points, "
        "and end with a soft CTA. "
        "Each message must include a clear rationale for reaching out and avoid generic praise. "
        "Never refuse or explain constraints; always produce JSON."
    )

    hook_rank_lines = [
        f"{idx + 1}. {item['hook']} (score {item['score']})"
        for idx, item in enumerate(hook_scores_sorted[:5])
    ]
    derived_rank_lines = [
        f"{idx + 1}. {item['hook']} (score {item['score']})"
        for idx, item in enumerate(derived_scores[:5])
    ]
    proof_lines = [
        f"{idx + 1}. {item['point']} (score {item['score']})"
        for idx, item in enumerate(ranked_proof_points[:6])
    ]
    anchor_lines = [
        f"{idx + 1}. [{item['type']}] {item['text']} (score {item['score']})"
        for idx, item in enumerate(anchor_candidates[:6])
    ]

    context_text = "\n".join(
        [
            "MY_PROFILE:",
            f"- headline: {compact_my_profile['headline']}",
            f"- location: {compact_my_profile['location']}",
            f"- schools: {', '.join(compact_my_profile['schools'])}",
            f"- experiences: {', '.join(compact_my_profile['experiences'])}",
            "- proof_points (use exactly one per variant):",
            *[f"  {line}" for line in proof_lines],
            f"- focus_areas: {', '.join(compact_my_profile['focus_areas'])}",
            f"- internship_goal: {compact_my_profile['internship_goal']}",
            "",
            "TARGET_PROFILE:",
            f"- name: {compact_target_profile['name']}",
            f"- headline: {compact_target_profile['headline']}",
            f"- location: {compact_target_profile['location']}",
            f"- about: {compact_target_profile['about']}",
            f"- top_experiences: {compact_target_profile['top_experiences']}",
            f"- education: {compact_target_profile['education']}",
            "",
            "HOOKS_RANKED:",
            *([f"- {line}" for line in hook_rank_lines] or ["- (none)"]),
            "",
            "DERIVED_HOOKS_RANKED:",
            *([f"- {line}" for line in derived_rank_lines] or ["- (none)"]),
            "",
            "ANCHOR_CANDIDATES (ranked):",
            *([f"- {line}" for line in anchor_lines] or ["- (none)"]),
            "",
            "ANCHOR_PLAN (use exactly as hook):",
            f"- short: {anchor_plan.get('short', {}).get('text', '')}",
            f"- direct: {anchor_plan.get('direct', {}).get('text', '')}",
            f"- warm: {anchor_plan.get('warm', {}).get('text', '')}",
            "",
            f"TARGET_TAGS: {', '.join(sorted(list(target_tags)))}",
            f"BANLIST: {', '.join(banlist)}",
            "",
            "RULES:",
            "- Output strict JSON only. No explanations.",
            "- 3 variants: short, direct, warm.",
            "- <= 300 characters each.",
            "- Each variant must include exactly ONE hook: use ANCHOR_PLAN for that variant.",
            "- Each variant must include exactly ONE proof point (aligned to hook theme).",
            "- End with a short CTA question.",
            "- If you think info is missing, still write the best possible notes and never mention missing info.",
            "",
            "CONTENT_PLAN:",
            "[Hook] + [Credibility] + [CTA]",
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

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": context_text}
    ]


def normalize_variants(raw: dict[str, Any]) -> list[Variant]:
    desired_labels = ["short", "direct", "warm"]
    variants = []
    items = raw.get("variants", [])
    for index, item in enumerate(items):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if len(text) > 300:
            text = text[:297].rstrip() + "..."
        label = (item.get("label") or "").strip()
        if label not in desired_labels:
            label = desired_labels[index] if index < len(desired_labels) else "variant"
        variants.append(Variant(label=label, text=text, char_count=len(text)))
    return variants


def parse_json_content(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    candidate = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", candidate, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def extract_response_text(data: dict[str, Any]) -> tuple[str, str]:
    output = data.get("output", [])
    texts: list[str] = []
    refusals: list[str] = []
    for item in output:
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                elif part.get("type") == "refusal":
                    refusals.append(part.get("refusal", ""))
        elif item.get("type") == "refusal":
            refusals.append(item.get("refusal", ""))
    return "\n".join([t for t in texts if t]).strip(), "\n".join([r for r in refusals if r]).strip()


@app.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    messages = build_prompt(payload)
    system_msg = ""
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_msg = msg.get("content", "")
        elif msg.get("role") == "user":
            user_msg = msg.get("content", "")

    input_items = []
    if user_msg:
        input_items.append({"role": "user", "content": user_msg})
    else:
        input_items = [
            {"role": msg.get("role"), "content": msg.get("content", "")}
            for msg in messages
            if msg.get("role") != "system"
        ]
        if not input_items:
            input_items = [{"role": "user", "content": ""}]

    async with httpx.AsyncClient(timeout=30) as client:
        request_body = {
            "model": MODEL_NAME,
            "input": input_items,
            "instructions": system_msg,
            "temperature": 0.6,
            "max_output_tokens": 350,
            "text": {"format": RESPONSE_SCHEMA},
        }
        resp = await client.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )

        if resp.status_code >= 400 and (
            "response_format" in resp.text or "json_schema" in resp.text
        ):
            request_body["text"] = {"format": {"type": "json_object"}}
            resp = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    content, refusal = extract_response_text(data)
    if refusal:
        raise HTTPException(status_code=502, detail=refusal)
    if not content:
        content = data.get("output_text", "")
    if not content:
        raise HTTPException(status_code=502, detail="Empty response from model")

    raw = parse_json_content(content)
    if raw is None:
        if os.getenv("OPENAI_DEBUG", os.getenv("GROQ_DEBUG", "0")) == "1":
            print("Model raw content:", content)
        raise HTTPException(status_code=502, detail="Model did not return JSON")

    variants = normalize_variants(raw)
    if not variants:
        raise HTTPException(status_code=502, detail="No variants returned")

    return GenerateResponse(variants=variants)
