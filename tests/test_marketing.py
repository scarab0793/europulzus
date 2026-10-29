import tempfile
import unittest
from datetime import date
from pathlib import Path
from marketing import read_news, key_for, candidate

class MarketingTests(unittest.TestCase):
    def test_embedded_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "index.html"
            p.write_text('<script type="application/json" id="news-data">[{"t":"Hi"}]</script>', encoding="utf-8")
            self.assertEqual(read_news(p)[0]["t"], "Hi")
    def test_fragment_ignored(self):
        a = {"d":"2026-10-29","c":"DE","t":"A","u":"https://example.com/a#one"}
        self.assertEqual(key_for(a), key_for(dict(a, u="https://example.com/a#two")))
    def test_trading_economics_excluded(self):
        x = {"d":"2026-10-29","t":"A","src":"TE","u":"https://tradingeconomics.com/germany/inflation"}
        self.assertFalse(candidate(x, date(2026,10,29), 2)[0])
    def test_stale_excluded(self):
        x = {"d":"2026-10-01","t":"A","src":"Official","u":"https://example.com/a"}
        self.assertFalse(candidate(x, date(2026,10,29), 2)[0])
if __name__ == "__main__":
    unittest.main()
