from pathlib import Path
import ast, datetime as dt, json, re

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT/"data/policy.json").read_text())
script = (ROOT/"scripts/update_policy.py").read_text()

def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise AssertionError(name)

banks = data["banks"]
ok("seven banks", len(banks) == 7)
ok("unique ids", len({b["id"] for b in banks}) == 7)
ok("official source status", all(b["status"] == "official" for b in banks))
ok("https links", all(b["sourceUrl"].startswith("https://") and b["scheduleUrl"].startswith("https://") for b in banks))
ok("future next meetings", all(dt.date.fromisoformat(b["nextMeeting"]) > dt.date(2026,8,28) for b in banks))
ok("current verified BoJ seed", next(b for b in banks if b["id"]=="BOJ")["displayRate"] == "~1.00%")
ok("current verified BoC next date", next(b for b in banks if b["id"]=="BOC")["nextMeeting"] == "2026-09-02")
ok("SNB uses discovery hub", next(b for b in banks if b["id"]=="SNB")["sourceUrl"].endswith("/monetary-policy/decisions"))
ok("SNB uses live event schedule", "event-schedule" in next(b for b in banks if b["id"]=="SNB")["scheduleUrl"])
ok("BoC no fixed decision URL seed", "key-interest-rate" in next(b for b in banks if b["id"]=="BOC")["sourceUrl"])
ok("BoJ uses annual decision index", "state_2026/index" in next(b for b in banks if b["id"]=="BOJ")["sourceUrl"])
ok("RBA uses coming-up schedule", "coming-up" in next(b for b in banks if b["id"]=="RBA")["scheduleUrl"])

# Architectural assertions
for fn in ["fed","ecb","boe","boj","snb","boc","rba"]:
    ok(f"{fn} updater exists", f"def {fn}(" in script)
ok("dynamic current year", "current_year_url" in script)
ok("SNB decision discovery", "parse_snb_decisions" in script)
ok("BoC schedule discovery", "parse_boc_schedule" in script)
ok("BoJ schedule parser", "parse_boj_meetings" in script)
ok("last-known-good fallback", "Restore last-known-good financial data" in script)
ok("lastChecked semantics", 'data["meta"]["lastChecked"]' in script)
ok("successful-vintage semantics", 'lastSuccessfulDataUpdate' in script)
ok("reject stale nextMeeting", 'nextMeeting is not in the future' in script)
ok("no third-party providers", not any(x in script.lower() for x in ["bloomberg","tradingeconomics","investing.com","reuters"]))

# Syntax validation
ast.parse(script)
ok("updater syntax", True)

# Frontend locale/copyright retained
index = (ROOT/"index.html").read_text()
widget = (ROOT/"widget.html").read_text()
ok("index explicit English locale", 'toLocaleDateString("en-GB"' in index)
ok("widget explicit English locale", 'toLocaleDateString("en-GB"' in widget)
ok("copyright retained", "BondStats Ltd. All rights reserved." in index)

print("ALL TESTS PASSED")
