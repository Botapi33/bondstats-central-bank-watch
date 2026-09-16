# Central Bank Watch GitHub Actions fix

Root-overlay patch.

Fixes:
- The validator no longer fails merely because a bank intentionally retained a just-expired last-known-good meeting while `refreshState` is `degraded`.
- Healthy bank records still MUST have a non-past `nextMeeting`.
- Updates GitHub Actions to `actions/checkout@v5` and `actions/setup-python@v6` (Node 24 generation).

No updater, policy rates, parser logic, frontend, or JSON data is modified.
