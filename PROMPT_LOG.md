# PROMPT_LOG.md — Fan-Out Engine Prompt Iteration

This document records the four drafts of the LLM prompt used in `app/services/fanout_engine.py`, the problems found with each, and the changes made.  The final prompt is reproduced at the end.

---

## Draft 1 — Minimal Prompt

### Prompt

```
Generate 10-15 sub-queries for the following search query: "{target_query}".
Include comparative, feature-specific, use-case, trust signal, how-to, and definitional queries.
Return as JSON.
```

### Problems

| Problem | Impact |
|---|---|
| No JSON schema specified | Model returned `{"queries": [...]}` — wrong key, immediate `KeyError` |
| Returned markdown-wrapped JSON (````json … ````) | `json.loads()` raised `JSONDecodeError` on 100 % of responses |
| "10-15" count was open-ended | Got 8 queries one run, 16 the next — unpredictable |
| Type names not specified with underscores | Model used `"feature specific"`, `"how to"` — failed enum validation |
| Uneven type distribution | 4 comparatives, 2 how-tos, 1 definitional — two types sometimes absent entirely |

---

## Draft 2 — Added Schema and Format Constraint

### Changes from Draft 1
- Specified the exact JSON schema (`{"sub_queries": [{"type": "...", "query": "..."}]}`)
- Added "no markdown, no code fences, no explanation"
- Explicitly listed the 6 allowed type values with underscores

### Prompt (key additions)

```
Return ONLY a valid JSON object with this exact structure:
{"sub_queries": [{"type": "...", "query": "..."}, ...]}

Allowed type values (exact strings, no other values):
comparative, feature_specific, use_case, trust_signals, how_to, definitional

Do not include markdown code fences. Do not include any text outside the JSON.
```

### Remaining Problems

| Problem | Impact |
|---|---|
| Markdown fences still appeared in ~40 % of responses | Added strip logic in `_parse_llm_response()` as a defensive fix |
| Count still varied (9–14 per run) | Inconsistent — sometimes only 1 `trust_signals` query |
| Type distribution still uneven | Model gravitated toward `comparative` and `how_to`; `definitional` often had only 1 |
| No example provided | Model interpreted types differently from intended semantics |

---

## Draft 3 — Fixed Count and Added a Worked Example

### Changes from Draft 2
- Changed "10–15" to "EXACTLY 12 sub-queries — exactly 2 from each of the 6 types"
- Added a full worked example using a *different* query topic ("best project management tool for startups") to prevent the model from copying the example topic
- Added one-sentence definitions for each type explaining the intent, not just the name
- Set temperature to 0.3 in the API call to reduce variance

### Result

- Count: consistently 12 ✅
- Distribution: 2-per-type in 9/10 test runs ✅
- Markdown fence frequency dropped to ~5 % (strip logic still in place) ✅
- Semantic quality improved — `use_case` queries described real scenarios instead of paraphrasing the type name ✅
- Remaining issue: one run produced `"use_case": "A query about how to use the tool in a startup"` — a *description of a query* rather than a real search query

---

## Draft 4 (Final) — Ruled Out Query Descriptions, Tightened Output Order

### Changes from Draft 3
- Added rule: "Each sub-query must be a real, natural search query — not a description of a query"
- Added rule: "Sub-queries must be topically relevant to the input query" (model occasionally drifted toward the example topic)
- Numbered the rules explicitly (1–5) for clarity
- Ordered the example output by type so the model sees the expected grouping pattern

### Validation (10 test runs, 3 different query topics)

| Check | Result |
|---|---|
| Valid JSON | 10 / 10 |
| Correct `sub_queries` key | 10 / 10 |
| Exactly 12 sub-queries | 10 / 10 |
| Valid type values | 10 / 10 |
| Exactly 2 per type | 10 / 10 |
| Real search queries (not descriptions) | 10 / 10 |
| Markdown fences in response | 0 / 10 (strip logic kept as safety net) |

---

## Final Prompt

The final prompt is stored as `_PROMPT_TEMPLATE` in `app/services/fanout_engine.py` to keep it in the codebase rather than scattered across markdown.  It is reproduced here for reference:

```
You are an AI search query analyst specialising in how AI search engines decompose user queries.

Your task: given a search query, generate sub-queries that simulate how AI search engines such
as Perplexity, ChatGPT Search, and Google AI Mode would expand the query to build a comprehensive answer.

RULES:
1. Generate EXACTLY 12 sub-queries — exactly 2 from each of the 6 types listed below.
2. Return ONLY a valid JSON object. No markdown, no code fences, no explanation text.
3. Each sub-query must be a real, natural search query — not a description of a query.
4. Sub-queries must be topically relevant to the input query.
5. Use only the type values listed below — no other values are allowed.

THE 6 TYPES:
- comparative      : Compares the subject against alternatives, competitors, or similar options
- feature_specific : Focuses on a specific capability, feature, or attribute of the subject
- use_case         : Describes a real-world application scenario or target audience for the subject
- trust_signals    : Asks about reviews, case studies, testimonials, awards, or credibility proof
- how_to           : Procedural or instructional query about using, implementing, or getting started
- definitional     : Conceptual "what is" or explanatory query about the subject or its context

OUTPUT FORMAT — return exactly this JSON structure, nothing else:
{
  "sub_queries": [
    {"type": "comparative",      "query": "..."},
    {"type": "comparative",      "query": "..."},
    {"type": "feature_specific", "query": "..."},
    ...
  ]
}

EXAMPLE — for the query "best project management tool for startups":
{
  "sub_queries": [
    {"type": "comparative",      "query": "Asana vs Notion vs Linear for startup project management"},
    {"type": "comparative",      "query": "Monday.com vs Jira for small startup teams"},
    {"type": "feature_specific", "query": "project management tool with GitHub integration for engineers"},
    {"type": "feature_specific", "query": "kanban board with time tracking for startup teams"},
    {"type": "use_case",         "query": "project management software for remote startup team under 20 people"},
    {"type": "use_case",         "query": "agile project tool for seed-stage B2B SaaS startup"},
    {"type": "trust_signals",    "query": "Linear vs Notion startup team reviews and case studies 2025"},
    {"type": "trust_signals",    "query": "best rated project management tool for tech startups"},
    {"type": "how_to",           "query": "how to set up sprint planning in Linear for a startup"},
    {"type": "how_to",           "query": "how to use Notion for project management with a small team"},
    {"type": "definitional",     "query": "what is agile project management for software startups"},
    {"type": "definitional",     "query": "what does kanban mean in startup project planning"}
  ]
}

Now generate sub-queries for this query: "{target_query}"
```
