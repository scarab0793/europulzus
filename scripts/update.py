#!/usr/bin/env python3
"""Europulse automatikus frissítés: EKB-árfolyamok + hírek (Anthropic API) -> index.html.
Csak a T.disc2-t, a hír-JSON-t, az árfolyamsávot és a hozzá tartozó dátumokat módosítja."""
import json, os, re, subprocess, sys, tempfile, urllib.request, xml.etree.ElementTree as ET
from datetime import date, datetime

HTML = os.environ.get("INDEX_HTML", "index.html")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
TODAY = date.today()
CODES = set("EU DE FR NL BE AT LU IE IT ES PT GR CY MT HU PL CZ SK RO BG HR SI SE DK FI EE LV LT CH NO".split())
ECB_URLS = ["https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml",
            "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"]
NEWS_RE = re.compile(r'(<script type="application/json" id="news-data">)(.*?)(</script>)', re.S)

MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
EN_M = "January February March April May June July August September October November December".split()

def log(*a): print(*a, file=sys.stderr)

# ---------- FX ----------
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (europulzus-updater)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def ecb_latest():
    best = None
    srcs = [open(os.environ["ECB_XML_FILE"], "rb").read()] if os.environ.get("ECB_XML_FILE") else None
    for i, url in enumerate(ECB_URLS if not srcs else [None]):
        try:
            raw = srcs[0] if srcs else fetch(url)
            root = ET.fromstring(raw)
        except Exception as e:
            log("ECB hiba", url, e); continue
        cubes = [c for c in root.iter() if c.tag.endswith("Cube") and c.get("time")]
        if not cubes: continue
        c = max(cubes, key=lambda c: c.get("time"))
        rates = {x.get("currency"): float(x.get("rate")) for x in c if x.get("currency")}
        if best is None or c.get("time") > best[0]: best = (c.get("time"), rates)
    return best

def hu(v, n): return f"{v:.{n}f}"

def fx_values(r):
    usd, huf, gbp, chf, jpy = r["USD"], r["HUF"], r["GBP"], r["CHF"], r["JPY"]
    return {
        "EUR/USD": hu(usd, 4), "EUR/HUF": hu(huf, 2), "USD/HUF": hu(huf / usd, 2), "EUR/GBP": hu(gbp, 4),
        "GBP/USD": hu(usd / gbp, 4), "EUR/CHF": hu(chf, 4), "USD/CHF": hu(chf / usd, 4),
        "CHF/HUF": hu(huf / chf, 2), "GBP/HUF": hu(huf / gbp, 2), "USD/JPY": hu(jpy / usd, 2),
        "EUR/JPY": hu(jpy, 2), "EUR/PLN": hu(r["PLN"], 4), "EUR/CZK": hu(r["CZK"], 3),
        "EUR/RON": hu(r["RON"], 4), "EUR/SEK": hu(r["SEK"], 4), "EUR/NOK": hu(r["NOK"], 4),
        "EUR/DKK": hu(r["DKK"], 4), "EUR/CNY": hu(r["CNY"], 4)}

def update_fx(html):
    got = ecb_latest()
    if not got: log("Nincs EKB-adat."); return html, None
    d, rates = got
    vals = fx_values(rates)
    y, m, dd = map(int, d.split("-"))
    cur = re.search(r"Date\.UTC\((\d+),(\d+),(\d+)\)", html)
    if cur and (int(cur[1]), int(cur[2]), int(cur[3])) > (y, m - 1, dd):
        log("A sávban frissebb dátum van, kihagyom."); return html, None
    new = html
    for pair, v in vals.items():
        new, n = re.subn(r'(<span class="p">%s</span>)[^<]*(</li>)' % re.escape(pair), r"\g<1>%s\g<2>" % v, new)
        if n != 2: raise SystemExit(f"FX-sor hiba: {pair} {n} találat")
    new, n = re.subn(r"Date\.UTC\(\d+,\d+,\d+\)", f"Date.UTC({y},{m-1},{dd})", new, count=1)
    if n != 1: raise SystemExit("Date.UTC nem található")
    new, n = re.subn(r'(<span style="opacity:\.75;font-weight:400">)[^<]*(</span>)', r"\g<1>%d %s\g<2>" % (dd, MON[m-1]), new, count=1)
    if n != 1: raise SystemExit("fx-label dátum nem található")
    return new, (d if new != html else None)

# ---------- disc2 ----------
def update_disc2(html):
    t = f"Compiled from public news sources on {TODAY.day} {EN_M[TODAY.month - 1]} {TODAY.year}. For information only, not investment advice."
    html, n = re.subn(r"disc2:'[^']*'", lambda _: "disc2:'%s'" % t, html)
    if n != 1: raise SystemExit(f"disc2 T-kulcs: {n}")
    html, n = re.subn(r'(data-i="disc2">)[^<]*(</p>)', lambda mo: mo[1] + t + mo[2], html, count=1)
    if n != 1: raise SystemExit("disc2 HTML nem található")
    return html

# ---------- News ----------
def load_news(html):
    mo = NEWS_RE.search(html)
    return json.loads(mo[2].replace("<\\/", "</"))

def valid_item(x, seen):
    try:
        datetime.strptime(x["d"], "%Y-%m-%d")
        if x["c"] not in CODES: return False
        if not all(isinstance(x[k], str) and x[k].strip() for k in ("t", "s", "src", "u")): return False
        if not x["u"].startswith("http") or x["u"] in seen: return False
        if x["d"] > TODAY.isoformat(): return False
        return True
    except Exception:
        return False

PROMPT = """You are the editor of Europulse, an English-language European business news portal. Today is {today}. The newest item in the feed is dated {latest}.
Collect new, verifiable business news from {latest} (re-check the last day for gaps) up to today. Tools: web_search and web_fetch.
Sources that work: Portfolio.hu list pages (portfolio.hu/gazdasag, /deviza, /uzlet), Euronews (euronews.com/business), Eurostat, ECB, central banks, ANSA, Trading Economics, Hungarian outlets (Economx, VG, HVG, G7, Telex, Index, Mfor, Privatbankar, Bank360). Bloomberg and snbchf.com cannot be loaded.
RULES
- Only include a story if you actually fetched the article page with web_fetch and its date is exactly known. Never write from search snippets. Never invent figures. Skip articles whose date does not match the page date.
- Write in your own words in English, no verbatim copying, 1-2 sentence summary. If a story rests on a single secondary source ("according to the WSJ"), say so in the text.
- Country codes: EU, DE, FR, NL, BE, AT, LU, IE, IT, ES, PT, GR, CY, MT, HU, PL, CZ, SK, RO, BG, HR, SI, SE, DK, FI, EE, LV, LT, CH, NO. One or two stories per country where available; at most {maxn} in total.
- Do not repeat already listed URLs (below).
- Number format: English (1.5, 1,234).
OUTPUT: a single JSON array only, no other text, no code block. Item:
{{"d":"YYYY-MM-DD","c":"code","t":"English headline","s":"English summary","src":"source name","u":"article URL"}}
If there is no new story, return [].
EXISTING (latest 120) URLs:
{urls}"""

def gather_news(items):
    import anthropic
    client = anthropic.Anthropic()
    prompt = PROMPT.format(today=TODAY.isoformat(), latest=items[0]["d"], maxn=int(os.environ.get("MAX_NEW", 25)),
                           urls="\n".join(x["u"] for x in items[:120]))
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 25},
             {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 40}]
    msgs = [{"role": "user", "content": prompt}]
    for _ in range(8):
        with client.beta.messages.stream(model=MODEL, max_tokens=32000, tools=tools, messages=msgs,
                                         betas=["web-fetch-2025-09-10"]) as st:
            r = st.get_final_message()
        if r.stop_reason == "pause_turn":
            msgs = [msgs[0], {"role": "assistant", "content": r.content}]; continue
        break
    text = "".join(b.text for b in r.content if b.type == "text")
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < 0: raise SystemExit("A modell nem adott JSON-t")
    return json.loads(text[a:b + 1])

def update_news(html):
    items = load_news(html)
    if os.environ.get("NO_NEWS"): return html, 0
    seen = {x["u"] for x in items}
    fresh = []
    for x in gather_news(items):
        if valid_item(x, seen): fresh.append(x); seen.add(x["u"])
        else: log("Elvetve:", str(x)[:120])
    if not fresh: return html, 0
    allitems = fresh + items
    allitems.sort(key=lambda x: x["d"], reverse=True)  # stabil: az egyenlő dátumú sorrend marad
    if len(allitems) > 820: allitems = allitems[:800]
    js = json.dumps(allitems, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return NEWS_RE.sub(lambda mo: mo[1] + js + mo[3], html, count=1), len(fresh)

# ---------- ellenőrzés ----------
def verify(html):
    items = load_news(html)
    urls = [x["u"] for x in items]
    assert len(urls) == len(set(urls)), "duplikált URL"
    assert len(items) <= 820
    ds = [x["d"] for x in items]; assert ds == sorted(ds, reverse=True), "dátumsorrend"
    for x in items:
        assert set(x) == {"d", "c", "t", "s", "src", "u"}, x["u"]
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S)]
    for s in scripts:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f: f.write(s)
        p = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        assert p.returncode == 0, p.stderr

def main():
    html = open(HTML, encoding="utf-8").read()
    orig = html
    html, fxdate = update_fx(html)
    html, n = update_news(html)
    if fxdate is None and n == 0:
        log("Nincs változás, nem írok."); return
    html = update_disc2(html)
    verify(html)
    open(HTML, "w", encoding="utf-8").write(html)
    print(f"új hír: {n}; árfolyam: {fxdate or 'változatlan'}")

if __name__ == "__main__":
    main()
