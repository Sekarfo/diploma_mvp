const AUTH_TOKEN_KEY = "hr_shortlist_auth_token";
const THEME_KEY = "hr_shortlist_theme";

const state = {
  authMode: "signin",
  page: "shortlist",
  shortlistMode: "existing",
  authToken: "",
  currentUser: null,
  jobs: [],
  historyRuns: [],
  vacancies: [],
  currentRunId: null,       // run_id of the last shortlist result
  feedbackByRank: {},       // { [final_rank]: decision } for current run
  noteByRank: {},           // { [final_rank]: note } for current run
  currentJobSkills: [],     // required skills of the vacancy in current results
};

const authScreenEl = document.getElementById("auth-screen");
const appShellEl = document.getElementById("app-shell");
const authStatusEl = document.getElementById("auth-status");
const appStatusEl = document.getElementById("app-status");

const authModeSignInBtn = document.getElementById("auth-mode-signin");
const authModeSignUpBtn = document.getElementById("auth-mode-signup");
const signinForm = document.getElementById("signin-form");
const signupForm = document.getElementById("signup-form");

const signoutBtn = document.getElementById("signout-btn");
const topbarUserNameEl = document.getElementById("topbar-user-name");

const pageButtons = {
  shortlist: document.getElementById("page-shortlist-btn"),
  profile: document.getElementById("page-profile-btn"),
  insights: document.getElementById("page-insights-btn"),
};

const pageSections = {
  shortlist: document.getElementById("page-shortlist"),
  profile: document.getElementById("page-profile"),
  insights: document.getElementById("page-insights"),
};

const modeExistingBtn = document.getElementById("mode-existing");
const modeCustomBtn = document.getElementById("mode-custom");
const existingForm = document.getElementById("existing-form");
const customForm = document.getElementById("custom-form");
const jobSearchInput = document.getElementById("job-search");
const jobOptionsEl = document.getElementById("job-options");

const vacancyTitleInput = document.getElementById("vacancy-title");
const vacancyDescriptionInput = document.getElementById("vacancy-description");
const vacancyYearsInput = document.getElementById("vacancy-years");
const vacancySkillsInput = document.getElementById("vacancy-skills");

const resultsMetaEl = document.getElementById("results-meta");
const resultsEl = document.getElementById("results");
const candidateTemplate = document.getElementById("candidate-template");

const profileUserNameEl = document.getElementById("profile-user-name");
const profileUserEmailEl = document.getElementById("profile-user-email");
const profileUserRoleEl = document.getElementById("profile-user-role");
const vacancyListEl = document.getElementById("vacancy-list");
const historyListEl = document.getElementById("history-list");
const vacanciesRefreshBtn = document.getElementById("vacancies-refresh");
const historyRefreshBtn = document.getElementById("history-refresh");

const globalExplainerMetaEl = document.getElementById("global-explainer-meta");
const globalShapListEl = document.getElementById("global-shap-list");
const featureGlossaryListEl = document.getElementById("feature-glossary-list");

const searchOverlayEl = document.getElementById("search-overlay");
const searchOverlayTextEl = document.getElementById("search-overlay-text");

const resumeModalEl = document.getElementById("resume-modal");
const resumeModalTextEl = document.getElementById("resume-modal-text");
const resumeModalTitleEl = document.getElementById("resume-modal-title");
const resumeModalCloseEl = document.getElementById("resume-modal-close");
const resumeModalBackdropEl = document.getElementById("resume-modal-backdrop");

const themeLightBtn = document.getElementById("theme-light-btn");
const themeDarkBtn = document.getElementById("theme-dark-btn");

const uploadZoneEl       = document.getElementById("upload-zone");
const vacancyFileInputEl = document.getElementById("vacancy-file-input");
const uploadStatusEl     = document.getElementById("upload-status");
const uploadParsedInfoEl = document.getElementById("upload-parsed-info");

function showSearchOverlay(text = "Searching candidates…") {
  if (searchOverlayTextEl) searchOverlayTextEl.textContent = text;
  searchOverlayEl.classList.remove("hidden");
}

function hideSearchOverlay() {
  searchOverlayEl.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function numOr(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function humanDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeLightBtn.classList.toggle("is-active", theme === "light");
  themeDarkBtn.classList.toggle("is-active", theme === "dark");
  localStorage.setItem(THEME_KEY, theme);
}

function setAuthStatus(text, type = "") {
  authStatusEl.textContent = text || "";
  authStatusEl.className = `mini-muted auth-note ${type}`.trim();
}

function setAppStatus(text, type = "") {
  appStatusEl.textContent = text || "";
  appStatusEl.className = `app-msg ${type}`.trim();
}

function setAuthMode(mode) {
  state.authMode = mode;
  const isSignIn = mode === "signin";
  authModeSignInBtn.classList.toggle("is-active", isSignIn);
  authModeSignUpBtn.classList.toggle("is-active", !isSignIn);
  signinForm.classList.toggle("hidden", !isSignIn);
  signupForm.classList.toggle("hidden", isSignIn);
}

function setPage(pageKey) {
  state.page = pageKey;
  Object.entries(pageButtons).forEach(([key, button]) => {
    const isActive = key === pageKey;
    button.classList.toggle("is-active", isActive);
    const glyph = button.querySelector(".nav-glyph");
    if (glyph) glyph.textContent = isActive ? "[x]" : "[+]";
  });
  Object.entries(pageSections).forEach(([key, section]) => {
    section.classList.toggle("is-active", key === pageKey);
  });
}

function setShortlistMode(mode) {
  state.shortlistMode = mode;
  const isExisting = mode === "existing";
  modeExistingBtn.classList.toggle("is-active", isExisting);
  modeCustomBtn.classList.toggle("is-active", !isExisting);
  existingForm.classList.toggle("hidden", !isExisting);
  customForm.classList.toggle("hidden", isExisting);
}

function getAuthHeaders() {
  if (!state.authToken) return {};
  return { Authorization: `Bearer ${state.authToken}` };
}

function applyUserToUi() {
  const user = state.currentUser || {};
  topbarUserNameEl.textContent = user.full_name || user.email || "—";
  profileUserNameEl.textContent = user.full_name || "—";
  profileUserEmailEl.textContent = user.email || "—";
  profileUserRoleEl.textContent = user.role || "hr";
}

function applyAuthGate() {
  const isAuthenticated = Boolean(state.authToken && state.currentUser);
  authScreenEl.classList.toggle("hidden", isAuthenticated);
  appShellEl.classList.toggle("hidden", !isAuthenticated);

  if (isAuthenticated) {
    applyUserToUi();
    setAppStatus("Welcome! Start by creating a shortlist.", "ok");
  } else {
    setAuthStatus("Use your HR credentials to continue.", "");
    setAppStatus("");
  }
}

function clearSession() {
  state.authToken = "";
  state.currentUser = null;
  state.jobs = [];
  state.historyRuns = [];
  state.vacancies = [];
  localStorage.removeItem(AUTH_TOKEN_KEY);
  applyAuthGate();
}

function setSessionFromAuthResponse(payload) {
  state.authToken = String(payload.access_token || "").trim();
  state.currentUser = payload.user || null;
  if (state.authToken) {
    localStorage.setItem(AUTH_TOKEN_KEY, state.authToken);
  }
  applyAuthGate();
}

async function apiRequest(path, options = {}, { authRequired = false } = {}) {
  const headers = {
    ...(options.headers || {}),
    ...getAuthHeaders(),
  };

  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));

  if (response.status === 401) {
    clearSession();
    if (authRequired) {
      throw new Error(data.detail || "Authentication required. Please sign in.");
    }
  }

  if (!response.ok) {
    throw new Error(data.detail || `Request failed (${response.status})`);
  }

  return data;
}

async function apiGet(path, options = {}) {
  return apiRequest(path, { method: "GET" }, options);
}

async function apiPost(path, payload, options = {}) {
  return apiRequest(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    options
  );
}

function openResumeModal(resumeId, resumeText) {
  resumeModalTitleEl.textContent = `Resume ${resumeId}`;
  resumeModalTextEl.textContent = resumeText && resumeText.trim() ? resumeText : "Resume text is not available.";
  resumeModalEl.classList.remove("hidden");
}

function closeResumeModal() {
  resumeModalEl.classList.add("hidden");
}

function updateResultsMeta(payload, extra = "") {
  const vacancy = payload.job_title || payload.vacancy_title || payload.job_id || "Custom vacancy";
  const shown = payload.total_candidates ?? payload.returned_count ?? "-";
  const evaluated = payload.retrieved_count ?? payload.num_candidates ?? "-";
  // Show human-readable summary, hide internal pool/proxy details
  const parts = [`${shown} candidates · "${vacancy}"`];
  if (extra && !extra.startsWith("proxy:")) parts.push(extra);
  resultsMetaEl.textContent = parts.join(" · ");
}

// Maps raw ML feature names to plain-English one-liners for HR users.
const FACTOR_LABELS = {
  "ce_score_x_skill":                   "Strong content + skills relevance",
  "embedding_cosine":                   "High semantic match to vacancy",
  "embedding_cosine_norm":              "High semantic match to vacancy",
  "embedding_cosine_squared":           "High semantic match to vacancy",
  "skill_overlap_count":                "Covers required skills",
  "skill_overlap_ratio":                "Good skill coverage",
  "title_overlap_ratio":                "Job title aligns",
  "years_gap":                          "Experience level fits",
  "experience_match_flag":              "Meets experience requirements",
  "resume_years_experience":            "Relevant experience level",
  "job_years_required":                 "Experience requirement considered",
  "abs_years_gap":                      "Experience level close to required",
  "years_gap_squared":                  "Experience level close to required",
  "retrieval_rank":                     "High retrieval relevance",
  "log_retrieval_rank":                 "High retrieval relevance",
  "retrieval_rank_inv":                 "High retrieval relevance",
  "is_top5_retrieval":                  "Top-5 retrieval result",
  "is_top10_retrieval":                 "Top-10 retrieval result",
  "skill_overlap_x_emb":                "Skills + semantic match combined",
  "experience_x_skill":                 "Experience and skills align",
  "experience_x_emb":                   "Experience and content match",
  "title_x_emb":                        "Title and content match",
  "skill_x_title":                      "Skills and title align",
  "embedding_cosine_zscore_in_job":     "Stands out semantically among candidates",
  "skill_overlap_ratio_zscore_in_job":  "Stands out by skill coverage",
  "title_overlap_ratio_zscore_in_job":  "Stands out by title match",
  "embedding_cosine_rank_in_job":       "Top semantic match among candidates",
  "skill_overlap_rank_in_job":          "Best skill coverage among candidates",
  "title_overlap_rank_in_job":          "Best title match among candidates",
  "combined_rank_in_job":               "Overall top-ranked candidate",
};

function friendlyFactorLabel(rawLabel, feature) {
  return FACTOR_LABELS[feature] || FACTOR_LABELS[rawLabel] || rawLabel;
}

function buildCandidateSummary(candidate) {
  const explanation = candidate.explanation || {};
  const matched = explanation.matched_skills || [];
  const missing = explanation.missing_skills || [];
  const years = numOr(candidate.resume_years_experience, 0);
  const reqYears = numOr(candidate.job_years_required, 0);
  const expFit = years >= reqYears;

  if (matched.length && missing.length) {
    return `Skills matched: ${matched.slice(0, 4).join(", ")}. Not found: ${missing.slice(0, 3).join(", ")}.`;
  }
  if (matched.length) {
    return `Strong skill alignment — covers: ${matched.slice(0, 5).join(", ")}.`;
  }
  if (explanation.experience_summary) {
    return explanation.experience_summary;
  }
  if (expFit && years > 0) {
    return `${Math.round(years)} years of experience — meets the requirement.`;
  }
  return "Review resume for skill and experience details.";
}

function renderCandidateDetails(candidate, jobSkills = []) {
  const explanation = candidate.explanation || {};
  const matched = (explanation.matched_skills || []).slice(0, 6);
  const missing = (explanation.missing_skills || []).slice(0, 5);

  // Top positive SHAP factors translated to plain English
  const positives = (explanation.top_positive_factors || [])
    .slice(0, 3)
    .map((item) => friendlyFactorLabel(item.label, item.feature))
    .filter(Boolean);

  const overlapCount = numOr(candidate.skill_overlap_count, 0);

  // Build a clear skills label:
  // - if we have named matches → show them
  // - if count > 0 but no names → show count (shouldn't normally happen)
  // - if job has no required skills → explain that
  // - otherwise → "No match in top results"
  let matchedLabel;
  if (matched.length) {
    matchedLabel = matched.join(", ");
  } else if (overlapCount > 0) {
    matchedLabel = `${overlapCount} matched`;
  } else if (jobSkills.length === 0) {
    matchedLabel = "Vacancy has no required skills defined";
  } else {
    matchedLabel = "No exact match in top results";
  }

  // For missing: use explanation missing_skills, or derive from jobSkills − matched
  let missingLabel;
  if (missing.length) {
    missingLabel = missing.join(", ");
  } else if (jobSkills.length > 0 && matched.length === 0) {
    // Show the required skills so user knows what was looked for
    missingLabel = jobSkills.slice(0, 6).join(", ") + (jobSkills.length > 6 ? ` +${jobSkills.length - 6} more` : "");
  } else {
    missingLabel = "—";
  }

  const expSummary = explanation.experience_summary || "—";
  const pct = scoreToPercent(candidate.final_fusion_score ?? candidate.score);
  const tierText = pct >= 75 ? "Strong match" : pct >= 50 ? "Good match" : "Partial match";

  const rows = [
    ["Overall fit",       `${pct}% — ${tierText}`],
    ["Skills matched",    matchedLabel],
    ["Skills missing",    missingLabel],
    ["Experience",        expSummary],
    ["Why recommended",   positives.length ? positives.join(" · ") : "Good overall relevance"],
  ];

  return rows
    .map(
      ([key, val]) => `
      <div class="kv-row">
        <span class="kv-key">${escapeHtml(key)}</span>
        <span class="kv-val">${escapeHtml(val)}</span>
      </div>`
    )
    .join("");
}

function scoreToPercent(value) {
  const v = numOr(value, 0);
  return Math.max(0, Math.min(100, Math.round(v * 100)));
}

function matchTier(pct) {
  if (pct >= 75) return "strong";
  if (pct >= 50) return "good";
  return "weak";
}

// ── Vacancy file upload ──────────────────────────────────────────────────────

function setUploadStatus(text, type = "") {
  uploadStatusEl.textContent = text;
  uploadStatusEl.className = `upload-status ${type}`.trim();
}

function showParsedInfo(parsed) {
  const skills = (parsed.skills || []).slice(0, 8).join(", ");
  const more   = parsed.skills.length > 8 ? ` +${parsed.skills.length - 8} more` : "";
  const pages  = parsed.page_count > 1 ? ` · ${parsed.page_count} pages` : "";
  const warns  = parsed.parse_warnings?.length
    ? `<br><span style="color:var(--warning)">⚠ ${escapeHtml(parsed.parse_warnings[0])}</span>`
    : "";
  uploadParsedInfoEl.innerHTML =
    `<b>${escapeHtml(parsed.file_name)}</b> · ${parsed.char_count.toLocaleString()} chars${pages}` +
    (skills ? `<br>skills detected: ${escapeHtml(skills)}${escapeHtml(more)}` : "") +
    warns;
  uploadParsedInfoEl.classList.add("visible");
}

async function handleVacancyFileUpload(file) {
  if (!file) return;
  if (!state.authToken) {
    setUploadStatus("sign in first to use file upload.", "error");
    return;
  }

  setUploadStatus("parsing file…", "loading");
  uploadParsedInfoEl.classList.remove("visible");

  const form = new FormData();
  form.append("file", file);

  try {
    const response = await fetch("/vacancies/parse", {
      method: "POST",
      headers: { Authorization: `Bearer ${state.authToken}` },
      body: form,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setUploadStatus(data.detail || `Parse failed (${response.status})`, "error");
      return;
    }

    // Fill in the custom-vacancy form fields
    if (data.title) {
      document.getElementById("vacancy-title").value = data.title;
    }
    if (data.description) {
      document.getElementById("vacancy-description").value = data.description;
    }
    if (data.years_required != null) {
      document.getElementById("vacancy-years").value = data.years_required;
    }
    if (data.skills && data.skills.length) {
      document.getElementById("vacancy-skills").value = data.skills.join(", ");
    }

    setUploadStatus(`filled from ${escapeHtml(file.name)} — review and edit before searching`, "ok");
    showParsedInfo(data);

    // Switch to the custom tab if not already there
    if (state.shortlistMode !== "custom") setShortlistMode("custom");
  } catch (error) {
    setUploadStatus(error.message || "Upload failed.", "error");
  }
}

// Drag-and-drop wiring
uploadZoneEl.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadZoneEl.classList.add("drag-over");
});
uploadZoneEl.addEventListener("dragleave", () => uploadZoneEl.classList.remove("drag-over"));
uploadZoneEl.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadZoneEl.classList.remove("drag-over");
  const file = e.dataTransfer?.files?.[0];
  if (file) handleVacancyFileUpload(file);
});
vacancyFileInputEl.addEventListener("change", () => {
  const file = vacancyFileInputEl.files?.[0];
  if (file) handleVacancyFileUpload(file);
  vacancyFileInputEl.value = "";   // reset so same file can be re-selected
});

// ── Feedback ─────────────────────────────────────────────────────────────────

function applyFeedbackToCard(cardEl, decision) {
  cardEl.querySelectorAll(".fb-btn").forEach((btn) => {
    const d = btn.dataset.decision;
    btn.classList.toggle(`is-active-${d}`, d === decision);
  });
}

function showCommentBox(cardEl, decision, existingNote = "") {
  const box = cardEl.querySelector(".fb-comment-box");
  if (!box) return;
  // Store which decision is pending on the card element
  cardEl.dataset.pendingDecision = decision;
  box.classList.remove("hidden");
  // Hide the read-only saved-comment view while editing
  const savedView = cardEl.querySelector(".fb-saved-comment");
  if (savedView) savedView.classList.add("hidden");
  const textarea = box.querySelector(".fb-comment-input");
  if (textarea) {
    textarea.classList.remove("has-error");
    textarea.placeholder = "Briefly explain your decision…";
    if (existingNote && !textarea.value) textarea.value = existingNote;
    textarea.focus();
  }
}

function renderSavedComment(cardEl, note) {
  const savedView = cardEl.querySelector(".fb-saved-comment");
  if (!savedView) return;
  if (note && note.trim()) {
    savedView.querySelector(".fb-saved-text").textContent = note;
    savedView.classList.remove("hidden");
  } else {
    savedView.classList.add("hidden");
  }
}

function hideCommentBox(cardEl) {
  const box = cardEl.querySelector(".fb-comment-box");
  if (!box) return;
  box.classList.add("hidden");
  const textarea = box.querySelector(".fb-comment-input");
  if (textarea) {
    textarea.value = "";
    textarea.classList.remove("has-error");
  }
  delete cardEl.dataset.pendingDecision;
}

async function submitFeedback(runId, finalRank, decision, note, cardEl) {
  try {
    await apiPost(
      `/shortlist/${encodeURIComponent(runId)}/feedback`,
      { final_rank: finalRank, decision, note: note || null },
      { authRequired: true }
    );
    state.feedbackByRank[finalRank] = decision;
    state.noteByRank[finalRank] = note || "";
    applyFeedbackToCard(cardEl, decision);
    hideCommentBox(cardEl);
    renderSavedComment(cardEl, note);
  } catch (error) {
    setAppStatus(error.message || "Failed to save decision.", "error");
  }
}

async function clearFeedback(runId, finalRank, cardEl) {
  try {
    await apiRequest(
      `/shortlist/${encodeURIComponent(runId)}/feedback/${encodeURIComponent(finalRank)}`,
      { method: "DELETE" },
      { authRequired: true }
    );
    delete state.feedbackByRank[finalRank];
    delete state.noteByRank[finalRank];
    applyFeedbackToCard(cardEl, null);
    hideCommentBox(cardEl);
    renderSavedComment(cardEl, "");
  } catch (error) {
    setAppStatus(error.message || "Failed to clear decision.", "error");
  }
}

async function loadFeedbackForRun(runId) {
  if (!runId || !state.authToken) return;
  try {
    const data = await apiGet(`/shortlist/${encodeURIComponent(runId)}/feedback`, {
      authRequired: true,
    });
    state.feedbackByRank = {};
    state.noteByRank = {};
    (data.feedbacks || []).forEach((fb) => {
      state.feedbackByRank[fb.final_rank] = fb.decision;
      if (fb.note) state.noteByRank[fb.final_rank] = fb.note;
    });
  } catch (_) {
    state.feedbackByRank = {};
    state.noteByRank = {};
  }
}

// ─────────────────────────────────────────────────────────────────────────────

function makeAsciiBar(pct, width = 16) {
  const filled = Math.round((pct / 100) * width);
  return "█".repeat(filled) + "─".repeat(width - filled);
}

function makeResumeSnippet(text, maxLen = 260) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return 'Resume text is not available — click "view resume" for the source record.';
  if (clean.length <= maxLen) return clean;
  return clean.slice(0, maxLen).trimEnd() + "…";
}

function renderCandidates(payload, runId = null) {
  const candidates = payload.candidates || [];
  resultsEl.innerHTML = "";

  if (!candidates.length) {
    resultsEl.innerHTML =
      '<p class="mono-mute results-hint">No candidates matched this vacancy. Try a broader description or increase the candidate pool.</p>';
    return;
  }

  const fragment = document.createDocumentFragment();

  candidates.forEach((candidate) => {
    const node = candidateTemplate.content.cloneNode(true);
    const fusedScore = candidate.final_fusion_score ?? candidate.score;
    const pct = scoreToPercent(fusedScore);
    const tier = matchTier(pct);
    const rank = candidate.final_rank;

    node.querySelector(".rank-pill").textContent = `#${rank}`;
    // Show short resume ID suffix, not the full raw ID, to keep cards readable
    const idShort = String(candidate.resume_id).slice(-6);
    node.querySelector(".resume-id").textContent = `ID ···${idShort}`;

    const scoreEl = node.querySelector(".score-fused");
    scoreEl.textContent = `${pct}%`;
    if (tier === "strong") scoreEl.classList.add("badge-success");
    else if (tier === "good") scoreEl.classList.add("badge-warning");
    else scoreEl.classList.add("badge-danger");

    node.querySelector(".score-bar-ascii").textContent = makeAsciiBar(pct);
    node.querySelector(".candidate-summary").textContent = buildCandidateSummary(candidate);
    node.querySelector(".resume-snippet-box").textContent = makeResumeSnippet(candidate.resume_text);
    node.querySelector(".details-grid").innerHTML = renderCandidateDetails(candidate, state.currentJobSkills);

    node.querySelector(".view-resume-btn").addEventListener("click", () => {
      openResumeModal(candidate.resume_id, candidate.resume_text || "");
    });

    // Wire up feedback buttons
    const cardEl = node.querySelector(".cand-card");
    const existingDecision = state.feedbackByRank[rank] || null;
    const existingNote = state.noteByRank[rank] || "";
    if (existingDecision) applyFeedbackToCard(cardEl, existingDecision);
    if (existingNote) renderSavedComment(cardEl, existingNote);

    if (runId) {
      // Decision button: highlight + show comment box (no submit yet)
      cardEl.querySelectorAll(".fb-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const d = btn.dataset.decision;
          // Visually highlight the selected option immediately
          applyFeedbackToCard(cardEl, d);
          showCommentBox(cardEl, d, state.noteByRank[rank] || "");
        });
      });

      // Edit button on the saved-comment view: reopen the comment box pre-filled
      const editBtn = cardEl.querySelector(".fb-edit-btn");
      if (editBtn) {
        editBtn.addEventListener("click", () => {
          const d = state.feedbackByRank[rank];
          if (!d) return;
          showCommentBox(cardEl, d, state.noteByRank[rank] || "");
        });
      }

      // Save button: validate comment, then submit
      const saveBtn = cardEl.querySelector(".fb-save-btn");
      if (saveBtn) {
        saveBtn.addEventListener("click", () => {
          const textarea = cardEl.querySelector(".fb-comment-input");
          const note = (textarea ? textarea.value : "").trim();
          if (!note) {
            if (textarea) textarea.classList.add("has-error");
            textarea.placeholder = "Comment is required before saving.";
            textarea.focus();
            return;
          }
          const decision = cardEl.dataset.pendingDecision;
          if (!decision) return;
          submitFeedback(runId, rank, decision, note, cardEl);
        });
      }

      // Cancel button: revert to previous saved decision, hide box
      const cancelBtn = cardEl.querySelector(".fb-cancel-btn");
      if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
          hideCommentBox(cardEl);
          // Revert button highlights to the last saved decision
          const saved = state.feedbackByRank[rank] || null;
          applyFeedbackToCard(cardEl, saved);
          // Re-show the saved comment block if one exists
          renderSavedComment(cardEl, state.noteByRank[rank] || "");
        });
      }

      // Clear button: delete saved feedback
      cardEl.querySelector(".fb-clear").addEventListener("click", () =>
        clearFeedback(runId, rank, cardEl)
      );
    } else {
      // no run_id yet (history replay without live run) — hide feedback bar
      const bar = cardEl.querySelector(".feedback-bar");
      if (bar) bar.style.display = "none";
      const commentBox = cardEl.querySelector(".fb-comment-box");
      if (commentBox) commentBox.style.display = "none";
    }

    fragment.appendChild(node);
  });

  resultsEl.appendChild(fragment);
}

function mapHistoryDetailToCandidates(detail) {
  return (detail.candidates || []).map((candidate) => {
    const feature = candidate.feature_snapshot || {};
    return {
      final_rank: candidate.final_rank,
      resume_id: candidate.resume_id,
      resume_text: "",
      final_fusion_score: candidate.final_fusion_score ?? 0,
      retrieval_rank: candidate.retrieval_rank ?? 0,
      retrieval_score_norm: numOr(feature.retrieval_score_norm, 0),
      reranker_score_norm: numOr(feature.reranker_score_norm, 0),
      skill_overlap_count: numOr(feature.skill_overlap_count, 0),
      skill_overlap_ratio: numOr(feature.skill_overlap_ratio, 0),
      title_overlap_ratio: numOr(feature.title_overlap_ratio, 0),
      years_gap: numOr(feature.years_gap, 0),
      explanation: candidate.explanation || {},
    };
  });
}

async function loadHistoryRun(runId) {
  try {
    setAppStatus("Loading shortlist from history...", "ok");
    const [detail] = await Promise.all([
      apiGet(`/cabinet/history/${encodeURIComponent(runId)}`, { authRequired: true }),
      loadFeedbackForRun(runId),
    ]);
    state.currentRunId = runId;

    const mapped = {
      run_id: runId,
      job_id: detail.existing_job_id || detail.vacancy_title || "custom",
      top_k: detail.top_k,
      retrieved_count: detail.retrieved_count,
      total_candidates: detail.returned_count,
      candidates: mapHistoryDetailToCandidates(detail),
    };

    updateResultsMeta(mapped, "loaded from history");
    renderCandidates(mapped, runId);
    setPage("shortlist");
    setAppStatus("History shortlist loaded.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to load history run.", "error");
  }
}

function renderHistoryList(runs) {
  historyListEl.innerHTML = "";

  if (!runs || !runs.length) {
    historyListEl.innerHTML = "<p class='mono-mute panel-empty'>No shortlist history yet.</p>";
    return;
  }

  const fragment = document.createDocumentFragment();
  runs.forEach((run) => {
    const item = document.createElement("div");
    item.className = "pipeline-row";

    const label = run.vacancy_title || run.existing_job_id || "Custom vacancy";
    item.innerHTML = `
      <div>
        <div class="pipeline-name">${escapeHtml(label)}</div>
        <div class="pipeline-sub">${escapeHtml(humanDate(run.created_at))} · ${escapeHtml(String(run.returned_count))} candidates ranked</div>
      </div>
      <button type="button" class="btn btn-ghost btn-sm open-history-btn">Reopen</button>
    `;

    const button = item.querySelector(".open-history-btn");
    button.addEventListener("click", () => loadHistoryRun(run.run_id));
    fragment.appendChild(item);
  });

  historyListEl.appendChild(fragment);
}

function renderVacancyList(vacancies) {
  vacancyListEl.innerHTML = "";

  if (!vacancies || !vacancies.length) {
    vacancyListEl.innerHTML = "<p class='mono-mute panel-empty'>No custom vacancies yet.</p>";
    return;
  }

  const fragment = document.createDocumentFragment();
  vacancies.forEach((vacancy) => {
    const item = document.createElement("div");
    item.className = "pipeline-row";
    item.innerHTML = `
      <div>
        <div class="pipeline-name">${escapeHtml(vacancy.title || "Untitled vacancy")}</div>
        <div class="pipeline-sub">${escapeHtml(humanDate(vacancy.created_at))} · <span class="badge">${escapeHtml(vacancy.source || "manual")}</span></div>
      </div>
    `;
    fragment.appendChild(item);
  });

  vacancyListEl.appendChild(fragment);
}

function renderGlobalExplanation(payload) {
  const features = payload.top_features || [];

  // Normalize SHAP values to 0–1 range for bar rendering
  const maxShap = Math.max(...features.map((f) => numOr(f.mean_abs_shap, 0)), 0.001);

  const rows = features
    .slice(0, 10)
    .map((feature, index) => {
      const ratio = Math.max(0, Math.min(1, numOr(feature.mean_abs_shap, 0) / maxShap));
      const filled = Math.round(ratio * 32);
      const bar = "█".repeat(filled) + "─".repeat(32 - filled);
      const friendlyName = FACTOR_LABELS[feature.feature] || feature.label;
      const pct = Math.round(ratio * 100);
      return `
        <div class="shap-item">
          <span class="shap-rank">#${index + 1}</span>
          <div class="shap-content">
            <div class="shap-feature-name">${escapeHtml(friendlyName)}</div>
            <div class="shap-ascii-bar">${escapeHtml(bar)} ${pct}%</div>
          </div>
        </div>
      `;
    })
    .join("");

  globalShapListEl.innerHTML = rows || "<p class='mono-mute'>No SHAP data available yet.</p>";
  globalExplainerMetaEl.textContent = `${payload.validation_rows ?? 0} candidates analyzed`;

  const glossary = (payload.feature_glossary || [])
    .filter((item) => item.used_in_model)
    .map(
      (item) => `
      <div class="pipeline-row">
        <div>
          <div class="pipeline-name">${escapeHtml(FACTOR_LABELS[item.feature] || item.label)}</div>
          <div class="pipeline-sub">${escapeHtml(item.description)}</div>
        </div>
      </div>`
    )
    .join("");

  featureGlossaryListEl.innerHTML = glossary || "<p class='mono-mute panel-empty'>No glossary available.</p>";
}

async function loadJobs() {
  const data = await apiGet("/jobs", { authRequired: true });
  state.jobs = data.jobs || [];
  jobOptionsEl.innerHTML = "";

  state.jobs.forEach((job) => {
    const option = document.createElement("option");
    option.value = `${job.job_title} — ${job.job_id}`;
    jobOptionsEl.appendChild(option);
  });
}

function resolveSelectedJobId() {
  const raw = (jobSearchInput.value || "").trim();
  if (!raw) return "";
  const dashSplit = raw.split("—").map((s) => s.trim());
  const tail = dashSplit[dashSplit.length - 1];
  if (state.jobs.some((j) => j.job_id === tail)) return tail;
  const byTitle = state.jobs.find((j) => j.job_title.toLowerCase() === raw.toLowerCase());
  return byTitle ? byTitle.job_id : "";
}

async function loadVacancies() {
  const data = await apiGet("/cabinet/vacancies?limit=200", { authRequired: true });
  state.vacancies = data.vacancies || [];
  renderVacancyList(state.vacancies);
}

async function loadHistory() {
  const data = await apiGet("/cabinet/history?limit=100", { authRequired: true });
  state.historyRuns = data.runs || [];
  renderHistoryList(state.historyRuns);
}

async function loadGlobalExplanation() {
  globalExplainerMetaEl.textContent = "loading SHAP summary...";
  globalShapListEl.innerHTML = "<p class='mono-mute'>Loading...</p>";
  featureGlossaryListEl.innerHTML = "";

  try {
    const data = await apiGet("/stats/explanations/global", { authRequired: true });
    renderGlobalExplanation(data);
  } catch (error) {
    globalExplainerMetaEl.textContent = "SHAP summary unavailable";
    globalShapListEl.innerHTML = "<p class='mono-mute'>SHAP artifacts are not available yet.</p>";
    featureGlossaryListEl.innerHTML = "";
  }
}

async function refreshMe() {
  if (!state.authToken) return;
  try {
    const me = await apiGet("/auth/me", { authRequired: true });
    state.currentUser = me;
  } catch (_) {
    clearSession();
  }
}

async function loadAppData() {
  try {
    setAppStatus("Loading workspace data...", "ok");
    await Promise.all([loadJobs(), loadGlobalExplanation(), loadVacancies(), loadHistory()]);
    setAppStatus("Workspace ready.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to load workspace data.", "error");
  }
}

existingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const jobId = resolveSelectedJobId();
  if (!jobId) {
    setAppStatus("Please pick a vacancy from the suggestions list first.", "error");
    return;
  }
  showSearchOverlay("Searching candidates…");
  try {
    setAppStatus("Searching candidates and re-ranking with the ML model…", "ok");
    const payload = {
      job_id: jobId,
      top_k: Number(document.getElementById("existing-topk").value || 20),
      num_candidates: Number(document.getElementById("existing-num-candidates").value || 100),
    };

    const data = await apiPost("/shortlist", payload, { authRequired: true });
    state.currentRunId = data.run_id || null;
    state.feedbackByRank = {};
    // Store job skills for matched/missing display in candidate cards
    const jobObj = state.jobs.find((j) => j.job_id === jobId);
    state.currentJobSkills = jobObj ? (jobObj.job_skills_norm || []) : [];
    updateResultsMeta(data);
    renderCandidates(data, state.currentRunId);
    await Promise.all([loadHistory(), loadVacancies()]);
    setAppStatus("Shortlist ready. Open candidate cards for details.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to build shortlist.", "error");
  } finally {
    hideSearchOverlay();
  }
});

customForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showSearchOverlay("Searching candidates…");
  try {
    setAppStatus("Searching candidates and re-ranking with the ML model…", "ok");

    const rawSkills = vacancySkillsInput.value || "";
    const parsedSkills = rawSkills
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);

    const yearsRaw = vacancyYearsInput.value;
    const payload = {
      vacancy_title: vacancyTitleInput.value.trim(),
      vacancy_description: vacancyDescriptionInput.value.trim(),
      top_k: Number(document.getElementById("custom-topk").value || 20),
      num_candidates: Number(document.getElementById("custom-num-candidates").value || 100),
      job_skills_norm: parsedSkills.length ? parsedSkills : null,
      job_years_required: yearsRaw ? Number(yearsRaw) : null,
    };

    const data = await apiPost("/shortlist/vacancy", payload, { authRequired: true });
    state.currentRunId = data.run_id || null;
    state.feedbackByRank = {};
    // For custom vacancies, use skills the user typed in the form
    state.currentJobSkills = parsedSkills;
    updateResultsMeta(data, "");
    renderCandidates(data, state.currentRunId);
    await Promise.all([loadHistory(), loadVacancies()]);
    setAppStatus("Custom vacancy shortlist generated and saved.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to build shortlist.", "error");
  } finally {
    hideSearchOverlay();
  }
});

signinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setAuthStatus("Signing in…", "ok");
    const payload = {
      email: document.getElementById("signin-email").value.trim(),
      password: document.getElementById("signin-password").value,
    };
    const data = await apiPost("/auth/signin", payload);
    setSessionFromAuthResponse(data);
    await loadAppData();
    setPage("shortlist");
  } catch (error) {
    setAuthStatus(error.message || "Sign in failed.", "error");
  }
});

signupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setAuthStatus("Creating account…", "ok");
    const payload = {
      full_name: document.getElementById("signup-fullname").value.trim(),
      email: document.getElementById("signup-email").value.trim(),
      password: document.getElementById("signup-password").value,
    };
    const data = await apiPost("/auth/signup", payload);
    setSessionFromAuthResponse(data);
    await loadAppData();
    setPage("shortlist");
  } catch (error) {
    setAuthStatus(error.message || "Sign up failed.", "error");
  }
});

signoutBtn.addEventListener("click", async () => {
  try {
    if (state.authToken) {
      await apiPost("/auth/signout", {}, { authRequired: true });
    }
  } catch (_) {
    // local signout continues regardless
  } finally {
    clearSession();
    setAuthMode("signin");
  }
});

historyRefreshBtn.addEventListener("click", async () => {
  try {
    setAppStatus("Refreshing shortlist history…", "ok");
    await loadHistory();
    setAppStatus("Shortlist history updated.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to refresh history.", "error");
  }
});

vacanciesRefreshBtn.addEventListener("click", async () => {
  try {
    setAppStatus("Refreshing vacancy list…", "ok");
    await loadVacancies();
    setAppStatus("Vacancy list updated.", "ok");
  } catch (error) {
    setAppStatus(error.message || "Failed to refresh vacancies.", "error");
  }
});

pageButtons.shortlist.addEventListener("click", () => setPage("shortlist"));
pageButtons.profile.addEventListener("click", () => setPage("profile"));
pageButtons.insights.addEventListener("click", () => setPage("insights"));

modeExistingBtn.addEventListener("click", () => setShortlistMode("existing"));
modeCustomBtn.addEventListener("click", () => setShortlistMode("custom"));

authModeSignInBtn.addEventListener("click", () => setAuthMode("signin"));
authModeSignUpBtn.addEventListener("click", () => setAuthMode("signup"));

themeLightBtn.addEventListener("click", () => setTheme("light"));
themeDarkBtn.addEventListener("click", () => setTheme("dark"));

resumeModalCloseEl.addEventListener("click", closeResumeModal);
resumeModalBackdropEl.addEventListener("click", closeResumeModal);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeResumeModal();
});

async function boot() {
  const savedTheme = localStorage.getItem(THEME_KEY) || "dark";
  setTheme(savedTheme);

  setAuthMode("signin");
  setPage("shortlist");
  setShortlistMode("existing");

  const savedToken = localStorage.getItem(AUTH_TOKEN_KEY);
  if (savedToken) {
    state.authToken = savedToken;
    await refreshMe();
  }

  applyAuthGate();

  if (state.authToken && state.currentUser) {
    await loadAppData();
  }
}

boot();
