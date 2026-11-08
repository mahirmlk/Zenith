# AI Evaluation Status (`update.md` §10)

## Current deterministic smoke suite

`evals/runners/run_evals.py` uses the production `hybrid_rank` and extractive claim selector on a fixed local corpus. It checks abstention against expected cases, citation IDs against the retrieved set and expected allowed sources, and has a fabricated-ID negative control.

Run it with:

```bash
python evals/runners/run_evals.py
```

This is a real code-path smoke test. It does not call external providers or a deployed API, and the current two-case fixture is too small to establish retrieval quality, claim support across varied writing, contradictions, prompt-injection resistance, or calibrated confidence. Do not treat 3/3 passing checks as a complete research-quality baseline.

## Required before a release gate

- Grow a versioned corpus and cases covering retrieval recall, false support, contradictions, adversarial content, and project/tenant scope.
- Compare claim-level citations with source spans and measure abstention precision/recall.
- Record a repeatable baseline before setting thresholds; retain metrics as CI artifacts.
- Add a deployed staging smoke test separately from the hermetic CI suite.

See [STATUS.md](STATUS.md) for remaining release blockers and current local validation.
