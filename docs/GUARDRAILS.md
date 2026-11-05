# Guardrails (update.md §6)

Enforcement is trusted Python, not prompts: `backend/security/` (authorization, policies, prompt_injection, output_validation, audit) + `backend/guardrails/` (pipeline, action_approval).

Checkpoints: (1) before retrieval — auth + project membership + quotas; (2) imported data treated as untrusted (`<untrusted_content>` annotation + injection scan); (3) before each tool call — `check_tool_call` denies unknown/forbidden tools by default and requires backend-recorded approval for high-risk actions; (4) before model context — inaccessible private content excluded; (5) after output — fabricated citation IDs rejected (`check_output`); (6) before external writes — fresh approval token recorded in `action_approval.py`.

Adversarial tests: `backend/tests/test_security.py` (SSRF, JWT, registry, fabricated citations via evals).
