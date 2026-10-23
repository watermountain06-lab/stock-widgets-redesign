"""scripts/live_set.py: a new ticker without a price is left out for the day; a live one without a price stops (2026-10-23)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import live_set  # noqa: E402


def home(d, rows):
    p = d / "index.html"
    p.write_text("x\nvar DATA = " + json.dumps(rows, indent=2).replace("\n]", "\n  ]") + ";\n", encoding="utf-8")
    live_set.PREVIEW_HOME = p


def main():
    d = Path(tempfile.mkdtemp())
    (d / "cards").mkdir()
    for t in ("AAA", "BBB"):
        (d / "cards" / f"{t}_full_widget.html").write_text("x")
    live_set.LIVE_CARDS, live_set.TOP_N = d / "cards", 2
    home(d, [{"ticker": "AAA", "marketCap": 5}, {"ticker": "BBB", "marketCap": 3},
             {"ticker": "NEW", "marketCap": None}, {"ticker": "CCC", "marketCap": 1}])
    assert live_set.live_tickers() == {"AAA", "BBB"}, "a new ticker without a price is left out"
    home(d, [{"ticker": "AAA", "marketCap": None}, {"ticker": "BBB", "marketCap": 3}])
    try:
        live_set.live_tickers()
        raise AssertionError("a live ticker without a price must stop")
    except SystemExit as e:
        assert "AAA" in str(e)
    print("OK - live_set")


if __name__ == "__main__":
    main()
