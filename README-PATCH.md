# BondStats Central Bank Watch — Robust Test Patch

This patch replaces only:

`tests/test_policy.py`

It fixes the recurring GitHub Actions failures caused by brittle, hard-coded
assertions such as:

- a specific Bank of Canada meeting date
- a specific Swiss National Bank URL path

The new validator checks the generated feed structurally and plausibly instead:

- exactly the expected seven central banks
- unique bank IDs
- HTTPS source URLs
- non-empty source-status values when that field exists
- next-meeting dates are valid and not in the past
- no specific meeting date is hard-coded
- no exact central-bank webpage path is hard-coded

It also discovers the generated JSON feed by content, so it does not depend on a
single fragile JSON file path.

## Install

Overlay this ZIP on the repository root so that the file ends up exactly at:

`tests/test_policy.py`

Commit and push, then rerun the existing `update` GitHub Action.

The workflow already calls `python tests/test_policy.py`, so no workflow change
is required.

## Scope

No updater/parser, data source, website UI, generated JSON schema, or GitHub
workflow is modified by this patch.
