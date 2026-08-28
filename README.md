# BondStats Central Bank Watch — Production V3

**Financial policy monitoring from official central-bank sources only.**

This build fixes the remaining automation weaknesses from V2. It is designed to be deployed once and then refreshed by GitHub Actions every six hours.

## What V3 fixes

- **SNB:** no fixed latest-decision URL. The updater discovers the newest monetary-policy assessment from the SNB monetary-policy decisions hub and independently discovers the next assessment from the SNB event schedule.
- **Bank of Canada:** no dependency on the previous press release for the next meeting. The updater reads the official fixed-announcement schedule from the Bank's key-interest-rate page, determines the latest past decision and next future decision, and optionally resolves the matching official FAD release.
- **Bank of Japan:** current policy rate comes from the BoJ's official current guideline, while the latest decision date/source comes from the current-year policy-decision index and the next meeting is discovered from the official MPM schedule. PDF-only releases do not force the updater to guess.
- **RBA / ECB:** current-year source indexes are generated dynamically instead of hard-coding 2026 into the update architecture.
- **Freshness semantics:** `lastChecked` is separate from `lastSuccessfulDataUpdate`. A failed parser no longer makes stale financial data appear freshly updated.
- **Fail closed:** a failed parser preserves the last-known-good observation and marks that source `degraded`.
- **Future-date guard:** a parsed `nextMeeting` must actually be later than the run date.

## Coverage

Federal Reserve · ECB · Bank of England · Bank of Japan · Swiss National Bank · Bank of Canada · Reserve Bank of Australia

## Deployment

1. Upload the contents of this package to `bondstats-central-bank-watch`.
2. In GitHub, enable **Actions → Read and write permissions**.
3. Publish GitHub Pages from `main` / repository root.
4. Run **Update Central Bank Watch** manually once.
5. Open `/health.html`.
6. Confirm all seven sources show `OK`.
7. Publish `/index.html`; use `/widget.html` only where a compact embed is needed.

## Operational safety

Central-bank websites can change markup without notice. No scraper can truthfully be guaranteed never to break. This build therefore treats parser failure as an observable health event rather than silently publishing a guessed value. That is the intended production behavior.

© 2026 BondStats Ltd. All rights reserved.
