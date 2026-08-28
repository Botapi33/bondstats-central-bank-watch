from pathlib import Path
import json,datetime as dt
ROOT=Path(__file__).resolve().parents[1];d=json.loads((ROOT/"data/policy.json").read_text())
def ok(n,c):
 print(("PASS " if c else "FAIL ")+n)
 if not c:raise AssertionError(n)
bs=d["banks"];ok("schema",len(bs)>=7);ok("unique ids",len({b["id"] for b in bs})==len(bs));ok("official only",all(b["status"]=="official" for b in bs));ok("https sources",all(b["sourceUrl"].startswith("https://") for b in bs));ok("display rates",all("%" in b["displayRate"] for b in bs));ok("single rates",all(-2<=b.get("rate",0)<=25 for b in bs if b["rateType"]=="single"));ok("ranges",all(0<=b["rateLow"]<=b["rateHigh"]<=25 for b in bs if b["rateType"]=="range"));ok("decision dates",all(dt.date.fromisoformat(b["decisionDate"]) for b in bs));ok("future meetings",all(dt.date.fromisoformat(b["nextMeeting"])>=dt.date(2026,8,28) for b in bs));h=(ROOT/"index.html").read_text();ok("english locale",'toLocaleDateString("en-GB"' in h);ok("copyright","© 2026 BondStats Ltd." in h);print("ALL TESTS PASSED")
