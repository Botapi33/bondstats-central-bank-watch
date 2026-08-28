#!/usr/bin/env python3
from pathlib import Path
import json,re,urllib.request,datetime as dt
ROOT=Path(__file__).resolve().parents[1]; PATH=ROOT/"data/policy.json"
UA={"User-Agent":"BondStats CentralBankWatch/1.0 (+https://www.bondstats.org/)"}
def fetch(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode("utf-8","ignore")
def frac(v):
    if "/" not in v:return float(v)
    if "-" in v:
        whole,fr=v.split("-",1);a,b=fr.split("/");return float(whole)+float(a)/float(b)
    a,b=v.split("/");return float(a)/float(b)
def num(s):return float(s.replace("¼",".25").replace("½",".5").replace("¾",".75"))
P={
"FED":(r'target range for the federal funds rate at\s+([0-9-]+/[0-9]+|[0-9.]+)\s+to\s+([0-9-]+/[0-9]+|[0-9.]+)\s+percent',"range"),
"ECB":(r'deposit facility.*?remain unchanged at\s*([0-9.]+)%',"single"),
"BOE":(r'Current Bank Rate\s*([0-9.]+)%',"single"),
"BOJ":(r'uncollateralized overnight call rate.*?around\s+([0-9.]+)\s+percent',"single"),
"SNB":(r'(?:SNB policy rate|policy rate).*?([0-9.]+)%',"single"),
"BOC":(r'(?:target for the overnight rate at|policy rate at)\s*([0-9¼½¾.]+)%',"single"),
"RBA":(r'cash rate target.*?(?:unchanged at|to)\s*([0-9.]+)\s*per\s*cent',"single")}
d=json.loads(PATH.read_text()); results={}
for b in d["banks"]:
    try:
        html=re.sub(r"<[^>]+>"," ",fetch(b["sourceUrl"]));html=re.sub(r"\s+"," ",html)
        pat,typ=P[b["id"]];m=re.search(pat,html,re.I|re.S)
        if not m:raise ValueError("expected rate pattern not found")
        if typ=="range":
            lo,hi=frac(m.group(1)),frac(m.group(2))
            if not(0<=lo<=hi<=25):raise ValueError("implausible range")
            b["rateLow"],b["rateHigh"]=lo,hi;b["displayRate"]=f"{lo:.2f}–{hi:.2f}%"
        else:
            x=num(m.group(1))
            if not(-2<=x<=25):raise ValueError("implausible rate")
            b["rate"]=x;b["displayRate"]=("~" if b["id"]=="BOJ" else "")+f"{x:.2f}%"
        results[b["id"]]="ok"
    except Exception as e:results[b["id"]]="retained: "+str(e)[:120]
d["meta"]["lastUpdated"]=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
d["meta"]["refreshResults"]=results;PATH.write_text(json.dumps(d,indent=2)+"\n");print(json.dumps(results,indent=2))
