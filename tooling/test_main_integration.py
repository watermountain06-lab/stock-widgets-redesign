"""Offline regression checks: python3 -m unittest discover -s tooling -v."""
from datetime import date, timedelta
from pathlib import Path
import importlib.util
import json
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

class AnalysisRegression(unittest.TestCase):
    def test_52week_excludes_old_extremes(self):
        bars = [dict(date=str(date(2024, 1, 1) + timedelta(days=i)), o=100, h=110, l=90, c=100) for i in range(300)]
        bars[0].update(h=999, l=1)
        result = module('fetch_price').summarize('TEST', bars)
        self.assertEqual((result['high52w'], result['low52w']), (110, 90))

    def test_split_adjustment_preserves_input(self):
        fin = {'epsDiluted': {'annual': [{'end': '2025-12-31', 'filed': '2026-02-11', 'val': 10}]},
               'sharesOutstanding': {'annual': [{'end': '2025-12-31', 'filed': '2026-02-11', 'val': 100}]}}
        result, notes = module('compute_valuation_score').correct_for_splits('APH', fin)
        self.assertEqual(result['epsDiluted']['annual'][0]['val'], 5)
        self.assertEqual(result['sharesOutstanding']['annual'][0]['val'], 200)
        self.assertEqual(fin['epsDiluted']['annual'][0]['val'], 10)
        self.assertTrue(notes)

    def test_short_history_is_not_called_five_years(self):
        score = module('compute_valuation_score')
        self.assertEqual(score.avg_key([1]*4), 'historicalAvg')
        self.assertEqual(score.avg_key([1]*5), 'historicalAvg5y')

    def test_operating_margin_requires_same_period(self):
        fin = {'revenue': {'annual': [{'end': '2025-12-31', 'val': 100}]},
               'netIncome': {'annual': [{'end': '2025-12-31', 'val': 10}]}}
        config = json.loads((ROOT / 'scripts/fundamental_score_config_v1.json').read_text())
        fn = module('compute_fundamental_score').compute_growth_profit_axis
        stale = fn(fin, config, [{'end': '2014-12-31', 'val': 40}], False)
        self.assertNotIn('opMargin', stale)
        self.assertIn('2014', stale['dataQuality']['opMargin'])
        current = fn(fin, config, [{'end': '2025-12-31', 'val': 40}], False)
        self.assertEqual(current['opMargin']['value'], 40)

    def test_catalog_and_deployment_cover_all_stocks(self):
        code = "const fs=require('fs'),vm=require('vm'),c={window:{}};vm.runInNewContext(fs.readFileSync('stock-data.js','utf8'),c);process.stdout.write(JSON.stringify(c.window.StockData));"
        data = json.loads(subprocess.check_output(['node', '-e', code], cwd=ROOT))
        # 종목 수는 카드 파일 수와 같아야 한다(70 → 103, 2026-10-07 v2 승격 — 고정값이면 종목이 늘 때마다 깨진다)
        n_cards = len(list((ROOT / 'cards').glob('*_full_widget.html')))
        self.assertGreaterEqual(len(data['stocks']), 70)
        self.assertEqual(len(data['stocks']), n_cards)
        self.assertEqual(len({s['ticker'] for s in data['stocks']}), n_cards)
        for stock in data['stocks']:
            path = ROOT / stock['href']
            self.assertTrue(path.exists(), stock['ticker'])
            self.assertEqual(path.read_bytes(), (ROOT / 'dist' / stock['href']).read_bytes())
            self.assertTrue((ROOT / 'dist/logos' / (stock['ticker'].lower() + '.png')).exists())
        self.assertRegex(data['meta']['asOf'] or '', r'^\d{4}-\d{2}-\d{2}$')   # 기준일은 매 승격마다 바뀐다

if __name__ == '__main__':
    unittest.main()
