import json
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from xml.etree import ElementTree

DEFAULT_MODEL_NAME = "llama-3.3-70b-versatile"
MODEL_NAME = os.getenv("GROQ_MODEL", DEFAULT_MODEL_NAME)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

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

    compact_my_profile = {
        "headline": my_profile.get("headline", ""),
        "location": my_profile.get("location", ""),
        "schools": (my_profile.get("schools") or [])[:3],
        "experiences": (my_profile.get("experiences") or [])[:3],
        "proof_points": [p for p in (my_profile.get("proof_points") or []) if p][:6],
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
    proof_points = [p for p in (my_profile.get("proof_points") or []) if p]
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

    system = (
        "You write sharp, non-generic LinkedIn connection notes. "
        "Return strict XML only (no markdown, no prose). "
        "The output must start with <response> and end with </response>. "
        "Use CDATA for text fields. "
        "Do NOT fabricate details. Use only the provided my_profile, target_profile, hooks, and ranked lists. "
        "Write exactly 3 variants labeled short, direct, warm. "
        "Each variant must be <= 300 characters (hard limit). "
        "Each variant must contain exactly one hook, exactly one credibility proof point from my_profile.proof_points, "
        "and end with a soft CTA. "
        "Each message must include a clear rationale for reaching out and avoid generic praise."
    )

    user = {
        "my_profile": compact_my_profile,
        "target_profile": compact_target_profile,
        "hooks": hooks,
        "derived_hooks": derived,
        "hook_candidates_ranked": hook_scores_sorted,
        "derived_hook_scores": derived_scores,
        "target_tags": sorted(list(target_tags)),
        "proof_points_ranked": ranked_proof_points,
        "banlist": banlist,
        "instructions": {
            "hard_rules": [
                "Return strict XML matching the schema exactly",
                "Create exactly 3 variants: short, direct, warm",
                "Each variant must be <= 300 characters",
                "Do not invent any detail not present in target_profile or my_profile",
                "Each variant must use exactly 1 hook",
                "Each variant must use exactly 1 proof point from my_profile.proof_points",
                "End each variant with a soft CTA (e.g., 'Open to connect?')",
                "Avoid all banlist phrases"
            ],
            "content_plan": [
                "[Hook] + [Credibility] + [CTA]",
                "Hook must be specific to target_profile",
                "Credibility must align to the hook theme",
                "CTA must be a short question at the very end"
            ],
            "hook_selection_rules": [
                "Score hooks by specificity: overlap with target_profile fields + matching company/school + length",
                "Prefer highest-scoring hook; if hooks are weak, use derived_hooks",
                "Use different hooks across variants when 2+ good hooks exist",
                "If only one strong hook exists, reuse it with different phrasing"
            ],
            "credibility_alignment_rules": [
                "If hook is analytics/data: use Chanel pipelines or Sigma dashboards proof point",
                "If hook is computer vision: use Forvia YOLO/OpenCV proof point",
                "If hook is community/product: use Columbia PMC outreach proof point",
                "If hook is internship/NYC: use the NYC Summer 2026 proof point",
                "Otherwise choose the highest-ranked proof point"
            ],
            "style_guidance": {
                "short": "1 sentence max, very dense, no filler",
                "direct": "2 sentences max, professional, explicit reason for reaching out",
                "warm": "2 short sentences, friendly but still specific"
            },
            "output_xml_schema": (
                "<response>"
                "<variant><label>short</label><text><![CDATA[...]]></text></variant>"
                "<variant><label>direct</label><text><![CDATA[...]]></text></variant>"
                "<variant><label>warm</label><text><![CDATA[...]]></text></variant>"
                "</response>"
            )
        }
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user)}
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


def extract_xml_block(content: str) -> str | None:
    fence = re.search(r"```(?:xml)?\s*([\s\S]*?)```", content, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
        if "<response" in candidate.lower():
            return candidate

    match = re.search(r"<response[\s\S]*?</response>", content, re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def sanitize_xml(xml_text: str) -> str:
    return re.sub(
        r"&(?![a-zA-Z]+;|#\d+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        xml_text,
    )


def parse_xml_content(content: str) -> dict[str, Any] | None:
    block = extract_xml_block(content)
    if not block:
        return None
    variants: list[dict[str, str]] = []

    def strip_cdata(value: str) -> str:
        return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", value, flags=re.DOTALL).strip()

    try:
        root = ElementTree.fromstring(sanitize_xml(block))
        for variant_el in root.findall(".//variant"):
            label = (variant_el.findtext("label") or "").strip()
            text = strip_cdata(variant_el.findtext("text") or "")
            variants.append({"label": label, "text": text})
        if variants:
            return {"variants": variants}
    except ElementTree.ParseError as exc:
        if os.getenv("GROQ_DEBUG", "0") == "1":
            print("XML parse error:", exc)

    # Regex fallback for slightly malformed XML.
    for variant_match in re.finditer(
        r"<variant[^>]*>([\s\S]*?)</variant>", block, re.IGNORECASE
    ):
        chunk = variant_match.group(1)
        label_match = re.search(r"<label[^>]*>([\s\S]*?)</label>", chunk, re.IGNORECASE)
        text_match = re.search(r"<text[^>]*>([\s\S]*?)</text>", chunk, re.IGNORECASE)
        label = strip_cdata(label_match.group(1)) if label_match else ""
        text = strip_cdata(text_match.group(1)) if text_match else ""
        variants.append({"label": label, "text": text})

    if variants:
        return {"variants": variants}

    # Last resort: extract label/text pairs in order.
    labels = re.findall(r"<label[^>]*>([\s\S]*?)</label>", block, re.IGNORECASE)
    texts = re.findall(r"<text[^>]*>([\s\S]*?)</text>", block, re.IGNORECASE)
    for idx in range(min(len(labels), len(texts))):
        variants.append(
            {
                "label": strip_cdata(labels[idx]),
                "text": strip_cdata(texts[idx]),
            }
        )

    return {"variants": variants} if variants else None


@app.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set")

    messages = build_prompt(payload)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 350
            },
        )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise HTTPException(status_code=502, detail="Empty response from model")

    raw = parse_xml_content(content)
    if raw is None:
        if os.getenv("GROQ_DEBUG", "0") == "1":
            print("Model raw content:", content)
        raise HTTPException(status_code=502, detail="Model did not return XML")

    variants = normalize_variants(raw)
    if not variants:
        raise HTTPException(status_code=502, detail="No variants returned")

    return GenerateResponse(variants=variants)
