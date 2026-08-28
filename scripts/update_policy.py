#!/usr/bin/env python3
"""
BondStats Central Bank Watch V3 updater.

Production principles
---------------------
1. Official central-bank sources only.
2. No fixed "latest decision" URL as the primary update mechanism.
3. Discover newest decision/current-rate source on every run.
4. Discover the next future meeting on every run.
5. Fail closed: retain last-known-good values if a source cannot be parsed safely.
6. Distinguish lastChecked from lastSuccessfulDataUpdate.
7. Never infer a rate from third-party data or from an unrelated number on a page.

The updater is intentionally conservative. A degraded source is preferable to a wrong rate.
"""
from pathlib import Path
from html import unescape
import datetime as dt
import json, re, urllib.parse, urllib.request

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data/policy.json"
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
TODAY = NOW.date()
UA = {"User-Agent": "BondStats-CentralBankWatch/3.0 (+https://www.bondstats.org/)"}

MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]
MONTHS = {m.lower(): i for i, m in enumerate(MONTH_NAMES, 1)}
MONTHS.update({m[:3].lower(): i for i, m in enumerate(MONTH_NAMES, 1)})

def iso_now():
    return NOW.isoformat().replace("+00:00", "Z")

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=35) as r:
        body = r.read()
        ctype = r.headers.get("content-type", "")
        # This updater intentionally parses HTML/text endpoints only.
        if "pdf" in ctype.lower():
            raise ValueError("PDF-only source rejected by HTML parser")
        return body.decode("utf-8", "ignore"), r.geturl()

def clean(html):
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I|re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I|re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def links(html, base):
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I|re.S):
        out.append((clean(m.group(2)), urllib.parse.urljoin(base, m.group(1))))
    return out

def parse_date_text(s, default_year=None):
    s = unescape(s).replace("\xa0", " ").strip()
    for pat, order in [
        (r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', "dmy"),
        (r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', "mdy"),
    ]:
        m = re.search(pat, s, re.I)
        if not m:
            continue
        if order == "dmy":
            day, mon, year = m.groups()
        else:
            mon, day, year = m.groups()
        mi = MONTHS.get(mon.lower()) or MONTHS.get(mon[:3].lower())
        if mi:
            return dt.date(int(year), mi, int(day))
    if default_year:
        m = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            r'\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?',
            s, re.I
        )
        if m:
            mi = MONTHS[m.group(1).lower()]
            return dt.date(default_year, mi, int(m.group(3) or m.group(2)))
    return None

def fmt_meeting(start, end=None):
    if end and end != start:
        if start.month == end.month and start.year == end.year:
            return f"{start.day}–{end.day} {start.strftime('%B %Y')}"
        return f"{start.day} {start.strftime('%B')}–{end.day} {end.strftime('%B %Y')}"
    return f"{start.day} {start.strftime('%B %Y')}"

def classify(old, new):
    if old is None or new is None:
        return None, None
    bp = round((new - old) * 100)
    return ("Hike" if bp > 0 else "Cut" if bp < 0 else "Hold"), bp

def single_rate(text, patterns):
    for pat in patterns:
        m = re.search(pat, text, re.I|re.S)
        if not m:
            continue
        raw = m.group(1).strip()
        raw = raw.replace("¼", ".25").replace("½", ".5").replace("¾", ".75")
        try:
            x = float(raw)
        except ValueError:
            continue
        if -2 <= x <= 25:
            return x
    return None

def latest_past_and_next(dates):
    uniq = sorted(set(dates))
    past = [d for d in uniq if d <= TODAY]
    future = [d for d in uniq if d > TODAY]
    return (max(past) if past else None, min(future) if future else None)

def current_year_url(template):
    return template.format(year=TODAY.year)

# ---------------- FED ----------------
def fed(b):
    cal = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    html, _ = fetch(cal)
    text = clean(html)

    candidates = []
    for label, url in links(html, cal):
        m = re.search(r'/monetary(\d{8})a\.htm', url)
        if not m:
            continue
        d = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
        if d <= TODAY:
            candidates.append((d, url))
    if not candidates:
        raise ValueError("Fed latest statement not discovered")

    decision_date, source = max(candidates)
    h, _ = fetch(source)
    t = clean(h)
    m = re.search(
        r'target range for the federal funds rate at\s+'
        r'(\d+(?:-\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?)\s+to\s+'
        r'(\d+(?:-\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?)\s+percent', t, re.I
    )
    if not m:
        raise ValueError("Fed rate range not parsed")

    def frac(v):
        if "-" in v:
            whole, f = v.split("-", 1)
            a, c = f.split("/")
            return float(whole) + float(a)/float(c)
        if "/" in v:
            a, c = v.split("/")
            return float(a)/float(c)
        return float(v)

    lo, hi = frac(m.group(1)), frac(m.group(2))
    if not (0 <= lo <= hi <= 25):
        raise ValueError("Fed implausible rate range")
    old_mid = (b.get("rateLow", lo) + b.get("rateHigh", hi)) / 2
    decision, bp = classify(old_mid, (lo + hi) / 2)

    # Parse meeting ranges across current + next year from the same official calendar.
    meetings = []
    for m in re.finditer(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?', text, re.I
    ):
        # nearest explicit year around this occurrence
        left = text[max(0, m.start()-700):m.start()]
        yrs = re.findall(r'\b(20\d{2})\b', left)
        year = int(yrs[-1]) if yrs else TODAY.year
        if year not in (TODAY.year, TODAY.year+1):
            continue
        mi = MONTHS[m.group(1).lower()]
        start = dt.date(year, mi, int(m.group(2)))
        end = dt.date(year, mi, int(m.group(3) or m.group(2)))
        if end > TODAY:
            meetings.append((end, start, end))
    if not meetings:
        raise ValueError("Fed next meeting not parsed")
    _, start, end = min(meetings)

    return {
        "rateLow": lo, "rateHigh": hi,
        "displayRate": f"{lo:.2f}–{hi:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source,
        "scheduleUrl": cal,
        "nextMeeting": end.isoformat(),
        "nextMeetingLabel": fmt_meeting(start, end)
    }

# ---------------- ECB ----------------
def ecb(b):
    index = current_year_url("https://www.ecb.europa.eu/press/pr/date/{year}/html/index.en.html")
    html, _ = fetch(index)
    candidates = []
    for label, url in links(html, index):
        m = re.search(r'ecb\.mp(\d{6})', url)
        if m:
            d = dt.datetime.strptime(m.group(1), "%y%m%d").date()
            if d <= TODAY:
                candidates.append((d, url))
    if not candidates:
        raise ValueError("ECB latest monetary-policy release not discovered")

    decision_date, source = max(candidates)
    h, _ = fetch(source)
    t = clean(h)
    rate = single_rate(t, [
        r'deposit facility.*?(?:remain unchanged at|increased to|decreased to|will be)\s*([0-9.]+)\s*%'
    ])
    if rate is None:
        raise ValueError("ECB deposit facility rate not parsed")
    decision, bp = classify(b.get("rate"), rate)

    sched = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
    hs, _ = fetch(sched)
    ts = clean(hs)
    meetings = []
    for m in re.finditer(
        r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
        r'(\d{4}).{0,180}?monetary policy',
        ts, re.I
    ):
        start = dt.date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(1)))
        end = dt.date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(2)))
        if end > TODAY:
            meetings.append((end, start, end))
    if not meetings:
        raise ValueError("ECB next meeting not parsed")
    _, start, end = min(meetings)

    return {
        "rate": rate, "displayRate": f"{rate:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": sched,
        "nextMeeting": end.isoformat(),
        "nextMeetingLabel": fmt_meeting(start, end)
    }

# ---------------- BOE ----------------
def boe(b):
    hub = "https://www.bankofengland.co.uk/monetary-policy"
    html, _ = fetch(hub)
    text = clean(html)
    rate = single_rate(text, [r'Current Bank Rate\s*([0-9.]+)\s*%'])

    candidates = []
    for label, url in links(html, hub):
        if "monetary policy summary" not in label.lower():
            continue
        # URLs normally contain year/month; page date is checked after fetch.
        try:
            h, _ = fetch(url)
            t = clean(h)
            dm = re.search(r'Published on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', t, re.I)
            d = parse_date_text(dm.group(1)) if dm else None
            rr = single_rate(t, [
                r'maintain Bank Rate at\s*([0-9.]+)\s*%',
                r'Bank Rate.*?(?:to|at)\s*([0-9.]+)\s*%'
            ])
            if d and d <= TODAY and rr is not None:
                candidates.append((d, url, rr))
        except Exception:
            pass
    if candidates:
        decision_date, source, rate2 = max(candidates)
        rate = rate2
    else:
        decision_date = dt.date.fromisoformat(b["decisionDate"])
        source = b["sourceUrl"]

    if rate is None:
        raise ValueError("BoE Bank Rate not parsed")
    decision, bp = classify(b.get("rate"), rate)

    sched = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"
    hs, _ = fetch(sched)
    ts = clean(hs)
    dates = []
    for m in re.finditer(
        r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        ts, re.I
    ):
        d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        if d > TODAY:
            dates.append(d)
    if not dates:
        raise ValueError("BoE next meeting not parsed")
    nxt = min(dates)

    return {
        "rate": rate, "displayRate": f"{rate:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": sched,
        "nextMeeting": nxt.isoformat(),
        "nextMeetingLabel": fmt_meeting(nxt)
    }

# ---------------- BOJ ----------------
def parse_boj_statement_index(html, base):
    """Return latest dated official statement/change-guideline link from annual BoJ index."""
    out = []
    for label, url in links(html, base):
        # Prefer an HTML statement when available; PDF-only links are not parsed.
        m = re.search(r'k(\d{6})[a-z]?\.htm', url, re.I)
        if m:
            d = dt.datetime.strptime(m.group(1), "%y%m%d").date()
            if d <= TODAY:
                out.append((d, url))
    return max(out) if out else None

def parse_boj_meetings(text):
    """Parse English BoJ two-day meeting ranges from official schedule text."""
    meetings = []
    pat = (
        r'(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)'
        r'\s+(\d{1,2})(?:\s*\([A-Za-z.]+\))?\s*(?:,|and|[-–])\s*'
        r'(\d{1,2})(?:\s*\([A-Za-z.]+\))?'
    )
    for m in re.finditer(pat, text, re.I):
        mon = m.group(1).rstrip(".")
        mi = MONTHS.get(mon.lower()) or MONTHS.get(mon[:3].lower())
        if not mi:
            continue
        # nearest preceding year heading
        left = text[max(0, m.start()-600):m.start()]
        yrs = re.findall(r'\b(20\d{2})\b', left)
        year = int(yrs[-1]) if yrs else TODAY.year
        start = dt.date(year, mi, int(m.group(2)))
        end = dt.date(year, mi, int(m.group(3)))
        meetings.append((start, end))
    return meetings

def boj(b):
    home = "https://www.boj.or.jp/en/"
    hh, _ = fetch(home)
    th = clean(hh)

    # Current guideline on official home page is the most resilient rate source.
    rate = single_rate(th, [
        r'Guideline.*?uncollateralized overnight call rate.*?around\s+([0-9.]+)\s+percent',
        r'Interest Rate Applied to the Complementary Deposit Facility\s+([0-9.]+)\s*%'
    ])
    if rate is None:
        raise ValueError("BoJ current policy guideline not parsed")

    annual = current_year_url("https://www.boj.or.jp/en/mopo/mpmdeci/state_{year}/index.htm")
    hi, _ = fetch(annual)
    latest = parse_boj_statement_index(hi, annual)

    # Some recent BoJ releases are PDF-only. In that case the annual index itself is the
    # official latest-decision source and the current guideline remains the rate source.
    source = latest[1] if latest else annual

    # Decision date = latest date present in the annual statement index, including PDF entries.
    ti = clean(hi)
    dates = []
    for m in re.finditer(
        r'(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)'
        r'\s+(\d{1,2}),?\s+(\d{4})',
        ti, re.I
    ):
        mon = m.group(1).rstrip(".")
        mi = MONTHS.get(mon.lower()) or MONTHS.get(mon[:3].lower())
        if mi:
            d = dt.date(int(m.group(3)), mi, int(m.group(2)))
            if d <= TODAY:
                dates.append(d)
    if not dates:
        raise ValueError("BoJ latest decision date not parsed")
    decision_date = max(dates)

    sched = "https://www.boj.or.jp/en/mopo/mpmsche_minu/"
    hs, _ = fetch(sched)
    ts = clean(hs)
    meetings = [(s, e) for s, e in parse_boj_meetings(ts) if e > TODAY]
    if not meetings:
        # Home page has an explicit next-meeting line; use as official fallback.
        m = re.search(
            r'Next Monetary Policy Meeting Date\s+'
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            r'\s+(\d{1,2})\s+and\s+(\d{1,2}),\s*(\d{4})', th, re.I
        )
        if not m:
            raise ValueError("BoJ next meeting not parsed")
        start = dt.date(int(m.group(4)), MONTHS[m.group(1).lower()], int(m.group(2)))
        end = dt.date(int(m.group(4)), MONTHS[m.group(1).lower()], int(m.group(3)))
    else:
        start, end = min(meetings, key=lambda x: x[1])

    decision, bp = classify(b.get("rate"), rate)
    return {
        "rate": rate, "displayRate": f"~{rate:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": sched,
        "nextMeeting": end.isoformat(),
        "nextMeetingLabel": fmt_meeting(start, end)
    }

# ---------------- SNB ----------------
def parse_snb_decisions(html, base):
    """Discover dated monetary-policy decision links from SNB's official decisions hub."""
    candidates = []
    for label, url in links(html, base):
        if "monetary policy assessment" not in label.lower():
            continue
        d = parse_date_text(label)
        if d and d <= TODAY:
            candidates.append((d, url))
    return max(candidates) if candidates else None

def snb(b):
    hub = "https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/decisions"
    html, _ = fetch(hub)
    latest = parse_snb_decisions(html, hub)
    if not latest:
        raise ValueError("SNB latest monetary-policy decision not discovered")
    decision_date, source = latest

    h, _ = fetch(source)
    t = clean(h)
    rate = single_rate(t, [
        r'SNB policy rate (?:unchanged )?at\s*([0-9.-]+)\s*%',
        r'SNB (?:is lowering|lowers|raised|raises).*?policy rate.*?to\s*([0-9.-]+)\s*%'
    ])
    if rate is None:
        # The official decisions hub can itself contain the latest decision text.
        rate = single_rate(clean(html), [
            r'SNB policy rate (?:unchanged )?at\s*([0-9.-]+)\s*%'
        ])
    if rate is None:
        raise ValueError("SNB policy rate not parsed")

    sched = "https://www.snb.ch/en/services-events/digital-services/event-schedule"
    hs, _ = fetch(sched)
    ts = clean(hs)
    dates = []
    for m in re.finditer(
        r'(\d{2})\.(\d{2})\.(\d{4}).{0,140}?Monetary policy assessment',
        ts, re.I
    ):
        d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d > TODAY:
            dates.append(d)
    if not dates:
        # Also accept natural-language English renderings if SNB changes locale formatting.
        for m in re.finditer(
            r'Monetary policy assessment of\s+(\d{1,2})\s+'
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            ts, re.I
        ):
            d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            if d > TODAY:
                dates.append(d)
    if not dates:
        raise ValueError("SNB next policy assessment not parsed")
    nxt = min(dates)

    decision, bp = classify(b.get("rate"), rate)
    return {
        "rate": rate, "displayRate": f"{rate:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": sched,
        "nextMeeting": nxt.isoformat(),
        "nextMeetingLabel": fmt_meeting(nxt)
    }

# ---------------- BOC ----------------
def parse_boc_schedule(text):
    """Extract fixed announcement dates from the BoC policy-rate page."""
    dates = []
    for m in re.finditer(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{1,2})', text, re.I
    ):
        # determine year from nearest previous "Schedule for YYYY" or page context
        left = text[max(0, m.start()-650):m.start()]
        yrs = re.findall(r'(?:Schedule for\s+)?\b(20\d{2})\b', left, re.I)
        year = int(yrs[-1]) if yrs else TODAY.year
        if year in (TODAY.year, TODAY.year+1):
            try:
                dates.append(dt.date(year, MONTHS[m.group(1).lower()], int(m.group(2))))
            except ValueError:
                pass
    return sorted(set(dates))

def boc(b):
    hub = "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"
    html, _ = fetch(hub)
    text = clean(html)

    rate = single_rate(text, [
        r'(?:Policy interest rate|target for the overnight rate).*?([0-9.]+)\s*%'
    ])
    if rate is None:
        raise ValueError("BoC policy interest rate not parsed")

    dates = parse_boc_schedule(text)
    past, nxt = latest_past_and_next(dates)
    if not past or not nxt:
        raise ValueError("BoC fixed announcement schedule not parsed")

    # The Bank uses a stable official URL convention for Fixed Announcement Date releases.
    candidate = f"https://www.bankofcanada.ca/{past.year}/{past.month:02d}/fad-press-release-{past.isoformat()}/"
    source = hub
    try:
        h, final = fetch(candidate)
        tt = clean(h)
        rr = single_rate(tt, [r'target for the overnight rate at\s*([0-9.]+)\s*%'])
        if rr is not None:
            rate = rr
            source = final
    except Exception:
        # The live key-rate page remains an official current-rate source.
        pass

    decision, bp = classify(b.get("rate"), rate)
    return {
        "rate": rate, "displayRate": f"{rate:.2f}%",
        "decisionDate": past.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": hub,
        "nextMeeting": nxt.isoformat(),
        "nextMeetingLabel": fmt_meeting(nxt)
    }

# ---------------- RBA ----------------
def rba(b):
    rate_url = "https://www.rba.gov.au/cash-rate-target-overview.html"
    html, _ = fetch(rate_url)
    t = clean(html)
    rate = single_rate(t, [r'Cash rate target\s*([0-9.]+)\s*%'])
    if rate is None:
        raise ValueError("RBA cash rate target not parsed")

    sched = "https://www.rba.gov.au/coming-up/"
    hs, _ = fetch(sched)
    ts = clean(hs)
    meetings = []
    for m in re.finditer(
        r'Monetary Policy Board Meeting.{0,250}?(\d{1,2})\s*[–-]\s*(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        ts, re.I|re.S
    ):
        start = dt.date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(1)))
        end = dt.date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(2)))
        if end > TODAY:
            meetings.append((end, start, end))
    if not meetings:
        raise ValueError("RBA next meeting not parsed")
    _, start, end = min(meetings)

    # Discover newest monetary-policy decision from current-year official media index.
    index = current_year_url("https://www.rba.gov.au/media-releases/{year}/")
    hi, _ = fetch(index)
    candidates = []
    for label, url in links(hi, index):
        if "monetary policy decision" not in label.lower():
            continue
        # Prefer explicit date from label; fall back to release number ordering.
        d = parse_date_text(label)
        order = -1
        mm = re.search(r'mr-\d{2}-(\d+)\.html', url)
        if mm:
            order = int(mm.group(1))
        candidates.append((d or dt.date.min, order, url))
    source = max(candidates)[2] if candidates else rate_url

    # derive latest decision date from schedule if the source label cannot supply one
    all_meetings = []
    for m in re.finditer(
        r'Monetary Policy Board Meeting.{0,250}?(\d{1,2})\s*[–-]\s*(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        ts, re.I|re.S
    ):
        endd = dt.date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(2)))
        if endd <= TODAY:
            all_meetings.append(endd)
    decision_date = max(all_meetings) if all_meetings else dt.date.fromisoformat(b["decisionDate"])

    decision, bp = classify(b.get("rate"), rate)
    return {
        "rate": rate, "displayRate": f"{rate:.2f}%",
        "decisionDate": decision_date.isoformat(),
        "decision": decision or b["decision"],
        "changeBp": bp if bp is not None else b["changeBp"],
        "sourceUrl": source, "scheduleUrl": sched,
        "nextMeeting": end.isoformat(),
        "nextMeetingLabel": fmt_meeting(start, end)
    }

UPDATERS = {
    "FED": fed, "ECB": ecb, "BOE": boe, "BOJ": boj,
    "SNB": snb, "BOC": boc, "RBA": rba
}

def snapshot_value(b):
    if b.get("rateType") == "range":
        return (b.get("rateLow"), b.get("rateHigh"), b.get("decisionDate"), b.get("nextMeeting"))
    return (b.get("rate"), b.get("decisionDate"), b.get("nextMeeting"))

data = json.loads(PATH.read_text(encoding="utf-8"))
results = {}
changed = False

for bank in data["banks"]:
    before = dict(bank)
    old_snapshot = snapshot_value(bank)
    try:
        patch = UPDATERS[bank["id"]](bank)
        mandatory = ["displayRate", "decisionDate", "sourceUrl", "nextMeeting", "nextMeetingLabel"]
        if any(not patch.get(k, bank.get(k)) for k in mandatory):
            raise ValueError("mandatory output missing")
        # A "next" meeting must truly be future-dated.
        if dt.date.fromisoformat(patch.get("nextMeeting", bank["nextMeeting"])) <= TODAY:
            raise ValueError("nextMeeting is not in the future")

        bank.update(patch)
        bank["status"] = "official"
        bank["lastChecked"] = iso_now()
        bank["refreshState"] = "ok"
        if snapshot_value(bank) != old_snapshot:
            bank["lastSuccessfulDataUpdate"] = iso_now()
            changed = True
        results[bank["id"]] = {
            "state": "ok",
            "source": bank["sourceUrl"],
            "decisionDate": bank["decisionDate"],
            "nextMeeting": bank["nextMeeting"]
        }
    except Exception as exc:
        # Restore last-known-good financial data, but record health separately.
        bank.clear()
        bank.update(before)
        bank["refreshState"] = "degraded"
        bank["lastChecked"] = iso_now()
        results[bank["id"]] = {
            "state": "degraded",
            "error": str(exc)[:220]
        }

data["meta"]["lastChecked"] = iso_now()
if changed or not data["meta"].get("lastSuccessfulDataUpdate"):
    data["meta"]["lastSuccessfulDataUpdate"] = iso_now()
# Legacy field retained for frontend compatibility, but now means successful data vintage.
data["meta"]["lastUpdated"] = data["meta"]["lastSuccessfulDataUpdate"]
data["meta"]["refreshResults"] = results
data["meta"]["healthySources"] = sum(v["state"] == "ok" for v in results.values())
data["meta"]["degradedSources"] = sum(v["state"] != "ok" for v in results.values())

PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
