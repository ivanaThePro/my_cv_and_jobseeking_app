/**
 * Job browser — list + CV match detail (requirements in English).
 */
(function () {
  var dataEl = document.getElementById("jobs-data");
  var listEl = document.getElementById("jobs-list");
  var detailContent = document.getElementById("jobs-detail-content");
  var splitEl = document.getElementById("jobs-split");
  if (!dataEl || !listEl || !detailContent) return;

  var jobs = [];
  var masterJobs = [];
  var selectedId = (window.JOBS_HUB && window.JOBS_HUB.selectedId) || "";
  var byId = {};
  var generatingJobId = "";
  var appliedIds = new Set((window.JOBS_HUB && window.JOBS_HUB.appliedIds) || []);
  var appliedToggleUrl = (window.JOBS_HUB && window.JOBS_HUB.appliedToggleUrl) || "";
  var generateMaterialsUrl =
    (window.JOBS_HUB && (window.JOBS_HUB.generateMaterialsUrl || window.JOBS_HUB.generateCvUrl)) || "";
  var refineMaterialsUrl = (window.JOBS_HUB && window.JOBS_HUB.refineMaterialsUrl) || "";
  var importJobUrl = (window.JOBS_HUB && window.JOBS_HUB.importJobUrl) || "";
  var scoreOneUrl = (window.JOBS_HUB && window.JOBS_HUB.scoreOneUrl) || "";
  var csrfToken = (window.JOBS_HUB && window.JOBS_HUB.csrfToken) || "";
  var isAppliedView = window.JOBS_HUB && window.JOBS_HUB.view === "applied";

  if (!window.JOBS_HUB) window.JOBS_HUB = {};

  var STORAGE_KEY = "jobs_hub_snapshot_v1";

  var HARD_GERMAN_REQUIRED = /\b(muttersprache|native german|deutsch als muttersprache|verhandlungssicher(?:e|es|en)?\s+deutsch|fließend(?:e|es|en)?\s+deutsch|deutsch\s+(?:auf\s+)?(?:c1|c2)(?:[\s-]?niveau)?|german\s+(?:c1|c2)|deutschkenntnisse.*(?:c1|c2|muttersprache|verhandlungssicher))\b/i;
  var TRAINEE_PROGRAM_SIGNAL = /\b(traineeprogramm|trainee program|graduate program|absolventenprogramm|einstiegsprogramm|entry program|berufseinsteiger)\b/i;
  var WERKSTUDENT_SIGNAL = /\b(werkstudent|working student|studentische|student assistant|praktikant)\b/i;
  var SENIOR_EXCLUDE = /\b(vice president|\bvp\b|director of|head of|chief |c-level|\bsenior\b|\blead\b|chapter lead|teamleiter|teamleitung|10\+\s*years|15\+\s*years|20\+\s*years|principal engineer|staff engineer|executive director|senior director|experte\b|oberärzt)\b/i;
  var JUNIOR_SIGNAL = /\b(junior|entry[\s-]?level|associate|graduate|trainee|intern|werkstudent|praktikant|working student|0-2 years|1-2 years|2 years)\b/i;

  function jobFilterBlob(job) {
    return [
      job.title || "",
      job.title_en || "",
      job.company || "",
      job.description || "",
      job.ai_summary || "",
    ].join(" ");
  }

  function enrichJobBrowseFlags(job) {
    if (!job || typeof job !== "object") return job;
    var blob = jobFilterBlob(job);
    if (job.german_required == null) {
      job.german_required = HARD_GERMAN_REQUIRED.test(blob);
    }
    if (job.senior_excluded == null) {
      job.senior_excluded = SENIOR_EXCLUDE.test(blob) && !JUNIOR_SIGNAL.test(blob);
    }
    if (job.has_trainee_program == null) {
      job.has_trainee_program = TRAINEE_PROGRAM_SIGNAL.test(blob);
    }
    if (job.has_werkstudent == null) {
      job.has_werkstudent = WERKSTUDENT_SIGNAL.test(blob);
    }
    return job;
  }

  function enrichJobsBrowseFlags(list) {
    return (list || []).map(enrichJobBrowseFlags);
  }

  function getCsrfToken() {
    if (csrfToken) return csrfToken;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function fetchJsonResponse(res) {
    return res.text().then(function (text) {
      var data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          var snippet = text.replace(/\s+/g, " ").slice(0, 120);
          if (snippet.indexOf("<!DOCTYPE") !== -1 || snippet.indexOf("<html") !== -1) {
            if (res.status === 502 || res.status === 504) {
              throw new Error(
                "Server timed out while creating your CV (AI can take up to 2 minutes). Try again in a moment."
              );
            }
            if (res.status === 403) {
              throw new Error("Session expired — refresh the page and try again.");
            }
            throw new Error("Server error (" + res.status + "). Refresh the page and try again.");
          }
          throw new Error("Unexpected server response (" + res.status + ").");
        }
      }
      return { ok: res.ok, data: data || {}, status: res.status };
    });
  }

  var snapshotTimer = null;
  var lastJobsFingerprint = "";
  var lastRefreshAt = 0;
  var refreshInFlight = false;
  var refreshQueued = false;
  var refreshDebounceTimer = null;
  var displayOrder = [];
  var scoreOneInFlight = 0;

  function jobsFingerprint(list) {
    return (list || [])
      .map(function (job) {
        return (
          (job.job_id || "") +
          ":" +
          (job.scored ? "1" : "0") +
          ":" +
          (job.match_score != null ? job.match_score : "u")
        );
      })
      .join("|");
  }

  function jobRecordFingerprint(job) {
    if (!job) return "";
    var mats = job.materials || {};
    return (
      (job.job_id || "") +
      ":" +
      (job.match_score != null ? job.match_score : "u") +
      ":" +
      (mats.has_tailored_cv ? "cv" : "") +
      (mats.has_tailored_cover_letter ? "cl" : "")
    );
  }

  function saveJobsSnapshot() {
    if (!masterJobs.length || isAppliedView) return;
    clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(function () {
      var slim = masterJobs.map(function (job) {
        var copy = Object.assign({}, job);
        if (copy.description && copy.description.length > 900) {
          copy.description = copy.description.slice(0, 900);
        }
        return copy;
      });
      var payload = JSON.stringify({ jobs: slim, savedAt: Date.now() });
      try {
        sessionStorage.setItem(STORAGE_KEY, payload);
      } catch (e) {}
      try {
        localStorage.setItem(STORAGE_KEY, payload);
      } catch (e) {}
    }, 2500);
  }

  function loadJobsSnapshot() {
    var sources = [];
    try {
      var ls = localStorage.getItem(STORAGE_KEY);
      if (ls) sources.push(JSON.parse(ls));
    } catch (e) {}
    try {
      var ss = sessionStorage.getItem(STORAGE_KEY);
      if (ss) sources.push(JSON.parse(ss));
    } catch (e) {}
    sources.sort(function (a, b) {
      return (b.savedAt || 0) - (a.savedAt || 0);
    });
    for (var i = 0; i < sources.length; i++) {
      var parsed = sources[i];
      if (parsed && Array.isArray(parsed.jobs) && parsed.jobs.length) {
        return parsed.jobs;
      }
    }
    return null;
  }

  var lastMarketStats = null;
  var marketLoadState = "idle";

  var BROWSE_VIEW_LABELS = {
    all: "All jobs",
    good: "Good matches",
    it_good: "IT · ready to apply",
    it: "IT & tech",
    non_it_good: "Non-tech · ready",
    non_it: "Non-tech",
    unscored: "Awaiting score",
    degree: "Degree-ready",
    full: "Full match"
  };

  function updateBrowseButtonLabel(view) {
    var btn = document.querySelector(".topbar-browse-btn");
    if (!btn) return;
    var label = BROWSE_VIEW_LABELS[view] || view;
    btn.innerHTML = "Browse: " + label + ' <span class="topbar-caret">&#9662;</span>';
    var viewInput = document.querySelector('.browse-filter-form input[name="view"]');
    if (viewInput) viewInput.value = view;
  }

  function currentBrowseView() {
    try {
      var fromUrl = new URL(window.location.href).searchParams.get("view");
      if (fromUrl) return fromUrl;
    } catch (e) {}
    return (window.JOBS_HUB && window.JOBS_HUB.view) || "all";
  }

  function urlBrowseFilters() {
    var params = new URL(window.location.href).searchParams;
    return {
      english_ok: params.get("english_ok") === "1",
      entry: params.get("entry") === "1",
      program: (params.get("program") || "").toLowerCase(),
    };
  }

  function passesUrlBrowseFilters(job) {
    var filters = urlBrowseFilters();
    if (filters.english_ok && job.german_required) return false;
    if (filters.entry && job.senior_excluded) return false;
    if (filters.program === "trainee" && !job.has_trainee_program) return false;
    if (filters.program === "werkstudent" && !job.has_werkstudent) return false;
    return true;
  }

  function filterJobsForView(list, view) {
    list = list || [];
    if (view === "it_good") {
      return list.filter(function (job) {
        return job.career_branch === "it" && job.good_match;
      });
    }
    if (view === "non_it_good") {
      return list.filter(function (job) {
        return job.career_branch === "non_it" && job.good_match;
      });
    }
    if (view === "it") {
      return list.filter(function (job) {
        return job.career_branch === "it";
      });
    }
    if (view === "non_it") {
      return list.filter(function (job) {
        return job.career_branch === "non_it";
      });
    }
    if (view === "good") {
      return list.filter(function (job) {
        return job.good_match;
      });
    }
    if (view === "unscored") {
      return list.filter(function (job) {
        return !job.scored;
      });
    }
    if (view === "degree") {
      return list.filter(function (job) {
        return job.degree_ready;
      });
    }
    if (view === "full") {
      return list.filter(function (job) {
        return job.full_match;
      });
    }
    if (view === "all") {
      return list.filter(function (job) {
        if (job.listable_in_all === false) return false;
        if (!job.scored) return true;
        var score = job.match_score != null ? job.match_score : 0;
        return score >= 30;
      });
    }
    return list;
  }

  function filterJobsForCurrentView(list) {
    var view = currentBrowseView();
    list = (list || []).filter(passesUrlBrowseFilters);
    return filterJobsForView(list, view);
  }

  function updateActiveBrowseChips(view) {
    document.querySelectorAll(".browse-chip").forEach(function (link) {
      try {
        var linkView = new URL(link.href, window.location.origin).searchParams.get("view") || "all";
        link.classList.toggle("is-active", linkView === view);
      } catch (e) {}
    });
    document.querySelectorAll(".stat-chip-link[data-stat-view]").forEach(function (link) {
      var linkView = link.getAttribute("data-stat-view") || "all";
      link.classList.toggle("is-active", linkView === view);
    });
  }

  function switchBrowseView(view) {
    if (isAppliedView) return false;
    view = view || "all";
    var url = new URL(window.location.href);
    url.searchParams.set("view", view);
    history.replaceState({ browseView: view }, "", url.toString());
    if (window.JOBS_HUB) window.JOBS_HUB.view = view;
    updateActiveBrowseChips(view);
    updateBrowseButtonLabel(view);
    marketLoadState = "ready";
    refilterFromUrl();
    return true;
  }

  function refilterFromUrl() {
    if (isAppliedView) return false;
    var view = currentBrowseView();
    marketLoadState = "ready";
    updateActiveBrowseChips(view);
    updateBrowseButtonLabel(view);
    if (!masterJobs.length) {
      renderList();
      return false;
    }
    jobs = jobsInStableOrder(filterJobsForCurrentView(masterJobs));
    byId = {};
    jobs.forEach(function (job) {
      byId[job.job_id] = job;
    });
    var keepId = selectedId && byId[selectedId] ? selectedId : jobs[0] ? jobs[0].job_id : "";
    selectedId = keepId;
    renderList({ preserveScroll: true, skipAutoSelect: true });
    syncJobListSelection({ scroll: false });
    if (keepId) renderDetail(byId[keepId]);
    updateTopbarFromMarket(getBrowseStats(lastMarketStats || {}));
    return true;
  }

  function maybeOpenAllWhenEmpty() {
    if (isAppliedView || jobs.length > 0 || !masterJobs.length) return false;
    var hub = window.JOBS_HUB || {};
    var view = currentBrowseView();
    var needsScores = view === "good" || view === "it_good" || view === "non_it_good" || view === "full" || view === "degree";
    if (!needsScores) return false;
    if ((hub.goodFitsTotal || 0) > 0) return false;
    if ((hub.cacheRawTotal || 0) <= 0) return false;
    switchBrowseView("all");
    showHubToast("Showing all jobs — Good matches appear after AI scoring.");
    return true;
  }

  function ensureJobsLoaded() {
    var hub = window.JOBS_HUB || {};
    var expected = hub.jobsTotalCount || hub.cacheRawTotal || 0;
    if (!masterJobs.length && expected > 0) {
      refreshLiveJobs();
      return true;
    }
    return false;
  }

  function shouldMergeJobsDuringSearch() {
    return currentBrowseView() === "all";
  }

  function mergeJobRecord(existing, incoming) {
    if (!existing) return enrichJobBrowseFlags(incoming);
    if (!incoming) return enrichJobBrowseFlags(existing);
    var merged = Object.assign({}, existing, incoming);
    var existingDesc = existing.description || "";
    var incomingDesc = incoming.description || "";
    if (existingDesc.length > incomingDesc.length) {
      merged.description = existingDesc;
    }
    if (existing.materials || incoming.materials) {
      var mats = Object.assign({}, incoming.materials || {}, existing.materials || {});
      if (existing.materials && existing.materials.has_tailored_cv) {
        mats.has_tailored_cv = true;
        mats.tailored_cv_url =
          existing.materials.tailored_cv_url || mats.tailored_cv_url || "";
      }
      if (existing.materials && existing.materials.has_tailored_cover_letter) {
        mats.has_tailored_cover_letter = true;
        mats.tailored_cover_letter_url =
          existing.materials.tailored_cover_letter_url || mats.tailored_cover_letter_url || "";
      }
      merged.materials = mats;
    }
    if (existing.scored && !incoming.scored) {
      if (existing.match_score != null && existing.match_score > 0) {
        merged.scored = true;
        merged.match_score = existing.match_score;
        merged.match_detail = existing.match_detail || incoming.match_detail;
        merged.ai_summary = existing.ai_summary || incoming.ai_summary;
        merged.recommendation = existing.recommendation || incoming.recommendation;
      } else {
        merged.scored = false;
        merged.match_score = incoming.match_score;
        merged.match_detail = incoming.match_detail;
        merged.ai_summary = incoming.ai_summary || "";
        merged.recommendation = incoming.recommendation || "";
      }
    }
    if (existing.good_match && !incoming.good_match) merged.good_match = true;
    if (existing.full_match && !incoming.full_match) merged.full_match = true;
    if (existing.degree_ready && !incoming.degree_ready) merged.degree_ready = true;
    if (existing.listable_in_all !== false && incoming.listable_in_all === false) {
      merged.listable_in_all = existing.listable_in_all;
    }
    return enrichJobBrowseFlags(merged);
  }

  function mergeJobArrays(existing, incoming) {
    var map = {};
    (existing || []).forEach(function (job) {
      if (job && job.job_id) map[job.job_id] = job;
    });
    (incoming || []).forEach(function (job) {
      if (!job || !job.job_id) return;
      map[job.job_id] = mergeJobRecord(map[job.job_id], job);
    });
    return Object.keys(map).map(function (id) {
      return map[id];
    });
  }

  function parseJobs() {
    try {
      masterJobs = JSON.parse(dataEl.textContent || "[]");
    } catch (e) {
      masterJobs = [];
    }
    if (!masterJobs.length) {
      var snap = loadJobsSnapshot();
      if (snap) masterJobs = snap;
    }
    masterJobs = enrichJobsBrowseFlags(masterJobs);
    if (!displayOrder.length) {
      displayOrder = masterJobs.map(function (job) {
        return job.job_id;
      });
    } else {
      syncDisplayOrderFromList(masterJobs);
    }
    applyStableJobView();
    if (masterJobs.length) saveJobsSnapshot();
  }

  function rebuildJobs(newJobs, opts) {
    opts = opts || {};
    newJobs = newJobs || [];
    var hasReal = newJobs.length && !newJobs[0]._preview;
    if (opts.merge && masterJobs.length && newJobs.length) {
      var base = hasReal ? stripPreviewJobs(masterJobs) : masterJobs;
      newJobs = mergeJobArrays(base, newJobs);
    }
    if (newJobs.length) {
      masterJobs = enrichJobsBrowseFlags(newJobs);
      if (!opts.merge || !displayOrder.length) {
        displayOrder = masterJobs.map(function (job) {
          return job.job_id;
        });
      } else {
        syncDisplayOrderFromList(newJobs);
      }
    }
    applyStableJobView();
    if (masterJobs.length) saveJobsSnapshot();
  }

  function effectiveJobCount(data) {
    var fromServer = data.cache_raw_total != null ? data.cache_raw_total : data.display_count;
    if (fromServer == null) return jobs.length;
    return Math.max(fromServer || 0, jobs.length);
  }

  function deriveBrowseStatsFromJobs(list) {
    var urlFiltered = (list || []).filter(passesUrlBrowseFilters);
    var allJobs = filterJobsForView(urlFiltered, "all");
    var stats = {
      cache_raw_total: allJobs.length,
      scored_total: 0,
      unscored_total: 0,
      good_fits_total: filterJobsForView(urlFiltered, "good").length,
      it_total: filterJobsForView(urlFiltered, "it").length,
      non_it_total: filterJobsForView(urlFiltered, "non_it").length,
      other_total: 0,
      it_good_total: filterJobsForView(urlFiltered, "it_good").length,
      non_it_good_total: filterJobsForView(urlFiltered, "non_it_good").length,
      degree_ready_total: filterJobsForView(urlFiltered, "degree").length,
      full_match_total: filterJobsForView(urlFiltered, "full").length,
    };
    urlFiltered.forEach(function (job) {
      if (job.scored) stats.scored_total++;
      else stats.unscored_total++;
      var branch = job.career_branch || "other";
      if (branch !== "it" && branch !== "non_it") stats.other_total++;
    });
    stats.unscored_total = filterJobsForView(urlFiltered, "unscored").length;
    return stats;
  }

  function getBrowseStats(data) {
    if (masterJobs.length) {
      return deriveBrowseStatsFromJobs(masterJobs);
    }
    return Object.assign({}, deriveBrowseStatsFromJobs([]), lastMarketStats || data || {});
  }

  function touchDisplayOrder(jobId) {
    if (!jobId) return;
    if (displayOrder.indexOf(jobId) < 0) displayOrder.push(jobId);
  }

  function syncDisplayOrderFromList(list) {
    (list || []).forEach(function (job) {
      if (job && job.job_id) touchDisplayOrder(job.job_id);
    });
  }

  function jobsInStableOrder(filteredList) {
    var map = Object.create(null);
    (filteredList || []).forEach(function (job) {
      if (job && job.job_id) map[job.job_id] = job;
    });
    var ordered = [];
    displayOrder.forEach(function (id) {
      if (map[id]) {
        ordered.push(map[id]);
        delete map[id];
      }
    });
    Object.keys(map).forEach(function (id) {
      ordered.push(map[id]);
      touchDisplayOrder(id);
    });
    return ordered;
  }

  function applyStableJobView() {
    jobs = jobsInStableOrder(filterJobsForCurrentView(masterJobs));
    byId = {};
    masterJobs.forEach(function (job) {
      if (job && job.job_id) byId[job.job_id] = job;
    });
    jobs.forEach(function (job) {
      if (job && job.job_id) byId[job.job_id] = job;
    });
  }

  function sortJobsForDisplay(list) {
    function tier(job) {
      var score = job.match_score != null ? job.match_score : -1;
      if (job.scored && score >= 50) return 0;
      if (!job.scored) return 1;
      if (job.scored && score < 30) return 3;
      return 2;
    }
    return (list || []).slice().sort(function (a, b) {
      var ta = tier(a);
      var tb = tier(b);
      if (ta !== tb) return ta - tb;
      var sa = a.match_score != null ? a.match_score : 0;
      var sb = b.match_score != null ? b.match_score : 0;
      if (sb !== sa) return sb - sa;
      return (a.title || "").localeCompare(b.title || "");
    });
  }

  function enrichMarketStats(data) {
    if (data && data.cache_raw_total != null) {
      lastMarketStats = Object.assign({}, lastMarketStats || {}, data);
    }
    if (masterJobs.length) {
      return deriveBrowseStatsFromJobs(masterJobs);
    }
    return Object.assign({}, deriveBrowseStatsFromJobs([]), lastMarketStats || data || {});
  }

  function marketDataUrl() {
    var base = (window.JOBS_HUB && window.JOBS_HUB.marketDataUrl) || "/jobs/market/data/";
    var qs = window.location.search.replace(/^\?/, "");
    return base + (qs ? "?" + qs : "");
  }

  function syncScoreButton(stats) {
    var scoreBtn = document.querySelector('[data-pipeline-btn="score"]');
    if (!scoreBtn) return;
    if (document.body.getAttribute("data-pipeline-running") === "1") return;
    var waiting = stats.unscored_total != null ? stats.unscored_total : 0;
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

  function updateTopbarFromMarket(data) {
    var stats = enrichMarketStats(data || lastMarketStats || {});
    if (data && data.cache_raw_total != null) {
      lastMarketStats = stats;
    }
    if (stats.cache_raw_total == null) return;
    if (typeof window.renderTopbarStatChips === "function") {
      window.renderTopbarStatChips(stats);
    } else if (typeof window.updateBrowseDropdownCounts === "function") {
      window.updateBrowseDropdownCounts(stats);
      syncScoreButton(stats);
    }
  }

  function renderMarketBanner(data) {
    var banner = document.getElementById("jobs-market-banner");
    if (!banner || isAppliedView) return;
    data = data || lastMarketStats || {};
    var hub = window.JOBS_HUB || {};
    var cacheTotal =
      data.cache_raw_total != null ? data.cache_raw_total : hub.cacheRawTotal;
    var issues = data.source_issues || [];
    var parts = [];
    var searching = document.body.getAttribute("data-pipeline-running") === "1";
    if (issues.length && !searching) {
      var errText = issues
        .slice(0, 3)
        .map(function (issue) {
          var line = esc(issue.source || "Source");
          if (issue.error) line += " &mdash; " + esc(issue.error);
          else if (issue.status === "empty") line += " (empty)";
          return line;
        })
        .join("; ");
      parts.push(
        '<p class="jobs-banner-warn">Some sources returned few listings on last Find jobs: ' +
          errText +
          ".</p>"
      );
    }
    if (marketLoadState === "error") {
      parts.push(
        '<p class="jobs-banner-err">Could not refresh the job list. Refresh the page (Ctrl+F5) or click <strong>Find jobs</strong>.</p>'
      );
    } else if (
      marketLoadState === "ready" &&
      !searching &&
      jobs.length === 0 &&
      (cacheTotal == null || cacheTotal === 0)
    ) {
      parts.push(
        '<p class="jobs-banner-info">Welcome &mdash; click <strong>Find jobs</strong> in the top bar to load jobs.</p>'
      );
    } else if (
      marketLoadState === "ready" &&
      !searching &&
      jobs.length === 0 &&
      cacheTotal > 0
    ) {
      var view = currentBrowseView();
      var label = BROWSE_VIEW_LABELS[view] || hub.viewLabel || view;
      parts.push(
        '<p class="jobs-banner-info">No jobs in <strong>' +
          esc(label) +
          '</strong> with your current filters. Try <a href="?view=all">All jobs</a>.</p>'
      );
    }
    banner.innerHTML = parts.join("");
  }

  function emptyListMessage() {
    var searching = document.body.getAttribute("data-pipeline-running") === "1";
    var stats = lastMarketStats || {};
    var hub = window.JOBS_HUB || {};
    var cacheTotal =
      stats.cache_raw_total != null ? stats.cache_raw_total : hub.cacheRawTotal;
    if (isAppliedView) {
      return "No applications yet. Browse All, apply on the company site, then click I applied.";
    }
    if (marketLoadState === "loading" && !jobs.length) {
      return "Loading jobs&hellip;";
    }
    if (
      !jobs.length &&
      window.JOBS_HUB &&
      window.JOBS_HUB.lazyLoadJobs &&
      (marketLoadState === "idle" || marketLoadState === "loading")
    ) {
      return "Loading jobs&hellip;";
    }
    if (
      !jobs.length &&
      (hub.cacheRawTotal || 0) > 0 &&
      marketLoadState !== "error" &&
      marketLoadState !== "ready"
    ) {
      return "Loading jobs&hellip;";
    }
    if (marketLoadState === "error") {
      return "Could not load jobs. Refresh the page (Ctrl+F5) or click Find jobs in the top bar.";
    }
    if (searching && !jobs.length) {
      var liveN = (stats && stats.live_count) || 0;
      var totalN = cacheTotal || liveN || 0;
      if (liveN > 0 || totalN > 0) {
        return (
          'Found ' +
          (liveN || totalN) +
          ' jobs &mdash; <button type="button" class="jobs-empty-cta" data-browse-view="all">Show all jobs</button>'
        );
      }
      return "Searching &mdash; jobs appear here as they are found (usually within 30 seconds).";
    }
    if (cacheTotal === 0 || cacheTotal == null) {
      return "No jobs yet. Click Find jobs in the top bar to fetch listings from Arbeitsagentur, EURES, and Arbeitnow.";
    }
    var view = currentBrowseView();
    if (view === "good" || view === "it_good" || view === "non_it_good") {
      return (
        'No apply-ready matches yet (need 50%+ AI score). ' +
        '<button type="button" class="jobs-empty-cta" data-browse-view="all">Show all jobs</button> ' +
        'or <button type="button" class="jobs-empty-cta" data-browse-view="unscored">Awaiting score</button>.'
      );
    }
    if (view === "unscored") {
      return "All jobs are scored. Check Good matches or All jobs.";
    }
    if (view === "non_it") {
      return "No non-tech roles in this list. Try Browse &rarr; All jobs.";
    }
    return "No jobs in this view. Try All jobs or change filters above.";
  }

  function showHubToast(message, isError) {
    var toast = document.getElementById("pipeline-toast");
    if (!toast) {
      if (isError) alert(message);
      return;
    }
    toast.textContent = message || "";
    toast.classList.toggle("is-error", !!isError);
    toast.hidden = false;
    clearTimeout(showHubToast._timer);
    showHubToast._timer = setTimeout(function () {
      toast.hidden = true;
    }, 9000);
  }

  function jobById(jobId) {
    if (!jobId) return null;
    if (byId[jobId]) return byId[jobId];
    for (var i = 0; i < masterJobs.length; i++) {
      if (masterJobs[i].job_id === jobId) return masterJobs[i];
    }
    return null;
  }

  function jobCardScoreBadgeHtml(job) {
    if (!job.scored && scoreOneUrl) {
      return (
        '<button type="button" class="job-card-score-btn" data-score-one="' +
        esc(job.job_id) +
        '" title="Score this job with AI">Score</button>'
      );
    }
    if (job.match_score != null) {
      return (
        '<span class="job-card-score ' +
        scoreClass(job.match_score) +
        '" title="' +
        esc(job.qualification_label || "Match score") +
        '">' +
        esc(String(job.match_score)) +
        "%</span>"
      );
    }
    return '<span class="job-card-score score-pending" title="Not scored yet — click Score">Score</span>';
  }

  function replaceJobInArrays(jobId, merged) {
    for (var i = 0; i < masterJobs.length; i++) {
      if (masterJobs[i].job_id === jobId) {
        masterJobs[i] = merged;
        break;
      }
    }
    for (var j = 0; j < jobs.length; j++) {
      if (jobs[j].job_id === jobId) {
        jobs[j] = merged;
        break;
      }
    }
    byId[jobId] = merged;
  }

  function patchJobCardDom(jobId) {
    var card = listEl.querySelector('.job-card[data-job-id="' + jobId + '"]');
    var job = byId[jobId];
    if (!card || !job) return false;
    var aside = card.querySelector(".job-card-aside");
    if (aside) aside.innerHTML = jobCardScoreBadgeHtml(job);
    var hintEl = card.querySelector(".job-card-hint");
    var hintLine = truncateText(jobCardHint(job), 120);
    if (hintLine) {
      if (hintEl) hintEl.textContent = hintLine;
      else {
        var textCol = card.querySelector(".job-card-text");
        if (textCol) {
          var p = document.createElement("p");
          p.className = "job-card-hint";
          p.textContent = hintLine;
          textCol.appendChild(p);
        }
      }
    }
    var badgesHost = card.querySelector(".job-card-text");
    if (badgesHost) {
      var oldBadges = badgesHost.querySelector(".job-card-meta");
      if (oldBadges) oldBadges.remove();
      var titleEl = badgesHost.querySelector(".job-card-title");
      if (titleEl) {
        titleEl.insertAdjacentHTML("afterend", jobCardBadgesHtml(job));
      }
    }
    return true;
  }

  function removeJobCardDom(jobId) {
    var card = listEl.querySelector('.job-card[data-job-id="' + jobId + '"]');
    if (card) card.remove();
    var countEl = document.getElementById("jobs-list-count");
    if (countEl) countEl.textContent = String(jobs.length);
  }

  function syncJobListSelection(opts) {
    opts = opts || {};
    listEl.querySelectorAll(".job-card").forEach(function (card) {
      var active = card.dataset.jobId === selectedId;
      card.classList.toggle("is-active", active);
      if (active && opts.scroll !== false) {
        card.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    });
  }

  function scoreOneJob(job, btn) {
    if (!scoreOneUrl) {
      showHubToast("Score is unavailable — refresh the page and try again.", true);
      return;
    }
    if (!job || !job.job_id) return;
    if (job.scored) return;
    scoreOneInFlight++;
    if (btn) btn.disabled = true;
    fetch(scoreOneUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      credentials: "same-origin",
      body: JSON.stringify({
        job_id: job.job_id,
        job: {
          job_id: job.job_id,
          title: job.title || "",
          company: job.company || "",
          location: job.location || "",
          description: job.description || "",
          apply_url: job.apply_url || "",
          source: job.source || "",
          remote: !!job.remote
        }
      })
    })
      .then(fetchJsonResponse)
      .then(function (result) {
        if (!result.ok || !result.data.ok || !result.data.job) {
          throw new Error((result.data && result.data.error) || "Score failed");
        }
        var updated = result.data.job;
        var merged = mergeJobRecord(byId[job.job_id] || job, updated);
        replaceJobInArrays(job.job_id, merged);
        saveJobsSnapshot();

        var view = currentBrowseView();
        var stillInView = filterJobsForView([merged], view).length > 0;
        if (stillInView) {
          if (!patchJobCardDom(job.job_id)) {
            var scrollTop = listEl.scrollTop;
            renderList({ preserveScroll: true, skipAutoSelect: true });
            listEl.scrollTop = scrollTop;
          }
        } else {
          jobs = jobs.filter(function (row) {
            return row.job_id !== job.job_id;
          });
          removeJobCardDom(job.job_id);
        }

        syncJobListSelection({ scroll: false });
        renderDetail(merged);
        updateTopbarFromMarket(deriveBrowseStatsFromJobs(masterJobs));
        showHubToast("Scored — " + (updated.match_score != null ? updated.match_score + "%" : "done"));
      })
      .catch(function (err) {
        showHubToast(err.message || "Could not score this job", true);
      })
      .finally(function () {
        scoreOneInFlight = Math.max(0, scoreOneInFlight - 1);
        if (btn) btn.disabled = false;
        if (scoreOneInFlight === 0 && refreshQueued) {
          refreshQueued = false;
          refreshFromMarketData({ merge: true });
        }
      });
  }

  function refreshFromMarketData(options) {
    if (isAppliedView) return;
    if (generatingJobId) return;
    options = options || {};
    if (scoreOneInFlight > 0 && !options.force) {
      refreshQueued = true;
      return;
    }
    var minGap = document.body.getAttribute("data-pipeline-running") === "1" ? 8000 : 12000;
    var now = Date.now();
    if (refreshInFlight) {
      refreshQueued = true;
      return;
    }
    if (!options.force && now - lastRefreshAt < minGap) {
      if (!refreshDebounceTimer) {
        refreshDebounceTimer = setTimeout(function () {
          refreshDebounceTimer = null;
          refreshFromMarketData(options);
        }, minGap - (now - lastRefreshAt));
      }
      return;
    }
    refreshInFlight = true;
    var hadJobs = jobs.length > 0;
    if (!hadJobs && marketLoadState !== "ready" && !masterJobs.length) {
      marketLoadState = "loading";
      renderList();
    }
    lastRefreshAt = now;
    var previousCount = jobs.length;
    var previousSelectedFingerprint = jobRecordFingerprint(byId[selectedId]);
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeoutId = controller
      ? setTimeout(function () {
          controller.abort();
        }, 25000)
      : null;
    fetch(marketDataUrl(), {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller ? controller.signal : undefined,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Could not load jobs (HTTP " + res.status + ").");
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.ok || !Array.isArray(data.jobs)) {
          throw new Error((data && data.error) || "Unexpected job list response.");
        }
        marketLoadState = "ready";
        lastMarketStats = enrichMarketStats(data);
        var incoming = data.jobs;
        var pipelineRunning = !!data.pipeline_running;
        var searchPhase = data.pipeline_phase === "search";

        if (incoming.length === 0 && previousCount > 0) {
          updateTopbarFromMarket(data);
          renderMarketBanner(data);
          return;
        }

        if (pipelineRunning && searchPhase && incoming.length > 0 && shouldMergeJobsDuringSearch()) {
          incoming = mergeJobArrays(jobs, incoming);
        }

        if (incoming.length === 0) {
          updateTopbarFromMarket(data);
          renderMarketBanner(data);
          if (!jobs.length) {
            renderList();
          }
          return;
        }

        var keepId = selectedId;
        rebuildJobs(incoming, {
          merge: options.merge || (pipelineRunning && previousCount > 0),
        });
        updateTopbarFromMarket(data);
        renderMarketBanner(data);
        renderList({ preserveScroll: true, skipAutoSelect: true });
        syncJobListSelection({ scroll: false });
        if (keepId && byId[keepId]) {
          if (jobRecordFingerprint(byId[keepId]) !== previousSelectedFingerprint) {
            renderDetail(byId[keepId]);
          }
        } else if (jobs.length && !selectedId) {
          setSelected(jobs[0].job_id, false, { scroll: false });
        }
      })
      .catch(function (err) {
        marketLoadState = hadJobs || masterJobs.length ? "ready" : "error";
        renderMarketBanner({});
        if (!jobs.length) {
          renderList();
        }
        if (!hadJobs) {
          showHubToast((err && err.message) || "Could not refresh job list.", true);
        }
      })
      .finally(function () {
        if (timeoutId) clearTimeout(timeoutId);
        refreshInFlight = false;
        if (refreshQueued) {
          refreshQueued = false;
          refreshFromMarketData({ merge: true });
        }
      });
  }

  function syncPipelineState() {
    var statusUrl = (window.JOBS_HUB && window.JOBS_HUB.statusUrl) || "";
    if (!statusUrl) return;
    fetch(statusUrl, { credentials: "same-origin", cache: "no-store" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.state === "running") {
          document.body.setAttribute("data-pipeline-running", "1");
          startScorePolling();
        } else {
          document.body.removeAttribute("data-pipeline-running");
          stopScorePolling();
        }
        updateTopbarFromMarket({
          cache_raw_total: data.cache_raw_total,
          good_fits_total: data.good_fits_total,
          unscored_total: data.unscored_total,
          scored_total: data.scored_total,
          it_total: data.it_total,
          non_it_total: data.non_it_total,
          other_total: data.other_total,
          it_good_total: data.it_good_total,
          non_it_good_total: data.non_it_good_total,
          degree_ready_total: data.degree_ready_total,
          full_match_total: data.full_match_total,
        });
        applyStatusJobPreviews(data);
        if (data.state === "running") {
          startLivePolling();
        } else {
          stopLivePolling();
        }
        var stable = stripPreviewJobs(masterJobs).length;
        var expected = data.cache_raw_total || 0;
        if (!masterJobs.length && (stable < expected || (data.live_count > 0 && expected > 0))) {
          refreshLiveJobs();
        }
      })
      .catch(function () {});
  }

  function simpleHash(text) {
    var h = 0;
    var s = String(text || "");
    for (var i = 0; i < s.length; i++) {
      h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    }
    return Math.abs(h).toString(36);
  }

  function previewJobFromStatus(row) {
    var url = (row && row.apply_url) || "";
    var title = (row && row.title) || "Untitled role";
    var company = (row && row.company) || "Company";
    var key = url || company + "|" + title;
    return {
      job_id: "preview-" + simpleHash(key),
      title: title,
      title_en: title,
      company: company,
      location: (row && row.location) || "",
      country: "",
      source: (row && row.source) || "",
      apply_url: url,
      remote: false,
      description: "",
      match_score: null,
      recommendation: "",
      ai_summary: "",
      scored: false,
      keyword_hint: "",
      good_match: false,
      full_match: false,
      degree_ready: false,
      listable_in_all: true,
      career_branch: "other",
      career_branch_label: "Mixed role",
      _preview: true,
    };
  }

  function stripPreviewJobs(list) {
    return (list || []).filter(function (job) {
      return !job._preview;
    });
  }

  function applyStatusJobPreviews(statusData) {
    if (isAppliedView || !statusData) return false;
    var previews = statusData.latest_jobs || [];
    if (!previews.length) return false;
    var stubs = previews.map(previewJobFromStatus);
    var merged = mergeJobArrays(stripPreviewJobs(masterJobs), stubs);
    masterJobs = merged;
    syncDisplayOrderFromList(masterJobs);
    applyStableJobView();
    marketLoadState = "ready";
    renderList({ preserveScroll: true, skipAutoSelect: true });
    syncJobListSelection({ scroll: false });
    if (!selectedId && jobs.length) setSelected(jobs[0].job_id, false);
    return true;
  }

  function liveDataUrl() {
    return (window.JOBS_HUB && window.JOBS_HUB.liveDataUrl) || "/jobs/market/live/";
  }

  function absorbServerJobs(incoming, meta) {
    meta = meta || {};
    if (!incoming || !incoming.length) return false;
    rebuildJobs(incoming, { merge: masterJobs.length > 0 });
    marketLoadState = "ready";
    if (meta.total_count != null) {
      updateTopbarFromMarket({
        cache_raw_total: meta.total_count,
        live_count: meta.live_count,
        unscored_total: meta.total_count,
      });
    }
    renderMarketBanner(lastMarketStats || {});
    renderList({ preserveScroll: true, skipAutoSelect: !!selectedId });
    if (!selectedId && jobs.length) setSelected(jobs[0].job_id, false);
    return true;
  }

  function refreshLiveJobs() {
    return fetch(liveDataUrl(), { credentials: "same-origin", cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("Could not load live jobs");
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.ok) return data;
        if (data.search_running || data.pipeline_running) {
          document.body.setAttribute("data-pipeline-running", "1");
        } else if (!data.pipeline_running) {
          document.body.removeAttribute("data-pipeline-running");
        }
        if (data.jobs && data.jobs.length) {
          absorbServerJobs(data.jobs, {
            total_count: data.total_count,
            live_count: data.live_count,
          });
        } else if (data.search_running && !jobs.length) {
          marketLoadState = "ready";
          renderList();
        }
        return data;
      })
      .catch(function () {
        return null;
      });
  }

  var livePollTimer = null;

  function startLivePolling() {
    if (livePollTimer || isAppliedView) return;
    if (document.body.getAttribute("data-pipeline-running") !== "1") return;
    if (jobs.length > 0) return;
    refreshLiveJobs();
    livePollTimer = setInterval(refreshLiveJobs, 5000);
  }

  function stopLivePolling() {
    if (livePollTimer) {
      clearInterval(livePollTimer);
      livePollTimer = null;
    }
  }

  function isMobileLayout() {
    return window.innerWidth <= 960;
  }

  function setMobileDetailOpen(open) {
    if (!splitEl) return;
    splitEl.classList.toggle("jobs-split--detail-open", !!open && isMobileLayout());
  }

  function closeMobileDetail() {
    setMobileDetailOpen(false);
    var panel = document.querySelector(".jobs-list-panel");
    if (panel) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function esc(text) {
    var d = document.createElement("div");
    d.textContent = text || "";
    return d.innerHTML;
  }

  function formatDescription(text) {
    return esc(text || "").replace(/\n/g, "<br>");
  }

  function scoreClass(score) {
    if (score == null) return "score-pending";
    if (score >= 50) return "score-high";
    if (score >= 30) return "score-mid";
    return "score-low";
  }

  function englishDisplayTitle(title) {
    if (!title) return "Role";
    return title
      .replace(/\s*[\(\[](?:m\/?w\/?d|w\/?m\/?d|d\/m\/w|mwd|all genders|divers)[\)\]]\s*/gi, " ")
      .replace(/:in\b/gi, "")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function jobDisplayTitle(job) {
    return (job.title_en || englishDisplayTitle(job.title) || job.title || "Role").trim();
  }

  function truncateText(text, max) {
    var t = (text || "").trim();
    if (!t) return "";
    if (t.length <= max) return t;
    return t.slice(0, max).replace(/\s+\S*$/, "") + "…";
  }

  function jobCardHint(job) {
    if (job.list_hint) return job.list_hint;
    if (job.scored && job.ai_summary) return job.ai_summary;
    if (!job.scored && job.keyword_hint) return job.keyword_hint;
    if (!job.scored) return "Not scored yet — use Score AI for an English match summary";
    return "";
  }

  function jobCardBadgesHtml(job) {
    var badges = [];
    if (job.career_branch_label) {
      badges.push(
        '<span class="job-card-badge branch-' +
          esc(job.career_branch || "other") +
          '">' +
          esc(job.career_branch_label) +
          "</span>"
      );
    } else if (job.role_category) {
      badges.push('<span class="job-card-badge">' + esc(job.role_category) + "</span>");
    }
    if (job.recommendation_label) {
      badges.push(
        '<span class="job-card-badge rec-' +
          esc(job.recommendation || "pending") +
          '">' +
          esc(job.recommendation_label) +
          "</span>"
      );
    } else if (job.scored && job.qualification_label) {
      badges.push('<span class="job-card-badge qual">' + esc(job.qualification_label) + "</span>");
    }
    if (job.remote) {
      badges.push('<span class="job-card-badge remote">Remote</span>');
    }
    if (job.country) {
      badges.push('<span class="job-card-badge country">' + esc(job.country) + "</span>");
    }
    if (!badges.length) return "";
    return '<p class="job-card-meta">' + badges.join("") + "</p>";
  }

  function recClass(rec, scored) {
    if (!scored) return "rec-pending";
    if (rec === "apply") return "rec-apply";
    if (rec === "review") return "rec-review";
    return "rec-skip";
  }

  function matchStatusLabel(job) {
    if (job && job.qualification_label) return job.qualification_label;
    if (!job || !job.scored) return "Awaiting score";
    return "Scored";
  }

  function matchChipHtml(job) {
    var scored = job.scored;
    var score = job.match_score;
    var label = matchStatusLabel(job);
    var detail = job.match_detail;
    var reqPart = "";
    if (detail && detail.must_have_total) {
      reqPart =
        detail.must_have_met +
        " / " +
        detail.must_have_total +
        " requirements met";
    }
    if (!scored || score == null) {
      return '<span class="jobs-hero-chip jobs-hero-chip-pending">' + esc(label) + "</span>";
    }
    var cls = score >= 50 ? "jobs-hero-chip-high" : "jobs-hero-chip-low";
    var parts = [String(score) + "%"];
    if (reqPart) parts.push(reqPart);
    parts.push(label);
    return (
      '<span class="jobs-hero-chip ' +
      cls +
      '">' +
      esc(parts.join(" · ")) +
      "</span>"
    );
  }

  function hasTailoredDoc(materials, materialType) {
    materials = materials || {};
    if (materialType === "cover_letter") {
      return !!(materials.has_tailored_cover_letter || materials.tailored_cover_letter_url);
    }
    return !!(materials.has_tailored_cv || materials.tailored_cv_url);
  }

  function buildHeroDocButtons(job) {
    if (!generateMaterialsUrl && !refineMaterialsUrl) {
      return "";
    }
    var materials = job.materials || {};
    var cvProfile = job.cv_profile || {};
    var hasCv = hasTailoredDoc(materials, "cv");
    var hasLetter = hasTailoredDoc(materials, "cover_letter");
    var parts = ['<span class="hero-materials-compact">'];
    parts.push(
      '<span class="hero-mat-create">' +
        '<select class="hero-mat-select hero-mat-select-compact" data-material-select aria-label="What to create" data-tip="Tailored CV, cover letter, or both">' +
        '<option value="cv">Tailored CV</option>' +
        '<option value="cover_letter">Cover letter</option>' +
        '<option value="both">Both</option>' +
        "</select>" +
        '<select class="hero-mat-select hero-mat-select-compact" data-language-select aria-label="Output language" data-tip="Language for tailored CV/cover letter">' +
        '<option value="auto">Auto language</option>' +
        '<option value="en">English</option>' +
        '<option value="de">Deutsch</option>' +
        '<option value="no">Norsk</option>' +
        "</select>" +
        '<button type="button" class="hero-btn hero-btn-generate hero-btn-compact" data-action="generate-materials" data-tip="AI writes from posting (~1–2 min)">Create</button>' +
        "</span>"
    );

    var roleCvUrl = cvProfile.slug
      ? (cvProfile.url || "/cv/html/" + encodeURIComponent(cvProfile.slug) + "/")
      : "";
    var docsItems = [];
    if (roleCvUrl) {
      docsItems.push(
        '<a class="hero-more-link" href="' +
          esc(roleCvUrl) +
          '" target="_blank" rel="noopener">Role CV ↗</a>'
      );
    }
    if (hasCv) {
      docsItems.push(
        '<a class="hero-more-link" href="' +
          esc(materials.tailored_cv_url) +
          '" target="_blank" rel="noopener">Tailored CV ↗</a>'
      );
    }
    if (hasLetter) {
      docsItems.push(
        '<a class="hero-more-link" href="' +
          esc(materials.tailored_cover_letter_url) +
          '" target="_blank" rel="noopener">Cover letter ↗</a>'
      );
    }
    if (refineMaterialsUrl || generateMaterialsUrl) {
      docsItems.push(
        '<button type="button" class="hero-more-link hero-more-button" data-action="open-ai-edit">Edit AI</button>'
      );
    }
    if (docsItems.length) {
      parts.push(
        '<details class="hero-more-menu"><summary class="hero-btn hero-btn-ghost hero-btn-compact">More actions ▾</summary>' +
          '<div class="hero-more-menu-list">' +
          docsItems.join("") +
          "</div></details>"
      );
    }

    parts.push("</span>");
    return parts.join("");
  }

  var aiEditModalEl = null;
  var aiEditModalJob = null;

  function ensureAiEditModal() {
    if (aiEditModalEl) return aiEditModalEl;
    aiEditModalEl = document.createElement("div");
    aiEditModalEl.id = "jobs-ai-edit-modal";
    aiEditModalEl.className = "jobs-ai-modal";
    aiEditModalEl.setAttribute("hidden", "");
    aiEditModalEl.innerHTML =
      '<div class="jobs-ai-modal-backdrop" data-close-ai-modal tabindex="-1"></div>' +
      '<div class="jobs-ai-modal-card" role="dialog" aria-labelledby="jobs-ai-modal-title" aria-modal="true">' +
      '<button type="button" class="jobs-ai-modal-close" data-close-ai-modal aria-label="Close">×</button>' +
      '<h3 id="jobs-ai-modal-title" class="jobs-ai-modal-title">Edit with AI</h3>' +
      '<p class="jobs-ai-modal-sub">Describe what to add, remove, or reword.</p>' +
      '<textarea class="jobs-ai-modal-input" data-ai-instruction rows="4" placeholder="e.g. Remove Java — I don’t know it. Add my Python project at LTU."></textarea>' +
      '<div class="jobs-ai-modal-actions">' +
      '<select class="hero-mat-select" data-ai-material aria-label="Document">' +
      '<option value="cv">Tailored CV</option>' +
      '<option value="cover_letter">Cover letter</option>' +
      "</select>" +
      '<select class="hero-mat-select" data-ai-language aria-label="Language">' +
      '<option value="auto">Auto language</option>' +
      '<option value="en">English</option>' +
      '<option value="de">Deutsch</option>' +
      '<option value="no">Norsk</option>' +
      "</select>" +
      '<button type="button" class="hero-btn hero-btn-generate" data-action="refine-materials">Update</button>' +
      "</div>" +
      '<p class="jobs-ai-modal-note" data-ai-chat-status hidden></p>' +
      "</div>";
    document.body.appendChild(aiEditModalEl);
    aiEditModalEl.querySelectorAll("[data-close-ai-modal]").forEach(function (el) {
      el.addEventListener("click", closeAiEditModal);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && aiEditModalEl && !aiEditModalEl.hasAttribute("hidden")) {
        closeAiEditModal();
      }
    });
    return aiEditModalEl;
  }

  function closeAiEditModal() {
    if (!aiEditModalEl) return;
    aiEditModalEl.setAttribute("hidden", "");
    document.body.classList.remove("jobs-ai-modal-open");
    aiEditModalJob = null;
  }

  function openAiEditModal(job) {
    if (!job) return;
    if (!refineMaterialsUrl) {
      alert("AI edit is not available on this page. Refresh and try again.");
      return;
    }
    var modal = ensureAiEditModal();
    aiEditModalJob = job;
    modal.removeAttribute("hidden");
    document.body.classList.add("jobs-ai-modal-open");
    syncApplyChatControls(modal, job);
    var note = modal.querySelector("[data-ai-chat-status]");
    var materials = job.materials || {};
    var hasAny = hasTailoredDoc(materials, "cv") || hasTailoredDoc(materials, "cover_letter");
    if (note) {
      if (!hasAny) {
        note.hidden = false;
        note.textContent = "Create a tailored CV or letter first (Create button), then describe changes here.";
      } else {
        note.hidden = true;
        note.textContent = "";
      }
    }
    var instructionEl = modal.querySelector("[data-ai-instruction]");
    if (instructionEl && !instructionEl.disabled) {
      instructionEl.focus();
    }
  }

  function syncApplyChatControls(root, job) {
    if (!root) return;
    job = job || aiEditModalJob || (selectedId && byId[selectedId]) || null;
    if (!job) return;
    var materials = job.materials || {};
    var matSelect = root.querySelector("[data-ai-material]");
    var refineBtn = root.querySelector("[data-action='refine-materials']");
    var instructionEl = root.querySelector("[data-ai-instruction]");
    var materialType = (matSelect && matSelect.value) || "cv";
    var ready = hasTailoredDoc(materials, materialType);
    if (refineBtn) {
      refineBtn.disabled = false;
    }
    if (instructionEl) {
      instructionEl.disabled = false;
    }
    var note = root.querySelector("[data-ai-chat-status]");
    if (note && !ready) {
      note.hidden = false;
      note.textContent =
        materialType === "cover_letter"
          ? "Create a cover letter first (pick “Cover letter”, then Create)."
          : "Create a tailored CV first (pick “Tailored CV”, then Create).";
    } else if (note && ready) {
      note.hidden = true;
      note.textContent = "";
    }
  }

  function reqStatusLabel(status) {
    var s = (status || "").toLowerCase();
    if (s === "met") return "Met";
    if (s === "partial") return "Partial";
    if (s === "missing") return "Missing";
    return esc(status);
  }

  function renderRequirements(detail) {
    if (!detail || !detail.requirements || !detail.requirements.length) {
      return "";
    }
    var rows = detail.requirements
      .map(function (row) {
        var status = (row.status || "missing").toLowerCase();
        return (
          "<tr><td>" +
          esc(row.requirement) +
          '</td><td><span class="jobs-req-status ' +
          esc(status) +
          '">' +
          reqStatusLabel(status) +
          "</span></td><td>" +
          esc(row.evidence || "") +
          "</td></tr>"
        );
      })
      .join("");
    return (
      '<div class="jobs-req-table-wrap"><table class="jobs-req-table"><thead><tr><th>Requirement</th><th>Fit</th><th>Your CV</th></tr></thead><tbody>' +
      rows +
      "</tbody></table></div>"
    );
  }

  function isApplied(jobId) {
    return appliedIds.has(jobId);
  }

  function toggleApplied(job, btn) {
    if (!appliedToggleUrl || !job) return;
    if (btn) btn.disabled = true;
    fetch(appliedToggleUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      credentials: "same-origin",
      body: JSON.stringify({
        job_id: job.job_id,
        title: job.title,
        company: job.company,
        location: job.location,
        country: job.country || "",
        apply_url: job.apply_url || ""
      })
    })
      .then(fetchJsonResponse)
      .then(function (result) {
        var data = result.data || {};
        if (!result.ok || !data.ok) {
          throw new Error(data.error || "Could not update applied status");
        }
        if (data.applied) {
          appliedIds.add(job.job_id);
          if (!isAppliedView) {
            window.location.href =
              (window.JOBS_HUB && window.JOBS_HUB.appliedPageUrl) || "/jobs/applied/";
            return;
          }
        } else {
          appliedIds.delete(job.job_id);
          if (isAppliedView) {
            masterJobs = masterJobs.filter(function (j) {
              return j.job_id !== job.job_id;
            });
            applyStableJobView();
            selectedId = jobs.length ? jobs[0].job_id : "";
          }
        }
        renderList({ preserveScroll: true, skipAutoSelect: true });
        if (!isAppliedView || data.applied) {
          renderDetail(byId[job.job_id] || null);
        }
      })
      .catch(function (err) {
        showHubToast((err && err.message) || "Could not update applied status", true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }


  function applyGenerateResult(job, data) {
    if (!job.materials) job.materials = {};
    if (data.tailored_cv_url) {
      job.materials.has_tailored_cv = true;
      job.materials.tailored_cv_url = data.tailored_cv_url;
    }
    if (data.tailored_cover_letter_url) {
      job.materials.has_tailored_cover_letter = true;
      job.materials.tailored_cover_letter_url = data.tailored_cover_letter_url;
    }
    byId[job.job_id] = job;
    saveJobsSnapshot();
  }

  function postGenerate(job, materialType) {
    var detail = document.getElementById("jobs-detail-content");
    var langSelect = detail ? detail.querySelector("[data-language-select]") : null;
    var outputLang = (langSelect && langSelect.value) || "auto";
    return fetch(generateMaterialsUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      credentials: "same-origin",
      body: JSON.stringify({ job_id: job.job_id, material: materialType, job: job, lang: outputLang })
    })
      .then(fetchJsonResponse)
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error((result.data && result.data.error) || "Generation failed");
        }
        applyGenerateResult(job, result.data);
        return result.data;
      });
  }

  function openGeneratedDoc(data, materialType) {
    var url = "";
    if (materialType === "cover_letter" && data.tailored_cover_letter_url) {
      url = data.tailored_cover_letter_url;
    } else if (data.tailored_cv_url) {
      url = data.tailored_cv_url;
    }
    if (!url) return false;
    var win = window.open(url, "_blank", "noopener");
    return !!win;
  }

  function generateTailoredMaterials(job, btn, materialType) {
    if (!generateMaterialsUrl || !job || !job.job_id) return;
    materialType = materialType || "cv";
    var steps =
      materialType === "both" ? ["cv", "cover_letter"] : [materialType];
    generatingJobId = job.job_id;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Creating…";
    }
    if (document.body.getAttribute("data-pipeline-running") === "1") {
      showHubToast(
        "Find jobs is still running — Create works but may be slow. Cancel Find jobs if it keeps failing.",
        false
      );
    } else {
      showHubToast(
        "Creating — please wait 1–2 minutes per document. Keep this tab open.",
        false
      );
    }

    var chain = Promise.resolve();
    steps.forEach(function (step, index) {
      chain = chain.then(function () {
        var label =
          step === "cover_letter"
            ? "cover letter"
            : "CV";
        if (btn) {
          btn.textContent =
            steps.length > 1
              ? "Creating " + label + " (" + (index + 1) + "/" + steps.length + ")…"
              : "Creating…";
        }
        showHubToast(
          "Writing " + label + (steps.length > 1 ? " (" + (index + 1) + "/" + steps.length + ")" : "") + "…",
          false
        );
        return postGenerate(job, step);
      });
    });

    chain
      .then(function (lastData) {
        renderDetail(job);
        var lastStep = steps[steps.length - 1];
        var opened = openGeneratedDoc(lastData, lastStep);
        if (steps.length > 1 && lastData.tailored_cv_url) {
          openGeneratedDoc({ tailored_cv_url: lastData.tailored_cv_url }, "cv");
        }
        if (opened) {
          showHubToast("Done — document opened in a new tab.", false);
        } else {
          showHubToast(
            "Done — use the ↗ button above to open it (popup may have been blocked).",
            false
          );
        }
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Create";
        }
        setTimeout(function () {
          openAiEditModal(job);
        }, 100);
      })
      .catch(function (err) {
        showHubToast(err.message || "Could not generate materials", true);
        alert(err.message || "Could not generate materials");
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Create";
        }
      })
      .finally(function () {
        generatingJobId = "";
      });
  }

  function refineMaterials(job, btn, materialType, instruction) {
    if (!refineMaterialsUrl || !job || !job.job_id) return;
    if (!instruction || instruction.length < 4) {
      alert("Describe what you want changed (at least a few words).");
      return;
    }
    if (!hasTailoredDoc(job.materials || {}, materialType)) {
      alert(
        materialType === "cover_letter"
          ? "Create a cover letter first (pick “Cover letter”, then Create)."
          : "Create a tailored CV first (pick “Tailored CV”, then Create)."
      );
      return;
    }
    generatingJobId = job.job_id;
    var modal = ensureAiEditModal();
    var statusEl = modal.querySelector("[data-ai-chat-status]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Updating…";
    }
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = "AI is rewriting your document…";
    }
    var langSelect = modal.querySelector("[data-ai-language]");
    fetch(refineMaterialsUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      credentials: "same-origin",
      body: JSON.stringify({
        job_id: job.job_id,
        material: materialType,
        instruction: instruction,
        job: job,
        lang: (langSelect && langSelect.value) || "auto"
      })
    })
      .then(fetchJsonResponse)
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error((result.data && result.data.error) || "Update failed");
        }
        if (!job.materials) job.materials = {};
        if (result.data.tailored_cv_url) {
          job.materials.has_tailored_cv = true;
          job.materials.tailored_cv_url = result.data.tailored_cv_url;
        }
        if (result.data.tailored_cover_letter_url) {
          job.materials.has_tailored_cover_letter = true;
          job.materials.tailored_cover_letter_url = result.data.tailored_cover_letter_url;
        }
        renderDetail(job);
        if (result.data.tailored_cv_url && materialType === "cv") {
          window.open(result.data.tailored_cv_url, "_blank", "noopener");
        } else if (result.data.tailored_cover_letter_url && materialType === "cover_letter") {
          window.open(result.data.tailored_cover_letter_url, "_blank", "noopener");
        }
        var refineStatus = modal.querySelector("[data-ai-chat-status]");
        if (refineStatus) {
          refineStatus.hidden = false;
          refineStatus.textContent = "Updated — check the document.";
        }
        var instructionEl = modal.querySelector("[data-ai-instruction]");
        if (instructionEl) {
          instructionEl.value = "";
          instructionEl.focus();
        }
      })
      .catch(function (err) {
        alert(err.message || "Could not update document");
        if (statusEl) {
          statusEl.textContent = err.message || "Update failed";
        }
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Update";
        }
      })
      .finally(function () {
        generatingJobId = "";
      });
  }

  function renderDetail(job) {
    if (!job) {
      detailContent.innerHTML = "";
      return;
    }

    var detail = job.match_detail;
    var scored = job.scored;
    var heroDocButtons = buildHeroDocButtons(job);

    var applied = isAppliedView || isApplied(job.job_id);
    var appliedBtn =
      '<button type="button" class="hero-btn hero-btn-applied' +
      (applied ? " is-applied" : "") +
      '" data-applied-toggle data-tip="Removes this job from your browse list after you apply">Mark applied</button>';
    if (isAppliedView) {
      appliedBtn =
        '<button type="button" class="hero-btn hero-btn-applied is-applied" data-applied-toggle data-tip="Remove from your applications list">Remove</button>';
    } else if (applied) {
      appliedBtn =
        '<button type="button" class="hero-btn hero-btn-applied is-applied" data-applied-toggle data-tip="You marked this as applied">Applied ✓</button>';
    }

    var appliedDateLine =
      isAppliedView && job.applied_date
        ? '<p class="jobs-hero-applied-date">Applied ' +
          esc(job.applied_date) +
          (job.country ? " · " + esc(job.country) : "") +
          "</p>"
        : "";

    var applyBtn = job.apply_url
      ? '<a class="hero-btn hero-btn-primary" href="' +
        esc(job.apply_url) +
        '" target="_blank" rel="noopener noreferrer" data-tip="Open the company job page and apply there">Apply on site ↗</a>'
      : "";

    var aiPanel = "";
    if (scored && detail) {
      var chips = "";
      (detail.required_met || []).slice(0, 4).forEach(function (item) {
        chips += '<span class="jobs-ai-chip chip-met">✓ ' + esc(item) + "</span>";
      });
      (detail.required_missing || []).slice(0, 3).forEach(function (item) {
        chips += '<span class="jobs-ai-chip chip-miss">✗ ' + esc(item) + "</span>";
      });
      aiPanel =
        '<section class="jobs-ai-panel">' +
        '<h3 data-tip="How your CV compares to this posting (in English)">CV match</h3>' +
        (detail.reasoning
          ? '<p class="jobs-ai-reasoning">' + esc(detail.reasoning) + "</p>"
          : job.ai_summary
            ? '<p class="jobs-ai-reasoning">' + esc(job.ai_summary) + "</p>"
            : "") +
        (chips ? '<div class="jobs-ai-meta">' + chips + "</div>" : "") +
        renderRequirements(detail) +
        "</section>";
    } else if (!scored) {
      var pendingHint = job.keyword_hint
        ? "<p class=\"jobs-ai-reasoning\">" + esc(job.keyword_hint) + "</p>"
        : "";
      aiPanel =
        '<section class="jobs-ai-panel">' +
        '<h3>Not scored yet</h3>' +
        pendingHint +
        '<p class="jobs-ai-reasoning">' +
        "Click <strong>Score this job</strong> for an urgent AI match, or use <strong>Score AI</strong> in the top bar for all jobs. " +
        "Bulk search keeps running on the server if you browse or refresh.</p>" +
        "</section>";
    }

    var postingDivider =
      '<div class="jobs-section-divider" role="separator">' +
      '<span class="jobs-section-divider-line" aria-hidden="true"></span>' +
      '<span class="jobs-section-divider-label">' +
      '<span class="jobs-section-tick" aria-hidden="true">✓</span> Job posting' +
      "</span>" +
      '<span class="jobs-section-divider-line" aria-hidden="true"></span>' +
      "</div>";

    var mobileBack = isMobileLayout()
      ? '<button type="button" class="jobs-mobile-back" data-mobile-back>← Back to jobs</button>'
      : "";

    var displayTitle = jobDisplayTitle(job);
    var originalTitle = (job.title || "").trim();
    var titleNote =
      originalTitle && displayTitle !== originalTitle
        ? '<p class="jobs-hero-title-original" title="Original listing title">' +
          esc(originalTitle) +
          "</p>"
        : "";
    var locationParts = [job.location, job.country, job.source, job.remote ? "Remote" : ""].filter(Boolean);

    var scoreOneBtn =
      !scored && scoreOneUrl
        ? '<button type="button" class="hero-btn hero-btn-score-one" data-score-one-job data-tip="Score only this job with AI">Score this job ✦</button>'
        : "";

    detailContent.innerHTML =
      mobileBack +
      '<div class="jobs-detail-hero">' +
      '<div class="jobs-detail-hero-head">' +
      '<div class="jobs-detail-hero-title">' +
      "<h2>" +
      esc(displayTitle) +
      "</h2>" +
      titleNote +
      '<p class="jobs-hero-company">' +
      esc(job.company) +
      "</p>" +
      '<p class="jobs-hero-location">' +
      esc(locationParts.join(" · ")) +
      "</p>" +
      appliedDateLine +
      "</div>" +
      '<div class="jobs-detail-hero-match">' +
      matchChipHtml(job) +
      "</div>" +
      "</div>" +
      '<div class="jobs-detail-hero-row">' +
      '<div class="jobs-detail-hero-actions">' +
      scoreOneBtn +
      applyBtn +
      appliedBtn +
      "</div>" +
      "</div>" +
      (heroDocButtons
        ? '<div class="jobs-detail-hero-row"><div class="jobs-detail-hero-actions jobs-detail-hero-actions-secondary">' +
          heroDocButtons +
          "</div></div>"
        : "") +
      "</div>" +
      aiPanel +
      postingDivider +
      '<section class="jobs-description-panel">' +
      '<div class="jobs-detail-body">' +
      formatDescription(job.description) +
      "</div>" +
      (job.apply_url
        ? '<p class="jobs-detail-link-note">Listing: <a href="' +
          esc(job.apply_url) +
          '" target="_blank" rel="noopener">' +
          esc(job.apply_url) +
          "</a></p>"
        : "") +
      "</section>";

    var toggleBtn = detailContent.querySelector("[data-applied-toggle]");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        toggleApplied(job, toggleBtn);
      });
    }
    var scoreOneHero = detailContent.querySelector("[data-score-one-job]");
    if (scoreOneHero) {
      scoreOneHero.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        scoreOneJob(job, scoreOneHero);
      });
    }
    var genBtn = detailContent.querySelector("[data-action='generate-materials']");
    if (genBtn) {
      genBtn.addEventListener("click", function () {
        var select = detailContent.querySelector("[data-material-select]");
        var materialType = (select && select.value) || "cv";
        generateTailoredMaterials(job, genBtn, materialType);
      });
    }
    var openAiBtn = detailContent.querySelector("[data-action='open-ai-edit']");
    if (openAiBtn) {
      openAiBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openAiEditModal(byId[job.job_id] || job);
      });
    }
    wireAiEditModalActions(job);
    var mobileBackBtn = detailContent.querySelector("[data-mobile-back]");
    if (mobileBackBtn) {
      mobileBackBtn.addEventListener("click", closeMobileDetail);
    }
  }

  function wireAiEditModalActions(job) {
    var modal = ensureAiEditModal();
    var refineBtn = modal.querySelector("[data-action='refine-materials']");
    if (refineBtn && !refineBtn.dataset.wired) {
      refineBtn.dataset.wired = "1";
      refineBtn.addEventListener("click", function () {
        var activeJob = aiEditModalJob || job;
        var instructionEl = modal.querySelector("[data-ai-instruction]");
        var matSelect = modal.querySelector("[data-ai-material]");
        var instruction = (instructionEl && instructionEl.value) || "";
        var materialType = (matSelect && matSelect.value) || "cv";
        refineMaterials(activeJob, refineBtn, materialType, instruction.trim());
      });
    }
    var aiMatSelect = modal.querySelector("[data-ai-material]");
    if (aiMatSelect && !aiMatSelect.dataset.wired) {
      aiMatSelect.dataset.wired = "1";
      aiMatSelect.addEventListener("change", function () {
        syncApplyChatControls(modal, aiEditModalJob || job);
      });
    }
  }

  function setSelected(jobId, pushState, opts) {
    opts = opts || {};
    selectedId = jobId;
    closeAiEditModal();
    syncJobListSelection({ scroll: opts.scroll !== false });

    renderDetail(byId[jobId]);

    if (pushState !== false && jobId) {
      var url = new URL(window.location.href);
      url.searchParams.set("job", jobId);
      history.replaceState({ jobId: jobId }, "", url.toString());
    }

    if (isMobileLayout() && byId[jobId]) {
      setMobileDetailOpen(true);
      document.getElementById("jobs-detail").scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      setMobileDetailOpen(false);
    }
  }

  function renderList(opts) {
    opts = opts || {};
    var scrollTop = opts.preserveScroll ? listEl.scrollTop : 0;
    listEl.innerHTML = "";
    if (!jobs.length) {
      listEl.innerHTML =
        '<p class="empty jobs-empty-state" style="padding:24px;line-height:1.6;">' +
        emptyListMessage() +
        "</p>";
      detailContent.innerHTML = "";
      var countElEmpty = document.getElementById("jobs-list-count");
      if (countElEmpty) countElEmpty.textContent = "0";
      renderMarketBanner(lastMarketStats || {});
      return;
    }

    if (isAppliedView) {
      var head = document.createElement("div");
      head.className = "applied-list-header";
      head.innerHTML =
        "<span>#</span><span>Company</span><span>Role</span><span>Applied</span>";
      listEl.appendChild(head);
    }

    jobs.forEach(function (job, index) {
      var card = document.createElement("div");
      card.className = "job-card" + (isApplied(job.job_id) ? " is-applied" : "");
      if (isAppliedView) {
        card.className += " job-card-applied-row";
      }
      card.dataset.jobId = job.job_id;
      card.setAttribute("role", "option");
      card.tabIndex = 0;

      if (isAppliedView) {
        var scoreMini =
          job.match_score != null
            ? '<span class="applied-card-score">' + esc(String(job.match_score)) + "% match</span>"
            : "";
        var company = job.company || "Unknown company";
        var role = jobDisplayTitle(job);
        card.innerHTML =
          '<span class="applied-card-num">' +
          String(index + 1) +
          "</span>" +
          '<span class="applied-card-company" title="' +
          esc(company) +
          '">' +
          esc(company) +
          "</span>" +
          '<span class="applied-card-role" title="' +
          esc(role) +
          '">' +
          esc(role) +
          "</span>" +
          '<span class="applied-card-date">' +
          esc(job.applied_date || "—") +
          scoreMini +
          "</span>";
        card.addEventListener("click", function () {
          setSelected(job.job_id);
        });
        card.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setSelected(job.job_id);
          }
        });
        listEl.appendChild(card);
        return;
      }

      var scoreBadge = jobCardScoreBadgeHtml(job);

      var displayTitle = jobDisplayTitle(job);
      var originalTitle = (job.title || "").trim();
      var titleAttr =
        originalTitle && displayTitle !== originalTitle
          ? ' title="Original: ' + esc(originalTitle) + '"'
          : "";
      var companyName = job.company || "Company";
      var subParts = [companyName, job.location, job.source].filter(Boolean);
      var hintLine = truncateText(jobCardHint(job), 120);
      var hintHtml = hintLine
        ? '<p class="job-card-hint">' + esc(hintLine) + "</p>"
        : "";

      card.innerHTML =
        '<div class="job-card-row">' +
        '<div class="job-card-text">' +
        '<p class="job-card-title"' +
        titleAttr +
        ">" +
        esc(displayTitle) +
        "</p>" +
        jobCardBadgesHtml(job) +
        '<p class="job-card-sub">' +
        esc(subParts.join(" · ")) +
        "</p>" +
        hintHtml +
        "</div>" +
        '<div class="job-card-aside">' +
        scoreBadge +
        "</div>" +
        "</div>";

      card.addEventListener("click", function (e) {
        if (e.target.closest("[data-score-one], .job-card-score-btn")) return;
        setSelected(job.job_id);
      });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          if (e.target.closest("[data-score-one], .job-card-score-btn")) return;
          e.preventDefault();
          setSelected(job.job_id);
        }
      });
      listEl.appendChild(card);
    });

    if (opts.preserveScroll) {
      listEl.scrollTop = scrollTop;
    }

    if (!opts.skipAutoSelect) {
      if (selectedId && byId[selectedId]) {
        setSelected(selectedId, false, { scroll: opts.scrollOnSelect !== true });
      } else if (jobs.length) {
        setSelected(jobs[0].job_id, false, { scroll: opts.scrollOnSelect === true });
      }
    } else {
      syncJobListSelection({ scroll: false });
    }
    var countEl = document.getElementById("jobs-list-count");
    if (countEl) {
      countEl.textContent = String(jobs.length);
    }
    if (lastMarketStats) {
      updateTopbarFromMarket(lastMarketStats);
    }
  }

  window.JOBS_HUB.getBrowseStats = function (data) {
    return enrichMarketStats(data || {});
  };

  window.JOBS_HUB.switchBrowseView = switchBrowseView;
  window.JOBS_HUB.refilterFromUrl = refilterFromUrl;
  window.JOBS_HUB.onPipelineCancelled = function () {
    stopLivePolling();
    stopScorePolling();
    document.body.removeAttribute("data-pipeline-running");
    marketLoadState = "ready";
    var hub = window.JOBS_HUB || {};
    var expected = hub.jobsTotalCount || hub.cacheRawTotal || 0;
    if (!masterJobs.length && expected > 0) {
      refreshLiveJobs().then(function () {
        if (!jobs.length) switchBrowseView("all");
        else renderList();
      });
      return;
    }
    if (!jobs.length && masterJobs.length > 0) {
      switchBrowseView("all");
    } else {
      renderMarketBanner(lastMarketStats || {});
      renderList();
    }
    showHubToast("Stopped. Browse → All jobs to see your listings.", false);
  };
  window.JOBS_HUB.applyStatusJobPreviews = applyStatusJobPreviews;
  window.JOBS_HUB.refreshLiveJobs = refreshLiveJobs;

  window.JOBS_HUB.reloadFromServer = function (detail) {
    detail = detail || {};
    refreshFromMarketData({ merge: !detail.force, force: !!detail.force });
  };

  var scorePollTimer = null;
  function pollIntervalMs() {
    return document.body.getAttribute("data-pipeline-running") === "1" ? 12000 : 0;
  }
  function startScorePolling() {
    if (scorePollTimer || isAppliedView) return;
    if (pollIntervalMs() <= 0) return;
    function tick() {
      refreshFromMarketData({ merge: true });
    }
    setTimeout(tick, 2000);
    scorePollTimer = setInterval(tick, pollIntervalMs());
  }
  function stopScorePolling() {
    if (scorePollTimer) {
      clearInterval(scorePollTimer);
      scorePollTimer = null;
    }
  }

  parseJobs();
  if (window.JOBS_HUB) {
    lastMarketStats = {
      cache_raw_total: window.JOBS_HUB.cacheRawTotal,
      good_fits_total: window.JOBS_HUB.goodFitsTotal,
      unscored_total: window.JOBS_HUB.unscoredTotal,
      scored_total: window.JOBS_HUB.scoredTotal,
    };
  }
  if (masterJobs.length) {
    marketLoadState = "ready";
  }
  if (!maybeOpenAllWhenEmpty()) {
    if (
      !jobs.length &&
      masterJobs.length > 0 &&
      (window.JOBS_HUB && window.JOBS_HUB.cacheRawTotal > 0) &&
      currentBrowseView() !== "all"
    ) {
      switchBrowseView("all");
    } else {
      renderMarketBanner(lastMarketStats || {});
      renderList();
    }
  }
  listEl.addEventListener(
    "click",
    function (e) {
      var scoreBtn = e.target.closest("[data-score-one]");
      if (!scoreBtn) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      var jobId = scoreBtn.getAttribute("data-score-one");
      if (jobId) {
        var job = jobById(jobId);
        if (job) scoreOneJob(job, scoreBtn);
        else showHubToast("Job not loaded yet — wait a moment or refresh once.", true);
      }
    },
    true
  );
  listEl.addEventListener("click", function (e) {
    var browseBtn = e.target.closest("[data-browse-view]");
    if (browseBtn) {
      e.preventDefault();
      switchBrowseView(browseBtn.getAttribute("data-browse-view") || "all");
      return;
    }
  });
  syncPipelineState();
  if (document.body.getAttribute("data-pipeline-running") === "1") {
    ensureJobsLoaded();
    startLivePolling();
  } else {
    var hubBg = window.JOBS_HUB || {};
    var expectedTotal = hubBg.jobsTotalCount || hubBg.cacheRawTotal || 0;
    if (masterJobs.length > 0 && masterJobs.length < expectedTotal) {
      refreshFromMarketData({ merge: true, force: false });
    } else if (!masterJobs.length && expectedTotal > 0) {
      refreshLiveJobs();
    }
  }
  wireAddJobLinkButton();

  function wireAddJobLinkButton() {
    var btn = document.getElementById("add-job-link-btn");
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      openAddJobModal();
    });
  }

  var addJobModalEl = null;

  function ensureAddJobModal() {
    if (addJobModalEl) return addJobModalEl;
    addJobModalEl = document.createElement("div");
    addJobModalEl.id = "jobs-add-link-modal";
    addJobModalEl.className = "jobs-ai-modal";
    addJobModalEl.setAttribute("hidden", "");
    addJobModalEl.innerHTML =
      '<div class="jobs-ai-modal-backdrop" data-close-add-job tabindex="-1"></div>' +
      '<div class="jobs-ai-modal-card" role="dialog" aria-labelledby="jobs-add-link-title" aria-modal="true">' +
      '<button type="button" class="jobs-ai-modal-close" data-close-add-job aria-label="Close">×</button>' +
      '<h3 id="jobs-add-link-title" class="jobs-ai-modal-title">Add job from link</h3>' +
      '<p class="jobs-ai-modal-sub">Paste a posting URL (LinkedIn, company site, Arbeitsagentur, StepStone…). We fetch the job, add it to your list, and score it with AI when possible.</p>' +
      '<input type="url" class="jobs-ai-modal-input jobs-add-link-input" data-import-url placeholder="https://…" autocomplete="off">' +
      '<div class="jobs-ai-modal-actions">' +
      '<button type="button" class="hero-btn hero-btn-generate" data-action="submit-import-job">Add &amp; score</button>' +
      "</div>" +
      '<p class="jobs-ai-modal-note" data-import-status hidden></p>' +
      "</div>";
    document.body.appendChild(addJobModalEl);
    addJobModalEl.querySelectorAll("[data-close-add-job]").forEach(function (el) {
      el.addEventListener("click", closeAddJobModal);
    });
    var submitBtn = addJobModalEl.querySelector("[data-action='submit-import-job']");
    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        submitImportJob(submitBtn);
      });
    }
    var input = addJobModalEl.querySelector("[data-import-url]");
    if (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          submitImportJob(submitBtn);
        }
      });
    }
    return addJobModalEl;
  }

  function closeAddJobModal() {
    if (!addJobModalEl) return;
    addJobModalEl.setAttribute("hidden", "");
    document.body.classList.remove("jobs-ai-modal-open");
  }

  function openAddJobModal() {
    if (!importJobUrl) {
      alert("Import URL is not available on this page. Refresh and try again.");
      return;
    }
    var modal = ensureAddJobModal();
    modal.removeAttribute("hidden");
    document.body.classList.add("jobs-ai-modal-open");
    var status = modal.querySelector("[data-import-status]");
    if (status) {
      status.hidden = true;
      status.textContent = "";
    }
    var input = modal.querySelector("[data-import-url]");
    if (input) {
      input.value = "";
      input.focus();
    }
  }

  if (window.JOBS_HUB) {
    window.JOBS_HUB.openAddJobModal = openAddJobModal;
  }

  function submitImportJob(btn) {
    if (!importJobUrl) return;
    var modal = ensureAddJobModal();
    var input = modal.querySelector("[data-import-url]");
    var status = modal.querySelector("[data-import-status]");
    var url = (input && input.value || "").trim();
    if (!url) {
      if (status) {
        status.hidden = false;
        status.textContent = "Paste a job URL first.";
      }
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Adding…";
    }
    if (status) {
      status.hidden = false;
      status.textContent = "Fetching job page and scoring — may take 30–90 seconds…";
    }
    fetch(importJobUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ url: url, score: true }),
    })
      .then(fetchJsonResponse)
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.ok) {
          throw new Error((res.data && res.data.error) || "Import failed");
        }
        var job = res.data.job;
        if (!job || !job.job_id) {
          throw new Error("Server did not return a job");
        }
        masterJobs = mergeJobArrays(masterJobs, [job]);
        touchDisplayOrder(job.job_id);
        applyStableJobView();
        saveJobsSnapshot();
        renderList({ preserveScroll: true });
        setSelected(job.job_id, true);
        closeAddJobModal();
        var msg = res.data.message || "Job added.";
        if (res.data.warning) msg += " " + res.data.warning;
        showHubToast(msg, false);
        if (typeof window.updateBrowseDropdownCounts === "function") {
          refreshFromMarketData({ merge: true, force: true });
        }
      })
      .catch(function (err) {
        if (status) {
          status.hidden = false;
          status.textContent = err.message || "Could not import that URL.";
        }
        showHubToast(err.message || "Import failed", true);
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Add & score";
        }
      });
  }

  document.addEventListener("jobs-score-tick", function (e) {
    var detail = (e && e.detail) || {};
    applyStatusJobPreviews(detail);
    if (scoreOneInFlight > 0) return;
    if (document.body.getAttribute("data-pipeline-running") === "1") return;
    if (detail.state === "completed") {
      refreshFromMarketData({ merge: true });
    }
  });

  document.addEventListener("jobs-pipeline-started", function () {
    document.body.setAttribute("data-pipeline-running", "1");
    startLivePolling();
    startScorePolling();
    syncPipelineState();
  });

  if (document.body.getAttribute("data-pipeline-running") === "1") {
    startScorePolling();
    startLivePolling();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && document.body.getAttribute("data-pipeline-running") === "1") {
      refreshFromMarketData();
    }
  });

  window.addEventListener("resize", function () {
    if (!isMobileLayout()) {
      setMobileDetailOpen(false);
    } else if (selectedId && byId[selectedId]) {
      setMobileDetailOpen(true);
    }
  });
})();
