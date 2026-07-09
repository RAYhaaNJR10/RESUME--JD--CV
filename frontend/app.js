// ═══════════════════════════════════════════════════════
//  ATS RECRUITMENT PLATFORM — app.js
//  Reuses all existing backend APIs unchanged.
// ═══════════════════════════════════════════════════════

// Auth guard
if (!localStorage.getItem("access_token")) {
    window.location.href = "/login";
}

// ─── Global State ───────────────────────────────────────
let currentTab = "dashboard";
let apiMetadata = { recruiters: [], skills: [], technologies: [], roles: [] };

// Pagination
let poolCandidatesState = { page: 1, limit: 10, total: 0, sortBy: "candidate_name", sortOrder: "asc" };

// Selection state (Candidate Pool)
let poolSelectedCompareCandidates = new Set();
let poolSelectedGenerateCandidates = new Set();
let activePoolQuery = "";
let _poolSetupDone = false;

// New Recruitment state
let nrUploadedNames = [];          // names from /upload-resumes
let nrSelectedCandidates = new Set();
let _nrSetupDone = false;

// ═══════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    const apiBaseInput = document.getElementById("apiBase");
    if (apiBaseInput && !apiBaseInput.value) {
        apiBaseInput.value = window.location.origin;
    }

    updateHeaderUserStatus();
    setupSidebarToggle();
    setupRouter();
    bindGlobalListeners();
    switchView(getHashPage() || "dashboard");
});

function getApiBase() {
    const input = document.getElementById("apiBase");
    return input ? input.value.trim().replace(/\/$/, "") : window.location.origin;
}

// ─── Auth & Fetch ──────────────────────────────────────

async function authedFetch(url, options = {}) {
    const token = localStorage.getItem("access_token");
    if (!options.headers) options.headers = {};
    if (token) options.headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(url, options);

    if (response.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("username");
        window.location.href = "/login";
        throw new Error("Session expired. Please log in again.");
    }
    return response;
}

// ─── UI Helpers ────────────────────────────────────────

function updateHeaderUserStatus() {
    const username = localStorage.getItem("username") || "Recruiter";
    document.querySelectorAll("#loggedInUsername, #settingsUsername, #settingsUsernameSession")
        .forEach(el => { if (el) el.textContent = username; });
}

function showMessage(msg, type = "info") {
    const alertBox = document.getElementById("alertBox");
    if (!alertBox) return;
    alertBox.textContent = msg;
    alertBox.className = `alert-box ${type}`;
    alertBox.hidden = false;
    setTimeout(() => { if (alertBox.textContent === msg) alertBox.hidden = true; }, 7000);
}

function hideMessage() {
    const alertBox = document.getElementById("alertBox");
    if (alertBox) alertBox.hidden = true;
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;")
              .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function formatToKolkataTime(utcString) {
    if (!utcString) return "";
    try {
        return new Date(utcString).toLocaleDateString("en-IN", {
            timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric"
        });
    } catch { return utcString; }
}

// ═══════════════════════════════════════════════════════
//  SIDEBAR TOGGLE
// ═══════════════════════════════════════════════════════

function setupSidebarToggle() {
    const sidebar = document.getElementById("appSidebar");
    const toggle  = document.getElementById("sidebarToggle");
    if (!sidebar || !toggle) return;

    toggle.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
    });
}

// ═══════════════════════════════════════════════════════
//  SPA ROUTER
// ═══════════════════════════════════════════════════════

function getHashPage() {
    return window.location.hash.replace("#", "") || null;
}

function setupRouter() {
    document.querySelectorAll(".menu-item").forEach(item => {
        item.addEventListener("click", () => {
            const page = item.getAttribute("data-page");
            if (page) { window.location.hash = page; switchView(page); }
        });
    });

    window.addEventListener("hashchange", () => {
        const page = getHashPage();
        if (page) switchView(page);
    });
}

function switchView(pageId) {
    currentTab = pageId;
    
    document.querySelectorAll(".menu-item").forEach(item => {
        item.classList.toggle("active", item.getAttribute("data-page") === pageId);
    });

    document.querySelectorAll(".page-view").forEach(section => {
        section.classList.toggle("active", section.id === `page-${pageId}`);
    });

    const pageTitles = {
        "dashboard":         "Dashboard",
        "new-recruitment":   "New Recruitment",
        "candidate-pool":    "Candidate Pool",
        "job-descriptions":  "Job Descriptions",
        "generated-cvs":     "Generated CVs",
        "analytics":         "Analytics",
        "settings":          "Settings"
    };

    const breadcrumb = document.getElementById("activePageBreadcrumb");
    if (breadcrumb) breadcrumb.textContent = pageTitles[pageId] || pageId;

    loadPageData(pageId);
}

async function loadPageData(pageId) {
    hideMessage();
    switch (pageId) {
        case "dashboard":
            await loadDashboardStats();
            await checkActiveTemplate();
            break;
        case "new-recruitment":
            await loadMetadata();
            setupNewRecruitment();
            break;
        case "candidate-pool":
            setupCandidatePoolPage();
            clearPoolSearch();
            break;
        case "job-descriptions":
            await fetchJobDescriptions();
            break;
        case "generated-cvs":
            await fetchGeneratedCvs();
            break;
        case "analytics":
            await fetchAnalytics();
            break;
    }
}

// ═══════════════════════════════════════════════════════
//  GLOBAL LISTENERS
// ═══════════════════════════════════════════════════════

function bindGlobalListeners() {
    // Logout
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", handleLogoutClick);

    const settingsLogoutBtn = document.getElementById("settingsLogoutBtn");
    if (settingsLogoutBtn) settingsLogoutBtn.addEventListener("click", handleLogoutClick);

    // Profile drawer close
    const closeDrawerBtn = document.getElementById("closeDrawerBtn");
    if (closeDrawerBtn) closeDrawerBtn.addEventListener("click", () => {
        document.getElementById("candidateProfileDrawer").hidden = true;
    });

    const candidateProfileDrawer = document.getElementById("candidateProfileDrawer");
    if (candidateProfileDrawer) {
        candidateProfileDrawer.addEventListener("click", (e) => {
            if (e.target === candidateProfileDrawer) candidateProfileDrawer.hidden = true;
        });
    }

    // Comparison overlay close
    const closeComparisonOverlayBtn = document.getElementById("closeComparisonOverlayBtn");
    if (closeComparisonOverlayBtn) closeComparisonOverlayBtn.addEventListener("click", () => {
        document.getElementById("candidateComparisonOverlay").hidden = true;
    });

    const comparisonOverlay = document.getElementById("candidateComparisonOverlay");
    if (comparisonOverlay) {
        comparisonOverlay.addEventListener("click", (e) => {
            if (e.target === comparisonOverlay) comparisonOverlay.hidden = true;
        });
    }

    // Delete modal
    const deleteModalCancelBtn = document.getElementById("deleteModalCancelBtn");
    if (deleteModalCancelBtn) deleteModalCancelBtn.addEventListener("click", () => {
        document.getElementById("deleteModalOverlay").hidden = true;
    });

    // Drawer tabs
    document.querySelectorAll(".drawer-tab").forEach(tab => {
        tab.addEventListener("click", () => switchDrawerTab(tab.getAttribute("data-tab")));
    });

    // Template dropzone
    setupTemplateDropzone();

    // JD modal
    setupJdModal();

    // Change password
    setupChangePassword();

    // Candidate Pool compare/generate buttons are managed inside setupCandidatePoolPage

    // Keyboard: escape closes drawers
    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            const drawer = document.getElementById("candidateProfileDrawer");
            const comparison = document.getElementById("candidateComparisonOverlay");
            const deleteModal = document.getElementById("deleteModalOverlay");
            const jdModal = document.getElementById("jdModalOverlay");
            if (!drawer.hidden) drawer.hidden = true;
            else if (!comparison.hidden) comparison.hidden = true;
            else if (!deleteModal.hidden) deleteModal.hidden = true;
            else if (jdModal && !jdModal.hidden) jdModal.hidden = true;
        }
    });
}

// ═══════════════════════════════════════════════════════
//  METADATA
// ═══════════════════════════════════════════════════════

async function loadMetadata() {
    try {
        const res = await authedFetch(`${getApiBase()}/api/candidates/metadata`);
        if (res.ok) {
            apiMetadata = await res.json();
            populateFilterOptions();
        }
    } catch (e) {
        console.error("Metadata load error:", e);
    }
}

function populateFilterOptions() {
    // Pool filters
    const poolRecSelect  = document.getElementById("filterPoolRecruiter");
    const poolRoleSelect = document.getElementById("filterPoolRole");
    const poolSkillSelect = document.getElementById("filterPoolSkill");
    if (poolRecSelect && poolRecSelect.options.length <= 1)
        apiMetadata.recruiters.forEach(rec => poolRecSelect.add(new Option(rec, rec)));
    if (poolRoleSelect && poolRoleSelect.options.length <= 1)
        apiMetadata.roles.forEach(r => poolRoleSelect.add(new Option(r, r)));
    if (poolSkillSelect && poolSkillSelect.options.length <= 1)
        apiMetadata.skills.forEach(s => poolSkillSelect.add(new Option(s, s)));

    // AI search filters
    const aiRoleSelect = document.getElementById("aiFilterRole");
    const aiRecSelect  = document.getElementById("aiFilterRecruiter");
    if (aiRoleSelect && aiRoleSelect.options.length <= 1)
        apiMetadata.roles.forEach(r => aiRoleSelect.add(new Option(r, r)));
    if (aiRecSelect && aiRecSelect.options.length <= 1)
        apiMetadata.recruiters.forEach(rec => aiRecSelect.add(new Option(rec, rec)));

    // NR JD dropdown
    const nrJdSelect = document.getElementById("nrJdSelect");
    if (nrJdSelect) fetchJdDropdown(nrJdSelect);
}

async function fetchJdDropdown(selectEl) {
    if (!selectEl) return;
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions`);
        if (res.ok) {
            const jds = await res.json();
            selectEl.innerHTML = '<option value="">-- Choose a saved Job Description --</option>';
            jds.forEach(jd => selectEl.add(new Option(jd.title, jd.jd_id)));
        }
    } catch (e) { console.error("JD dropdown error", e); }
}

// ═══════════════════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════════════════

async function loadDashboardStats() {
    try {
        const [resTotal, resMy, resJds, resCvs] = await Promise.all([
            authedFetch(`${getApiBase()}/api/candidates?global_pool=true&limit=1`).catch(() => null),
            authedFetch(`${getApiBase()}/api/candidates?global_pool=false&limit=1`).catch(() => null),
            authedFetch(`${getApiBase()}/api/job-descriptions`).catch(() => null),
            authedFetch(`${getApiBase()}/api/generated-cvs`).catch(() => null)
        ]);

        const el = (id) => document.getElementById(id);

        if (resTotal && resTotal.ok) {
            const data = await resTotal.json();
            if (el("statTotalCandidates")) el("statTotalCandidates").textContent = data.total ?? (Array.isArray(data) ? data.length : 0);
        }
        if (resMy && resMy.ok) {
            const data = await resMy.json();
            if (el("statMyCandidates")) el("statMyCandidates").textContent = data.total ?? (Array.isArray(data) ? data.length : 0);
        }
        if (resJds && resJds.ok) {
            const data = await resJds.json();
            if (el("statActiveJds")) el("statActiveJds").textContent = data.length;
        }
        if (resCvs && resCvs.ok) {
            const data = await resCvs.json();
            if (el("statGeneratedCvs")) el("statGeneratedCvs").textContent = data.length;
        }
    } catch (e) {
        console.error("Dashboard stats error:", e);
    }
}

// ─── Template ───────────────────────────────────────────

async function checkActiveTemplate() {
    try {
        const res = await authedFetch(`${getApiBase()}/active-template`);
        if (res.ok) {
            const data = await res.json();
            if (data.template_name) {
                document.getElementById("activeTemplateDisplay").hidden = false;
                document.getElementById("activeTemplateName").textContent = data.template_name;
                const dropzone = document.getElementById("templateDropzone");
                if (dropzone) dropzone.style.display = "none";
            } else {
                document.getElementById("activeTemplateDisplay").hidden = true;
                const dropzone = document.getElementById("templateDropzone");
                if (dropzone) dropzone.style.display = "";
            }
        }
    } catch (e) { console.error("Template check error:", e); }
}

function setupTemplateDropzone() {
    const dropzone   = document.getElementById("templateDropzone");
    const fileInput  = document.getElementById("templateFileInput");
    const removeBtn  = document.getElementById("removeTemplateBtn");

    if (!dropzone || !fileInput) return;

    dropzone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) uploadTemplate(e.target.files[0]);
    });

    ["dragenter","dragover","dragleave","drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); });
    });
    dropzone.addEventListener("dragover",  () => dropzone.classList.add("drag-over"));
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
        dropzone.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) uploadTemplate(e.dataTransfer.files[0]);
    });

    if (removeBtn) removeBtn.addEventListener("click", async () => {
        try {
            await authedFetch(`${getApiBase()}/active-template`, { method: "DELETE" });
            document.getElementById("activeTemplateDisplay").hidden = true;
            if (dropzone) dropzone.style.display = "";
            showMessage("Template removed.", "info");
        } catch (e) { showMessage("Failed to remove template.", "error"); }
    });
}

async function uploadTemplate(file) {
    const formData = new FormData();
    formData.append("file", file);
    try {
        const res = await authedFetch(`${getApiBase()}/upload-template`, { method: "POST", body: formData });
        if (!res.ok) throw new Error("Upload failed");
        showMessage("CV template uploaded successfully.", "success");
        await checkActiveTemplate();
    } catch (e) { showMessage(`Template upload failed: ${e.message}`, "error"); }
}

// ═══════════════════════════════════════════════════════
//  NEW RECRUITMENT — 6-STEP WORKFLOW
// ═══════════════════════════════════════════════════════

function setupNewRecruitment() {
    if (_nrSetupDone) return;
    _nrSetupDone = true;

    // Dropzone
    setupNrDropzone();

    // Source checkbox interactions
    const includePool = document.getElementById("nrIncludePool");
    const onlyNew     = document.getElementById("nrOnlyNew");
    const subOptions  = document.getElementById("nrPoolSubOptions");

    if (includePool) includePool.addEventListener("change", () => {
        if (subOptions) subOptions.style.display = includePool.checked ? "" : "none";
        if (onlyNew && includePool.checked) onlyNew.checked = false;
    });

    if (onlyNew) onlyNew.addEventListener("change", () => {
        if (onlyNew.checked && includePool) {
            includePool.checked = false;
            if (subOptions) subOptions.style.display = "none";
        }
    });

    // Upload button
    const uploadBtn = document.getElementById("nrUploadBtn");
    if (uploadBtn) uploadBtn.addEventListener("click", nrDoUpload);

    // JD file extraction
    const extractBtn = document.getElementById("nrExtractJdBtn");
    if (extractBtn) extractBtn.addEventListener("click", nrExtractJdFile);

    // JD select auto-fill
    const nrJdSelect = document.getElementById("nrJdSelect");
    if (nrJdSelect) {
        fetchJdDropdown(nrJdSelect);
        nrJdSelect.addEventListener("change", async () => {
            const val = nrJdSelect.value;
            if (!val) { document.getElementById("nrJdText").value = ""; return; }
            try {
                const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${val}`);
                if (res.ok) {
                    const jd = await res.json();
                    document.getElementById("nrJdText").value = jd.description || "";
                }
            } catch (e) {}
        });
    }

    // Rank button
    const rankBtn = document.getElementById("nrRankBtn");
    if (rankBtn) rankBtn.addEventListener("click", nrRunRanking);

    // Check all for ranked results
    const checkAll = document.getElementById("nrCheckAll");
    if (checkAll) checkAll.addEventListener("change", (e) => {
        document.querySelectorAll(".nr-rank-check").forEach(cb => {
            cb.checked = e.target.checked;
            const name = cb.dataset.name;
            if (e.target.checked) nrSelectedCandidates.add(name);
            else nrSelectedCandidates.delete(name);
        });
        updateNrSelectionActions();
    });

    // Compare & Generate buttons
    const compareBtn = document.getElementById("nrCompareBtn");
    if (compareBtn) compareBtn.addEventListener("click", () => {
        triggerCandidatesComparison(nrSelectedCandidates, document.getElementById("nrJdText")?.value || "");
    });

    const generateBtn = document.getElementById("nrGenerateBtn");
    if (generateBtn) generateBtn.addEventListener("click", nrDoGenerateCVs);

    // Reset
    const resetBtn = document.getElementById("nrResetBtn");
    if (resetBtn) resetBtn.addEventListener("click", nrReset);

    const startOverBtn = document.getElementById("nrStartOverBtn");
    if (startOverBtn) startOverBtn.addEventListener("click", nrReset);
}

// ─── Dropzone setup ────────────────────────────────────

let nrQueuedFiles = [];

function setupNrDropzone() {
    const dropzone  = document.getElementById("nrDropzone");
    const fileInput = document.getElementById("nrFileInput");
    const uploadBtn = document.getElementById("nrUploadBtn");
    if (!dropzone || !fileInput) return;

    dropzone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
        nrAddFiles(Array.from(e.target.files));
        fileInput.value = "";
    });

    ["dragenter","dragover","dragleave","drop"].forEach(ev => {
        dropzone.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); });
    });
    dropzone.addEventListener("dragover",  () => dropzone.classList.add("drag-over"));
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
        dropzone.classList.remove("drag-over");
        nrAddFiles(Array.from(e.dataTransfer.files));
    });
}

function nrAddFiles(files) {
    const valid   = files.filter(f => /\.(pdf|docx)$/i.test(f.name));
    const invalid = files.filter(f => !/\.(pdf|docx)$/i.test(f.name));

    if (invalid.length) showMessage(`Rejected ${invalid.length} file(s) — only PDF/DOCX allowed.`, "error");

    valid.forEach(f => {
        if (!nrQueuedFiles.find(q => q.name === f.name)) nrQueuedFiles.push(f);
    });

    nrRenderFileList();

    const uploadBtn = document.getElementById("nrUploadBtn");
    const hint      = document.getElementById("nrUploadHint");
    if (uploadBtn) uploadBtn.disabled = nrQueuedFiles.length === 0;
    if (hint) hint.textContent = nrQueuedFiles.length > 0
        ? `${nrQueuedFiles.length} file(s) ready to upload`
        : "Select at least one resume file to continue";
}

function nrRenderFileList() {
    const list = document.getElementById("nrFileList");
    if (!list) return;
    if (nrQueuedFiles.length === 0) { list.style.display = "none"; list.innerHTML = ""; return; }

    list.style.display = "flex";
    list.innerHTML = nrQueuedFiles.map((f, i) => `
        <div class="nr-file-item" id="nrFile-${i}">
            <span>📄</span>
            <span class="nr-file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
            <span class="nr-file-status"><span class="skill-tag">Ready</span></span>
            <button type="button" class="remove-btn" onclick="nrRemoveFile(${i})" title="Remove">×</button>
        </div>
    `).join("");
}

function nrRemoveFile(idx) {
    nrQueuedFiles.splice(idx, 1);
    nrRenderFileList();
    const uploadBtn = document.getElementById("nrUploadBtn");
    if (uploadBtn) uploadBtn.disabled = nrQueuedFiles.length === 0;
}

// ─── Upload & Processing ───────────────────────────────

async function nrDoUpload() {
    if (nrQueuedFiles.length === 0) { showMessage("Please select resume files first.", "error"); return; }

    const uploadBtn = document.getElementById("nrUploadBtn");
    if (uploadBtn) { uploadBtn.disabled = true; uploadBtn.textContent = "Uploading..."; }

    // Show step 2
    nrShowStep(2);
    nrSetChecklist("running", "running", "pending", "pending", "pending");

    // Progress bar elements
    const progressContainer = document.getElementById("nrUploadProgressContainer");
    const progressBarFill = document.getElementById("nrUploadProgressBarFill");
    const progressPercent = document.getElementById("nrUploadProgressPercent");
    if (progressContainer) progressContainer.style.display = "block";
    if (progressBarFill) progressBarFill.style.width = "0%";
    if (progressPercent) progressPercent.textContent = "0%";

    let uploadProgress = 0;
    const progressInterval = setInterval(() => {
        if (uploadProgress < 90) {
            uploadProgress += Math.floor(Math.random() * 10) + 5;
            uploadProgress = Math.min(uploadProgress, 90);
            if (progressBarFill) progressBarFill.style.width = `${uploadProgress}%`;
            if (progressPercent) progressPercent.textContent = `${uploadProgress}%`;
        }
    }, 150);

    const tStart = performance.now();
    const formData = new FormData();
    nrQueuedFiles.forEach(f => formData.append("files", f));

    try {
        // Mark upload
        nrSetChecklistItem("chk-upload", "running", "Uploading files...");

        const res = await authedFetch(`${getApiBase()}/upload-resumes`, { method: "POST", body: formData });

        clearInterval(progressInterval);
        if (progressBarFill) progressBarFill.style.width = "100%";
        if (progressPercent) progressPercent.textContent = "100%";
        setTimeout(() => { if (progressContainer) progressContainer.style.display = "none"; }, 800);

        nrSetChecklistItem("chk-upload", "done", "Files uploaded");
        nrSetChecklistItem("chk-dup",    "done", "Duplicate detection complete");
        nrSetChecklistItem("chk-parse",  "done", "Parsing complete via OpenAI");
        nrSetChecklistItem("chk-embed",  "done", "Embeddings generated & indexed");
        nrSetChecklistItem("chk-save",   "done", "Candidates saved to database");

        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();

        const parsed = data.uploaded || [];
        const failed = data.failed  || [];
        const dupes  = (nrQueuedFiles.length) - parsed.length - failed.length;
        const tElapsed = ((performance.now() - tStart) / 1000).toFixed(1);

        // Store uploaded names for ranking
        nrUploadedNames = parsed.map(u => u.candidate_name).filter(Boolean);

        // Show summary
        const uploadedEl = document.getElementById("procStatUploaded");
        if (uploadedEl) uploadedEl.textContent = nrQueuedFiles.length;
        document.getElementById("procStatParsed").textContent = parsed.length;
        document.getElementById("procStatDupes").textContent  = Math.max(0, dupes);
        document.getElementById("procStatFailed").textContent = failed.length;
        const timeEl = document.getElementById("procStatTime");
        if (timeEl) timeEl.textContent = `${tElapsed}s`;
        document.getElementById("nrProcessingSummary").style.display = "flex";

        // List parsed
        if (parsed.length > 0) {
            const pl = document.getElementById("nrParsedList");
            pl.style.display = "block";
            pl.innerHTML = `
                <div class="source-selection-card" style="margin-top:0;">
                    <h3 class="source-title">✅ Parsed Candidates</h3>
                    <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">
                        ${parsed.map(u => `
                            <div style="display:flex; align-items:center; gap:10px; font-size:12.5px;">
                                <span style="color:var(--success-strong);">✓</span>
                                <strong>${escapeHtml(u.candidate_name)}</strong>
                                <span style="color:var(--muted);">(${escapeHtml(u.filename)})</span>
                            </div>
                        `).join("")}
                    </div>
                </div>`;
        }

        // Mark connectors
        nrMarkConnector(1, true);
        nrMarkConnector(2, true);
        nrSetStepIndicator(3, "active");
        nrSetStepIndicator(2, "done");
        nrSetStepIndicator(1, "done");

        // Reveal step 3 after short delay
        setTimeout(() => nrShowStep(3), 600);

        await loadDashboardStats();

    } catch (e) {
        nrSetChecklistItem("chk-upload", "error", `Upload failed: ${e.message}`);
        showMessage(`Upload failed: ${e.message}`, "error");
        if (uploadBtn) { uploadBtn.disabled = false; uploadBtn.textContent = "Upload & Parse Resumes"; }
    }
}

function nrSetChecklistItem(id, state, desc) {
    const item    = document.getElementById(id);
    if (!item) return;
    const iconEl  = item.querySelector(".chk-icon");
    const descEl  = item.querySelector(".chk-desc");
    if (iconEl) iconEl.textContent = state === "done" ? "✓" : state === "error" ? "✗" : state === "running" ? "⟳" : "⏳";
    item.className = `checklist-item ${state === "pending" ? "" : state}`;
    if (descEl && desc) descEl.textContent = desc;
}

function nrSetChecklist(s1, s2, s3, s4, s5) {
    nrSetChecklistItem("chk-upload", s1, null);
    nrSetChecklistItem("chk-dup",    s2, null);
    nrSetChecklistItem("chk-parse",  s3, null);
    nrSetChecklistItem("chk-embed",  s4, null);
    nrSetChecklistItem("chk-save",   s5, null);
}

// ─── JD Extraction ────────────────────────────────────

async function nrExtractJdFile() {
    const fileInput = document.getElementById("nrJdFile");
    if (!fileInput || !fileInput.files.length) {
        showMessage("Please select a PDF or DOCX file first.", "error");
        return;
    }
    const btn = document.getElementById("nrExtractJdBtn");
    if (btn) { btn.disabled = true; btn.textContent = "Extracting..."; }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const res = await authedFetch(`${getApiBase()}/extract-jd-text`, { method: "POST", body: formData });
        if (!res.ok) throw new Error("Extraction failed");
        const data = await res.json();
        const textarea = document.getElementById("nrJdText");
        if (textarea && data.text) textarea.value = data.text;
        showMessage("JD text extracted successfully.", "success");
    } catch (e) {
        showMessage(`JD extraction failed: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Extract Text"; }
    }
}

// ─── Ranking ─────────────────────────────────────────

async function nrRunRanking() {
    const jdText = (document.getElementById("nrJdText")?.value || "").trim();
    if (!jdText) { showMessage("Please enter a Job Description to rank candidates.", "error"); return; }

    // Determine candidate source
    const includePool = document.getElementById("nrIncludePool")?.checked;
    const onlyNew     = document.getElementById("nrOnlyNew")?.checked;
    const scopeAll    = document.getElementById("nrScopeAll")?.checked;

    let payload = { jd: jdText, global_pool: true };

    if (onlyNew) {
        // Only score newly uploaded
        if (nrUploadedNames.length === 0) {
            showMessage("No newly uploaded candidates to rank. Either upload resumes or include the pool.", "error");
            return;
        }
        payload.global_pool = false;
        payload.candidate_names = nrUploadedNames;
    } else if (includePool) {
        // Pool + newly uploaded
        payload.global_pool = !scopeAll ? false : true;
        if (!scopeAll) payload.scope = "my";
        // Include newly uploaded names if any
        if (nrUploadedNames.length > 0) payload.include_names = nrUploadedNames;
    }

    const btn = document.getElementById("nrRankBtn");
    if (btn) { btn.disabled = true; btn.textContent = "Ranking..."; }

    // Show step 4
    nrShowStep(4);
    const body = document.getElementById("nrRankBody");
    if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state"><div class="spinner" style="margin:0 auto 8px;"></div>Ranking candidates with FAISS semantic matching...</td></tr>`;

    try {
        const res = await authedFetch(`${getApiBase()}/rank-candidates`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error(await res.text() || "Ranking failed");
        const rawData = await res.json();
        const results = Array.isArray(rawData) ? rawData : (rawData.results || []);

        nrSelectedCandidates.clear();
        nrRenderRankedResults(results);

        nrMarkConnector(2, true);
        nrMarkConnector(3, true);
        nrSetStepIndicator(3, "done");
        nrSetStepIndicator(4, "active");

        document.getElementById("nrRankCount").textContent = `(${results.length})`;

        const actions = document.getElementById("nrRankSelectionActions");
        if (actions) actions.hidden = false;

    } catch (e) {
        if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state error-text">Ranking failed: ${escapeHtml(e.message)}</td></tr>`;
        showMessage(`Ranking failed: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Rank Candidates ›"; }
    }
}

function nrRenderRankedResults(results) {
    const body = document.getElementById("nrRankBody");
    if (!body) return;

    if (!results || results.length === 0) {
        body.innerHTML = `<tr><td colspan="11" class="empty-state">No matching candidates found. Try adjusting the job description or candidate source.</td></tr>`;
        return;
    }

    body.innerHTML = "";
    results.forEach((r, idx) => {
        const score     = Math.round(r.match_score ?? r.score ?? 0);
        const scoreClass = score >= 75 ? "high" : score >= 45 ? "medium" : "low";
        const isNew     = nrUploadedNames.includes(r.candidate_name);
        const badge     = isNew
            ? `<span class="badge-new">NEW</span>`
            : `<span class="badge-existing">EXISTING</span>`;
        const mTags  = (r.matching_skills || []).map(s => `<span class="matching-skill-tag">${escapeHtml(s)}</span>`).join("");
        const msTags = (r.missing_skills  || []).map(s => `<span class="missing-skill-tag">${escapeHtml(s)}</span>`).join("");
        const summary = r.search_profile || "—";

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="checkbox-col">
                <input type="checkbox" class="nr-rank-check" data-name="${escapeHtml(r.candidate_name)}">
            </td>
            <td class="candidate-name-cell" onclick="viewCandidateProfile('${escapeHtml(r.candidate_name)}')">${escapeHtml(r.candidate_name)}</td>
            <td class="role-text">${escapeHtml(r.current_role || "Unknown")}</td>
            <td>${r.years_of_experience} yrs</td>
            <td class="score-badge-col"><span class="score-badge ${scoreClass}">${score}%</span></td>
            <td>${badge}</td>
            <td>${escapeHtml(r.uploaded_by || "—")}</td>
            <td>${mTags  || '<span style="color:var(--text-muted); font-size:12px;">—</span>'}</td>
            <td>${msTags || '<span style="color:var(--text-muted); font-size:12px;">—</span>'}</td>
            <td>
                <div style="max-height: 48px; overflow-y: auto; font-size: 11.5px; line-height: 1.4; color: var(--text-secondary); max-width: 240px;" title="${escapeHtml(summary)}">
                    ${escapeHtml(summary)}
                </div>
            </td>
            <td>
                <div class="actions-cell-wrap" style="display:flex; gap:6px;">
                    <button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(r.candidate_name)}')">Profile</button>
                    <button type="button" class="btn btn-secondary compact-btn" onclick="triggerSingleCandidateComparison('${escapeHtml(r.candidate_name)}')">Compare</button>
                    <button type="button" class="btn btn-primary compact-btn" onclick="triggerSingleCandidateCv('${escapeHtml(r.candidate_name)}')">Generate CV</button>
                </div>
            </td>`;
        body.appendChild(tr);

        tr.querySelector(".nr-rank-check").addEventListener("change", (e) => {
            if (e.target.checked) nrSelectedCandidates.add(r.candidate_name);
            else nrSelectedCandidates.delete(r.candidate_name);
            updateNrSelectionActions();
        });
    });
}

function updateNrSelectionActions() {
    const count = nrSelectedCandidates.size;
    const compareBtn  = document.getElementById("nrCompareBtn");
    const generateBtn = document.getElementById("nrGenerateBtn");
    if (compareBtn)  compareBtn.disabled  = count < 2;
    if (generateBtn) generateBtn.disabled = count === 0;
}

// ─── CV Generation ────────────────────────────────────

async function nrDoGenerateCVs() {
    const names  = Array.from(nrSelectedCandidates);
    const jdText = (document.getElementById("nrJdText")?.value || "").trim();

    if (names.length === 0) { showMessage("Select at least one candidate.", "error"); return; }

    // Show step 5
    nrShowStep(5);
    nrMarkConnector(3, true);
    nrMarkConnector(4, true);
    nrSetStepIndicator(4, "done");
    nrSetStepIndicator(5, "active");

    const countEl  = document.getElementById("nrGenerateCount");
    const progress = document.getElementById("nrGenerateProgress");
    const result   = document.getElementById("nrGenerateResult");

    if (countEl)  countEl.textContent = names.length;
    if (progress) progress.style.display = "flex";
    if (result)   result.style.display = "none";

    try {
        const res = await authedFetch(`${getApiBase()}/generate-selected-cvs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ candidate_names: names, jd: jdText || "General Professional Profile" })
        });

        if (!res.ok) throw new Error(await res.text() || "Generation failed");

        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);

        if (progress) progress.style.display = "none";
        if (result)   result.style.display   = "block";

        const link = document.getElementById("nrDownloadLink");
        if (link) {
            link.href = url;
            link.download = `CVs_${names.join("_").substring(0, 40)}_${new Date().toISOString().slice(0,10)}.zip`;
        }

        const descEl = document.getElementById("nrGenerateResultDesc");
        if (descEl) descEl.textContent = `${names.length} CV(s) generated. Your download should begin automatically.`;

        link?.click();
        await fetchGeneratedCvs();

    } catch (e) {
        if (progress) progress.style.display = "none";
        showMessage(`CV generation failed: ${e.message}`, "error");
    }
}

// ─── Step Navigation Helpers ──────────────────────────

function nrShowStep(stepNumber) {
    // Show all steps up to and including stepNumber
    for (let i = 1; i <= 5; i++) {
        const el = document.getElementById(`nrStep${i}`);
        if (el) el.style.display = i <= stepNumber ? "" : "none";
    }
    // Scroll to the new step
    const el = document.getElementById(`nrStep${stepNumber}`);
    if (el) setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}

function nrSetStepIndicator(step, state) {
    const el = document.getElementById(`nrStep${step}Indicator`);
    if (!el) return;
    el.className = `step-item ${state}`;
    const circle = el.querySelector(".step-circle");
    if (circle && state === "done") circle.textContent = "✓";
}

function nrMarkConnector(num, done) {
    const el = document.getElementById(`nrConn${num}`);
    if (el) el.classList.toggle("done", done);
}

function nrReset() {
    // Reset state
    nrQueuedFiles = [];
    nrUploadedNames = [];
    nrSelectedCandidates.clear();

    // Reset UI
    nrRenderFileList();
    for (let i = 1; i <= 5; i++) {
        const el = document.getElementById(`nrStep${i}`);
        if (el) el.style.display = i === 1 ? "" : "none";
    }
    for (let i = 1; i <= 5; i++) {
        const ind = document.getElementById(`nrStep${i}Indicator`);
        if (ind) { ind.className = `step-item${i === 1 ? " active" : ""}`; const c = ind.querySelector(".step-circle"); if (c) c.textContent = i; }
    }
    for (let i = 1; i <= 4; i++) nrMarkConnector(i, false);

    // Reset checkboxes
    const incPool = document.getElementById("nrIncludePool");
    if (incPool) incPool.checked = true;
    const onlyNew = document.getElementById("nrOnlyNew");
    if (onlyNew) onlyNew.checked = false;
    const scopeAll = document.getElementById("nrScopeAll");
    if (scopeAll) scopeAll.checked = true;
    const subOpts = document.getElementById("nrPoolSubOptions");
    if (subOpts) subOpts.style.display = "";

    const progressContainer = document.getElementById("nrUploadProgressContainer");
    if (progressContainer) progressContainer.style.display = "none";

    // Reset inputs
    const els = ["nrJdText"];
    els.forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });

    const rankBody = document.getElementById("nrRankBody");
    if (rankBody) rankBody.innerHTML = `<tr><td colspan="11" class="empty-state">Run ranking above to see results.</td></tr>`;

    const rankCount = document.getElementById("nrRankCount");
    if (rankCount) rankCount.textContent = "";

    const uploadBtn = document.getElementById("nrUploadBtn");
    if (uploadBtn) { uploadBtn.disabled = true; uploadBtn.textContent = "Upload & Parse Resumes"; }

    const hint = document.getElementById("nrUploadHint");
    if (hint) hint.textContent = "Select at least one resume file to continue";

    const summary = document.getElementById("nrProcessingSummary");
    if (summary) summary.style.display = "none";
    const parsedList = document.getElementById("nrParsedList");
    if (parsedList) { parsedList.style.display = "none"; parsedList.innerHTML = ""; }

    const genResult = document.getElementById("nrGenerateResult");
    if (genResult) genResult.style.display = "none";
    const genProgress = document.getElementById("nrGenerateProgress");
    if (genProgress) genProgress.style.display = "none";

    updateNrSelectionActions();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

// ═══════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════
//  CANDIDATE POOL (BROWSE + SEMANTIC SEARCH + PAGINATION)
// ═══════════════════════════════════════════════════════

// Pool state tracks mode (browse | search), current page, total, and query
const poolState = {
    mode:  "browse",   // "browse" | "search"
    page:  1,
    limit: 20,
    total: 0,
    query: ""
};

function showToast(message) {
    let toast = document.getElementById("toast-notification");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast-notification";
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = "toast-show";
    setTimeout(() => { if (toast.className === "toast-show") toast.className = ""; }, 3000);
}

async function copyJobDescription(jdId) {
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}`);
        if (!res.ok) throw new Error("Could not fetch JD");
        const jd = await res.json();
        await navigator.clipboard.writeText(jd.description || "");
        showToast("Job Description copied.");
    } catch (e) {
        showMessage(`Failed to copy JD: ${e.message}`, "error");
    }
}

function setupCandidatePoolPage() {
    if (_poolSetupDone) return;
    _poolSetupDone = true;

    const searchBtn   = document.getElementById("poolSearchBtn");
    const clearBtn    = document.getElementById("poolClearSearchBtn");
    const compareBtn  = document.getElementById("poolCompareBtn");
    const genBtn      = document.getElementById("poolGenerateCvsBtn");
    const searchInput = document.getElementById("poolSearchInput");
    const prevBtn     = document.getElementById("poolPrevBtn");
    const nextBtn     = document.getElementById("poolNextBtn");

    if (searchBtn) searchBtn.addEventListener("click", () => runPoolSemanticSearch(1));
    if (searchInput) {
        searchInput.addEventListener("keydown", e => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runPoolSemanticSearch(1); }
        });
    }
    if (clearBtn)  clearBtn.addEventListener("click", clearPoolSearch);
    if (prevBtn)   prevBtn.addEventListener("click",  () => loadPoolPage(poolState.page - 1));
    if (nextBtn)   nextBtn.addEventListener("click",  () => loadPoolPage(poolState.page + 1));

    if (compareBtn) compareBtn.addEventListener("click", () => triggerCandidatesComparison(poolSelectedCompareCandidates, activePoolQuery));
    if (genBtn) genBtn.addEventListener("click", async () => { await triggerCVsZipDownload(Array.from(poolSelectedGenerateCandidates), activePoolQuery, genBtn); });

    setupPoolSelectAllListeners();

    // Load default candidate list immediately
    loadPoolCandidates(1);
}

// Navigate to page (respects current mode)
function loadPoolPage(page) {
    if (poolState.mode === "search") {
        runPoolSemanticSearch(page);
    } else {
        loadPoolCandidates(page);
    }
}

// Browse mode: load all candidates paginated by upload date desc
async function loadPoolCandidates(page = 1) {
    poolState.mode = "browse";
    poolState.page = page;
    poolSelectedCompareCandidates.clear();
    poolSelectedGenerateCandidates.clear();
    activePoolQuery = "";
    updatePoolSelectionActions();

    const body = document.getElementById("poolTableBody");
    if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state"><div class="spinner" style="margin:0 auto 8px;"></div>Loading candidates...</td></tr>`;

    const scoreHeader   = document.getElementById("poolScoreHeader");
    const missingHeader = document.getElementById("poolMissingHeader");
    if (scoreHeader)   scoreHeader.textContent = "Top Skills";
    if (missingHeader) missingHeader.style.display = "";

    try {
        const params = new URLSearchParams({
            global_pool: "true",
            sort_by: "created_at",
            sort_order: "desc",
            page,
            limit: poolState.limit
        });
        const res = await authedFetch(`${getApiBase()}/api/candidates?${params}`);
        if (!res.ok) throw new Error("Could not load candidates");
        const data = await res.json();

        poolState.total = data.total || 0;
        poolState.page  = data.page  || page;

        const countBadge = document.getElementById("poolResultCount");
        if (countBadge) countBadge.textContent = poolState.total > 0 ? `(${poolState.total})` : "";

        renderPoolBrowseResults(data.results || []);
        renderPoolPagination();

    } catch (e) {
        if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state error-text">Error: ${escapeHtml(e.message)}</td></tr>`;
    }
}

// Render default (browse mode) rows — no match score
function renderPoolBrowseResults(results) {
    const body    = document.getElementById("poolTableBody");
    const actions = document.getElementById("poolSelectionActions");
    if (!body) return;

    if (!results || results.length === 0) {
        body.innerHTML = `<tr><td colspan="11" class="empty-state">No candidates found. Upload resumes to get started.</td></tr>`;
        if (actions) actions.hidden = true;
        renderPoolPagination();
        return;
    }

    if (actions) actions.hidden = false;
    body.innerHTML = "";

    const offset = (poolState.page - 1) * poolState.limit;
    results.forEach((c, idx) => {
        const skillTags = (c.skills || []).slice(0, 5).map(s => `<span class="skill-tag" style="font-size:11px;">${escapeHtml(s)}</span>`).join("");
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="text-align:center; color:var(--text-muted); font-size:12px;">${offset + idx + 1}</td>
            <td class="candidate-name-cell" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">${escapeHtml(c.candidate_name)}</td>
            <td class="role-text">${escapeHtml(c.current_role || "—")}</td>
            <td>${c.years_of_experience ?? "—"} yrs</td>
            <td>${escapeHtml(c.uploaded_by || "—")}</td>
            <td><span style="color:var(--text-muted); font-size:12px;">—</span></td>
            <td>${skillTags || '<span style="color:var(--text-muted); font-size:12px;">—</span>'}</td>
            <td><span style="color:var(--text-muted); font-size:12px;">—</span></td>
            <td style="text-align:center;"><input type="checkbox" class="pool-compare-check" data-name="${escapeHtml(c.candidate_name)}" id="pool-compare-check-b-${idx}"></td>
            <td style="text-align:center;"><input type="checkbox" class="pool-generate-check" data-name="${escapeHtml(c.candidate_name)}" id="pool-generate-check-b-${idx}"></td>
            <td style="text-align:center;"><button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">Preview</button></td>`;
        body.appendChild(tr);

        tr.querySelector(".pool-compare-check").addEventListener("change", e => {
            if (e.target.checked) poolSelectedCompareCandidates.add(c.candidate_name);
            else poolSelectedCompareCandidates.delete(c.candidate_name);
            updatePoolSelectionActions();
        });
        tr.querySelector(".pool-generate-check").addEventListener("change", e => {
            if (e.target.checked) poolSelectedGenerateCandidates.add(c.candidate_name);
            else poolSelectedGenerateCandidates.delete(c.candidate_name);
            updatePoolSelectionActions();
        });
    });
}

// Run semantic search and render ranked results with "Why Matched" rows
async function runPoolSemanticSearch(page = 1) {
    const query = (document.getElementById("poolSearchInput")?.value || "").trim();
    if (!query) {
        showMessage("Please enter a search query or paste a Job Description.", "error");
        return;
    }

    poolState.mode  = "search";
    poolState.page  = page;
    poolState.query = query;
    activePoolQuery = query;

    poolSelectedCompareCandidates.clear();
    poolSelectedGenerateCandidates.clear();
    const allCompare = document.getElementById("poolCheckAllCompare");
    if (allCompare) allCompare.checked = false;
    const allGen = document.getElementById("poolCheckAllGenerate");
    if (allGen) allGen.checked = false;
    updatePoolSelectionActions();

    const btn  = document.getElementById("poolSearchBtn");
    const body = document.getElementById("poolTableBody");
    if (btn)  { btn.disabled = true; btn.innerHTML = `<span class="ai-search-btn-icon">⏳</span> Searching...`; }
    if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state"><div class="spinner" style="margin:0 auto 8px;"></div>Searching candidate embeddings...</td></tr>`;

    const scoreHeader   = document.getElementById("poolScoreHeader");
    const missingHeader = document.getElementById("poolMissingHeader");
    if (scoreHeader)   scoreHeader.textContent = "Match Score";
    if (missingHeader) missingHeader.style.display = "";

    try {
        const res = await authedFetch(`${getApiBase()}/api/candidates/semantic-search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, min_score: 0.1, page, limit: poolState.limit })
        });
        if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || "Search failed"); }

        const data = await res.json();
        poolState.total = data.total || 0;
        poolState.page  = data.page  || page;

        const countBadge = document.getElementById("poolResultCount");
        if (countBadge) countBadge.textContent = poolState.total > 0 ? `(${poolState.total})` : "";

        renderPoolSemanticSearchResults(data.results || []);
        renderPoolPagination();

    } catch (e) {
        if (body) body.innerHTML = `<tr><td colspan="11" class="empty-state error-text">Error: ${escapeHtml(e.message)}</td></tr>`;
        showMessage(`Search failed: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `✦ Search Candidates`; }
    }
}

// Render semantic search result rows with expandable "Why Matched" sub-rows
function renderPoolSemanticSearchResults(results) {
    const body    = document.getElementById("poolTableBody");
    const actions = document.getElementById("poolSelectionActions");
    if (!body) return;

    if (!results || results.length === 0) {
        body.innerHTML = `<tr><td colspan="11" class="empty-state">No relevant candidates found.</td></tr>`;
        if (actions) actions.hidden = true;
        renderPoolPagination();
        return;
    }

    if (actions) actions.hidden = false;
    body.innerHTML = "";

    const offset = (poolState.page - 1) * poolState.limit;
    results.forEach((c, idx) => {
        const globalIdx  = offset + idx;
        const scorePct   = c.score_pct || Math.round((c.score || 0) * 100);
        const scoreColor = scorePct >= 75 ? "#10b981" : scorePct >= 45 ? "#f59e0b" : "#94a3b8";
        const scoreClass = scorePct >= 75 ? "high" : scorePct >= 45 ? "medium" : "low";

        const md = c.match_details || {};
        const matchingSkillsTags = (c.matching_skills || []).map(s => `<span class="matching-skill-tag">${escapeHtml(s)}</span>`).join("");
        const missingSkillsTags  = (c.missing_skills || []).map(s => `<span class="missing-skill-tag">${escapeHtml(s)}</span>`).join("");

        const rowId = `pool-why-row-${globalIdx}`;

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="text-align:center; font-weight:700; color:var(--text-muted); font-size:12px;">${globalIdx + 1}</td>
            <td class="candidate-name-cell" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">${escapeHtml(c.candidate_name)}</td>
            <td class="role-text">${escapeHtml(c.current_role || "—")}</td>
            <td>${c.years_of_experience ?? "—"} yrs</td>
            <td>${escapeHtml(c.uploaded_by || "—")}</td>
            <td>
                <div class="ai-score-bar-wrapper">
                    <span class="ai-score-pct" style="color:${scoreColor}">${scorePct}%</span>
                    <div class="ai-score-bar"><div class="ai-score-bar-fill ${scoreClass}" style="width:0%" data-target="${scorePct}%"></div></div>
                </div>
                <button type="button" class="pool-why-toggle-btn" onclick="togglePoolWhyRow('${rowId}')" style="font-size:10px; color:var(--accent); background:none; border:none; cursor:pointer; padding:2px 0; display:block; margin-top:3px;">▶ Why matched</button>
            </td>
            <td>${matchingSkillsTags || '<span style="color:var(--text-muted); font-size:12px;">—</span>'}</td>
            <td>${missingSkillsTags  || '<span style="color:var(--text-muted); font-size:12px;">—</span>'}</td>
            <td style="text-align:center;"><input type="checkbox" class="pool-compare-check" data-name="${escapeHtml(c.candidate_name)}" id="pool-compare-check-s-${globalIdx}"></td>
            <td style="text-align:center;"><input type="checkbox" class="pool-generate-check" data-name="${escapeHtml(c.candidate_name)}" id="pool-generate-check-s-${globalIdx}"></td>
            <td style="text-align:center;"><button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">Preview</button></td>`;
        body.appendChild(tr);

        // "Why Matched" expandable sub-row
        const whyRow = document.createElement("tr");
        whyRow.id = rowId;
        whyRow.style.display = "none";
        whyRow.innerHTML = `<td colspan="11" style="padding:0; background:var(--surface-hover);">
            <div class="pool-why-panel" style="padding:14px 20px; border-top:1px solid var(--border); border-bottom:1px solid var(--border);">
                ${buildWhyMatchedHTML(c, md)}
            </div>
        </td>`;
        body.appendChild(whyRow);

        tr.querySelector(".pool-compare-check").addEventListener("change", e => {
            if (e.target.checked) poolSelectedCompareCandidates.add(c.candidate_name);
            else poolSelectedCompareCandidates.delete(c.candidate_name);
            updatePoolSelectionActions();
        });
        tr.querySelector(".pool-generate-check").addEventListener("change", e => {
            if (e.target.checked) poolSelectedGenerateCandidates.add(c.candidate_name);
            else poolSelectedGenerateCandidates.delete(c.candidate_name);
            updatePoolSelectionActions();
        });
    });

    // Animate score bars
    requestAnimationFrame(() => setTimeout(() => {
        body.querySelectorAll(".ai-score-bar-fill[data-target]").forEach(fill => { fill.style.width = fill.dataset.target; });
    }, 80));
}

// Build the inner HTML for the "Why this candidate matched" panel
function buildWhyMatchedHTML(c, md) {
    const matchingItems = [];
    if (md.matching_exp) matchingItems.push(md.matching_exp);
    (md.matching_skills || []).forEach(s => matchingItems.push(s));
    (md.matching_tech   || []).forEach(t => matchingItems.push(t));
    (md.matching_domains|| []).forEach(d => matchingItems.push(d));

    const missingItems = [];
    (md.missing_skills || []).forEach(s => missingItems.push(s));
    (md.missing_tech   || []).forEach(t => missingItems.push(t));
    if (md.missing_exp)  missingItems.push(md.missing_exp);

    const matchingHTML = matchingItems.length
        ? matchingItems.map(i => `<div style="color:#10b981; font-size:12.5px; margin-bottom:3px;">✓ ${escapeHtml(i)}</div>`).join("")
        : `<div style="color:var(--text-muted); font-size:12px;">No direct skill matches — matched semantically.</div>`;

    const missingHTML = missingItems.length
        ? missingItems.map(i => `<div style="color:#f59e0b; font-size:12.5px; margin-bottom:3px;">• ${escapeHtml(i)}</div>`).join("")
        : `<div style="color:var(--text-muted); font-size:12px;">No obvious gaps detected.</div>`;

    const explanation = c.explanation
        ? `<div style="margin-top:10px; padding-top:10px; border-top:1px solid var(--border); color:var(--text-secondary); font-size:12.5px; font-style:italic;">"${escapeHtml(c.explanation)}"</div>`
        : "";

    return `
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px 24px;">
            <div>
                <div style="font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--text-muted); margin-bottom:6px; font-weight:600;">Why Matched</div>
                ${matchingHTML}
            </div>
            <div>
                <div style="font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--text-muted); margin-bottom:6px; font-weight:600;">Missing / Gaps</div>
                ${missingHTML}
            </div>
        </div>
        ${explanation}`;
}

// Toggle the Why Matched sub-row open/closed
function togglePoolWhyRow(rowId) {
    const row = document.getElementById(rowId);
    if (!row) return;
    const isHidden = row.style.display === "none";
    row.style.display = isHidden ? "" : "none";
    // Update button label
    const btn = row.previousElementSibling?.querySelector(".pool-why-toggle-btn");
    if (btn) btn.textContent = isHidden ? "▼ Why matched" : "▶ Why matched";
}

// Render pagination controls
function renderPoolPagination() {
    const paginationEl = document.getElementById("poolPagination");
    const infoEl       = document.getElementById("poolPaginationInfo");
    const prevBtn      = document.getElementById("poolPrevBtn");
    const nextBtn      = document.getElementById("poolNextBtn");
    const pageNums     = document.getElementById("poolPageNumbers");
    if (!paginationEl) return;

    const { total, page, limit } = poolState;
    const totalPages = Math.ceil(total / limit) || 1;

    if (total === 0) { paginationEl.hidden = true; return; }
    paginationEl.hidden = false;

    const from = Math.min((page - 1) * limit + 1, total);
    const to   = Math.min(page * limit, total);
    if (infoEl) infoEl.textContent = `Showing ${from}–${to} of ${total} candidates`;

    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= totalPages;

    if (pageNums) {
        pageNums.innerHTML = "";
        const range = buildPageRange(page, totalPages);
        range.forEach(p => {
            if (p === "…") {
                const span = document.createElement("span");
                span.textContent = "…";
                span.style.cssText = "padding:0 4px; color:var(--text-muted);";
                pageNums.appendChild(span);
            } else {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = p;
                btn.className = "btn compact-btn " + (p === page ? "btn-primary" : "btn-secondary");
                btn.style.minWidth = "32px";
                btn.addEventListener("click", () => loadPoolPage(p));
                pageNums.appendChild(btn);
            }
        });
    }
}

// Build a compact page number range like [1 … 4 5 6 … 12]
function buildPageRange(current, total) {
    if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);
    const pages = new Set([1, total, current]);
    for (let d = 1; d <= 2; d++) { if (current - d >= 1) pages.add(current - d); if (current + d <= total) pages.add(current + d); }
    const sorted = Array.from(pages).sort((a, b) => a - b);
    const result = [];
    for (let i = 0; i < sorted.length; i++) {
        if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push("…");
        result.push(sorted[i]);
    }
    return result;
}

function clearPoolSearch() {
    poolSelectedCompareCandidates.clear();
    poolSelectedGenerateCandidates.clear();
    activePoolQuery = "";

    const input = document.getElementById("poolSearchInput");
    if (input) input.value = "";

    const allCompare = document.getElementById("poolCheckAllCompare");
    if (allCompare) allCompare.checked = false;
    const allGen = document.getElementById("poolCheckAllGenerate");
    if (allGen) allGen.checked = false;

    updatePoolSelectionActions();

    const countBadge = document.getElementById("poolResultCount");
    if (countBadge) countBadge.textContent = "";

    // Return to browse mode
    loadPoolCandidates(1);
}

function setPoolSearchQuery(text) {
    const input = document.getElementById("poolSearchInput");
    if (input) { input.value = text; input.focus(); }
}

function updatePoolSelectionActions() {
    const compareCount  = poolSelectedCompareCandidates.size;
    const generateCount = poolSelectedGenerateCandidates.size;
    const compareBtn  = document.getElementById("poolCompareBtn");
    const generateBtn = document.getElementById("poolGenerateCvsBtn");

    if (compareBtn) {
        compareBtn.disabled = compareCount < 2;
        compareBtn.textContent = compareCount > 0 ? `Compare Selected (${compareCount})` : "Compare Selected";
    }
    if (generateBtn) {
        generateBtn.disabled = generateCount === 0;
        generateBtn.textContent = generateCount > 0 ? `Generate Client CVs (${generateCount})` : "Generate Client CVs";
    }
}

function setupPoolSelectAllListeners() {
    const selectAllCompare  = document.getElementById("poolCheckAllCompare");
    const selectAllGenerate = document.getElementById("poolCheckAllGenerate");

    if (selectAllCompare) {
        selectAllCompare.addEventListener("change", e => {
            document.querySelectorAll(".pool-compare-check").forEach(cb => {
                cb.checked = e.target.checked;
                if (e.target.checked) poolSelectedCompareCandidates.add(cb.dataset.name);
                else poolSelectedCompareCandidates.delete(cb.dataset.name);
            });
            updatePoolSelectionActions();
        });
    }

    if (selectAllGenerate) {
        selectAllGenerate.addEventListener("change", e => {
            document.querySelectorAll(".pool-generate-check").forEach(cb => {
                cb.checked = e.target.checked;
                if (e.target.checked) poolSelectedGenerateCandidates.add(cb.dataset.name);
                else poolSelectedGenerateCandidates.delete(cb.dataset.name);
            });
            updatePoolSelectionActions();
        });
    }
}


// ═══════════════════════════════════════════════════════
//  AI TALENT SEARCH
// ═══════════════════════════════════════════════════════

function setupAITalentSearch() {
    if (_aiSearchSetupDone) return;
    _aiSearchSetupDone = true;

    const searchBtn = document.getElementById("aiTalentSearchBtn");
    const input     = document.getElementById("aiTalentSearchInput");
    const clearBtn  = document.getElementById("aiClearSearchBtn");
    const filterBtn = document.getElementById("aiFilterApplyBtn");
    const checkAll  = document.getElementById("checkAllAiResults");
    const compareBtn = document.getElementById("aiCompareBtn");
    const genBtn    = document.getElementById("aiGenerateCvsBtn");

    if (searchBtn) searchBtn.addEventListener("click", runAITalentSearch);
    if (input)     input.addEventListener("keydown", e => { if (e.key === "Enter") runAITalentSearch(); });
    if (clearBtn)  clearBtn.addEventListener("click", clearAISearch);
    if (filterBtn) filterBtn.addEventListener("click", runAITalentSearch);

    if (checkAll) checkAll.addEventListener("change", (e) => {
        document.querySelectorAll(".ai-result-check").forEach(cb => {
            cb.checked = e.target.checked;
            if (e.target.checked) aiSearchSelectedCandidates.add(cb.dataset.name);
            else aiSearchSelectedCandidates.delete(cb.dataset.name);
        });
        updateAISelectionActions();
    });

    if (compareBtn) compareBtn.addEventListener("click", () => {
        triggerCandidatesComparison(new Set(aiSearchSelectedCandidates), "");
    });

    if (genBtn) genBtn.addEventListener("click", async () => {
        await triggerCVsZipDownload(Array.from(aiSearchSelectedCandidates), "", genBtn);
    });
}

function setAIQuery(text) {
    const input = document.getElementById("aiTalentSearchInput");
    if (input) { input.value = text; input.focus(); }
}

async function runAITalentSearch() {
    const query = (document.getElementById("aiTalentSearchInput")?.value || "").trim();
    if (!query) { showMessage("Please enter a search query.", "error"); return; }

    const btn = document.getElementById("aiTalentSearchBtn");
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="ai-search-btn-icon">⏳</span> Searching...`; }

    const panel = document.getElementById("aiSearchResultsPanel");
    const body  = document.getElementById("aiResultsBody");
    if (panel) panel.hidden = false;
    if (body)  body.innerHTML = `<tr><td colspan="9"><div class="ai-searching-state">✦ Analyzing query and searching the talent pool...</div></td></tr>`;

    const expFilter  = document.getElementById("aiFilterExperience")?.value || "";
    const roleFilter = document.getElementById("aiFilterRole")?.value || "";
    const recFilter  = document.getElementById("aiFilterRecruiter")?.value || "";

    try {
        const res = await authedFetch(`${getApiBase()}/api/candidates/semantic-search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, top_k: 20, min_score: 0.25, experience: expFilter, role: roleFilter, recruiter: recFilter })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Search failed");
        }

        const data = await res.json();
        aiSearchActive = true;
        aiSearchSelectedCandidates.clear();

        const filters = document.getElementById("aiSearchFilters");
        if (filters) filters.hidden = false;

        const countBadge = document.getElementById("aiResultCount");
        const queryLabel = document.getElementById("aiResultQueryLabel");
        if (countBadge) countBadge.textContent = `(${data.count})`;
        if (queryLabel) queryLabel.textContent  = `Query: "${data.query}"`;

        renderSemanticSearchResults(data.results, data.query);

    } catch (e) {
        if (body) body.innerHTML = `<tr><td colspan="9"><div class="empty-state error-text">Error: ${escapeHtml(e.message)}</div></td></tr>`;
        showMessage(`AI Search failed: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `<span class="ai-search-btn-icon">✦</span> Search`; }
    }
}

function renderSemanticSearchResults(results, query) {
    const body    = document.getElementById("aiResultsBody");
    const actions = document.getElementById("aiSelectionActions");
    if (!body) return;

    if (!results || results.length === 0) {
        body.innerHTML = `<tr><td colspan="9"><div class="ai-no-results"><span class="ai-no-results-icon">🔍</span><h3>No relevant candidates found</h3><p>Try broadening your search query or uploading additional resumes.</p></div></td></tr>`;
        if (actions) actions.hidden = true;
        return;
    }

    if (actions) actions.hidden = false;
    body.innerHTML = "";

    results.forEach((c, idx) => {
        const scorePct   = c.score_pct || Math.round(c.score * 100);
        const scoreClass = scorePct >= 70 ? "high" : scorePct >= 45 ? "medium" : "low";
        const scoreColor = scorePct >= 70 ? "#10b981" : scorePct >= 45 ? "#f59e0b" : "#94a3b8";
        const skillTags  = (c.skills || []).slice(0, 4).map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join("");
        const explanation = c.explanation || "";

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="checkbox-col">
                <input type="checkbox" class="ai-result-check" data-name="${escapeHtml(c.candidate_name)}" id="ai-check-${idx}">
            </td>
            <td style="text-align:center; font-weight:700; color:var(--muted);">#${idx + 1}</td>
            <td class="candidate-name-cell" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">${escapeHtml(c.candidate_name)}</td>
            <td class="role-text">${escapeHtml(c.current_role || "Unknown")}</td>
            <td>${c.years_of_experience} yrs</td>
            <td>${escapeHtml(c.uploaded_by || "")}</td>
            <td>
                <div class="ai-score-bar-wrapper">
                    <span class="ai-score-pct" style="color:${scoreColor}">${scorePct}%</span>
                    <div class="ai-score-bar"><div class="ai-score-bar-fill ${scoreClass}" style="width:0%" data-target="${scorePct}%"></div></div>
                </div>
            </td>
            <td>${skillTags}</td>
            <td>
                <div class="actions-cell-wrap" style="display:flex; gap:6px;">
                    <button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">Profile</button>
                    <button type="button" class="btn btn-secondary compact-btn" onclick="triggerSingleCandidateComparison('${escapeHtml(c.candidate_name)}')">Compare</button>
                    <button type="button" class="btn btn-primary compact-btn" onclick="triggerSingleCandidateCv('${escapeHtml(c.candidate_name)}')">Generate CV</button>
                </div>
            </td>`;
        body.appendChild(tr);

        let strengthsHtml = "";
        if (c.strengths && c.strengths.length) {
            strengthsHtml = `<div class="ai-strengths-list" style="margin-top:6px; display:flex; flex-wrap:wrap; gap:4px; align-items:center;">
                <strong style="font-size:11.5px; color:var(--text-primary); margin-right:4px;">Key Strengths:</strong>
                ${c.strengths.slice(0, 4).map(s => `<span class="matching-skill-tag" style="background:var(--primary-light); color:var(--primary); font-size:10.5px; padding: 2px 6px;">${escapeHtml(s)}</span>`).join("")}
            </div>`;
        }

        if (explanation) {
            const expTr = document.createElement("tr");
            expTr.className = "ai-explanation-row";
            expTr.innerHTML = `
                <td colspan="9">
                    <div class="ai-explanation-text" style="display:flex; flex-direction:column; gap:4px;">
                        <div><span class="ai-explanation-icon">✦</span> <strong>Assessment:</strong> ${escapeHtml(explanation)}</div>
                        ${strengthsHtml}
                    </div>
                </td>`;
            body.appendChild(expTr);
        }

        tr.querySelector(".ai-result-check").addEventListener("change", (e) => {
            if (e.target.checked) aiSearchSelectedCandidates.add(c.candidate_name);
            else aiSearchSelectedCandidates.delete(c.candidate_name);
            updateAISelectionActions();
        });
    });

    // Animate score bars
    requestAnimationFrame(() => setTimeout(() => {
        body.querySelectorAll(".ai-score-bar-fill[data-target]").forEach(fill => { fill.style.width = fill.dataset.target; });
    }, 80));
}

function updateAISelectionActions() {
    const count = aiSearchSelectedCandidates.size;
    const compareBtn = document.getElementById("aiCompareBtn");
    const genBtn     = document.getElementById("aiGenerateCvsBtn");
    if (compareBtn) compareBtn.disabled = count < 2;
    if (genBtn)     genBtn.disabled     = count === 0;
}

function clearAISearch() {
    aiSearchActive = false;
    aiSearchSelectedCandidates.clear();
    const input   = document.getElementById("aiTalentSearchInput");
    const panel   = document.getElementById("aiSearchResultsPanel");
    const filters = document.getElementById("aiSearchFilters");
    const body    = document.getElementById("aiResultsBody");
    const checkAll = document.getElementById("checkAllAiResults");
    if (input)   input.value = "";
    if (panel)   panel.hidden = true;
    if (filters) filters.hidden = true;
    if (body)    body.innerHTML = "";
    if (checkAll) checkAll.checked = false;
    updateAISelectionActions();
}

// ═══════════════════════════════════════════════════════
//  JOB DESCRIPTIONS
// ═══════════════════════════════════════════════════════

async function fetchJobDescriptions() {
    const container = document.getElementById("jdsContainer");
    if (!container) return;
    container.innerHTML = `<div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div>`;

    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions`);
        if (!res.ok) throw new Error("Failed to load JDs");
        const jds = await res.json();
        container.innerHTML = "";

        if (jds.length === 0) {
            container.innerHTML = `<p class="empty-state" style="grid-column:1/-1;">No saved job descriptions yet. Click "Add Job Description" to create one.</p>`;
            return;
        }

        jds.forEach(jd => {
            const card = document.createElement("div");
            card.className = "jd-card";
            card.innerHTML = `
                <div class="jd-title-row">
                    <h3>${escapeHtml(jd.title)}</h3>
                    <div class="jd-meta">
                        <span>By: <strong>${escapeHtml(jd.created_by || "—")}</strong></span>
                        <span>${formatToKolkataTime(jd.created_date)}</span>
                    </div>
                    <p class="jd-body-preview">${escapeHtml(jd.description)}</p>
                </div>
                <div class="jd-footer">
                    <span class="jd-matches-count" style="cursor:pointer;" onclick="viewJdMatches(${jd.jd_id}, '${escapeHtml(jd.title)}')">${jd.match_count ?? 0} Matches</span>
                    <div class="jd-actions">
                        <button type="button" class="btn btn-secondary compact-btn" onclick="triggerJdMatch(${jd.jd_id})">Match</button>
                        <button type="button" class="btn btn-secondary compact-btn" onclick="viewJdMatches(${jd.jd_id}, '${escapeHtml(jd.title)}')">View Matches</button>
                        <button type="button" class="btn btn-secondary compact-btn" onclick="copyJobDescription(${jd.jd_id})">Copy Job Description</button>
                        <button type="button" class="btn btn-secondary compact-btn" onclick="duplicateJobDescription(${jd.jd_id})">Duplicate</button>
                        <button type="button" class="btn btn-ghost compact-btn" onclick="editJobDescription(${jd.jd_id})">Edit</button>
                        <button type="button" class="btn btn-danger compact-btn" onclick="deleteJobDescription(${jd.jd_id})">Delete</button>
                    </div>
                </div>`;
            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<p class="empty-state error-text" style="grid-column:1/-1;">Error loading job descriptions: ${e.message}</p>`;
    }
}

// Trigger "Match Candidates" from JD card → navigates to New Recruitment with JD prefilled
async function triggerJdMatch(jdId) {
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}`);
        if (!res.ok) throw new Error("Could not fetch JD");
        const jd = await res.json();

        window.location.hash = "new-recruitment";
        switchView("new-recruitment");

        setTimeout(() => {
            const textarea = document.getElementById("nrJdText");
            const select   = document.getElementById("nrJdSelect");
            if (textarea) textarea.value = jd.description || "";
            if (select) {
                Array.from(select.options).forEach(opt => {
                    if (parseInt(opt.value) === jdId) opt.selected = true;
                });
            }
            nrShowStep(3);
            showMessage(`JD "${jd.title}" loaded — add resumes and rank candidates.`, "info");
        }, 300);
    } catch (e) {
        showMessage(`Failed to load JD: ${e.message}`, "error");
    }
}

function setupJdModal() {
    const addJdBtn = document.getElementById("addJdBtn");
    if (addJdBtn) addJdBtn.addEventListener("click", showJdModal);

    const jdModalCloseBtn = document.getElementById("jdModalCloseBtn");
    if (jdModalCloseBtn) jdModalCloseBtn.addEventListener("click", hideJdModal);

    const jdModalOverlay = document.getElementById("jdModalOverlay");
    if (jdModalOverlay) jdModalOverlay.addEventListener("click", (e) => { if (e.target === jdModalOverlay) hideJdModal(); });

    const jdMatchesModalCloseBtn = document.getElementById("jdMatchesModalCloseBtn");
    if (jdMatchesModalCloseBtn) {
        jdMatchesModalCloseBtn.addEventListener("click", () => {
            const overlay = document.getElementById("jdMatchesModalOverlay");
            if (overlay) overlay.hidden = true;
        });
    }
    const jdMatchesModalOverlay = document.getElementById("jdMatchesModalOverlay");
    if (jdMatchesModalOverlay) {
        jdMatchesModalOverlay.addEventListener("click", (e) => {
            if (e.target === jdMatchesModalOverlay) jdMatchesModalOverlay.hidden = true;
        });
    }

    const extractModalJdBtn = document.getElementById("extractModalJdBtn");
    if (extractModalJdBtn) extractModalJdBtn.addEventListener("click", async () => {
        const fileInput = document.getElementById("jdModalFile");
        const file = fileInput?.files[0];
        if (!file) { showMessage("Please select a file first.", "error"); return; }
        extractModalJdBtn.disabled = true;
        extractModalJdBtn.textContent = "Extracting...";
        try {
            const fd = new FormData();
            fd.append("file", file);
            const res = await authedFetch(`${getApiBase()}/extract-jd-text`, { method: "POST", body: fd });
            if (!res.ok) throw new Error("Extraction failed");
            const data = await res.json();
            const textarea = document.getElementById("jdModalText");
            if (textarea && data.text) textarea.value = data.text;
        } catch (e) {
            showMessage(`Extraction failed: ${e.message}`, "error");
        } finally {
            extractModalJdBtn.disabled = false;
            extractModalJdBtn.textContent = "Extract";
        }
    });

    const jdForm = document.getElementById("jdForm");
    if (jdForm) jdForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const title       = document.getElementById("jdModalRole")?.value.trim();
        const description = document.getElementById("jdModalText")?.value.trim();
        const id          = document.getElementById("jdModalId")?.value;
        if (!title || !description) { showMessage("Please fill in all required fields.", "error"); return; }

        const method = id ? "PUT" : "POST";
        const url    = id ? `${getApiBase()}/api/job-descriptions/${id}` : `${getApiBase()}/api/job-descriptions`;
        try {
            const res = await authedFetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, description })
            });
            if (!res.ok) throw new Error("Failed to save job description");
            hideJdModal();
            showMessage("Job description saved!", "success");
            await fetchJobDescriptions();
        } catch (e) { showMessage(e.message, "error"); }
    });
}

function showJdModal() {
    document.getElementById("jdModalOverlay").hidden = false;
    document.getElementById("jdModalTitle").textContent = "Save Job Description";
    document.getElementById("jdModalId").value = "";
    document.getElementById("jdForm").reset();
}

function hideJdModal() {
    document.getElementById("jdModalOverlay").hidden = true;
    document.getElementById("jdForm").reset();
    document.getElementById("jdModalId").value = "";
}

async function editJobDescription(jdId) {
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}`);
        if (!res.ok) throw new Error("Could not fetch JD data");
        const jd = await res.json();
        document.getElementById("jdModalId").value    = jd.jd_id;
        document.getElementById("jdModalRole").value  = jd.title;
        document.getElementById("jdModalText").value  = jd.description;
        document.getElementById("jdModalTitle").textContent = "Edit Job Description";
        document.getElementById("jdModalOverlay").hidden = false;
    } catch (e) { showMessage(e.message, "error"); }
}

async function deleteJobDescription(jdId) {
    if (!confirm("Are you sure you want to delete this job description?")) return;
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Deletion failed");
        showMessage("Job description deleted.", "info");
        await fetchJobDescriptions();
    } catch (e) { showMessage(e.message, "error"); }
}

// ═══════════════════════════════════════════════════════
//  GENERATED CVS
// ═══════════════════════════════════════════════════════

async function fetchGeneratedCvs() {
    const tbody = document.getElementById("generatedCvsTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state"><div class="spinner" style="margin:0 auto 8px;"></div>Loading...</td></tr>`;

    try {
        const res = await authedFetch(`${getApiBase()}/api/generated-cvs`);
        if (!res.ok) throw new Error("Failed to load CVs");
        const cvs = await res.json();
        tbody.innerHTML = "";

        if (!cvs || cvs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No CVs generated yet. Use New Recruitment to generate client CVs.</td></tr>`;
            return;
        }

        cvs.forEach(cv => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight:600;">${escapeHtml(cv.candidate_name || "—")}</td>
                <td class="role-text">${escapeHtml(cv.jd_title || "—")}</td>
                <td>${escapeHtml(cv.generated_by || "—")}</td>
                <td>${formatToKolkataTime(cv.generated_date)}</td>
                <td>
                    <div class="actions-cell-wrap" style="display:flex; gap:6px;">
                        <button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(cv.candidate_name)}')">Preview</button>
                        <a href="${getApiBase()}/api/generated-cvs/${cv.candidate_id}/download"
                           class="btn btn-secondary compact-btn" download>⬇ Download</a>
                        <button type="button" class="btn btn-danger compact-btn" onclick="deleteGeneratedCv(${cv.candidate_id})">Delete</button>
                    </div>
                </td>`;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state error-text">Error: ${escapeHtml(e.message)}</td></tr>`;
    }
}

// ═══════════════════════════════════════════════════════
//  ANALYTICS
// ═══════════════════════════════════════════════════════

async function fetchAnalytics() {
    try {
        const res = await authedFetch(`${getApiBase()}/api/analytics`);
        if (!res.ok) throw new Error("Analytics failed");
        const data = await res.json();
        renderAnalytics(data);
    } catch (e) {
        console.error("Analytics error:", e);
    }
}

function renderAnalytics(data) {
    renderBarChart("chartExperience", data.experience_distribution || {});
    renderBarChart("chartSkills",     data.skill_distribution     || {});
    renderBarChart("chartRecruiters", data.recruiter_distribution || {});
    renderBarChart("chartTrends",     data.upload_trends          || {});
}

function renderBarChart(containerId, data) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const entries = Object.entries(data).sort(([,a],[,b]) => b - a).slice(0, 10);
    const max = entries.length > 0 ? Math.max(...entries.map(([,v]) => v)) : 1;

    if (entries.length === 0) {
        container.innerHTML = `<p class="empty-state">No data available.</p>`;
        return;
    }

    container.innerHTML = `<div class="bar-chart">${
        entries.map(([label, value]) => {
            const pct = max > 0 ? Math.round((value / max) * 100) : 0;
            return `<div class="bar-item">
                <span class="bar-label" title="${escapeHtml(String(label))}">${escapeHtml(String(label))}</span>
                <div class="bar-track">
                    <div class="bar-fill" style="width:${pct}%">${value > 0 ? value : ""}</div>
                </div>
                <span class="bar-count">${value}</span>
            </div>`;
        }).join("")
    }</div>`;
}

// ═══════════════════════════════════════════════════════
//  CANDIDATE PROFILE DRAWER
// ═══════════════════════════════════════════════════════

async function viewCandidateProfile(candidateName) {
    const drawer = document.getElementById("candidateProfileDrawer");
    if (!drawer) return;
    drawer.hidden = false;

    document.getElementById("drawerCandidateName").textContent = candidateName;

    try {
        const res = await authedFetch(`${getApiBase()}/candidate/${encodeURIComponent(candidateName)}`);
        if (!res.ok) throw new Error("Profile not found");
        const c = await res.json();

        const notAvail = "Not available";

        document.getElementById("drawerCandidateName").textContent = c.candidate_name || candidateName;

        // Sub-title: current role
        const roleEl = document.getElementById("drawerCurrentRole");
        if (roleEl) roleEl.textContent = c.current_role || c.role || "";

        // Contact card
        const yrsEl = document.getElementById("drawerYearsExp");
        if (yrsEl) {
            const yrs = c.years_of_experience ?? c.experience_years ?? null;
            yrsEl.textContent = (yrs !== null && yrs !== "") ? `${yrs} years` : notAvail;
        }
        document.getElementById("drawerEmployeeId").textContent  = c.employee_id  || notAvail;
        document.getElementById("drawerEmail").textContent       = c.email        || notAvail;
        document.getElementById("drawerPhone").textContent       = c.phone        || notAvail;
        const locEl = document.getElementById("drawerLocation");
        if (locEl) locEl.textContent = c.location || notAvail;
        document.getElementById("drawerUploaderName").textContent = c.uploaded_by || notAvail;

        const linkedinEl = document.getElementById("drawerLinkedIn");
        if (linkedinEl) {
            const linkedin = c.linkedin || "";
            if (linkedin) {
                const url = linkedin.startsWith("http") ? linkedin : `https://linkedin.com/in/${linkedin}`;
                linkedinEl.innerHTML = `<a href="${escapeHtml(url)}" target="_blank" style="color:var(--accent); text-decoration:underline;">${escapeHtml(linkedin)}</a>`;
            } else {
                linkedinEl.textContent = notAvail;
            }
        }

        const githubEl = document.getElementById("drawerGitHub");
        if (githubEl) {
            const github = c.github || "";
            if (github) {
                const url = github.startsWith("http") ? github : `https://github.com/${github}`;
                githubEl.innerHTML = `<a href="${escapeHtml(url)}" target="_blank" style="color:var(--accent); text-decoration:underline;">${escapeHtml(github)}</a>`;
            } else {
                githubEl.textContent = notAvail;
            }
        }

        document.getElementById("drawerResumeName").textContent  = c.resume_filename || c.filename || notAvail;

        const downloadLink = document.getElementById("drawerResumeDownloadLink");
        if (downloadLink) downloadLink.href = c.resume_url || "#";

        // About / Summary
        document.getElementById("drawerAbout").textContent = c.professional_summary || c.about_candidate || c.about || "No summary available.";

        // Education
        const educationContainer = document.getElementById("drawerEducation");
        if (educationContainer) {
            const edu = c.education || [];
            educationContainer.innerHTML = edu.length === 0 ? "<p class='empty-state'>No education data.</p>" :
                edu.map(e => `
                    <div class="education-item" style="border-left:2px solid var(--border); padding-left:12px; margin-bottom:8px;">
                        <div style="font-weight:600; color:var(--text-primary); font-size:13px;">${escapeHtml(e.degree || "—")}</div>
                        <div style="color:var(--text-secondary); font-size:12.5px;">${escapeHtml(e.institution || "—")}</div>
                        <div style="color:var(--text-muted); font-size:11.5px;">${escapeHtml(e.start_year || "—")} – ${escapeHtml(e.end_year || "—")}</div>
                    </div>`).join("");
        }

        // Experience timeline
        const timeline = document.getElementById("drawerExperienceTimeline");
        if (timeline) {
            const exp = c.work_experience || c.experience || [];
            timeline.innerHTML = exp.length === 0 ? "<p class='empty-state'>No experience data.</p>" :
                exp.map(e => `
                    <div class="timeline-item">
                        <div class="timeline-dot"></div>
                        <div class="timeline-content">
                            <div class="timeline-role">${escapeHtml(e.title || e.role || "—")}</div>
                            <div class="timeline-company">${escapeHtml(e.company || "—")}</div>
                            <div class="timeline-duration">${escapeHtml(e.duration || e.dates || "—")}</div>
                        </div>
                    </div>`).join("");
        }

        // Skills
        const skillsContainer = document.getElementById("drawerSkillsTags");
        if (skillsContainer) {
            const skills = c.skills || c.key_skills || [];
            skillsContainer.innerHTML = skills.length === 0 ? "<p class='empty-state'>No skills listed.</p>" :
                skills.map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join("");
        }

        // Projects
        const projectsList = document.getElementById("drawerProjectsList");
        if (projectsList) {
            const projs = c.projects || [];
            projectsList.innerHTML = projs.length === 0 ? "<p class='empty-state'>No projects listed.</p>" :
                projs.map(p => `
                    <div class="project-item">
                        <div class="project-name">${escapeHtml(p.name || p.title || "Project")}</div>
                        <div class="project-desc">${escapeHtml(p.description || "")}</div>
                    </div>`).join("");
        }

        // Reset to first tab
        switchDrawerTab("tab-summary");

    } catch (e) {
        document.getElementById("drawerAbout").textContent = `Could not load profile: ${e.message}`;
    }
}


function switchDrawerTab(tabId) {
    document.querySelectorAll(".drawer-tab").forEach(t => t.classList.toggle("active", t.getAttribute("data-tab") === tabId));
    document.querySelectorAll(".drawer-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
}

// ═══════════════════════════════════════════════════════
//  CANDIDATE COMPARISON
// ═══════════════════════════════════════════════════════

async function triggerCandidatesComparison(selectedSet, jdText) {
    const overlay = document.getElementById("candidateComparisonOverlay");
    const body    = document.getElementById("comparisonOverlayBody");
    if (!overlay || !body) return;

    if (selectedSet.size < 2) {
        showMessage("Select at least 2 candidates to compare.", "error");
        return;
    }

    body.innerHTML = `<div class="spinner" style="margin:40px auto;"></div><p style="text-align:center;">Compiling comparison...</p>`;
    overlay.hidden = false;

    try {
        const names = Array.from(selectedSet);
        const res = await authedFetch(`${getApiBase()}/compare-candidates`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ candidate_names: names, jd: jdText || "General Profile Comparison" })
        });

        if (!res.ok) throw new Error("Comparison service failed");
        const data = await res.json();
        const results = data.results || [];

        if (results.length === 0) {
            body.innerHTML = `<div class="empty-state">No comparison details returned.</div>`;
            return;
        }

        let table = `<table class="comparison-overlay-table"><thead><tr><th style="width:160px;">Category</th>`;
        results.forEach(c => { table += `<th class="comparison-candidate-header">${escapeHtml(c.candidate_name)}</th>`; });
        table += `</tr></thead><tbody>`;

        const addRow = (label, fn) => {
            table += `<tr><td><strong>${label}</strong></td>`;
            results.forEach(c => { table += `<td>${fn(c)}</td>`; });
            table += `</tr>`;
        };

        const bulletList = (items, escape = true) => {
            if (!items || !items.length) return `<span style="color:var(--muted); font-size:12px;">—</span>`;
            return `<ul class="comparison-bullet-list">${items.slice(0, 8).map(i => `<li>${escape ? escapeHtml(String(i)) : String(i)}</li>`).join("")}</ul>`;
        };

        addRow("Match Score", c => {
            const score = Math.round(c.match_score || 0);
            const cls   = score >= 75 ? "high" : score >= 45 ? "medium" : "low";
            return `<span class="score-badge ${cls}">${score}%</span>`;
        });
        addRow("Experience", c => `${c.years_of_experience ?? "—"} yrs`);
        addRow("Current Role", c => escapeHtml(c.current_role || "—"));
        addRow("Education", c => {
            const eduList = (c.education || []).map(e => `<strong>${escapeHtml(e.degree || '—')}</strong><br>${escapeHtml(e.institution || '—')} (${escapeHtml(e.start_year || '?')} - ${escapeHtml(e.end_year || '?')})`);
            return bulletList(eduList, false);
        });
        addRow("Skills", c => bulletList(c.key_skills || c.skills, true));
        addRow("Strengths", c => bulletList(c.strengths, true));
        addRow("Assessment", c => escapeHtml(c.about_candidate || c.assessment || "—"));
        addRow("Projects", c => {
            const projList = (c.projects || []).map(p => `<strong>${escapeHtml(p.name || '—')}</strong>: ${escapeHtml(p.description || '—')} ${p.technologies && p.technologies.length ? `<br><em style="font-size:11px; color:var(--primary);">Tech: ${p.technologies.join(", ")}</em>` : ""}`);
            return bulletList(projList, false);
        });

        table += `</tbody></table>`;
        body.innerHTML = `<div style="overflow-x:auto; padding:4px;">${table}</div>`;

        document.getElementById("comparisonSubTitle").textContent = `Comparing ${names.length} candidates`;

    } catch (e) {
        body.innerHTML = `<div class="empty-state error-text">Comparison failed: ${escapeHtml(e.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════
//  CV GENERATION (with ZIP download)
// ═══════════════════════════════════════════════════════

async function triggerCVsZipDownload(names, jdText, triggerBtn) {
    if (!names || names.length === 0) { showMessage("Select at least one candidate.", "error"); return; }
    if (triggerBtn) { triggerBtn.disabled = true; triggerBtn.textContent = "Generating..."; }

    try {
        const res = await authedFetch(`${getApiBase()}/generate-selected-cvs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ candidate_names: names, jd: jdText || "General Profile" })
        });

        if (!res.ok) throw new Error(await res.text() || "Generation failed");
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement("a");
        a.href     = url;
        a.download = `CVs_${new Date().toISOString().slice(0,10)}.zip`;
        a.click();
        URL.revokeObjectURL(url);
        showMessage(`${names.length} CV(s) generated and downloading...`, "success");
        await fetchGeneratedCvs();

    } catch (e) {
        showMessage(`CV generation failed: ${e.message}`, "error");
    } finally {
        if (triggerBtn) { triggerBtn.disabled = false; triggerBtn.textContent = "Generate CVs"; }
    }
}

// ═══════════════════════════════════════════════════════
//  PAGINATION
// ═══════════════════════════════════════════════════════

function renderPagination(state, paginationEl, fetchFunc) {
    if (!paginationEl) return;
    const { page, limit, total } = state;
    const totalPages = Math.ceil(total / limit);
    const start = (page - 1) * limit + 1;
    const end   = Math.min(page * limit, total);

    const infoEl   = paginationEl.querySelector(".pagination-info");
    const prevBtn  = paginationEl.querySelector(".prev-btn");
    const nextBtn  = paginationEl.querySelector(".next-btn");

    if (infoEl)  infoEl.textContent = total > 0 ? `Showing ${start}–${end} of ${total}` : "No results";
    if (prevBtn) { prevBtn.disabled = page <= 1; prevBtn.onclick = () => { state.page--; fetchFunc(); }; }
    if (nextBtn) { nextBtn.disabled = page >= totalPages; nextBtn.onclick = () => { state.page++; fetchFunc(); }; }
}

// ═══════════════════════════════════════════════════════
//  SETTINGS — CHANGE PASSWORD
// ═══════════════════════════════════════════════════════

function setupChangePassword() {
    const form = document.getElementById("changePasswordForm");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const oldPw  = document.getElementById("oldPassword")?.value;
        const newPw  = document.getElementById("newPassword")?.value;
        const confPw = document.getElementById("confirmPassword")?.value;

        if (newPw !== confPw) { showMessage("New passwords do not match.", "error"); return; }

        const btn = document.getElementById("changePasswordBtn");
        if (btn) btn.disabled = true;

        try {
            const res = await authedFetch(`${getApiBase()}/api/change-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ old_password: oldPw, new_password: newPw })
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Password change failed");
            }
            showMessage("Password updated successfully.", "success");
            form.reset();
        } catch (e) {
            showMessage(e.message, "error");
        } finally {
            if (btn) btn.disabled = false;
        }
    });
}

// ═══════════════════════════════════════════════════════
//  LOGOUT
// ═══════════════════════════════════════════════════════

async function handleLogoutClick() {
    try {
        await authedFetch(`${getApiBase()}/logout`, { method: "POST" });
    } catch (e) { console.error("Logout request failed:", e); }
    localStorage.removeItem("access_token");
    localStorage.removeItem("username");
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("username");
    window.location.href = "/login";
}

// ─── Single Row Candidate Actions (Rankings / Pool / Search) ──────────────────────────

function triggerSingleCandidateComparison(name) {
    const jdText = document.getElementById("nrJdText")?.value || "";
    triggerCandidatesComparison(new Set([name]), jdText);
}

function triggerSingleCandidateCv(name) {
    const jdText = document.getElementById("nrJdText")?.value || "";
    const singleSet = [name];
    
    // Switch to step 5 (CV generation step) visually
    const step5 = document.getElementById("nrStep5");
    if (step5) step5.style.display = "";
    nrShowStep(5);
    
    const countEl = document.getElementById("nrGenerateCount");
    if (countEl) countEl.textContent = "1";
    
    const progress = document.getElementById("nrGenerateProgress");
    const result = document.getElementById("nrGenerateResult");
    if (progress) progress.style.display = "flex";
    if (result) result.style.display = "none";
    
    triggerCVsZipDownload(singleSet, jdText, null).then(() => {
        if (progress) progress.style.display = "none";
        if (result) result.style.display = "block";
    }).catch(e => {
        if (progress) progress.style.display = "none";
        showMessage(`Generation failed: ${e.message}`, "error");
    });
}

// ─── Job Description Duplication & Matches Modal ──────────────────────────

async function duplicateJobDescription(jdId) {
    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}`);
        if (!res.ok) throw new Error("Could not fetch JD data to duplicate");
        const jd = await res.json();

        showJdModal();
        const roleInput = document.getElementById("jdModalRole");
        const textInput = document.getElementById("jdModalText");
        const idInput = document.getElementById("jdModalId");
        
        if (roleInput) roleInput.value = `${jd.title} (Copy)`;
        if (textInput) textInput.value = jd.description || "";
        if (idInput) idInput.value = ""; // Create new entry
        
        document.getElementById("jdModalTitle").textContent = "Duplicate Job Description";
        showMessage(`Duplicating "${jd.title}" — edit details and save.`, "info");
    } catch (e) {
        showMessage(`Failed to duplicate: ${e.message}`, "error");
    }
}

async function viewJdMatches(jdId, jdTitle) {
    const modal = document.getElementById("jdMatchesModalOverlay");
    const body = document.getElementById("jdMatchesModalBody");
    const title = document.getElementById("jdMatchesModalTitle");
    if (!modal || !body) return;

    if (title) title.textContent = `Top Matches — ${jdTitle}`;
    body.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="spinner" style="margin:0 auto 8px;"></div>Finding matching candidates...</td></tr>`;
    modal.hidden = false;

    try {
        const res = await authedFetch(`${getApiBase()}/api/job-descriptions/${jdId}/matches`);
        if (!res.ok) throw new Error("Failed to fetch matches");
        const results = await res.json();

        if (!results || results.length === 0) {
            body.innerHTML = `<tr><td colspan="7" class="empty-state">No matching candidates in the pool yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";
        results.slice(0, 15).forEach(c => {
            const score = Math.round(c.score || 0);
            const scoreClass = score >= 75 ? "high" : score >= 45 ? "medium" : "low";
            const skills = (c.matching_skills || []).slice(0, 4).map(s => `<span class="matching-skill-tag">${escapeHtml(s)}</span>`).join("");
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="candidate-name-cell" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">${escapeHtml(c.candidate_name)}</td>
                <td>${escapeHtml(c.current_role || "—")}</td>
                <td>${c.years_of_experience} yrs</td>
                <td><span class="score-badge ${scoreClass}">${score}%</span></td>
                <td>${escapeHtml(c.uploaded_by || "—")}</td>
                <td>${skills || "—"}</td>
                <td>
                    <button type="button" class="btn btn-secondary compact-btn" onclick="viewCandidateProfile('${escapeHtml(c.candidate_name)}')">Profile</button>
                </td>
            `;
            body.appendChild(tr);
        });
    } catch (e) {
        body.innerHTML = `<tr><td colspan="7" class="empty-state error-text">Error loading matches: ${escapeHtml(e.message)}</td></tr>`;
    }
}

// ─── Generated CV Actions ──────────────────────────

async function deleteGeneratedCv(candidateId) {
    if (!confirm("Are you sure you want to permanently delete this generated CV? The candidate profile will remain, but the formatted client CV will be deleted.")) return;
    try {
        const res = await authedFetch(`${getApiBase()}/api/generated-cvs/${candidateId}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Failed to delete generated CV");
        showMessage("Generated CV deleted successfully.", "info");
        await fetchGeneratedCvs();
    } catch (e) {
        showMessage(`Delete failed: ${e.message}`, "error");
    }
}
