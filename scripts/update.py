#!/usr/bin/env python3
"""Európulzus automatikus frissítés: EKB-árfolyamok + hírek (Anthropic API) -> index.html.
Csak a T.disc2-t, a hír-JSON-t, az árfolyamsávot és a hozzá tartozó dátumokat módosítja."""
import json, os, re, subprocess, sys, tempfile, urllib.request, xml.etree.ElementTree as ET
from datetime import date, datetime

HTML = os.environ.get("INDEX_HTML", "index.html")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
TODAY = date.today()
LANGS = ["en", "de", "fr", "es", "pl"]
CODES = set("EU DE FR NL BE AT LU IE IT ES PT GR CY MT HU PL CZ SK RO BG HR SI SE DK FI EE LV LT CH NO".split())
ECB_URLS = ["https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml",
            "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"]
NEWS_RE = re.compile(r'(<script type="application/json" id="news-data">)(.*?)(</script>)', re.S)

HU_M = "január február március április május június július augusztus szeptember október november december".split()
HU_SHORT = ["jan.", "febr.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.", "okt.", "nov.", "dec."]
EN_M = "January February March April May June July August September October November December".split()
DE_M = "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split()
FR_M = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
ES_M = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
PL_M = "stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października listopada grudnia".split()

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

def hu(v, n): return f"{v:.{n}f}".replace(".", ",")

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
    new, n = re.subn(r'(<span style="opacity:\.75;font-weight:400">)[^<]*(</span>)', r"\g<1>%s %d.\g<2>" % (HU_SHORT[m-1], dd), new, count=1)
    if n != 1: raise SystemExit("fx-label dátum nem található")
    return new, (d if new != html else None)

# ---------- disc2 ----------
def update_disc2(html):
    d, m, y = TODAY.day, TODAY.month - 1, TODAY.year
    t = [f"Összeállítva nyilvános hírforrásokból {y}. {HU_M[m]} {d}-én. Tájékoztató jellegű, nem befektetési tanácsadás.",
         f"Compiled from public news sources on {d} {EN_M[m]} {y}. For information only, not investment advice.",
         f"Zusammengestellt aus öffentlichen Nachrichtenquellen am {d}. {DE_M[m]} {y}. Nur zur Information, keine Anlageberatung.",
         f"Compilé à partir de sources publiques le {d if d>1 else '1er'} {FR_M[m]} {y}. À titre informatif, ne constitue pas un conseil en investissement.",
         f"Elaborado con fuentes públicas el {d} de {ES_M[m]} de {y}. Solo informativo, no constituye asesoramiento de inversión.",
         f"Zestawiono z publicznych źródeł {d} {PL_M[m]} {y} r. Wyłącznie informacyjnie, nie stanowi porady inwestycyjnej."]
    it = iter(t)
    html, n = re.subn(r"disc2:'[^']*'", lambda _: "disc2:'%s'" % next(it), html)
    if n != 6: raise SystemExit(f"disc2 T-kulcs: {n}")
    html, n = re.subn(r'(data-i="disc2">)[^<]*(</p>)', lambda mo: mo[1] + t[0] + mo[2], html, count=1)
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
        for l in LANGS:
            v = x[l]
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(s, str) and s.strip() for s in v)): return False
        return True
    except Exception:
        return False

PROMPT = """Te az Európulzus (európai gazdasági hírportál) szerkesztője vagy. Ma {today}. A hírfolyam legfrissebb tétele {latest} napi.
Gyűjts új, ellenőrizhető gazdasági híreket {latest}-tól (az utolsó napnál nézd meg, mi hiányzik) máig. Eszközök: web_search és web_fetch.
Források, amik működnek: Portfolio listaoldalak (portfolio.hu/gazdasag, /deviza, /uzlet), Euronews (euronews.com/business), Eurostat, EKB, jegybankok, ANSA, Trading Economics, magyar portálok (Economx, VG, HVG, G7, Telex, Index, Mfor, Privátbankár, Bank360). Bloomberg és snbchf.com nem tölthető be.
SZABÁLYOK
- Csak olyan hírt vegyél fel, aminek a cikkoldalát a web_fetch-csel tényleg beolvastad, és a cikk dátuma pontosan ismert. A keresési kivonatból ne írj hírt. Számot ne találj ki. Ha a cikk dátuma nem egyezik az oldal dátumával, hagyd ki.
- Saját szavakkal, szó szerinti átvétel nélkül, 1-2 mondatos összefoglaló. Ha egyetlen másodlagos forrásra épül („a WSJ szerint"), jelezd minden nyelven.
- Országkódok: EU, DE, FR, NL, BE, AT, LU, IE, IT, ES, PT, GR, CY, MT, HU, PL, CZ, SK, RO, BG, HR, SI, SE, DK, FI, EE, LV, LT, CH, NO. Országonként egy-két hír, ha van; legfeljebb {maxn} hír összesen.
- Ne ismételd a már meglévő URL-eket (lista lent).
- Számformátum: HU 1,5 / 1 234; EN 1.5 / 1,234; DE és ES 1,5 / 1.234; FR és PL 1,5 / 1 234. A számok mindenhol egyezzenek.
KIMENET: kizárólag egy JSON-tömb, semmi más szöveg, kódblokk nélkül. Elem:
{{"d":"ÉÉÉÉ-HH-NN","c":"kód","t":"magyar cím","s":"magyar összefoglaló","src":"forrás neve","u":"cikk URL","en":["cím","összefoglaló"],"de":[..],"fr":[..],"es":[..],"pl":[..]}}
Mind az öt fordítás kötelező, természetes és pontos. Ha nincs új hír, adj vissza üres tömböt: [].
MÁR MEGLÉVŐ (utolsó 120) URL-ek:
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
        r = client.beta.messages.create(model=MODEL, max_tokens=32000, tools=tools, messages=msgs,
                                        betas=["web-fetch-2025-09-10"])
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
        assert all(isinstance(x[l], list) and len(x[l]) == 2 for l in LANGS), x["u"]
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S)]
    for s in scripts:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f: f.write(s)
        p = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        assert p.returncode == 0, p.stderr
    keys = [set(re.findall(r"(\w+):'", blk)) for blk in re.split(r"\n\s*(?:hu|en|de|fr|es|pl):\{", re.search(r"var T=\{.*?\n  \};", html, re.S)[0])[1:]]
    assert len(keys) == 6 and all(k == keys[0] for k in keys), "T kulcsok eltérnek"

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
