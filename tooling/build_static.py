"""Copy the complete public site to dist: python3 tooling/build_static.py."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ['market-news.js', 'market-news-snapshot.json', 'flow.css', 'flow.js', 'index.html', 'today.html', 'market-news.html', 'styles.css', 'today.css',
          'theme.css', 'header.css', 'detail-theme.css', 'stock-data.js',
          'data-status.js', 'today.js', 'theme.js', 'navigation.js', 'reading.js',
          'news.js', 'news-snapshot.json', 'quotes-snapshot.json', 'CNAME',
          'value-data.js', 'value-gap.js', 'value-gap.css',
          'stock-news.js', 'stock-news-view.js', 'stock-news-view.css',
          'tracking-data.js', 'tracking.css']

def etf_files():
    """ETF 화면·데이터·카드 페이지(2026-10-21 — 목록은 etf.js ORDER, scripts/sync_etf.py와 같은 함수)."""
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    import sync_etf
    order, _ = sync_etf.read_order(ROOT)
    return ['etf.js', 'etf.css', 'etf-data.js'] + [f'etf-{t.lower()}.html' for t in order]


def build():
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    etf = etf_files()
    for name in PUBLIC + etf:
        shutil.copy2(ROOT / name, target / name)   # 없으면 오류 — 첫 배포는 ETF 파일을 같은 커밋에 넣는다
    for old in target.glob('etf-*.html'):          # ORDER에서 빠진 ETF의 dist 사본은 지운다(루트 삭제는 손 승격)
        if old.name not in etf:
            old.unlink()
    for name in ['cards', 'logos']:
        # 지운 카드(상위 100에서 빠진 종목, scripts/live_set.py)가 dist에 남지 않도록 통째로 다시 만든다
        shutil.rmtree(target / name, ignore_errors=True)
        shutil.copytree(ROOT / name, target / name)
    print('Built complete static site in dist')

if __name__ == '__main__':
    build()
