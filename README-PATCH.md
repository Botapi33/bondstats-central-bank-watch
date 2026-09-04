# BondStats Central Bank Watch — Test Hotfix

This patch fixes the recurring GitHub Actions failure caused by a hard-coded
Bank of Canada meeting date in `tests/test_policy.py`.

## What changes

It removes this obsolete assertion:

    ok("current verified BoC next date", next(b for b in banks if b["id"]=="BOC")["nextMeeting"] == "2026-09-02")

The test suite already contains the broader `future next meetings` validation,
so the hard-coded BoC date is redundant and causes the workflow to fail as soon
as the meeting date passes or the updater advances to the next meeting.

No updater, source parser, generated feed, website UI, or central-bank data is changed.

## Apply

From the repository root:

    git apply patches/fix-central-bank-watch-tests.patch

Then commit and push.

If you edit in the GitHub web UI instead, simply delete the obsolete BoC assertion
from `tests/test_policy.py`, commit the change, and rerun the `update` workflow.
