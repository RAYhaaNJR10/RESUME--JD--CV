// STATE MANAGEMENT
const state = {
    totalCandidates: 0,
    candidatesList: [],
    selectedCandidates: new Set(),
    activeTemplate: { active: false, filename: null },
    currentJdText: '',
    jdTab: 'text' // 'text' or 'upload'
};

const API_BASE = window.location.origin;

// DOM ELEMENTS
const resumesDropzone = document.getElementById('resumes-dropzone');
const resumesInput = document.getElementById('resumes-input');
const resumesStatus = document.getElementById('resumes-status');
const indexedCountLabel = document.getElementById('indexed-count');
const uploadList = document.getElementById('upload-list');

const templateDropzone = document.getElementById('template-dropzone');
const templateInput = document.getElementById('template-input');
const templateStatus = document.getElementById('template-status');
const activeTemplateName = document.getElementById('active-template-name');
const activeTemplateDate = document.getElementById('active-template-date');
const deleteTemplateBtn = document.getElementById('delete-template-btn');

const jdTabs = document.querySelectorAll('.jd-tab');
const jdTextContainer = document.getElementById('jd-text-container');
const jdUploadContainer = document.getElementById('jd-upload-container');
const jdTextarea = document.getElementById('jd-textarea');
const jdDropzone = document.getElementById('jd-dropzone');
const jdInput = document.getElementById('jd-input');

const statTotalCandidates = document.getElementById('stat-total-candidates');
const statSelectedCount = document.getElementById('stat-selected-count');

const rankBtn = document.getElementById('rank-btn');
const compareBtn = document.getElementById('compare-btn');
const generateCvsBtn = document.getElementById('generate-cvs-btn');

const emptyState = document.getElementById('empty-state');
const candidatesContainer = document.getElementById('candidates-container');
const candidatesTbody = document.getElementById('candidates-tbody');
const masterCheckbox = document.getElementById('master-checkbox');
const selectAllBtn = document.getElementById('select-all-btn');
const matchingSummary = document.getElementById('matching-summary');

const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');

const candidateModal = document.getElementById('candidate-modal');
const closeCandidateModal = document.getElementById('close-candidate-modal');
const modalCandidateAvatar = document.getElementById('modal-candidate-avatar');
const modalCandidateName = document.getElementById('modal-candidate-name');
const modalCandidateRole = document.getElementById('modal-candidate-role');
const profileDetailsContent = document.getElementById('profile-details-content');

const comparisonModal = document.getElementById('comparison-modal');
const closeComparisonModal = document.getElementById('close-comparison-modal');
const comparisonThead = document.getElementById('comparison-thead');
const comparisonTbody = document.getElementById('comparison-tbody');

const toastContainer = document.getElementById('toast-container');

// INITIALIZATION
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    // 1. Fetch active template
    fetchActiveTemplate();

    // 2. Fetch candidates list count
    fetchTotalCandidatesCount();

    // 3. Register Drag & Drop events
    setupDragAndDrop(resumesDropzone, resumesInput, handleResumesUpload);
    setupDragAndDrop(templateDropzone, templateInput, handleTemplateUpload);
    setupDragAndDrop(jdDropzone, jdInput, handleJdUpload);

    // 4. Register Action Buttons & Tab listeners
    setupJdTabs();
    setupActions();
    setupModals();
}

// TOAST NOTIFICATIONS
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'fa-circle-info';
    if (type === 'success') icon = 'fa-circle-check';
    if (type === 'error') icon = 'fa-circle-xmark';
    if (type === 'warning') icon = 'fa-circle-exclamation';

    toast.innerHTML = `
        <i class="fa-solid ${icon}"></i>
        <div>${message}</div>
    `;

    toastContainer.appendChild(toast);
    
    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);
    
    // Remove after 4s
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// LOADING OVERLAY CONTROLLER
function showLoading(text = 'Processing...') {
    loadingText.innerText = text;
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

// API: FETCH ACTIVE TEMPLATE
async function fetchActiveTemplate() {
    try {
        const response = await fetch(`${API_BASE}/active-template`);
        const data = await response.json();
        updateTemplateUI(data);
    } catch (error) {
        console.error('Error fetching active template:', error);
        showToast('Failed to check active template.', 'error');
    }
}

// API: FETCH TOTAL CANDIDATES
async function fetchTotalCandidatesCount() {
    try {
        const response = await fetch(`${API_BASE}/candidates`);
        const data = await response.json();
        state.totalCandidates = data.length;
        statTotalCandidates.innerText = state.totalCandidates;
        indexedCountLabel.innerText = `${state.totalCandidates} candidates`;
    } catch (error) {
        console.error('Error fetching candidates:', error);
    }
}

// UPDATE TEMPLATE UI
function updateTemplateUI(data) {
    state.activeTemplate = data;
    if (data && data.active) {
        activeTemplateName.innerText = data.filename;
        const uploadDate = data.uploaded_at ? new Date(data.uploaded_at).toLocaleString() : 'Recruiter template';
        activeTemplateDate.innerText = `Uploaded at: ${uploadDate}`;
        deleteTemplateBtn.style.display = 'block';
        statTotalCandidates.parentElement.parentElement.classList.add('template-active'); // style helper if needed
    } else {
        activeTemplateName.innerText = 'Default CV Format';
        activeTemplateDate.innerText = 'Using built-in styling';
        deleteTemplateBtn.style.display = 'none';
    }
}

// DRAG AND DROP UTILITY
function setupDragAndDrop(dropzoneEl, inputEl, uploadCallback) {
    // Click dropzone to trigger input
    dropzoneEl.addEventListener('click', () => inputEl.click());

    inputEl.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadCallback(e.target.files);
            inputEl.value = ''; // Reset input
        }
    });

    // Drag-over highlights
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzoneEl.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzoneEl.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzoneEl.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzoneEl.classList.remove('dragover');
        }, false);
    });

    dropzoneEl.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            uploadCallback(files);
        }
    });
}

// HANDLER: RESUMES UPLOAD
async function handleResumesUpload(files) {
    const formData = new FormData();
    let validFilesCount = 0;
    
    // Clear list of previous uploads
    uploadList.innerHTML = '';
    resumesStatus.style.display = 'block';

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const ext = file.name.split('.').pop().toLowerCase();
        
        const item = document.createElement('li');
        item.className = 'upload-item';
        item.innerHTML = `
            <span class="upload-item-name" title="${file.name}">${file.name}</span>
            <span class="upload-item-status status-parsing" id="upload-item-${i}">
                <i class="fa-solid fa-spinner fa-spin"></i> Parsing
            </span>
        `;
        uploadList.appendChild(item);

        if (ext === 'pdf' || ext === 'docx') {
            formData.append('files', file);
            validFilesCount++;
        } else {
            const statusEl = document.getElementById(`upload-item-${i}`);
            statusEl.className = 'upload-item-status status-failed';
            statusEl.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Format`;
        }
    }

    if (validFilesCount === 0) {
        showToast('No valid PDF or DOCX files selected.', 'warning');
        return;
    }

    showLoading('Parsing resumes & updating FAISS index...');

    try {
        const response = await fetch(`${API_BASE}/upload-resumes`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        // Update items status based on api response
        const successfulNames = data.uploaded.map(u => u.filename);
        const failedMap = {};
        data.failed.forEach(f => { failedMap[f.filename] = f.error; });

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const statusEl = document.getElementById(`upload-item-${i}`);
            if (!statusEl) continue;

            if (successfulNames.includes(file.name)) {
                statusEl.className = 'upload-item-status status-success';
                statusEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> Success`;
            } else if (file.name in failedMap) {
                statusEl.className = 'upload-item-status status-failed';
                statusEl.innerHTML = `<i class="fa-solid fa-circle-xmark" title="${failedMap[file.name]}"></i> Failed`;
            }
        }

        fetchTotalCandidatesCount();

        if (data.total_successful > 0) {
            showToast(`Parsed & indexed ${data.total_successful} resumes successfully!`, 'success');
        }
        if (data.total_failed > 0) {
            showToast(`Failed to parse ${data.total_failed} resumes.`, 'error');
        }

    } catch (error) {
        console.error('Error uploading resumes:', error);
        showToast('Server error while uploading resumes.', 'error');
        
        // Mark all active spinners as failed
        const activeSpinners = uploadList.querySelectorAll('.status-parsing');
        activeSpinners.forEach(s => {
            s.className = 'upload-item-status status-failed';
            s.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Error`;
        });
    } finally {
        hideLoading();
    }
}

// HANDLER: TEMPLATE UPLOAD
async function handleTemplateUpload(files) {
    if (files.length === 0) return;
    const file = files[0];
    const ext = file.name.split('.').pop().toLowerCase();
    
    if (ext !== 'docx') {
        showToast('CV template must be a DOCX file.', 'warning');
        return;
    }

    showLoading('Uploading template...');
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/upload-template`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            showToast('Recruiter CV template uploaded successfully!', 'success');
            fetchActiveTemplate();
        } else {
            showToast('Failed to upload CV template.', 'error');
        }
    } catch (error) {
        console.error('Error uploading template:', error);
        showToast('Server error uploading template.', 'error');
    } finally {
        hideLoading();
    }
}

// HANDLER: DELETE TEMPLATE
async function handleDeleteTemplate() {
    showLoading('Resetting template...');
    try {
        const response = await fetch(`${API_BASE}/active-template`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (data.status === 'success') {
            showToast('Template reset. Using default CV format.', 'info');
            fetchActiveTemplate();
        }
    } catch (error) {
        console.error('Error deleting template:', error);
        showToast('Failed to reset template.', 'error');
    } finally {
        hideLoading();
    }
}

// HANDLER: JD TABS
function setupJdTabs() {
    jdTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            jdTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const tabName = tab.getAttribute('data-tab');
            state.jdTab = tabName;

            if (tabName === 'text') {
                jdTextContainer.classList.add('active');
                jdUploadContainer.classList.remove('active');
            } else {
                jdTextContainer.classList.remove('active');
                jdUploadContainer.classList.add('active');
            }
        });
    });
}

// HANDLER: JD FILE UPLOAD
async function handleJdUpload(files) {
    if (files.length === 0) return;
    const file = files[0];
    showLoading('Extracting JD text...');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/upload-jd`, {
            method: 'POST',
            body: formData
        });
        
        if (response.status === 200) {
            const extractedText = await response.text();
            jdTextarea.value = extractedText;
            state.currentJdText = extractedText;
            
            // Switch tab to text area automatically to show user the text
            const textTab = document.querySelector('[data-tab="text"]');
            if (textTab) textTab.click();

            showToast('Job description file parsed successfully!', 'success');
        } else {
            const err = await response.json();
            showToast(err.detail || 'Failed to parse JD file.', 'error');
        }
    } catch (error) {
        console.error('Error parsing JD file:', error);
        showToast('Error uploading JD file.', 'error');
    } finally {
        hideLoading();
    }
}

// ACTION BUTTON EVENTS
function setupActions() {
    // 1. Rank Candidates
    rankBtn.addEventListener('click', () => {
        state.currentJdText = jdTextarea.value.trim();
        if (!state.currentJdText) {
            showToast('Please paste a Job Description or upload a JD file first.', 'warning');
            return;
        }
        rankCandidates(state.currentJdText);
    });

    // 2. Compare Candidates
    compareBtn.addEventListener('click', () => {
        if (state.selectedCandidates.size < 2) {
            showToast('Please select at least 2 candidates to compare.', 'warning');
            return;
        }
        compareCandidates();
    });

    // 3. Generate Selected CVs
    generateCvsBtn.addEventListener('click', () => {
        if (state.selectedCandidates.size === 0) {
            showToast('Please select at least 1 candidate to generate CVs.', 'warning');
            return;
        }
        generateSelectedCvs();
    });

    // 4. Delete Template
    deleteTemplateBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDeleteTemplate();
    });

    // 5. Select All checkbox logic
    masterCheckbox.addEventListener('change', (e) => {
        const checkBoxes = candidatesTbody.querySelectorAll('.cand-checkbox');
        const checked = e.target.checked;
        
        checkBoxes.forEach(cb => {
            cb.checked = checked;
            const name = cb.getAttribute('data-name');
            if (checked) {
                state.selectedCandidates.add(name);
            } else {
                state.selectedCandidates.delete(name);
            }
        });

        updateSelectionState();
    });

    selectAllBtn.addEventListener('click', () => {
        const checkBoxes = candidatesTbody.querySelectorAll('.cand-checkbox');
        checkBoxes.forEach(cb => {
            cb.checked = true;
            state.selectedCandidates.add(cb.getAttribute('data-name'));
        });
        masterCheckbox.checked = true;
        updateSelectionState();
    });
}

// API: RANK CANDIDATES
async function rankCandidates(jdText) {
    showLoading('Ranking candidates semantically using FAISS...');
    state.selectedCandidates.clear();
    masterCheckbox.checked = false;
    updateSelectionState();

    try {
        const response = await fetch(`${API_BASE}/rank-candidates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jd: jdText })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to rank candidates');
        }

        const data = await response.json();
        state.candidatesList = data.results;

        renderCandidatesTable();
        matchingSummary.innerText = `Matched ${data.count} candidates against the JD.`;
        showToast(`Success! Found and ranked ${data.count} candidates.`, 'success');
    } catch (error) {
        console.error('Error ranking candidates:', error);
        showToast(error.message || 'Error scoring candidates.', 'error');
    } finally {
        hideLoading();
    }
}

// RENDER CANDIDATES TABLE
function renderCandidatesTable() {
    candidatesTbody.innerHTML = '';
    
    if (!state.candidatesList || state.candidatesList.length === 0) {
        emptyState.style.display = 'flex';
        candidatesContainer.style.display = 'none';
        selectAllBtn.style.display = 'none';
        return;
    }

    emptyState.style.display = 'none';
    candidatesContainer.style.display = 'block';
    selectAllBtn.style.display = 'inline-block';

    state.candidatesList.forEach(cand => {
        const name = cand.candidate_name;
        const initial = name ? name.charAt(0).toUpperCase() : 'C';
        const score = Math.round(cand.score * 100);
        
        let scoreClass = 'score-poor';
        if (score >= 80) scoreClass = 'score-excellent';
        else if (score >= 50) scoreClass = 'score-good';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <input type="checkbox" class="cand-checkbox" data-name="${name}" ${state.selectedCandidates.has(name) ? 'checked' : ''}>
            </td>
            <td>
                <div class="candidate-name-cell">
                    <div class="avatar-placeholder">${initial}</div>
                    <div>
                        <span class="candidate-meta-name">${name}</span>
                        <span class="candidate-meta-file">${cand.resume_filename || ''}</span>
                    </div>
                </div>
            </td>
            <td>${cand.current_role || 'Not Specified'}</td>
            <td>
                <span class="exp-badge">Calculating...</span>
            </td>
            <td style="text-align: right;">
                <span class="score-badge ${scoreClass}">${score}% Match</span>
            </td>
            <td style="text-align: center;">
                <button class="action-view-btn" data-name="${name}">
                    <i class="fa-regular fa-folder-open"></i> Profile
                </button>
            </td>
        `;

        // We fetch the candidate detail to get actual years of experience dynamically!
        // To avoid making N API calls sequentially in JS, we can pull it asynchronously.
        // Let's implement dynamic experience retrieval:
        fetchCandidateSummaryDetails(name, row.querySelector('.exp-badge'));

        // Register checkbox listener
        row.querySelector('.cand-checkbox').addEventListener('change', (e) => {
            if (e.target.checked) {
                state.selectedCandidates.add(name);
            } else {
                state.selectedCandidates.delete(name);
            }
            updateMasterCheckboxState();
            updateSelectionState();
        });

        // Register view profile listener
        row.querySelector('.action-view-btn').addEventListener('click', () => {
            viewCandidateProfile(name);
        });

        candidatesTbody.appendChild(row);
    });
}

// FETCH EXPERIENCE DETAIL DYNAMICALLY
async function fetchCandidateSummaryDetails(name, badgeEl) {
    try {
        const response = await fetch(`${API_BASE}/candidate/${encodeURIComponent(name)}`);
        if (response.ok) {
            const data = await response.json();
            const y = data.years_of_experience || 0;
            badgeEl.innerText = `${y} yr${y !== 1 ? 's' : ''} exp`;
        } else {
            badgeEl.innerText = 'N/A';
        }
    } catch (e) {
        badgeEl.innerText = 'N/A';
    }
}

// UPDATE SELECTION COUNT AND BUTTON STATES
function updateSelectionState() {
    const size = state.selectedCandidates.size;
    statSelectedCount.innerText = size;

    // Toggle Rank/Compare/Generate button active states
    if (size >= 2) {
        compareBtn.removeAttribute('disabled');
    } else {
        compareBtn.setAttribute('disabled', 'true');
    }

    if (size >= 1) {
        generateCvsBtn.removeAttribute('disabled');
    } else {
        generateCvsBtn.setAttribute('disabled', 'true');
    }
}

function updateMasterCheckboxState() {
    const checkboxes = candidatesTbody.querySelectorAll('.cand-checkbox');
    if (checkboxes.length === 0) {
        masterCheckbox.checked = false;
        return;
    }
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    masterCheckbox.checked = allChecked;
}

// API: VIEW CANDIDATE PROFILE DETAILS
async function viewCandidateProfile(name) {
    showLoading(`Loading ${name}'s profile...`);
    try {
        const response = await fetch(`${API_BASE}/candidate/${encodeURIComponent(name)}`);
        if (!response.ok) throw new Error('Candidate details not found');
        const data = await response.json();
        
        // Populate modal details
        modalCandidateAvatar.innerText = name.charAt(0).toUpperCase();
        modalCandidateName.innerText = data.candidate_name || name;
        modalCandidateRole.innerText = data.current_role || 'Not Specified';

        renderProfileDetails(data);
        
        // Show modal
        candidateModal.classList.add('active');
    } catch (error) {
        console.error('Error loading candidate detail:', error);
        showToast('Error loading candidate profile details.', 'error');
    } finally {
        hideLoading();
    }
}

// RENDER PROFILE IN MODAL
function renderProfileDetails(data) {
    let html = '';

    // Summary stats
    html += `
        <div class="profile-section">
            <h3>Overview</h3>
            <div class="profile-grid-2">
                <div class="profile-item">
                    <label>Years of Experience</label>
                    <span>${data.years_of_experience || 0} Years</span>
                </div>
                <div class="profile-item">
                    <label>Profile Match Term</label>
                    <span>${data.resume_filename || 'Parsed Raw Resume'}</span>
                </div>
            </div>
        </div>
    `;

    // Core Skills
    if (data.skills && data.skills.length > 0) {
        html += `
            <div class="profile-section">
                <h3>Technical & Core Skills</h3>
                <div class="pills-container">
                    ${data.skills.map(s => `<span class="pill">${s}</span>`).join('')}
                </div>
            </div>
        `;
    }

    // Domains
    if (data.domains && data.domains.length > 0) {
        html += `
            <div class="profile-section">
                <h3>Domain Focus</h3>
                <div class="pills-container">
                    ${data.domains.map(d => `<span class="pill">${d}</span>`).join('')}
                </div>
            </div>
        `;
    }

    // Professional Experience
    if (data.experience && data.experience.length > 0) {
        html += `
            <div class="profile-section">
                <h3>Professional Experience</h3>
                <div class="profile-card-list">
                    ${data.experience.map(exp => `
                        <div class="profile-subcard">
                            <div class="subcard-header">
                                <span class="subcard-title">${exp.company || 'Company'}</span>
                                <span class="subcard-meta">${exp.start_date || ''} - ${exp.end_date || 'Present'}</span>
                            </div>
                            <div class="subcard-subtitle">${exp.role || 'Role'} ${exp.project ? `| Project: ${exp.project}` : ''}</div>
                            ${exp.technologies && exp.technologies.length > 0 ? `
                                <div style="margin-top: 6px; margin-bottom: 8px;">
                                    ${exp.technologies.map(t => `<span class="badge badge-accent" style="margin-right: 4px; font-size: 0.65rem;">${t}</span>`).join('')}
                                </div>
                            ` : ''}
                            ${exp.responsibilities && exp.responsibilities.length > 0 ? `
                                <ul class="subcard-list">
                                    ${exp.responsibilities.map(r => `<li>${r}</li>`).join('')}
                                </ul>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Projects
    if (data.projects && data.projects.length > 0) {
        html += `
            <div class="profile-section">
                <h3>Projects</h3>
                <div class="profile-card-list">
                    ${data.projects.map(proj => `
                        <div class="profile-subcard">
                            <div class="subcard-title">${proj.name || 'Project Name'}</div>
                            <p class="subcard-text" style="margin-top: 6px;">${proj.description || ''}</p>
                            ${proj.technologies && proj.technologies.length > 0 ? `
                                <div>
                                    ${proj.technologies.map(t => `<span class="pill">${t}</span>`).join('')}
                                </div>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Education
    if (data.education && data.education.length > 0) {
        html += `
            <div class="profile-section">
                <h3>Education</h3>
                <div class="profile-card-list">
                    ${data.education.map(edu => `
                        <div class="profile-subcard">
                            <div class="subcard-title">${edu.degree || 'Degree'}</div>
                            <div class="subcard-subtitle">${edu.institution || 'Institution'}</div>
                            <span class="subcard-meta">${edu.start_year || ''} - ${edu.end_year || ''}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    profileDetailsContent.innerHTML = html;
}

// API: COMPARE SELECTED CANDIDATES
async function compareCandidates() {
    showLoading('Generating side-by-side comparison matrix...');
    const candidateNamesArr = Array.from(state.selectedCandidates);

    try {
        const response = await fetch(`${API_BASE}/compare-candidates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                candidate_names: candidateNamesArr,
                jd: state.currentJdText
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Comparison request failed');
        }

        const data = await response.json();
        renderComparisonMatrix(data.results);
        comparisonModal.classList.add('active');

    } catch (error) {
        console.error('Error comparing candidates:', error);
        showToast(error.message || 'Failed to compare candidates.', 'error');
    } finally {
        hideLoading();
    }
}

// RENDER COMPARISON MATRIX
function renderComparisonMatrix(results) {
    // Clear
    comparisonThead.innerHTML = '';
    comparisonTbody.innerHTML = '';

    // 1. Headers: Features | Candidate 1 | Candidate 2 ...
    const trHead = document.createElement('tr');
    trHead.innerHTML = `<th>Features</th>`;
    results.forEach(res => {
        trHead.innerHTML += `
            <th class="candidate-col">
                <span class="comp-cand-name">${res.candidate_name}</span>
                <span class="comp-cand-role">${res.current_role || 'Not Specified'}</span>
            </th>
        `;
    });
    comparisonThead.appendChild(trHead);

    // 2. Row: Match Score
    const trScore = document.createElement('tr');
    trScore.innerHTML = `<td>Match Score</td>`;
    results.forEach(res => {
        const score = Math.round(res.match_score);
        let scoreClass = 'score-poor';
        if (score >= 80) scoreClass = 'score-excellent';
        else if (score >= 50) scoreClass = 'score-good';
        trScore.innerHTML += `
            <td>
                <span class="score-badge ${scoreClass}">${score}% Match</span>
            </td>
        `;
    });
    comparisonTbody.appendChild(trScore);

    // 3. Row: Experience
    const trExp = document.createElement('tr');
    trExp.innerHTML = `<td>Experience</td>`;
    results.forEach(res => {
        trExp.innerHTML += `
            <td>
                <span class="exp-badge">${res.years_of_experience || 0} Years</span>
            </td>
        `;
    });
    comparisonTbody.appendChild(trExp);

    // 4. Row: Strengths
    const trStrengths = document.createElement('tr');
    trStrengths.innerHTML = `<td>Key Strengths</td>`;
    results.forEach(res => {
        const listItems = res.strengths.map(s => `<li>${s}</li>`).join('');
        trStrengths.innerHTML += `<td><ul class="comp-ul">${listItems || 'None extracted'}</ul></td>`;
    });
    comparisonTbody.appendChild(trStrengths);

    // 5. Row: Core Skills
    const trSkills = document.createElement('tr');
    trSkills.innerHTML = `<td>Matching Skills</td>`;
    results.forEach(res => {
        const listItems = res.key_skills.map(s => `<span class="pill" style="margin-right: 4px; margin-bottom: 4px; display: inline-block;">${s}</span>`).join('');
        trSkills.innerHTML += `<td><div>${listItems || 'None matched'}</div></td>`;
    });
    comparisonTbody.appendChild(trSkills);

    // 6. Row: Domains
    const trDomains = document.createElement('tr');
    trDomains.innerHTML = `<td>Domains</td>`;
    results.forEach(res => {
        const listItems = res.domains.map(d => `<span class="pill" style="margin-right: 4px; margin-bottom: 4px; display: inline-block;">${d}</span>`).join('');
        trDomains.innerHTML += `<td><div>${listItems || 'None detected'}</div></td>`;
    });
    comparisonTbody.appendChild(trDomains);

    // 7. Row: Education
    const trEdu = document.createElement('tr');
    trEdu.innerHTML = `<td>Education</td>`;
    results.forEach(res => {
        const eduInfo = res.education && res.education.length > 0 ? 
            res.education.map(e => `${e.degree || 'Degree'} - ${e.institution || 'Institution'}`).join('<br>') : 
            'Not Specified';
        trEdu.innerHTML += `<td>${eduInfo}</td>`;
    });
    comparisonTbody.appendChild(trEdu);
}

// API: GENERATE CLIENT CVS AND DOWNLOAD ZIP
async function generateSelectedCvs() {
    showLoading('Generating client CVs and assembling ZIP archive...');
    const candidateNamesArr = Array.from(state.selectedCandidates);

    try {
        const response = await fetch(`${API_BASE}/generate-selected-cvs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                candidate_names: candidateNamesArr,
                jd: state.currentJdText
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'CV generation request failed');
        }

        const blob = await response.blob();
        
        // Download Zip
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'selected_cvs.zip';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showToast('Successfully generated and downloaded ZIP with selected CVs!', 'success');
        
        // Reset selection after download
        state.selectedCandidates.clear();
        const checkboxes = candidatesTbody.querySelectorAll('.cand-checkbox');
        checkboxes.forEach(cb => cb.checked = false);
        masterCheckbox.checked = false;
        updateSelectionState();

    } catch (error) {
        console.error('Error generating selected CVs:', error);
        showToast(error.message || 'Failed to generate CVs.', 'error');
    } finally {
        hideLoading();
    }
}

// MODAL WINDOW CONTROL
function setupModals() {
    // Close profile details modal
    closeCandidateModal.addEventListener('click', () => {
        candidateModal.classList.remove('active');
    });

    candidateModal.addEventListener('click', (e) => {
        if (e.target === candidateModal) {
            candidateModal.classList.remove('active');
        }
    });

    // Close comparison matrix modal
    closeComparisonModal.addEventListener('click', () => {
        comparisonModal.classList.remove('active');
    });

    comparisonModal.addEventListener('click', (e) => {
        if (e.target === comparisonModal) {
            comparisonModal.classList.remove('active');
        }
    });

    // Close modals on Escape key
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            candidateModal.classList.remove('active');
            comparisonModal.classList.remove('active');
        }
    });
}
