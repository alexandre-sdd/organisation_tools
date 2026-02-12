# Bridge-Plan Prompting + Trace Logging (New Logic)

This document explains the **new deterministic “bridge plan” prompting logic** and the **always-on traces** written to NDJSON logs.

It does **not** replace `Linkedin_cold_msg_extension/server/LOGIC.md`; it complements it.

## What Changed (Conceptually)

The system used to ask the model to “write good notes” with ranked hints.

Now the backend builds a deterministic plan per variant (`short`, `direct`, `warm`) and then forces the model to:

- include specific strings verbatim (`TARGET_FACT`, `HOOK_TEXT`, `PROOF_POINT`, `CTA`, optional `REQUIRED_TOKEN`)
- include a fixed “bridge” sentence that contains both `TARGET_FACT` and `PROOF_POINT`
- keep everything under a hard 300-character limit

This is meant to reduce generic outputs by removing model degrees of freedom.

## Where The Logic Lives

- Prompt + planning: `Linkedin_cold_msg_extension/server/app/services/prompting.py`
- Endpoint route: `Linkedin_cold_msg_extension/server/app/api/routes/generate.py`
- Orchestration + logging: `Linkedin_cold_msg_extension/server/app/services/generation_service.py`
- NDJSON append helper: `Linkedin_cold_msg_extension/server/app/logging_utils.py`

## Bridge Plan: Deterministic Planning

The planner computes:

- `target_facts`: ranked target facts extracted from `target_profile`
- `anchor_candidates` and `anchor_plan`: one chosen anchor per variant (existing concept)
- `bridge_plan`: the enforced per-variant plan

### Target Facts (`build_target_facts`)

Each fact is a dict:

```json
{"type":"role_company|company|school|domain|headline|location","text":"...","score":12}
```

Key rules:

- role+company from `top_experiences[0]` is the top signal
- company and school facts are also included
- domain facts are derived **only from headline/about** (not from experiences)
- facts are deduplicated by `normalize_key(text)`

### Anchor Types (`classify_anchor_type`)

Anchor types are normalized to:

`school`, `company`, `role`, `location`, `domain`, `hook`, `derived`, `other`

This standardization makes the later deterministic mapping predictable.

### Proof Point Selection (Deterministic + Non-Weak)

`select_proof_point_for_variant(...)` chooses one proof point verbatim from `my_profile.proof_points[:6]`.

Important behavior:

- it tries to match by tags (cv/community/product/finance/analytics)
- it uses `proof_point_strength_score()` to avoid weak “goal/filler” lines like:
  - “Targeting Summer 2026…”
  - “Core stack…”
- among candidates, it prefers higher strength, then shorter length to fit 300 chars

### Required Token (Specificity Token)

The plan may include an optional `required_token` to force a second target-specific token in the final message.

Current selection order:

1. `top_experiences[0].company` (preferred)
2. `education[0].school` **only if it matches your schools** (shared-signal only)
3. a keyword extracted from `target_profile.headline`

If `required_token` would duplicate the `target_fact`, we try to substitute a role keyword from the target’s title.

### Bridge Plan (`build_bridge_plan`)

For each variant (`short`, `direct`, `warm`) we build:

```json
{
  "target_fact":"...",
  "hook_text":"...",
  "proof_point":"...",
  "intent":"...",
  "cta":"...",
  "required_token":"..." // optional
}
```

Key rules:

- `cta` is fixed per variant:
  - short: `Open to connect?`
  - direct: `Open to a quick chat?`
  - warm: `Worth connecting?`
- `hook_text` comes from `anchor_plan[variant].text` unless the anchor is too generic:
  - if anchor type is `domain` or `location` and score < 7, `hook_text` becomes the variant’s `target_fact`

## Prompt Forcing: What The Model Must Do

The system prompt tells the model:

- output strict JSON only (matches `RESPONSE_SCHEMA`)
- each variant must include required strings verbatim
- each variant must include an explicit bridge sentence:
  - `Seeing {TARGET_FACT}, {PROOF_POINT}.`
- end with the CTA verbatim
- avoid banlist phrases
- keep everything minimal (do not add extra background beyond the `PROOF_POINT`)

In the user message we include:

- `TARGET_NAME`
- `TARGET_FACTS_RANKED` (top 5)
- `BRIDGE_PLAN (MUST FOLLOW EXACTLY)` with the verbatim strings
- `BANLIST`
- a recommended short template

## Validation + Retry

`validate_variant_text(text, plan, banlist)` checks:

- length <= 300
- includes `target_fact`, `hook_text`, `proof_point`, `cta` (and `required_token` if present)
- does not contain banlist phrases (case-insensitive)

The generation service now retries once with a lower temperature when violations are present, then returns the best final attempt and logs all validation results.

## Traces: What Gets Logged (Always-On)

Each `/generate` call appends a record to:

`Linkedin_cold_msg_extension/logs/requests.ndjson`

Each line includes:

- `request_id`, timestamp, model name
- `debug` object:
  - compact profiles used for planning
  - `target_facts`, `anchor_candidates` (top 10), `anchor_plan`
  - full `bridge_plan`
- `messages`: the exact system/user prompt sent to the model
- `model_output_preview`
- the returned `variants`
- `validations` (per variant)
- error info if anything fails

This is designed so you can answer: “what did the system see?” and “what did it enforce?”

## Modularization Opportunities (Next Refactor)

`prompting.py` has become a “god file” again. A clean split that matches the logic would be:

- `services/planning.py`
  - target facts, bridge plan, required token, intent selection
- `services/anchors.py`
  - anchor building + plan selection + anchor type classification
- `services/proof_points.py`
  - proof point scoring + deterministic selection
- `services/prompt_render.py`
  - system/user prompt assembly
- `services/validation.py`
  - `validate_variant_text`

We can do this later without changing external interfaces by keeping:

- `RESPONSE_SCHEMA`
- `build_prompt(payload)` returning the same messages
- `build_prompt_context(...)` as the single entrypoint used by `app/main.py`
