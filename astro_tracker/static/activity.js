// Activity panel: every background job, on every page.
//
// Shows what is running, what is waiting for its turn, and a cancel
// button for each. Include with <script src="/static/activity.js" defer>;
// the panel is inserted at the top of the page and hides itself when
// nothing is running or waiting.
(function () {
    const POLL_BUSY_MS = 2000;
    const POLL_IDLE_MS = 10000;

    const style = document.createElement("style");
    style.textContent = `
        #activityPanel { font: 0.85rem/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: var(--bg-secondary, #1a1f2e); color: var(--text-primary, #f3f4f6);
            border-bottom: 1px solid var(--border-color, #374151); padding: 0.5rem 1rem; }
        #activityPanel[hidden] { display: none; }
        #activityPanel .act-head { display: flex; align-items: center; gap: 0.75rem; }
        #activityPanel .act-title { font-weight: 600; }
        #activityPanel .act-spacer { flex: 1; }
        #activityPanel ul { list-style: none; margin: 0.35rem 0 0; padding: 0; }
        #activityPanel li { display: flex; align-items: center; gap: 0.6rem; padding: 0.2rem 0; min-width: 0; }
        #activityPanel .act-state { flex: none; width: 4.6rem; font-size: 0.7rem; text-transform: uppercase;
            letter-spacing: 0.05em; color: var(--text-secondary, #9ca3af); }
        #activityPanel .act-running .act-state { color: #10b981; }
        #activityPanel .act-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        #activityPanel .act-detail { flex: none; color: var(--text-secondary, #9ca3af); font-variant-numeric: tabular-nums; }
        #activityPanel button { flex: none; font: inherit; font-size: 0.75rem; padding: 0.15rem 0.6rem; cursor: pointer;
            background: transparent; color: var(--text-primary, #f3f4f6);
            border: 1px solid var(--border-color, #374151); border-radius: 4px; }
        #activityPanel button:hover { border-color: #ef4444; color: #ef4444; }
        #activityPanel button:disabled { opacity: 0.5; cursor: default; }
    `;

    const panel = document.createElement("div");
    panel.id = "activityPanel";
    panel.hidden = true;
    panel.setAttribute("aria-live", "polite");

    function esc(text) {
        return String(text ?? "").replace(/[&<>"']/g, (c) =>
            ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
    }

    // One short line of progress, from whatever the job reports.
    function detail(job) {
        const p = job.progress || {};
        if (job.kind === "hash") {
            const done = (p.hashed ?? 0) + (p.failed ?? 0);
            return p.total ? `${done} of ${p.total} files` : "";
        }
        if (job.kind === "ingest" || job.kind === "derive") {
            if (p.step === "derive") return "regrouping the library";
            if (p.step === "scan" && p.counts) return `${p.counts.total_seen ?? 0} files read`;
            return "";
        }
        if (job.kind === "pull") return p.copied != null ? `${p.copied} files copied` : "";
        if (job.kind === "analysis") return p.total ? `${p.processed ?? 0} of ${p.total} files` : "";
        return "";
    }

    function row(job, state) {
        const shown = state === "waiting" && job.paused ? "paused" : state;
        return `<li class="act-${state}">
            <span class="act-state">${shown}</span>
            <span class="act-label" title="${esc(job.label)}">${esc(job.label)}</span>
            <span class="act-detail">${esc(state === "running" ? detail(job) : "")}</span>
            <button type="button" data-cancel="${job.id}">${state === "running" ? "Stop" : "Cancel"}</button>
        </li>`;
    }

    function render(activity) {
        const running = activity.running || [], waiting = activity.waiting || [];
        panel.hidden = running.length + waiting.length === 0;
        if (panel.hidden) return;
        const summary = `${running.length} running` + (waiting.length ? `, ${waiting.length} waiting` : "");
        panel.innerHTML = `
            <div class="act-head">
                <span class="act-title">Activity</span><span class="act-detail">${summary}</span>
                <span class="act-spacer"></span>
                ${waiting.length > 1 ? '<button type="button" data-cancel-waiting>Cancel all waiting</button>' : ""}
            </div>
            <ul>${running.map((j) => row(j, "running")).join("")}${waiting.map((j) => row(j, "waiting")).join("")}</ul>`;
    }

    let timer = null;

    async function refresh() {
        clearTimeout(timer);
        let busy = false;
        try {
            const res = await fetch("/api/jobs");
            if (res.ok) {
                const activity = await res.json();
                render(activity);
                busy = (activity.running || []).length + (activity.waiting || []).length > 0;
                document.dispatchEvent(new CustomEvent("activity", { detail: activity }));
            }
        } catch (e) {
            // The server is unreachable; keep the last view and try again.
        }
        timer = setTimeout(refresh, busy ? POLL_BUSY_MS : POLL_IDLE_MS);
    }

    panel.addEventListener("click", async (event) => {
        const button = event.target.closest("button");
        if (!button) return;
        button.disabled = true;
        const url = button.hasAttribute("data-cancel-waiting")
            ? "/api/jobs/cancel-waiting" : `/api/jobs/${button.dataset.cancel}/cancel`;
        try { await fetch(url, { method: "POST" }); } catch (e) { /* shown on the next refresh */ }
        refresh();
    });

    function mount() {
        document.head.appendChild(style);
        document.body.insertBefore(panel, document.body.firstChild);
        refresh();
    }

    // Pages call this after starting a job so the panel does not wait for its next poll.
    window.refreshActivity = refresh;

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
    else mount();
})();
