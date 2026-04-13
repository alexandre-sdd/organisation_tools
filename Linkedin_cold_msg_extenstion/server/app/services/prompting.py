"""Facade module that re-exports the prompting API and constants.

Keep existing imports stable while logic lives in focused modules.
"""

from .planning.anchors import build_anchor_candidates, classify_anchor_type, select_anchor_plan
from .planning.bridge_plan import build_bridge_plan, build_intent, build_target_facts, select_required_token
from .planning.proof_points import (
    proof_point_strength_score,
    score_proof_point,
    select_proof_point_for_variant,
)
from .planning.target_analysis import (
    build_target_text,
    classify_target,
    derive_hooks,
    extract_company_from_fact,
    extract_headline_keyword,
    extract_role_keyword,
    is_domain_fact,
    score_hook,
)
from .render.prompt_render import build_prompt, build_prompt_context
from .utils.constants import (
    BASE_BANLIST,
    CTA_BY_VARIANT,
    DOMAIN_FACTS,
    FALLBACK_PROOF_POINTS,
    MAX_PROOF_POINTS,
    RESPONSE_SCHEMA,
    ROLE_KEYWORD_MIN_LEN,
)
from .utils.debug import build_debug_log
from .utils.text_utils import (
    compact_role_title,
    is_nyc,
    match_entity,
    normalize_key,
    tokenize,
    tokens_without_stopwords,
)
from .utils.validation import validate_variant_text

__all__ = [
    "BASE_BANLIST",
    "CTA_BY_VARIANT",
    "DOMAIN_FACTS",
    "FALLBACK_PROOF_POINTS",
    "MAX_PROOF_POINTS",
    "RESPONSE_SCHEMA",
    "ROLE_KEYWORD_MIN_LEN",
    "build_anchor_candidates",
    "select_anchor_plan",
    "classify_anchor_type",
    "build_bridge_plan",
    "build_intent",
    "build_target_facts",
    "select_required_token",
    "proof_point_strength_score",
    "score_proof_point",
    "select_proof_point_for_variant",
    "build_prompt",
    "build_prompt_context",
    "build_debug_log",
    "build_target_text",
    "classify_target",
    "derive_hooks",
    "extract_company_from_fact",
    "extract_headline_keyword",
    "extract_role_keyword",
    "is_domain_fact",
    "score_hook",
    "compact_role_title",
    "is_nyc",
    "match_entity",
    "normalize_key",
    "tokenize",
    "tokens_without_stopwords",
    "validate_variant_text",
]
