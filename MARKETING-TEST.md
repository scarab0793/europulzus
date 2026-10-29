# EuroPulses marketing preview (safe test branch)

This branch adds an offline, read-only marketing preview. It does not modify index.html, the Claude updater, or the live site.

Run locally:

```sh
python -m unittest discover -s tests -v
python marketing.py --input index.html --output marketing-preview.json
```

Output is a local JSON preview, not published content. Dates are evaluated in UTC. Source links are not verified live; the preview is **not fact-checking**. Trading Economics, Bloomberg and CNBC are excluded pending manual review. Until article permalinks exist, the text points to the homepage.

The workflow has **manual dispatch only**, no schedule and no push trigger. No API credentials, posting, network calls, commits, or pushes. Do not merge to main until reviewed. A future automated publisher needs explicit approval, stable article IDs, source verification and a durable posted-items ledger.
