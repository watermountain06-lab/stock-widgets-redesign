import unittest
from unittest.mock import patch
import news_server as api

class NewsApiTests(unittest.TestCase):
    def tearDown(self):
        api.CACHE.clear()

    def test_parse_deduplicates_and_rejects_bad_links_dates(self):
        item = '<item><title>Market update - CNBC</title><source>CNBC</source><link>https://example.com/article</link><pubDate>Wed, 23 Sep 2026 10:00:00 GMT</pubDate></item>'
        feed = '<rss><channel>' + item * 2 + item.replace('https:', 'javascript:') + item.replace('Wed, 23 Sep 2026 10:00:00 GMT', 'bad') + '</channel></rss>'
        articles = api.parse_feed(feed)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'Market update')
        self.assertEqual(articles[0]['source'], 'CNBC')

    def test_cache_avoids_duplicate_upstream_requests(self):
        with patch.object(api, 'fetch_topic', return_value={'articles': [], 'stale': False}) as fetch:
            api.get_topic('all')
            api.get_topic('all')
            self.assertEqual(fetch.call_count, 1)

    def test_stale_cache_survives_upstream_failure(self):
        api.CACHE['all'] = (-10000, {'articles': [{'title': 'Saved'}], 'stale': False})
        with patch.object(api, 'fetch_topic', side_effect=OSError()):
            result = api.get_topic('all')
        self.assertTrue(result['stale'])
        self.assertEqual(result['articles'][0]['title'], 'Saved')

if __name__ == '__main__':
    unittest.main()
