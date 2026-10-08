"""Refresh market-news-snapshot.json once a day (2026-10-08 user decision).

GitHub Pages has no /api/news, so the 뉴스·영상 tab always reads this snapshot. It used to be
refreshed by hand (news_server.py --snapshot) and sat at 2026-09-23. The daily workflow
(.github/workflows/market_news.yml) runs this and commits only the snapshot and its dist/ copy -
the one file the user exempted from per-push approval.

A topic that fails to download or comes back empty keeps yesterday's articles, marked
stale=True so the page says "갱신 지연", instead of replacing them with nothing. Exits 0 even
then; a day-old news list is better than a broken page.

Usage: python3 tooling/refresh_market_news.py
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_server as ns  # noqa: E402

PATH = ns.ROOT / 'market-news-snapshot.json'
DIST = ns.ROOT / 'dist' / 'market-news-snapshot.json'


def main():
    old = json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}
    out = {}
    for topic in ns.TOPICS:
        try:
            payload = ns.fetch_topic(topic)
            if not payload['articles']:
                raise ValueError('no articles')
            out[topic] = payload
            print(f'{topic}: {len(payload["articles"])} articles')
        except Exception as e:  # keep yesterday's list for this topic
            if topic in old:
                out[topic] = dict(old[topic], stale=True)
            print(f'{topic}: failed ({type(e).__name__}: {str(e)[:100]}) - kept previous')
    if not out:
        print('nothing fetched and no previous snapshot - left unchanged')
        return
    tmp = PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(PATH)
    if DIST.parent.exists():
        shutil.copy2(PATH, DIST)


if __name__ == '__main__':
    main()
