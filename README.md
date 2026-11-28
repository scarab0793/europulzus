# Európulzus

Hatnyelvű európai gazdasági hírportál (europulses.com).

## Automatikus frissítés
A `.github/workflows/update.yml` hétköznap reggel (és kézzel, az Actions fülön) lefuttatja a `scripts/update.py`-t:
EKB-árfolyamok (XML) + új hírek az Anthropic API-val (web search/fetch), majd commit az `index.html`-be.

Beállítás: Repo → Settings → Secrets and variables → Actions → `ANTHROPIC_API_KEY`.
Opcionális környezeti változók: `ANTHROPIC_MODEL`, `MAX_NEW`.
