---
name: ticker
description: Use when the user asks to add/build a new ticker card in the stock-widgets redesign project ("/ticker", "add-ticker", "다음 티커 추가해줘", "새 티커 카드 만들어줘", or names a specific company/ticker to build) — builds a {TICKER}_full_widget.html in this repo through the same 5-tab, SEC-verified, Codex-reviewed process used for NVDA/AAPL/GOOGL.
version: 1.0.0
user-invocable: true
---

# /ticker

Builds one new `{TICKER}_full_widget.html` in this repo, reusing the exact process validated across NVDA, AAPL, and GOOGL (all 3 shipped with all 5 tabs, Codex-reviewed, browser-verified).

Read `playbook.md` in this skill's own directory in full and follow it exactly. It covers, in order:

- non-negotiable boundaries (never touch the live `stock-widgets` repo; never fabricate a number; never hand-type a numeric array)
- how to pick/confirm the ticker
- the data pipeline (price fetch, SEC EDGAR XBRL, analyst ratings) with the exact commands and known gotchas
- the locked per-tab structure and card checklist for `#tech` / `#fund` / `#valuation` / `#news` / `#invest`, in that build order
- the Codex text-mode review protocol (what to package, how to avoid false positives, how to weigh findings)
- the browser verification protocol (local server, click-after-scroll flakiness workaround)
- joining preview's daily pipeline (Step 5b, since 2026-09-11): `site_data/stocks.json` entry, `tier_history.json`, `seed_shares`/`fetch_prices`/`build_index`, and an `update_cards.py` dry run — card and entry in the same commit
- wrap-up steps (proto-banner, progress log, Claude Code memory)

**Autonomous mode (2026-08-25 on, per explicit user request):** no per-card chat confirmation. The judgment calls listed near the end of `playbook.md` (ticker selection, peer/anchor selection, GAAP-distortion handling, Bull/Bear content, any new #news event) are made independently using the documented criteria in that section, not discussed live with the user card-by-card. What stays mandatory and non-skippable instead: Codex text-mode review every tab, full browser verification every tab, never fabricate a number, never hand-type a numeric array, never touch the live `stock-widgets` repo, and a full wrap-up summary (including every judgment call made and why) at ticker completion so the user can review after the fact.
