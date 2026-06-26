/**
 * Pipeline progress — progress bars on Search / Score buttons (polls /jobs/status/)
 */
(function () {
  var statusUrl = document.body.getAttribute("data-status-url");
  var toast = document.getElementById("pipeline-toast");
  var modal = document.getElementById("pipeline-modal");
  if (!statusUrl) return;

  var pollMsRunning = 5000;
  var pollMsIdle = 30000;
  var timerId = null;
  var lastState = "";
  var lastScoreProgress = -1;
  var lastLiveCount = -1;
  var toastTimer = null;
  var completionShown = false;
  var idlePollCount = 0;

  function formatClock(totalSeconds) {
    var s = Math.max(0, parseInt(totalSeconds, 10) || 0);
    var m = Math.floor(s / 3600) > 0 ? Math.floor(s / 3600) + ":" : "";
    var min = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    if (m) {
      return (
        m +
        String(min).padStart(2, "0") +
        ":" +
        String(sec).padStart(2, "0")
      );
    }
    return String(min).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
  }

  function renderTopbarStatChips(data) {
    if (data.cache_raw_total == null) return;
    if (window.JOBS_HUB && typeof window.JOBS_HUB.getBrowseStats === "function") {
      data = window.JOBS_HUB.getBrowseStats(data);
    }
    var listCount = document.querySelectorAll("#jobs-list .job-card").length;
    var jobs = Math.max(data.cache_raw_total || 0, listCount);
    var good = data.good_fits_total != null ? data.good_fits_total : 0;
    var scored = data.scored_total || 0;
    var waiting =
      data.unscored_total != null
        ? Math.max(data.unscored_total, Math.max(0, jobs - scored))
        : Math.max(0, jobs - scored);
    var stats = Object.assign({}, data, {
      cache_raw_total: jobs,
      unscored_total: waiting,
    });
    var jobsEl = document.querySelector("[data-stat-jobs]");
    var goodEl = document.querySelector("[data-stat-good]");
    var waitEl = document.querySelector("[data-stat-waiting]");
    if (jobsEl) jobsEl.textContent = String(jobs);
    if (goodEl) goodEl.textContent = String(good);
    if (waitEl) waitEl.textContent = String(waiting);
    updateBrowseDropdownCounts(stats);
    syncScoreButtonFromStats(stats);
    return stats;
  }

  function updateTopbarSummary(data) {
    renderTopbarStatChips(data);
  }

  window.renderTopbarStatChips = renderTopbarStatChips;

  function updateBrowseDropdownCounts(data) {
    var menu = document.getElementById("browse-menu");
    if (!menu || data.cache_raw_total == null) return;
    if (window.JOBS_HUB && typeof window.JOBS_HUB.getBrowseStats === "function") {
      data = window.JOBS_HUB.getBrowseStats(data);
    }
    var byView = {
      good: data.good_fits_total || 0,
      it_good: data.it_good_total || 0,
      non_it_good: data.non_it_good_total || 0,
      all: data.cache_raw_total || 0,
      it: data.it_total || 0,
      non_it: data.non_it_total || 0,
      unscored: data.unscored_total || 0,
      degree: data.degree_ready_total || 0,
      full: data.full_match_total || 0,
    };
    menu.querySelectorAll(".topbar-dropdown-link").forEach(function (link) {
      var view = "all";
      try {
        var u = new URL(link.href, window.location.origin);
        view = u.searchParams.get("view") || "all";
      } catch (e) {}
      var countEl = link.querySelector(".browse-count");
      if (countEl && byView[view] != null) {
        var n = byView[view] || 0;
        countEl.textContent = String(n);
        countEl.classList.toggle("is-positive", n > 0);
      }
    });
    var note = menu.querySelector(".browse-dropdown-note");
    if (note) {
      var all = data.cache_raw_total || 0;
      var scored = data.scored_total || 0;
      var unscored = data.unscored_total || 0;
      note.textContent = scored + " scored · " + unscored + " wait · " + all + " total";
    }
  }

  window.updateBrowseDropdownCounts = updateBrowseDropdownCounts;

  function syncScoreButtonFromStats(data) {
    var scoreBtn = document.querySelector('[data-pipeline-btn="score"]');
    if (!scoreBtn) return;
    if (document.body.getAttribute("data-pipeline-running") === "1") return;
    if (window.JOBS_HUB && typeof window.JOBS_HUB.getBrowseStats === "function") {
      data = window.JOBS_HUB.getBrowseStats(data || {});
    }
    var waiting = data.unscored_total != null ? data.unscored_total : 0;
    scoreBtn.disabled = waiting <= 0;
    var label = waiting > 0 ? "Score " + waiting : "Score AI";
    scoreBtn.dataset.labelDefault = label;
    var labelEl = scoreBtn.querySelector(".btn-label");
    if (labelEl) labelEl.textContent = label;
    scoreBtn.setAttribute(
      "data-tip",
      waiting > 0
        ? "Compare unscored jobs to your CV — IT jobs scored first"
        : "All jobs scored — click Find jobs for new listings"
    );
  }

  function setButtonProgress(btn, active, pct, label, statusText) {
    if (!btn) return;
    var fill = btn.querySelector(".topbar-btn-fill");
    var status = btn.querySelector(".topbar-btn-status");
    var labelEl = btn.querySelector(".btn-label");
    btn.classList.toggle("is-pipeline-active", !!active);
    if (fill) {
      fill.style.width = active ? Math.min(100, Math.max(0, pct)) + "%" : "0%";
    }
    if (status) {
      if (active && statusText) {
        status.hidden = false;
        status.textContent = statusText;
      } else {
        status.hidden = true;
        status.textContent = "";
      }
    }
    if (labelEl) {
      if (active && label) {
        labelEl.textContent = label;
      } else if (btn.dataset.labelDefault) {
        labelEl.textContent = btn.dataset.labelDefault;
      } else if (btn.dataset.pipelineBtn === "search") {
        labelEl.textContent = "Find jobs";
      }
    }
  }

  function updateActionButtons(data) {
    var searchBtn = document.querySelector('[data-pipeline-btn="search"]');
    var scoreBtn = document.querySelector('[data-pipeline-btn="score"]');
    var cancelForm = document.getElementById("topbar-pipeline-cancel");
    var running = data.state === "running";
    var phase = data.phase || "";

    if (cancelForm) {
      cancelForm.hidden = !running;
    }

    if (!running) {
      setButtonProgress(searchBtn, false, 0);
      setButtonProgress(scoreBtn, false, 0);
      if (searchBtn) searchBtn.disabled = false;
      syncScoreButtonFromStats(data);
      return;
    }

    if (searchBtn) searchBtn.disabled = true;
    if (scoreBtn) scoreBtn.disabled = true;

    var pct = data.percent || 0;
    if (data.total > 0) {
      pct = Math.round((100 * data.progress) / data.total);
    } else if (data.live_count > 0) {
      pct = Math.min(92, 10 + Math.floor(data.live_count / 2));
    } else if (phase === "score") {
      pct = Math.max(pct, 5);
    } else {
      pct = Math.max(pct, 8);
    }

    var clock = formatClock(data.elapsed_seconds);

    if (phase === "score") {
      setButtonProgress(searchBtn, false, 0);
      var runDone = data.progress || 0;
      var runTotal = data.total || 0;
      var scoreStatus =
        runTotal > 0
          ? runDone + "/" + runTotal + " · " + pct + "% · " + clock
          : pct + "% · " + clock;
      setButtonProgress(scoreBtn, true, pct, "Scoring…", scoreStatus);
    } else {
      setButtonProgress(scoreBtn, false, 0);
      var found = data.live_count || 0;
      var searchStatus = found
        ? found + " found · " + pct + "% · " + clock
        : pct + "% · " + clock;
      setButtonProgress(searchBtn, true, pct, "Searching…", searchStatus);
    }
  }

  var pollMode = "";

  function stopPolling() {
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
    pollMode = "";
  }

  function startPolling(running) {
    var mode = running ? "running" : "idle";
    if (timerId && pollMode === mode) return;
    stopPolling();
    pollMode = mode;
    timerId = setInterval(poll, running ? pollMsRunning : pollMsIdle);
  }

  function triggerListRefresh(data) {
    document.dispatchEvent(new CustomEvent("jobs-score-tick", { detail: data || {} }));
    if (!window.JOBS_HUB || typeof window.JOBS_HUB.reloadFromServer !== "function") return;
    if (data && data.phase === "search") return;
    var listCount = document.querySelectorAll("#jobs-list .job-card").length;
    if (listCount > 0 && !(data && data.live_count)) return;
    window.JOBS_HUB.reloadFromServer({ merge: true, force: !!(data && data.live_count) });
  }

  function showToast(message, isError) {
    if (!toast) return;
    toast.textContent = message || "";
    toast.classList.toggle("is-error", !!isError);
    toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.hidden = true;
    }, 6000);
  }

  function showCompletionToast(message, phase) {
    if (completionShown) return;
    completionShown = true;
    var isAi = phase === "score" || /analy|scor|ai/i.test(message || "");
    showToast(
      (isAi ? "Scoring complete — " : "Search complete — ") +
        (message || "Your job list is updated."),
      false
    );
  }

  function updateLiveBanner(data) {
    var banner = document.getElementById("pipeline-live-banner");
    if (!banner) return;
    var titleEl = document.getElementById("pipeline-banner-title");
    var detailEl = document.getElementById("pipeline-banner-detail");
    var running = data && data.state === "running";
    if (!running) {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    var phase = data.phase || "";
    var label = data.label || (phase === "score" ? "Scoring with AI" : "Searching job boards");
    if (titleEl) titleEl.textContent = label + "…";
    if (detailEl) {
      var parts = [];
      if (data.live_count) parts.push(data.live_count + " found");
      if (data.total > 0) parts.push((data.progress || 0) + "/" + data.total);
      if (data.message) parts.push(data.message);
      detailEl.textContent = parts.join(" · ");
    }
  }

  function updateUI(data) {
    var running = data.state === "running";
    var failed = data.state === "failed";
    var completed = data.state === "completed";

    var sidebar = document.getElementById("pipeline-sidebar");
    if (sidebar) sidebar.hidden = true;

    if (!running) {
      updateLiveBanner(data);
      updateActionButtons(data);
      stopPolling();
      document.body.removeAttribute("data-pipeline-running");
      if (window.JOBS_HUB && typeof window.JOBS_HUB.applyStatusJobPreviews === "function") {
        window.JOBS_HUB.applyStatusJobPreviews(data);
      }
      if (lastState === "running" && completed) {
        showCompletionToast(data.message || "Finished.", data.phase || "");
        triggerListRefresh(data);
        updateTopbarSummary(data);
      } else if (lastState === "running" && failed) {
        showToast(data.error || data.message || "Task failed", true);
      } else if (idlePollCount === 0 || data.cache_raw_total != null) {
        updateTopbarSummary(data);
      }
      lastState = data.state || "idle";
      lastScoreProgress = -1;
      lastLiveCount = -1;
      if (data.state !== "running") {
        document.body.removeAttribute("data-pipeline-running");
      }
      idlePollCount++;
      if (pollMode !== "idle") {
        startPolling(false);
      }
      return;
    }

    lastState = "running";
    completionShown = false;
    idlePollCount = 0;
    document.body.setAttribute("data-pipeline-running", "1");

    updateLiveBanner(data);
    updateTopbarSummary(data);
    updateActionButtons(data);
    if (window.JOBS_HUB && typeof window.JOBS_HUB.applyStatusJobPreviews === "function") {
      window.JOBS_HUB.applyStatusJobPreviews(data);
    }
    if (window.JOBS_HUB && typeof window.JOBS_HUB.refreshLiveJobs === "function") {
      if (!document.querySelectorAll("#jobs-list .job-card").length) {
        window.JOBS_HUB.refreshLiveJobs();
      }
    }
    if (data.live_count !== lastLiveCount) {
      lastLiveCount = data.live_count;
      triggerListRefresh(data);
    }
    if (pollMode !== "running") {
      startPolling(true);
    }
  }

  function poll() {
    fetch(statusUrl, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        return r.json();
      })
      .then(updateUI)
      .catch(function () {});
  }

  if (document.body.getAttribute("data-pipeline-running") === "1") {
    lastState = "idle";
  }

  document.addEventListener("jobs-pipeline-cancelled", function () {
    stopPolling();
    lastState = "idle";
    completionShown = false;
    document.body.removeAttribute("data-pipeline-running");
    updateLiveBanner({ state: "idle" });
    updateActionButtons({ state: "idle", phase: "" });
  });

  document.addEventListener("jobs-pipeline-started", function () {
    lastState = "idle";
    completionShown = false;
    idlePollCount = 0;
    poll();
    startPolling(true);
  });

  poll();
  startPolling(document.body.getAttribute("data-pipeline-running") === "1");
})();
