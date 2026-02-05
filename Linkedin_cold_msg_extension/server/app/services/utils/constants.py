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

BASE_BANLIST = [
    "hope you are well",
    "impressive",
    "pick your brain",
    "leverage",
    "synergy",
    "reach out",
    "would love to learn more",
    "amazing",
    "incredible",
    "admire",
    "inspiring",
]

CTA_BY_VARIANT = {
    "short": "Open to connect?",
    "direct": "Open to a quick chat?",
    "warm": "Worth connecting?",
}

DOMAIN_FACTS = [
    ("cv", "computer vision"),
    ("analytics", "analytics"),
    ("product", "product"),
    ("finance", "finance"),
    ("community", "community"),
]

ROLE_KEYWORD_MIN_LEN = 4
MAX_PROOF_POINTS = 6
