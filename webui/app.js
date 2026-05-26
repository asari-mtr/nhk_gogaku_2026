// NHK 語学ダウンローダ Web UI
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const fmtDate = (iso) => {
  if (!iso) return "―";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { dateStyle: "short", timeStyle: "short" });
};
const fmtDateOnly = (iso) => {
  if (!iso) return "―";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", weekday: "short" });
};

const api = {
  status: () => fetch("/api/status").then((r) => r.json()),
  series: () => fetch("/api/series").then((r) => r.json()),
  programs: (force = false) =>
    fetch("/api/programs" + (force ? "?force=1" : "")).then((r) => r.json()),
  episodes: () => fetch("/api/episodes").then((r) => r.json()),
  feeds: () => fetch("/api/feeds").then((r) => r.json()),
  logs: () => fetch("/api/logs/recent").then((r) => r.json()),
  saveSeries: (series) =>
    fetch("/api/series", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series }),
    }).then((r) => r.json()),
  runDL: () => fetch("/api/dl/run", { method: "POST" }).then((r) => r.json()),
  retryDL: (episode_id, series_id) =>
    fetch("/api/dl/retry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ episode_id, series_id }),
    }).then((r) => r.json()),
};

// ─── ステータスピル ───
async function loadStatus() {
  let s;
  try { s = await api.status(); } catch { return; }
  const pill = $("#status-pill");
  const dot = pill.querySelector(".dot");
  const text = pill.querySelector(".pill-text");
  if (s.dl_running) {
    dot.className = "dot warn";
    text.textContent = "DL中";
    pill.title = "ダウンロード実行中";
  } else if (s.dl_state === "failed") {
    dot.className = "dot ng";
    text.textContent = "失敗";
    pill.title = "前回のDLは失敗";
  } else {
    dot.className = "dot ok";
    text.textContent = "稼働中";
    pill.title = "サーバ稼働中";
  }
  // KPI 更新
  $("#kpi-last").textContent = s.dl_ended_at
    ? fmtDate(s.dl_ended_at)
    : s.dl_started_at
    ? "実行中"
    : "未実行";
}

// ─── ホーム: KPI と 直近エピソード + 警告 ───
async function loadHome() {
  const [seriesResp, epsResp] = await Promise.all([api.series(), api.episodes()]);
  $("#kpi-series").textContent = seriesResp.series.length;
  $("#kpi-episodes").textContent = epsResp.episodes.length;

  // 警告セクション
  const shortEps = epsResp.episodes.filter((e) => e.validation === "short");
  const warnSec = $("#warn-section");
  if (shortEps.length > 0) {
    warnSec.classList.remove("hidden");
    $("#warn-count").textContent = `${shortEps.length} 件`;
    $("#warn-list").innerHTML = shortEps.map(renderWarnRow).join("");
  } else {
    warnSec.classList.add("hidden");
  }

  // 直近5件
  const root = $("#home-episodes");
  if (!epsResp.episodes.length) {
    root.innerHTML = `<p class="muted small">まだダウンロード済みのエピソードはありません。</p>`;
    return;
  }
  const recent = epsResp.episodes.slice(0, 5);
  root.innerHTML = recent.map(renderEpisodeRowSimple).join("");
}

function renderWarnRow(ep) {
  const ratio = ep.expected_duration_s
    ? Math.round((ep.actual_duration_s / ep.expected_duration_s) * 100)
    : null;
  const confirmedLabel = ep.short_confirmed
    ? `<span class="badge failed" title="再DLしても短かったため確定">確定</span>`
    : "";
  return `
    <div class="warn-row">
      <div class="warn-info">
        <div class="ep-title">${escapeHtml(ep.title || "")} ${confirmedLabel}</div>
        <div class="muted small">${escapeHtml(ep.series_name)} · ${escapeHtml(fmtDateOnly(ep.broadcast_date))}</div>
        <div class="muted small">
          実 ${fmtSecs(ep.actual_duration_s)} / 期待 ${fmtSecs(ep.expected_duration_s)}
          ${ratio != null ? `(${ratio}%)` : ""}
        </div>
      </div>
      <button class="secondary" data-act="retry" data-ep="${escapeAttr(ep.episode_id)}" data-series="${escapeAttr(ep.series_id)}">
        ↻ 再取得
      </button>
    </div>`;
}

function renderEpisodeRowSimple(ep) {
  const warn = ep.validation === "short" ? ` <span class="badge failed" title="DL不完全 or 短縮配信">⚠</span>` : "";
  return `
    <div class="ep-row${ep.validation === "short" ? " ep-row-warn" : ""}">
      <div class="ep-head">
        <div>
          <div class="ep-title">${escapeHtml(ep.title || "")}${warn}</div>
          <div class="muted small">${escapeHtml(ep.series_name)}</div>
        </div>
        <div class="ep-date">${escapeHtml(fmtDateOnly(ep.broadcast_date))}</div>
      </div>
      <audio controls preload="none" src="${escapeAttr(ep.url)}"></audio>
    </div>`;
}

// ─── 番組一覧 ───
async function loadSeries() {
  const d = await api.series();
  const root = $("#series-list");
  if (!d.series.length) {
    root.innerHTML = `<p class="muted small">番組が登録されていません。「番組を編集」から追加してください。</p>`;
    return;
  }
  root.innerHTML = d.series
    .map((s) => {
      const nhkUrl = s.page_url || `https://www.nhk.jp/p/rs/${s.id}/`;
      return `
    <div class="series-row">
      <div class="info">
        <div class="name">${escapeHtml(s.name)}</div>
        <div class="meta">
          <span class="chip ${s.enabled ? "on" : ""}">${s.enabled ? "✓ 有効" : "停止中"}</span>
          ${s.group_by_weekday ? `<span class="chip">曜日別</span>` : ""}
          <span>DL済 ${s.downloaded_count} 本</span>
        </div>
      </div>
      <a class="nhk-link" href="${escapeAttr(nhkUrl)}"
         target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"
         title="NHK 公式番組ページを開く (リファラ送信なし)">
        NHK公式 ↗
      </a>
    </div>`;
    })
    .join("");
}

// ─── ホスト切替 ───
const HOST_MODES = ["short", "local", "ip"];
const HOST_LABELS = { short: "ホスト名", local: ".local", ip: "IPアドレス" };
function getHostMode() {
  const m = localStorage.getItem("hostMode") || "short";
  return HOST_MODES.includes(m) ? m : "short";
}
function setHostMode(mode) {
  localStorage.setItem("hostMode", mode);
  updateHostToggleUI();
  loadFeeds();
}
function cycleHostMode() {
  const i = HOST_MODES.indexOf(getHostMode());
  setHostMode(HOST_MODES[(i + 1) % HOST_MODES.length]);
}
function updateHostToggleUI() {
  const btn = $("#host-toggle");
  if (!btn) return;
  btn.textContent = "URL: " + HOST_LABELS[getHostMode()];
}
function pickUrl(feed) {
  const m = getHostMode();
  if (m === "ip") return feed.url_ip;
  if (m === "local") return feed.url_local;
  return feed.url_short || feed.url_local || feed.url_ip;
}
function pickPodcastUrl(feed) {
  const m = getHostMode();
  if (m === "ip") return feed.podcast_ip;
  if (m === "local") return feed.podcast_local;
  return feed.podcast_short || feed.podcast_local || feed.podcast_ip;
}

// ─── フィード一覧 ───
async function loadFeeds() {
  const d = await api.feeds();
  const root = $("#feeds-list");
  if (!d.feeds.length) {
    root.innerHTML = `<p class="muted small">まだフィードがありません。DLを実行してください。</p>`;
    return;
  }
  root.innerHTML = d.feeds
    .map((f) => {
      const url = pickUrl(f);
      const podcastUrl = pickPodcastUrl(f);
      return `
    <div class="feed-row">
      <div class="title">${escapeHtml(f.name)}</div>
      <div class="url-text">${escapeHtml(url)}</div>
      <div class="actions">
        <a class="btn primary" href="${escapeAttr(podcastUrl)}">
          🎧 Apple Podcasts で開く
        </a>
        <button class="primary" data-act="qr"
                data-url-http="${escapeAttr(url)}"
                data-url-podcast="${escapeAttr(podcastUrl)}"
                data-title="${escapeAttr(f.name)}">QRコード</button>
        <button class="secondary" data-act="copy" data-url="${escapeAttr(url)}">📋 URLコピー</button>
      </div>
    </div>`;
    })
    .join("");
}

// ─── エピソード一覧 (履歴タブ) ───
const EP_PER_SERIES = 5;

function fmtSecs(s) {
  if (s == null) return "?";
  const n = Math.round(s);
  const m = Math.floor(n / 60);
  const r = n % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}
function renderEpisodeRow(ep) {
  let warn = "";
  if (ep.validation === "short") {
    warn = `<div class="ep-warn">⚠ DLが不完全か元配信が短い (実 ${fmtSecs(ep.actual_duration_s)} / 期待 ${fmtSecs(ep.expected_duration_s)})</div>`;
  }
  const durLabel = ep.actual_duration_s != null ? ` · ${fmtSecs(ep.actual_duration_s)}` : "";
  return `
    <div class="ep-row${ep.validation === "short" ? " ep-row-warn" : ""}">
      <div class="ep-head">
        <div class="ep-title">${escapeHtml(ep.title || "")}</div>
        <div class="ep-date">${escapeHtml(fmtDateOnly(ep.broadcast_date))}${durLabel}</div>
      </div>
      ${ep.description ? `<div class="ep-desc">${escapeHtml(ep.description)}</div>` : ""}
      ${warn}
      <audio controls preload="none" src="${escapeAttr(ep.url)}"></audio>
    </div>`;
}

async function loadEpisodes() {
  const d = await api.episodes();
  $("#ep-count").textContent = `全 ${d.episodes.length} 本`;
  const root = $("#episodes");
  if (!d.episodes.length) {
    root.innerHTML = `<p class="muted small">DL済みエピソードがありません。</p>`;
    return;
  }
  const groups = new Map();
  for (const ep of d.episodes) {
    if (!groups.has(ep.series_id)) {
      groups.set(ep.series_id, { name: ep.series_name, episodes: [] });
    }
    groups.get(ep.series_id).episodes.push(ep);
  }
  let html = "";
  for (const [sid, g] of groups) {
    const total = g.episodes.length;
    const head = g.episodes.slice(0, EP_PER_SERIES);
    const rest = g.episodes.slice(EP_PER_SERIES);
    html += `<div class="ep-group">
      <h3 class="ep-group-head">
        ${escapeHtml(g.name)}
        <span class="muted small">${total} 本</span>
      </h3>`;
    html += head.map(renderEpisodeRow).join("");
    if (rest.length > 0) {
      html += `
        <details class="ep-more">
          <summary>その他のエピソード (${rest.length} 件)</summary>
          ${rest.map(renderEpisodeRow).join("")}
        </details>`;
    }
    html += `</div>`;
  }
  root.innerHTML = html;
}

// ─── ログ ───
async function loadLogs() {
  const d = await api.logs();
  $("#log-date").textContent = d.date;
  const el = $("#recent-log");
  if (!d.lines.length) {
    el.textContent = "(本日はまだログがありません)";
    return;
  }
  el.textContent = d.lines.slice(-20).join("\n");
  el.scrollTop = el.scrollHeight;
}

// ─── DL実行 + SSE ───
let sseSource = null;
async function runDL() {
  const btn = $("#btn-run");
  const result = await api.runDL();
  $("#dl-panel").classList.remove("hidden");
  if (!result.started) {
    appendLog("(既に実行中です。進捗に接続します)");
  } else {
    $("#dl-log").textContent = "";
  }
  $("#dl-state").textContent = "実行中";
  $("#dl-state").className = "badge running";
  btn.disabled = true;
  btn.innerHTML = "実行中…";

  if (sseSource) sseSource.close();
  sseSource = new EventSource("/api/dl/stream");
  sseSource.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === "log") {
      appendLog(msg.line);
    } else if (msg.type === "end") {
      $("#dl-state").textContent = msg.state === "done" ? "完了" : "失敗";
      $("#dl-state").className = "badge " + msg.state;
      btn.disabled = false;
      btn.innerHTML = '<span aria-hidden="true">▶</span>&nbsp;DL実行';
      sseSource.close();
      sseSource = null;
      // 全部リロード
      loadStatus(); loadHome(); loadSeries(); loadEpisodes(); loadFeeds(); loadLogs();
    }
  };
  sseSource.onerror = () => {
    btn.disabled = false;
    btn.innerHTML = '<span aria-hidden="true">▶</span>&nbsp;DL実行';
    if (sseSource) { sseSource.close(); sseSource = null; }
  };
}

function appendLog(line) {
  const log = $("#dl-log");
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
}

// ─── 個別エピソードの再取得 ───
async function retryEpisode(btn) {
  const ep = btn.dataset.ep;
  const sid = btn.dataset.series;
  btn.disabled = true;
  btn.textContent = "再取得中…";
  try {
    const r = await api.retryDL(ep, sid);
    if (r.error) {
      alert("再取得失敗: " + r.error);
      btn.disabled = false;
      btn.textContent = "↻ 再取得";
      return;
    }
    // DL進捗パネルを表示してSSE接続 (runDL と同じ接続)
    $("#dl-panel").classList.remove("hidden");
    $("#dl-log").textContent = "";
    $("#dl-state").textContent = "実行中";
    $("#dl-state").className = "badge running";
    $("#btn-run").disabled = true;
    $("#btn-run").innerHTML = "実行中…";
    if (sseSource) sseSource.close();
    sseSource = new EventSource("/api/dl/stream");
    sseSource.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "log") {
        appendLog(msg.line);
      } else if (msg.type === "end") {
        $("#dl-state").textContent = msg.state === "done" ? "完了" : "失敗";
        $("#dl-state").className = "badge " + msg.state;
        $("#btn-run").disabled = false;
        $("#btn-run").innerHTML = '<span aria-hidden="true">▶</span>&nbsp;DL実行';
        sseSource.close();
        sseSource = null;
        loadStatus(); loadHome(); loadSeries(); loadEpisodes(); loadFeeds(); loadLogs();
      }
    };
    sseSource.onerror = () => {
      $("#btn-run").disabled = false;
      $("#btn-run").innerHTML = '<span aria-hidden="true">▶</span>&nbsp;DL実行';
      if (sseSource) { sseSource.close(); sseSource = null; }
    };
  } catch (e) {
    alert("再取得失敗: " + e.message);
    btn.disabled = false;
    btn.textContent = "↻ 再取得";
  }
}

// ─── 番組編集モーダル ───
async function openSeriesModal() {
  $("#modal").classList.remove("hidden");
  const progRoot = $("#modal-programs");
  progRoot.innerHTML = "<p class='muted small'>取得中…</p>";
  const [progsResp, currentResp] = await Promise.all([api.programs(), api.series()]);
  const enabledIds = new Set(currentResp.series.filter((s) => s.enabled).map((s) => s.id));
  const weekdayIds = new Set(currentResp.series.filter((s) => s.group_by_weekday).map((s) => s.id));
  const nameById = {};
  const langOrder = ["english","chinese","hangeul","french","german","italian","spanish","portuguese","russian","other"];
  let html = "";
  for (const lang of langOrder) {
    const g = progsResp[lang];
    if (!g) continue;
    html += `<div class="lang-group"><div class="lang-label">${escapeHtml(g.label)}</div>`;
    for (const p of g.programs) {
      nameById[p.id] = p.name;
      const ch = enabledIds.has(p.id) ? "checked" : "";
      html += `<label class="check-row">
        <input type="checkbox" data-name="${escapeAttr(p.name)}" data-id="${escapeAttr(p.id)}" ${ch}>
        <span class="pname">${escapeHtml(p.name)}</span>
        <span class="pid">${escapeHtml(p.id)}</span>
      </label>`;
    }
    html += `</div>`;
  }
  progRoot.innerHTML = html;
  progRoot._nameById = nameById;
  const updateWeekday = () => {
    const checked = [...progRoot.querySelectorAll("input:checked")];
    const wkRoot = $("#modal-weekday");
    if (!checked.length) {
      wkRoot.innerHTML = "<p class='muted small'>有効な番組がありません。</p>";
      return;
    }
    wkRoot.innerHTML = checked.map((cb) => {
      const id = cb.dataset.id, name = cb.dataset.name;
      const ch = weekdayIds.has(id) ? "checked" : "";
      return `<label class="check-row">
        <input type="checkbox" data-id="${escapeAttr(id)}" ${ch}>
        <span class="pname">${escapeHtml(name)}</span>
      </label>`;
    }).join("");
  };
  updateWeekday();
  progRoot.addEventListener("change", updateWeekday);
}

function closeSeriesModal() { $("#modal").classList.add("hidden"); }

async function saveSeriesModal() {
  const progRoot = $("#modal-programs");
  const wkRoot = $("#modal-weekday");
  const nameById = progRoot._nameById || {};
  const selectedIds = [...progRoot.querySelectorAll("input:checked")].map((cb) => cb.dataset.id);
  const wkIds = new Set([...wkRoot.querySelectorAll("input:checked")].map((cb) => cb.dataset.id));
  const newSeries = selectedIds.map((id) => ({
    id, name: nameById[id] || id,
    page_url: `https://www.nhk.jp/p/rs/${id}/plus/`,
    enabled: true,
    ...(wkIds.has(id) ? { group_by_weekday: true } : {}),
  }));
  const result = await api.saveSeries(newSeries);
  if (result.ok) {
    closeSeriesModal();
    loadSeries(); loadHome(); loadFeeds();
  }
}

// ─── QR ───
function renderQR(canvasEl, url) {
  canvasEl.innerHTML = "";
  if (typeof qrcode !== "function") {
    canvasEl.innerHTML = `<p class="muted small">QRライブラリの読み込みに失敗しました。<br>下のURLを長押しコピーしてください。</p>`;
    return;
  }
  try {
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    canvasEl.innerHTML = qr.createImgTag(6, 2);
    const img = canvasEl.querySelector("img");
    if (img) { img.style.maxWidth = "100%"; img.style.height = "auto"; img.alt = "QR: " + url; }
  } catch (e) {
    canvasEl.innerHTML = `<p class="muted small">QR生成失敗: ${escapeHtml(e.message)}</p>`;
  }
}

function showQR(title, urls) {
  // urls = { http: "...", podcast: "..." }
  $("#qr-title").textContent = title;
  $("#qr-url-podcast").textContent = urls.podcast;
  $("#qr-url-http").textContent = urls.http;
  $("#qr-open-podcast").href = urls.podcast;
  $("#qr-modal").classList.remove("hidden");
  $("#qr-modal").dataset.urlHttp = urls.http;
  $("#qr-modal").dataset.urlPodcast = urls.podcast;
  renderQR($("#qr-canvas-podcast"), urls.podcast);
  renderQR($("#qr-canvas-http"), urls.http);
}
function closeQR() { $("#qr-modal").classList.add("hidden"); }

// ─── タブ ───
function activateTab(name) {
  $$(".tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.setAttribute("aria-selected", on);
  });
  $$(".tab-panel").forEach((p) => {
    p.classList.toggle("hidden", p.id !== `panel-${name}`);
  });
  localStorage.setItem("activeTab", name);
  // タブ初期ロード
  if (name === "home") { loadHome(); loadLogs(); }
  if (name === "series") loadSeries();
  if (name === "feeds") loadFeeds();
  if (name === "history") loadEpisodes();
  // スクロールトップ
  window.scrollTo({ top: 0, behavior: "instant" });
}

// ─── ヘルパ ───
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
async function copyToClipboard(text) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove();
  }
}

// ─── 委譲クリック ───
document.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) { activateTab(tab.dataset.tab); return; }
  const jump = e.target.closest("[data-jump]");
  if (jump) { activateTab(jump.dataset.jump); return; }
  const act = e.target.closest("button[data-act]");
  if (act) {
    if (act.dataset.act === "copy") {
      copyToClipboard(act.dataset.url).then(() => {
        const orig = act.textContent;
        act.textContent = "✓ コピー済";
        setTimeout(() => (act.textContent = orig), 1500);
      });
    } else if (act.dataset.act === "qr") {
      showQR(act.dataset.title, {
        http: act.dataset.urlHttp,
        podcast: act.dataset.urlPodcast,
      });
    } else if (act.dataset.act === "retry") {
      retryEpisode(act);
    }
    return;
  }
  // QRモーダル内 URL コピー (data-copy="podcast" / "http")
  const copyBtn = e.target.closest("button[data-copy]");
  if (copyBtn) {
    const modal = $("#qr-modal");
    const url = copyBtn.dataset.copy === "podcast" ? modal.dataset.urlPodcast : modal.dataset.urlHttp;
    copyToClipboard(url).then(() => {
      const orig = copyBtn.textContent;
      copyBtn.textContent = "✓ コピー済";
      setTimeout(() => (copyBtn.textContent = orig), 1500);
    });
  }
});

// ─── 初期化 ───
document.addEventListener("DOMContentLoaded", () => {
  $("#btn-run").addEventListener("click", runDL);
  $("#btn-edit-series").addEventListener("click", openSeriesModal);
  $("#modal-close").addEventListener("click", closeSeriesModal);
  $("#modal-cancel").addEventListener("click", closeSeriesModal);
  $("#modal-save").addEventListener("click", saveSeriesModal);
  $("#qr-close").addEventListener("click", closeQR);
  $("#host-toggle").addEventListener("click", cycleHostMode);
  $("#dl-close").addEventListener("click", () => $("#dl-panel").classList.add("hidden"));

  updateHostToggleUI();
  // 前回のタブを復元
  const tab = localStorage.getItem("activeTab") || "home";
  activateTab(tab);
  loadStatus();
  // 30秒ごとにステータスを更新
  setInterval(loadStatus, 30000);
});
