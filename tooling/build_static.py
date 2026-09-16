"""Copy the complete public site to dist: python3 tooling/build_static.py."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ['index.html', 'today.html', 'market-news.html', 'styles.css', 'today.css',
          'theme.css', 'header.css', 'detail-theme.css', 'stock-data.js',
          'data-status.js', 'today.js', 'theme.js', 'navigation.js', 'reading.js',
          'news.js', 'news-snapshot.json', 'quotes-snapshot.json', 'CNAME']

def build():
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    for name in PUBLIC:
        shutil.copy2(ROOT / name, target / name)
    for name in ['cards', 'logos']:
        shutil.copytree(ROOT / name, target / name, dirs_exist_ok=True)
    print('Built complete static site in dist')

if __name__ == '__main__':
    build()
