# CI-Sense
Evidence-Grounded LLMs for Flaky Test Detection and Diagnosis

Flaky test outcomes can change across runs even when source code is unchanged, so relying on test code alone often misses whether a specific CI failure is truly flaky.

CI-Sense addresses this by grounding LLM-based flaky-test classification and diagnosis in CI execution evidence (for example, historical reruns, logs, and failure patterns) alongside test-code signals.
