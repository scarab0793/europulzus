# Europulse

English-language European business news portal (europulses.com).

## Automatikus frissítés
A `.github/workflows/update.yml` hétköznap reggel (és kézzel, az Actions fülön) lefuttatja a `scripts/update.py`-t:
ECB exchange rates (XML) + new English-language stories via the Anthropic API (web search/fetch), then a commit to `index.html`.

Beállítás: Repo → Settings → Secrets and variables → Actions → `ANTHROPIC_API_KEY`.
Opcionális környezeti változók: `ANTHROPIC_MODEL`, `MAX_NEW`.
