# Plan 003: Fix summary agent greedy JSON regex

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d21a134..HEAD -- backend/agents/summary_agent.py`
> If the file has changed, compare the "Current state" excerpts against the
> live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

The `_extract_json` function in `summary_agent.py` uses greedy regex patterns (`\{.*\}` and `\{.*\}` with `re.DOTALL`). If the LLM emits multiple JSON objects or markdown blocks, the greedy `.*` matches from the first `{` to the last `}`, producing invalid JSON and causing a parse failure. This silently degrades summaries to truncated abstracts.

## Current state

File: `backend/agents/summary_agent.py:25-47`

```python
def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences and partial responses."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found in response")
```

Lines 33 and 40 use greedy `.*` which matches across multiple JSON blocks.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Backend lint | `cd backend && ruff check agents/summary_agent.py` | exit 0 |
| Backend type check | `cd backend && mypy agents/summary_agent.py` | exit 0 (or pre-existing errors only) |
| Backend tests | `cd backend && pytest tests/test_agents.py -v` | all pass |

## Scope

**In scope**:
- `backend/agents/summary_agent.py` — change two regex patterns

**Out of scope**:
- Changes to the prompt file (`agents/prompts/summary_prompt.txt`)
- Changes to how the LLM is called

## Git workflow

- Branch: `advisor/003-fix-regex-greedy`
- Commit message: `fix(agents): use non-greedy regex for JSON extraction`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Change greedy patterns to non-greedy

In `backend/agents/summary_agent.py`, make two changes:

**Line 33** — change:
```python
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
```
to:
```python
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
```

**Line 40** — change:
```python
    match = re.search(r"(\{.*\})", text, re.DOTALL)
```
to:
```python
    match = re.search(r"(\{.*?\})", text, re.DOTALL)
```

The only change in each line is `\{.*\}` → `\{.*?\}` (adding `?` after `*`).

**Verify**: `grep -n "\\\\{.*\\\\}" backend/agents/summary_agent.py` — should show `.*?` not `.*`

### Step 2: Run lint and tests

```bash
cd backend && ruff check agents/summary_agent.py
cd backend && pytest tests/test_agents.py -v
```

**Verify**: exit 0, all tests pass

## Test plan

The existing tests in `test_agents.py` already test `_extract_json` with direct JSON, markdown fences, and nested JSON. These tests should continue to pass.

Optionally, add a test for the multi-block case:
```python
def test_extract_json_multiple_blocks():
    text = '```json\n{"tldr": "first", "difficulty": "introductory"}\n```\nSome text\n```json\n{"tldr": "second", "difficulty": "expert"}\n```'
    result = _extract_json(text)
    assert result["tldr"] == "first"  # Should grab the first block, not the last
```

## Done criteria

- [ ] `grep -n ".*?" backend/agents/summary_agent.py` shows non-greedy patterns
- [ ] `cd backend && ruff check agents/summary_agent.py` exits 0
- [ ] `cd backend && pytest tests/test_agents.py -v` passes
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- If the test suite fails after the change
- You discover the regex is used elsewhere in the codebase (it's not — `_extract_json` is local to this file)

## Maintenance notes

- The non-greedy `.*?` matches the smallest possible string between `{` and `}`. For well-formed LLM output (one JSON block), the behavior is identical. For malformed output (multiple blocks), it now correctly extracts the first complete JSON object.
- If the LLM ever needs to return multiple JSON objects, this function would need a different approach (e.g., `json.JSONDecoder.raw_decode` in a loop).
