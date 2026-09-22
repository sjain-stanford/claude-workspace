// Local review queue. Polling reads cached state; only explicit actions launch work.
(() => {
  "use strict";
  const base = window.PR_BASE_URL || "";
  const byId = (id) => document.getElementById(id);
  const active = new Set(["queued", "preparing", "reviewing", "curating"]);
  let data = { items: [], accounts: [] };
  let loading = false;
  let submitting = false;
  const themes = ["system", "dark-plus", "light"];
  let theme = "system";
  try { theme = localStorage.getItem("pr.theme") || "system"; } catch { /* optional */ }
  function applyTheme() {
    if (theme === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.dataset.theme = theme;
    byId("theme-toggle").textContent = `theme: ${theme}`;
  }
  byId("theme-toggle").addEventListener("click", () => {
    theme = themes[(themes.indexOf(theme) + 1) % themes.length];
    try { localStorage.setItem("pr.theme", theme); } catch { /* optional */ }
    applyTheme();
  });
  applyTheme();

  function node(tag, text, className = "") {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function relativeTime(value) {
    if (!value) return "Never checked";
    const seconds = Math.max(0, (Date.now() - Date.parse(value)) / 1000);
    if (seconds < 60) return "Checked just now";
    if (seconds < 3600) return `Checked ${Math.floor(seconds / 60)}m ago`;
    return `Checked ${Math.floor(seconds / 3600)}h ago`;
  }
  function error(message) {
    byId("queue-error").textContent = message;
    byId("queue-error").hidden = !message;
  }
  function visible(item) {
    const query = byId("queue-search").value.trim().toLowerCase();
    const account = byId("queue-account").value;
    if (account && item.account_key !== account) return false;
    if (query && !`${item.repo} ${item.number} ${item.title || ""} ${item.author || ""}`.toLowerCase().includes(query)) return false;
    const filter = byId("queue-filter").value;
    if (filter !== "all" && item.state && item.state !== "open") return false;
    if (filter === "requested") return item.requested;
    if (filter === "stale") return item.freshness === "stale";
    if (filter === "running") return active.has(item.job?.status);
    if (filter === "attention") return item.requested || item.freshness !== "current" || active.has(item.job?.status) || ["failed", "interrupted"].includes(item.job?.status);
    return true;
  }
  function render() {
    const accounts = byId("queue-accounts");
    accounts.replaceChildren();
    const selected = byId("queue-account").value;
    byId("queue-account").replaceChildren(new Option("All accounts", ""));
    for (const account of data.accounts) {
      byId("queue-account").add(new Option(account.label, account.key));
      const card = node("div", null, `queue-account-card${account.error ? " account-error" : ""}`);
      card.append(node("strong", account.label), node("span", `@${account.login} · ${account.hostname}`, "meta"));
      card.append(node("span", account.error || (data.refreshing ? "Checking GitHub…" : relativeTime(account.checked_at)), account.error ? "error" : "meta"));
      accounts.append(card);
    }
    byId("queue-account").value = selected;
    const rows = data.items.filter(visible);
    byId("queue-count").textContent = `${rows.length} of ${data.items.length} PRs`;
    byId("queue-refresh").disabled = submitting || data.refreshing;
    byId("queue-refresh").textContent = data.refreshing ? "Refreshing…" : "Refresh queue";
    const body = byId("queue-rows");
    body.replaceChildren();
    for (const item of rows) {
      const row = node("tr", null, "session-row");
      const pr = node("td", null, "queue-pr");
      const link = node("a", item.title || `${item.repo} #${item.number}`);
      // Construct URLs from validated identity fields, never arbitrary PR text.
      link.href = `https://${item.account.hostname}/${item.repo}/pull/${item.number}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      pr.append(link, node("div", `${item.repo} #${item.number}${item.author ? ` · ${item.author}` : ""}${item.draft ? " · Draft" : ""}${item.state && item.state !== "open" ? ` · ${item.state}` : ""}`, "sub"));
      const identity = node("td");
      const account = data.accounts.find((a) => a.key === item.account_key);
      identity.append(node("div", account?.label || item.account.login), node("div", item.requested ? `${item.request_kind || "Review"} request` : "Following", "sub"));
      const review = node("td");
      const status = item.job?.status;
      const labels = { queued: "Queued", preparing: "Preparing checkout", reviewing: "Reviewers running", curating: "Curator running", done: "Review complete", failed: "Review failed", interrupted: "Review interrupted" };
      const progress = active.has(status) ? "running" : status === "done" ? "done" : ["failed", "interrupted"].includes(status) ? "failed" : item.session_progress?.status || "pending";
      review.append(node("span", labels[status] || item.session_progress?.label || "Not started", `badge review-progress progress-${progress}`));
      const problem = item.job?.error || item.setup_error;
      if (problem) review.append(node("div", problem, "queue-detail error"));
      const freshness = node("td");
      const freshLabels = { current: "Up to date", stale: "Stale", unknown: "Unknown", unreviewed: "Not reviewed" };
      freshness.append(node("span", freshLabels[item.freshness], `queue-freshness freshness-${item.freshness}`));
      const detail = item.completed_snapshot ? `Reviewed ${item.completed_snapshot.head_sha.slice(0, 8)} · latest ${(item.head_sha || "").slice(0, 8)}` : item.head_sha ? `Latest ${item.head_sha.slice(0, 8)}` : "";
      freshness.append(node("div", detail, "sub mono"), node("div", relativeTime(item.checked_at), "sub"));
      if (item.error) freshness.append(node("div", item.error, "queue-detail error"));
      const actions = node("td", null, "queue-actions");
      if (item.session_id) {
        const open = node("a", "Open review", "queue-open");
        open.href = `${base}/${encodeURIComponent(item.session_id)}`;
        actions.append(open);
      }
      if (item.state === "open") {
        const label = active.has(status) ? "In progress" : ["failed", "interrupted"].includes(status) ? "Retry review" : item.session_id ? (item.freshness === "current" ? "Re-review" : "Refresh & re-review") : "Start review";
        const start = node("button", label);
        start.type = "button";
        start.disabled = submitting || active.has(status) || Boolean(item.setup_error);
        start.addEventListener("click", () => action("start", { key: item.key }));
        actions.append(start);
      }
      row.append(pr, identity, review, freshness, actions);
      body.append(row);
    }
    byId("queue-empty").hidden = rows.length > 0;
    byId("queue-empty").textContent = data.refreshing && !data.items.length ? "Checking your accounts for review requests…" : data.accounts.some((a) => a.error) && !data.items.length ? "Could not load every account. See account details above and refresh to retry." : "No PRs match this view.";
    document.querySelector(".queue-table").hidden = rows.length === 0;
  }
  async function refresh() {
    if (loading || !window.PR_QUEUE_ENABLED) return;
    loading = true;
    try {
      const response = await fetch(`${base}/api/queue`, { cache: "no-store" });
      if (!response.ok) throw new Error(`Could not load queue (${response.status})`);
      data = await response.json();
      render();
    } catch (err) { error(err.message); }
    finally { loading = false; }
  }
  async function action(name, body = {}) {
    submitting = true;
    error("");
    render();
    try {
      const response = await fetch(`${base}/api/queue/${name}`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Peanut-Queue-Token": window.PR_QUEUE_TOKEN },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Action failed (${response.status})`);
    } catch (err) { error(err.message); }
    finally { submitting = false; await refresh(); render(); }
  }
  byId("queue-refresh").addEventListener("click", () => action("refresh"));
  byId("queue-search").addEventListener("input", render);
  byId("queue-account").addEventListener("change", render);
  byId("queue-filter").addEventListener("change", render);
  if (window.PR_QUEUE_ENABLED) {
    refresh();
    setInterval(refresh, 3000);
  } else byId("queue-refresh").disabled = true;
})();
