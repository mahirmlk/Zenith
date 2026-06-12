# Plan 004: Add frontend tests to CI and fix CI pipeline

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d21a134..HEAD -- .github/`
> If the CI file has changed, compare the "Current state" excerpts against the
> live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `d21a134`, 2026-06-12

## Why this matters

The frontend CI job in `.github/workflows/ci.yml` runs `npm run lint`, `npm run typecheck`, and `npm run build`, but **not** `npm run test`. The 16 existing frontend tests (hooks, components, PaperCard) are never executed in CI. A breaking change in a shared component or hook will pass CI and reach production.

## Current state

File: `.github/workflows/ci.yml:30-48`

```yaml
  frontend:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: ['20']
    defaults:
      run:
        working-directory: ./frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
          cache-dependency-path: './frontend/package-lock.json'
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run build
```

`npm run test` is missing between `typecheck` and `build`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Frontend tests locally | `cd frontend && npm test` | all 16 tests pass |
| Verify CI syntax | Check YAML is valid | no syntax errors |

## Scope

**In scope**:
- `.github/workflows/ci.yml` — add `npm run test` step

**Out of scope**:
- Adding new frontend tests
- Changes to `package.json` scripts
- Changes to the backend CI job

## Git workflow

- Branch: `advisor/004-add-frontend-ci-tests`
- Commit message: `ci(frontend): add npm run test to CI pipeline`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `npm run test` to the frontend CI job

In `.github/workflows/ci.yml`, in the `frontend` job's `steps` list, add a new step after `npm run typecheck` and before `npm run build`:

```yaml
      - run: npm run test
```

The complete steps block becomes:
```yaml
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
          cache-dependency-path: './frontend/package-lock.json'
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - run: npm run build
```

**Verify**: `grep -n "npm run test" .github/workflows/ci.yml` — should show the new step

### Step 2: Verify tests pass locally

```bash
cd frontend && npm test
```

**Verify**: all 16 tests pass, exit 0

## Test plan

- No new tests required — this is a CI configuration change only.
- The existing 16 frontend tests serve as the verification.

## Done criteria

- [ ] `grep -n "npm run test" .github/workflows/ci.yml` returns a match
- [ ] `cd frontend && npm test` passes (all 16 tests)
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- If `npm run test` fails locally (investigate and fix the test, or revert the CI change)
- The YAML becomes invalid after editing

## Maintenance notes

- Future frontend test additions will now be caught by CI automatically.
- Consider adding coverage thresholds (`vitest --coverage`) in a follow-up plan.
