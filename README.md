# BondStats Central Bank Watch

Official-source monetary-policy dashboard for BondStats.

Coverage: Federal Reserve, ECB, Bank of England, Bank of Japan, Swiss National Bank, Bank of Canada and Reserve Bank of Australia.

Data integrity:
- official central-bank sources only
- no consensus forecasts
- no third-party editorial feeds, copied logos or copied UI
- last-known-good protection: failed parsers retain the previous valid record
- automatic refresh every 6 hours through GitHub Actions
- direct official decision and schedule links in the interface

Deploy: publish from main/root with GitHub Pages, enable Actions read/write, manually run `Update Central Bank Watch` once, then check `/health.html`.

© 2026 BondStats Ltd. All rights reserved.
