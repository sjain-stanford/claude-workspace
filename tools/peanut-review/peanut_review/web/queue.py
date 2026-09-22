"""Review queue page; data and actions are served by the existing HTTP app."""
from __future__ import annotations

import html
import json

from .render import FAVICON_HREF, THEME_BOOTSTRAP, THEME_TOGGLE_BUTTON, _asset_url


def render_queue(base_url: str, token: str, enabled: bool) -> str:
    base = html.escape(base_url, quote=True)
    setup = "" if enabled else '<p class="queue-notice">Enable the queue with <code>peanut-review serve --queue-config /path/to/queue.json</code>. See the review queue setup in the README.</p>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>peanut-review — review queue</title>
<link rel="icon" href="{FAVICON_HREF}">
<link rel="stylesheet" href="{html.escape(_asset_url(base_url, "style.css"), quote=True)}">
{THEME_BOOTSTRAP}</head>
<body class="index queue-page">
<header>
<h1><a href="{base}/">🥜 peanut-review</a></h1>
<nav class="app-nav" aria-label="Dashboard"><a href="{base}/queue" aria-current="page">Review queue</a><a href="{base}/">Sessions</a></nav>
<span class="spacer"></span>{THEME_TOGGLE_BUTTON}
<button id="queue-refresh" type="button">Refresh queue</button>
</header>
<main class="index-main">
<div class="queue-heading"><div><h2>Your review queue</h2><p class="meta">Review requests and PRs you are following across your accounts.</p></div><span id="queue-count" class="meta" aria-live="polite"></span></div>
{setup}
<div id="queue-accounts" class="queue-accounts"></div>
<div class="queue-toolbar">
<input id="queue-search" type="search" placeholder="Search PRs, repositories, authors…" aria-label="Search review queue">
<select id="queue-account" aria-label="Filter by account"><option value="">All accounts</option></select>
<select id="queue-request-type" aria-label="Filter by request type">
<option value="">All request types</option><option value="team">Team request</option><option value="direct">Direct request</option><option value="following">Following</option>
</select>
<select id="queue-filter" aria-label="Filter review queue">
<option value="attention">Needs attention</option><option value="open">All open PRs</option><option value="requested">Review requested</option><option value="stale">Stale reviews</option><option value="running">Running reviews</option><option value="all">Include closed PRs</option>
</select></div>
<p id="queue-error" class="queue-notice error" role="alert" hidden></p>
<div class="queue-table-wrap"><table class="sessions queue-table">
<thead><tr><th>Pull request</th><th>Account / request</th><th>Review</th><th>Freshness</th><th>Actions</th></tr></thead>
<tbody id="queue-rows"></tbody></table></div>
<div id="queue-empty" class="empty">{"Loading your review queue…" if enabled else "Queue is not configured."}</div>
</main>
<script>window.PR_BASE_URL = {json.dumps(base_url).replace('<', chr(92) + 'u003c')}; window.PR_QUEUE_TOKEN = {json.dumps(token)}; window.PR_QUEUE_ENABLED = {json.dumps(enabled)};</script>
<script src="{html.escape(_asset_url(base_url, 'queue.js'), quote=True)}"></script>
</body></html>'''
