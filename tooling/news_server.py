"""News JSON API and static preview. Run: python3 tooling/news_server.py --port 8091.
Generate a static fallback: python3 tooling/news_server.py --snapshot.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOPICS = {'all': 'stock market economy', 'rates': 'Federal Reserve interest rates',
          'fx': 'US dollar exchange rates', 'economy': 'US economy inflation',
          'jobs': 'US unemployment jobs report', 'companies': 'company earnings stocks'}
DOMAINS = ['wsj.com', 'washingtonpost.com', 'ft.com', 'cnbc.com', 'investing.com', 'finance.yahoo.com']
CACHE = {}
LOCK = threading.Lock()

def parse_feed(xml):
    articles, seen = [], set()
    for item in ET.fromstring(xml).findall('./channel/item'):
        title = item.findtext('title', '').strip()
        url = item.findtext('link', '').strip()
        source = item.findtext('source', '').strip()
        try:
            published = parsedate_to_datetime(item.findtext('pubDate', '')).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            continue
        if not title or urlparse(url).scheme != 'https' or url in seen:
            continue
        seen.add(url)
        if source and title.endswith(' - ' + source):
            title = title[:-len(source)-3]
        articles.append(dict(title=title, url=url, source=source or 'Google News', publishedAt=published))
    return sorted(articles, key=lambda a: a['publishedAt'], reverse=True)[:40]

def fetch_topic(topic):
    query = TOPICS[topic] + ' (' + ' OR '.join('site:' + d for d in DOMAINS) + ') when:7d'
    url = 'https://news.google.com/rss/search?' + urlencode(dict(q=query, hl='en-US', gl='US', ceid='US:en'))
    with urlopen(Request(url, headers={'User-Agent': 'StockWidgetsNews/1.0'}), timeout=20) as response:
        articles = parse_feed(response.read(2_000_000))
    return dict(provider='Google News RSS', topic=topic, updatedAt=datetime.now(timezone.utc).isoformat(), articles=articles, stale=False)

def get_topic(topic):
    # Serialize cache misses to prevent concurrent clients multiplying upstream requests.
    with LOCK:
        cached = CACHE.get(topic)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        try:
            payload = fetch_topic(topic)
            CACHE[topic] = (time.monotonic(), payload)
            return payload
        except Exception:
            if cached:
                return dict(cached[1], stale=True)
            raise

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path)
        if route.path != '/api/news':
            # Serve only public output, never repository/configuration files.
            return super().do_GET()
        topic = parse_qs(route.query).get('topic', ['all'])[0]
        if topic not in TOPICS:
            return self.send_json({'error': 'Unknown topic'}, 400)
        try:
            self.send_json(get_topic(topic))
        except Exception:
            self.send_json({'error': 'News provider unavailable'}, 502)
    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    if args.snapshot:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(zip(TOPICS, pool.map(fetch_topic, TOPICS)))
        path = ROOT / 'market-news-snapshot.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        temporary.replace(path)
        print('Collected:', {key: len(value['articles']) for key, value in results.items()})
    else:
        ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(ROOT / 'dist'))).serve_forever()
