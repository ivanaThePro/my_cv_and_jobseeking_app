(function () {
  function wireDropdown(btnId, menuId) {
    var menuBtn = document.getElementById(btnId);
    var menu = document.getElementById(menuId);
    if (!menuBtn || !menu) return;

    function closeMenu() {
      menu.hidden = true;
      menuBtn.setAttribute("aria-expanded", "false");
    }

    menuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      hideTip();
      var open = menu.hidden;
      document.querySelectorAll(".topbar-dropdown").forEach(function (el) {
        if (el !== menu) el.hidden = true;
      });
      document.querySelectorAll("[aria-controls]").forEach(function (btn) {
        if (btn !== menuBtn && btn.getAttribute("aria-controls")) {
          btn.setAttribute("aria-expanded", "false");
        }
      });
      menu.hidden = !open;
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });

    menu.addEventListener("click", function (e) {
      e.stopPropagation();
    });

    return closeMenu;
  }

  var closeCv = wireDropdown("topbar-menu-btn", "topbar-menu");
  wireDropdown("browse-menu-btn", "browse-menu");

  document.addEventListener("click", function () {
    document.querySelectorAll(".topbar-dropdown").forEach(function (el) {
      el.hidden = true;
    });
    document.querySelectorAll("[aria-controls]").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".topbar-dropdown").forEach(function (el) {
        el.hidden = true;
      });
    }
  });

  function browseFilterQsFromForm(form) {
    if (!form) return "";
    var params = new URLSearchParams();
    var english = form.querySelector('input[name="english_ok"]');
    if (english && english.checked) params.set("english_ok", "1");
    var entry = form.querySelector('input[name="entry"]');
    if (entry && entry.checked) params.set("entry", "1");
    var program = form.querySelector('select[name="program"]');
    var programVal = program ? program.value : "";
    if (programVal) params.set("program", programVal);
    var s = params.toString();
    return s ? "&" + s : "";
  }

  function syncBrowseChipHrefs() {
    var extra = browseFilterQsFromForm(document.querySelector(".browse-filter-form"));
    document.querySelectorAll(".browse-chip, .stat-chip-link[data-stat-view]").forEach(function (link) {
      var view = link.getAttribute("data-stat-view");
      if (!view) {
        try {
          view = new URL(link.href, window.location.origin).searchParams.get("view") || "all";
        } catch (err) {
          view = "all";
        }
      }
      link.href = "?view=" + encodeURIComponent(view) + extra;
    });
  }

  function closeBrowseMenu() {
    var menu = document.getElementById("browse-menu");
    var menuBtn = document.getElementById("browse-menu-btn");
    if (menu) menu.hidden = true;
    if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
  }

  function applyBrowseFilters(form, opts) {
    opts = opts || {};
    if (!form) return;
    var url = new URL(window.location.href);
    var viewInput = form.querySelector('input[name="view"]');
    if (viewInput && viewInput.value) {
      url.searchParams.set("view", viewInput.value);
    }
    var english = form.querySelector('input[name="english_ok"]');
    if (english && english.checked) {
      url.searchParams.set("english_ok", "1");
    } else {
      url.searchParams.delete("english_ok");
    }
    var entry = form.querySelector('input[name="entry"]');
    if (entry && entry.checked) {
      url.searchParams.set("entry", "1");
    } else {
      url.searchParams.delete("entry");
    }
    var program = form.querySelector('select[name="program"]');
    var programVal = program ? program.value : "";
    if (programVal) {
      url.searchParams.set("program", programVal);
    } else {
      url.searchParams.delete("program");
    }
    history.replaceState(null, "", url.toString());
    syncBrowseChipHrefs();
    if (!document.body.classList.contains("jobs-hub-page")) {
      form.submit();
      return;
    }
    if (viewInput && viewInput.value && window.JOBS_HUB) {
      window.JOBS_HUB.view = viewInput.value;
    }
    if (window.JOBS_HUB && typeof window.JOBS_HUB.refilterFromUrl === "function") {
      window.JOBS_HUB.refilterFromUrl();
    } else if (window.JOBS_HUB && typeof window.JOBS_HUB.switchBrowseView === "function") {
      window.JOBS_HUB.switchBrowseView(viewInput ? viewInput.value : "all");
    } else {
      form.submit();
      return;
    }
    if (opts.closeMenu) closeBrowseMenu();
  }

  document.querySelectorAll(".browse-filter-form").forEach(function (form) {
    form.addEventListener("change", function (e) {
      e.preventDefault();
      applyBrowseFilters(form);
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      applyBrowseFilters(form, { closeMenu: true });
    });
    form.querySelectorAll('input[type="checkbox"], select').forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.stopPropagation();
      });
    });
    var doneBtn = form.querySelector(".browse-filter-done");
    if (doneBtn) {
      doneBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        applyBrowseFilters(form, { closeMenu: true });
      });
    }
  });

  if (document.body.classList.contains("jobs-hub-page")) {
    syncBrowseChipHrefs();
  }

  document.querySelectorAll(".browse-dropdown .browse-chip").forEach(function (link) {
    link.addEventListener("click", function (e) {
      if (!document.body.classList.contains("jobs-hub-page")) return;
      var target;
      try {
        target = new URL(link.href, window.location.origin);
      } catch (err) {
        return;
      }
      var view = target.searchParams.get("view") || "all";
      if (view === "applied") return;
      e.preventDefault();
      e.stopPropagation();
      var form = document.querySelector(".browse-filter-form");
      if (form) {
        applyBrowseFilters(form);
        try {
          target = new URL(window.location.href);
          target.searchParams.set("view", view);
        } catch (err2) {
          return;
        }
      }
      document.querySelectorAll(".topbar-dropdown").forEach(function (el) {
        el.hidden = true;
      });
      document.querySelectorAll("[aria-controls]").forEach(function (btn) {
        btn.setAttribute("aria-expanded", "false");
      });
      hideTip();
      history.replaceState({ browseView: view }, "", target.pathname + target.search);
      if (window.JOBS_HUB && typeof window.JOBS_HUB.switchBrowseView === "function") {
        window.JOBS_HUB.switchBrowseView(view);
      } else if (window.JOBS_HUB && typeof window.JOBS_HUB.refilterFromUrl === "function") {
        window.JOBS_HUB.view = view;
        window.JOBS_HUB.refilterFromUrl();
      }
    });
  });

  document.querySelectorAll(".stat-chip-link[data-stat-view]").forEach(function (link) {
    link.addEventListener("click", function (e) {
      if (!document.body.classList.contains("jobs-hub-page")) return;
      var view = link.getAttribute("data-stat-view") || "all";
      e.preventDefault();
      hideTip();
      if (window.JOBS_HUB && typeof window.JOBS_HUB.switchBrowseView === "function") {
        window.JOBS_HUB.switchBrowseView(view);
      }
    });
  });

  function getCsrfToken() {
    if (window.JOBS_HUB && window.JOBS_HUB.csrfToken) return window.JOBS_HUB.csrfToken;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function parseJsonResponse(res) {
    return res.text().then(function (text) {
      var data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error("Unexpected server response (" + res.status + ").");
        }
      }
      return { ok: res.ok, data: data || {}, status: res.status };
    });
  }

  var importModalEl = null;

  function ensureImportModal() {
    if (importModalEl) return importModalEl;
    importModalEl = document.createElement("div");
    importModalEl.id = "jobs-import-modal";
    importModalEl.className = "jobs-import-modal";
    importModalEl.setAttribute("hidden", "");
    importModalEl.innerHTML =
      '<div class="jobs-import-modal-backdrop" data-close-import tabindex="-1"></div>' +
      '<div class="jobs-import-modal-card" role="dialog" aria-labelledby="jobs-import-title" aria-modal="true">' +
      '<button type="button" class="jobs-import-modal-close" data-close-import aria-label="Close">&times;</button>' +
      '<h3 id="jobs-import-title" class="jobs-import-modal-title">Import job from URL</h3>' +
      '<p class="jobs-import-modal-sub">Paste a link from LinkedIn, a company site, Arbeitsagentur, StepStone, etc. We add it to your list and score it when possible.</p>' +
      '<input type="url" class="jobs-import-modal-input" data-import-url-input placeholder="https://..." autocomplete="off">' +
      '<div class="jobs-import-modal-actions">' +
      '<button type="button" class="jobs-import-modal-submit" data-import-submit>Add &amp; score</button>' +
      "</div>" +
      '<p class="jobs-import-modal-note" data-import-note hidden></p>' +
      "</div>";
    document.body.appendChild(importModalEl);

    importModalEl.querySelectorAll("[data-close-import]").forEach(function (el) {
      el.addEventListener("click", closeImportModal);
    });

    var submitBtn = importModalEl.querySelector("[data-import-submit]");
    if (submitBtn) {
      submitBtn.addEventListener("click", submitImportJob);
    }

    var input = importModalEl.querySelector("[data-import-url-input]");
    if (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          submitImportJob();
        }
      });
    }

    return importModalEl;
  }

  function closeImportModal() {
    if (!importModalEl) return;
    importModalEl.setAttribute("hidden", "");
    document.body.classList.remove("jobs-import-modal-open");
  }

  function openImportModal(triggerBtn) {
    var importUrl =
      (triggerBtn && triggerBtn.getAttribute("data-import-url")) ||
      (window.JOBS_HUB && window.JOBS_HUB.importJobUrl) ||
      "";
    if (!importUrl) {
      alert("Import is not available on this page.");
      return;
    }
    var modal = ensureImportModal();
    modal.dataset.importUrl = importUrl;
    modal.removeAttribute("hidden");
    document.body.classList.add("jobs-import-modal-open");
    var note = modal.querySelector("[data-import-note]");
    if (note) {
      note.hidden = true;
      note.textContent = "";
      note.classList.remove("is-error");
    }
    var input = modal.querySelector("[data-import-url-input]");
    if (input) {
      input.value = "";
      input.focus();
    }
  }

  function submitImportJob() {
    var modal = ensureImportModal();
    var importUrl = modal.dataset.importUrl || "";
    var input = modal.querySelector("[data-import-url-input]");
    var note = modal.querySelector("[data-import-note]");
    var submitBtn = modal.querySelector("[data-import-submit]");
    var url = (input && input.value || "").trim();
    if (!importUrl) return;
    if (!url) {
      if (note) {
        note.hidden = false;
        note.classList.add("is-error");
        note.textContent = "Paste a job URL first.";
      }
      return;
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Adding…";
    }
    if (note) {
      note.hidden = false;
      note.classList.remove("is-error");
      note.textContent = "Fetching and scoring — may take 30–90 seconds…";
    }
    fetch(importUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ url: url, score: true }),
    })
      .then(parseJsonResponse)
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.ok) {
          throw new Error((res.data && res.data.error) || "Import failed");
        }
        closeImportModal();
        if (window.JOBS_HUB && typeof window.JOBS_HUB.reloadFromServer === "function") {
          window.JOBS_HUB.reloadFromServer({ force: true });
        } else {
          window.location.reload();
        }
      })
      .catch(function (err) {
        if (note) {
          note.hidden = false;
          note.classList.add("is-error");
          note.textContent = err.message || "Could not import that URL.";
        }
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Add & score";
        }
      });
  }

  var addJobBtn = document.getElementById("add-job-link-btn");
  if (
    addJobBtn &&
    addJobBtn.dataset.siteWired !== "1" &&
    !document.body.classList.contains("jobs-hub-page")
  ) {
    addJobBtn.dataset.siteWired = "1";
    addJobBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      hideTip();
      openImportModal(addJobBtn);
    });
  }

  if (window.JOBS_HUB && !document.body.classList.contains("jobs-hub-page")) {
    window.JOBS_HUB.openAddJobModal = function () {
      openImportModal(addJobBtn);
    };
  }

  window.addEventListener("popstate", function () {
    if (!document.body.classList.contains("jobs-hub-page")) return;
    if (!window.JOBS_HUB || typeof window.JOBS_HUB.switchBrowseView !== "function") return;
    var view = new URL(window.location.href).searchParams.get("view") || "all";
    if (window.JOBS_HUB.view !== view) {
      window.JOBS_HUB.switchBrowseView(view);
    }
  });

  var tipEl = document.createElement("div");
  tipEl.className = "ui-tooltip";
  tipEl.setAttribute("role", "tooltip");
  tipEl.hidden = true;
  document.body.appendChild(tipEl);

  var tipTarget = null;

  function hideTip() {
    tipEl.hidden = true;
    tipTarget = null;
  }

  function showTip(el) {
    var text = el.getAttribute("data-tip");
    if (!text) {
      hideTip();
      return;
    }
    tipTarget = el;
    tipEl.textContent = text;
    tipEl.hidden = false;
    var rect = el.getBoundingClientRect();
    var inHero = el.closest(".jobs-detail-hero");
    var inDetail = el.closest(".jobs-detail-panel, .jobs-detail-content");
    var inTopbar = el.closest(
      ".topbar-end, .topbar-menu-wrap, .topbar-actions, .topbar-stats, .topbar-main-nav, .topbar-row-stats"
    );
    var left;
    var top;
    if (inTopbar) {
      top = rect.bottom + 8;
      left = rect.right - tipEl.offsetWidth;
      if (left < 8) {
        left = rect.left;
      }
    } else if (inHero) {
      top = rect.top - tipEl.offsetHeight - 10;
      left = rect.left + rect.width / 2 - tipEl.offsetWidth / 2;
      if (top < 8) {
        top = rect.bottom + 8;
      }
    } else {
      top = rect.bottom + 8;
      left = rect.left + rect.width / 2 - tipEl.offsetWidth / 2;
      if (top + tipEl.offsetHeight > window.innerHeight - 8) {
        top = rect.top - tipEl.offsetHeight - 8;
      }
    }
    if (inDetail && top + tipEl.offsetHeight > window.innerHeight - 8) {
      top = Math.max(8, rect.top - tipEl.offsetHeight - 10);
    }
    left = Math.max(8, Math.min(left, window.innerWidth - tipEl.offsetWidth - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - tipEl.offsetHeight - 8));
    tipEl.style.left = left + "px";
    tipEl.style.top = top + "px";
  }

  document.addEventListener(
    "mouseover",
    function (e) {
      var el = e.target.closest("[data-tip]");
      if (!el) {
        return;
      }
      if (el !== tipTarget) {
        showTip(el);
      }
    },
    true
  );

  document.addEventListener(
    "mouseout",
    function (e) {
      if (!tipTarget) return;
      var related = e.relatedTarget;
      if (related && (tipTarget.contains(related) || tipEl.contains(related))) return;
      if (e.target.closest("[data-tip]") === tipTarget) {
        hideTip();
      }
    },
    true
  );

  document.addEventListener("scroll", hideTip, true);
  window.addEventListener("resize", hideTip);
})();
