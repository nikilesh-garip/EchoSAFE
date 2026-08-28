// Global State
let isMonitoring = false;
let currentScreen = 'home';
let audioContext = null;
let mediaStream = null;
let recordingInterval = null;
let animationFrameId = null;
let pipelineBusy = false;
let guidanceRules = {};
// Set once the local session is restored/created (see Session gate below).
// Not real authentication: whatever is entered is accepted and nothing is
// transmitted. It exists so contacts/history/alerts scope to a stable id,
// and so displayName can appear in the message a contact actually receives.
let userId = "demo_panel_user";
let displayName = "Echo user";

// --- Toasts --------------------------------------------------------------
// Replaces bare alert()/console-only failures with a small, non-blocking,
// on-brand notification -- "something went wrong" should never feel like a
// browser popup in an app whose whole job is calm, trustworthy signaling.
const toastStack = document.getElementById('toast-stack');
function showToast(message, kind = 'info', timeoutMs = 4200) {
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.innerHTML = `<span class="dot"></span><span>${message}</span>`;
    toastStack.appendChild(el);
    setTimeout(() => {
        el.classList.add('leaving');
        setTimeout(() => el.remove(), 200);
    }, timeoutMs);
}

// --- Risk-level helpers ---------------------------------------------------
const RISK_LEVELS = ["NORMAL", "SUSPICIOUS", "POSSIBLE_DANGER", "HIGH_RISK"];
function normalizeRiskLevel(level) {
    return RISK_LEVELS.includes(level) ? level : "NORMAL";
}
function applyRiskAttr(el, level) {
    if (el) el.setAttribute('data-risk', normalizeRiskLevel(level));
}

// --- Session gate -----------------------------------------------------
// Mirrors app/lib/services/session_service.dart's local sign-in: derive a
// stable user id from whatever identifier is entered, store it, and gate
// the dashboard behind it. Credentials never leave this browser.
const SESSION_KEY = "echo_web_session";

function slugifyIdentifier(identifier) {
    const cleaned = identifier.trim().toLowerCase();
    const slug = cleaned.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    return slug ? `echo_${slug}` : 'echo_user';
}

function nameFromIdentifier(identifier) {
    const local = identifier.split('@')[0];
    if (!local) return 'Echo user';
    return local
        .split(/[._\-\s]+/)
        .filter(Boolean)
        .map(w => w[0].toUpperCase() + w.slice(1))
        .join(' ') || 'Echo user';
}

function applySession(session) {
    userId = session.userId;
    displayName = session.displayName;
    document.getElementById('session-name').textContent = `Signed in as ${displayName}`;
    const overlay = document.getElementById('login-overlay');
    const shell = document.getElementById('app-shell');
    // Belt-and-suspenders: set inline style directly rather than relying only
    // on the `hidden` attribute + CSS specificity, so a stale cached
    // stylesheet can never leave both screens visible at once.
    overlay.style.display = 'none';
    overlay.setAttribute('hidden', '');
    shell.style.display = '';
    shell.removeAttribute('hidden');
    loadEscalationStatus();
    loadReadiness();
}

function restoreSession() {
    try {
        const raw = localStorage.getItem(SESSION_KEY);
        if (!raw) return false;
        const session = JSON.parse(raw);
        if (!session || !session.userId) return false;
        applySession(session);
        return true;
    } catch (e) {
        return false;
    }
}

document.getElementById('login-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const identifier = document.getElementById('login-identifier').value.trim();
    const nameInput = document.getElementById('login-name').value.trim();
    if (!identifier) return;
    const session = {
        userId: slugifyIdentifier(identifier),
        email: identifier,
        displayName: nameInput || nameFromIdentifier(identifier),
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    applySession(session);
});

document.getElementById('sign-out-btn').addEventListener('click', () => {
    localStorage.removeItem(SESSION_KEY);
    location.reload();
});

restoreSession();

// --- Emergency channel status (Telegram / voice call) --------------------
// Surfaced in the sidebar (tiny dots), Settings (full detail), and the
// Overview "who would be told" card -- so "did my keys actually take
// effect" never requires opening /docs.
let escalationStatus = null;

async function loadEscalationStatus() {
    try {
        const res = await fetch('/escalation/status');
        if (!res.ok) return;
        escalationStatus = await res.json();
        applyEscalationStatusUI();
    } catch (e) {
        console.error("Could not load escalation status:", e);
    }
}

function applyEscalationStatusUI() {
    if (!escalationStatus) return;
    const tgLive = !!escalationStatus.telegram_configured;
    const voiceLive = !!escalationStatus.voice_call_configured;

    const tgDot = document.getElementById('channel-mini-telegram-dot');
    const voiceDot = document.getElementById('channel-mini-voice-dot');
    if (tgDot) tgDot.className = 'dot ' + (tgLive ? 'live' : 'sim');
    if (voiceDot) voiceDot.className = 'dot ' + (voiceLive ? 'live' : 'sim');

    const tgPill = document.getElementById('settings-telegram-pill');
    const voicePill = document.getElementById('settings-voice-pill');
    if (tgPill) { tgPill.textContent = tgLive ? 'Live' : 'Simulated'; tgPill.className = 'chan-pill ' + (tgLive ? 'live' : 'sim'); }
    if (voicePill) { voicePill.textContent = voiceLive ? 'Live' : 'Simulated'; voicePill.className = 'chan-pill ' + (voiceLive ? 'live' : 'sim'); }

    const classesEl = document.getElementById('settings-escalation-classes');
    if (classesEl) classesEl.textContent = (escalationStatus.escalation_classes || []).join(', ') || '—';
    const cancelEl = document.getElementById('settings-cancel-window');
    if (cancelEl) cancelEl.textContent = `${escalationStatus.cancel_window_seconds ?? '—'}s`;
    const minRiskEl = document.getElementById('settings-min-risk');
    if (minRiskEl) minRiskEl.textContent = `${escalationStatus.min_risk_score ?? '—'} / 100`;
}

async function loadReadiness() {
    const card = document.getElementById('readiness-card');
    const body = document.getElementById('readiness-body');
    if (!card || !body) return;
    try {
        const res = await fetch(`/escalation/readiness/${encodeURIComponent(userId)}`);
        if (!res.ok) return;
        const data = await res.json();
        card.hidden = false;
        if (data.ready) {
            body.innerHTML = `<p class="muted">${data.contact_count} contact${data.contact_count === 1 ? '' : 's'} would be called <strong>and</strong> Telegram-messaged, with your location and the evidence clip.</p>`;
        } else {
            const items = (data.blockers || []).map(b => `<li>${b}</li>`).join('');
            body.innerHTML = `<ul class="chat-picker" style="display:grid; gap:6px; list-style:none; padding:10px;">${items || '<li>Not ready yet.</li>'}</ul>`;
        }
    } catch (e) {
        console.error("Could not load escalation readiness:", e);
    }
}

// --- Model profile (production vs demo) ---------------------------------
// Selects which classifier head /detect runs: 'real' (8 production classes)
// or 'demo' (adds firecracker, aliased to gunshot). Applies to BOTH the
// live microphone pipeline and the demo-lab wav-injection buttons -- there
// is one shared pipeline, not two.
const PROFILE_KEY = "echo_model_profile";
let modelProfile = localStorage.getItem(PROFILE_KEY) || "real";

function applyProfileUI() {
    const isDemo = modelProfile === "demo";
    document.getElementById('profile-real-btn').classList.toggle('active', !isDemo);
    document.getElementById('profile-demo-btn').classList.toggle('active', isDemo);
    const badge = document.getElementById('profile-badge');
    badge.textContent = isDemo ? "Demo" : "Production";
    badge.classList.toggle('demo', isDemo);
    document.getElementById('profile-note').hidden = !isDemo;
    const firecrackerBtn = document.querySelector('.wav-btn[data-sound="firecracker"]');
    if (firecrackerBtn) firecrackerBtn.hidden = !isDemo;
}

document.getElementById('profile-real-btn').addEventListener('click', () => {
    modelProfile = 'real';
    localStorage.setItem(PROFILE_KEY, modelProfile);
    applyProfileUI();
});
document.getElementById('profile-demo-btn').addEventListener('click', () => {
    modelProfile = 'demo';
    localStorage.setItem(PROFILE_KEY, modelProfile);
    applyProfileUI();
});
applyProfileUI();

// Dom Elements
const screens = document.querySelectorAll('.screen');
const navItems = document.querySelectorAll('.nav-item');
const topbarTitle = document.getElementById('topbar-title');
const startBtn = document.getElementById('start-monitoring-btn');
const systemStatusBadge = document.getElementById('system-status-badge');
const micStatusIndicator = document.getElementById('mic-status-indicator');
const micStatusText = document.getElementById('mic-status-text');
const threeCanvasContainer = document.getElementById('three-canvas');
const monClassBox = document.getElementById('mon-class-box');
const monRiskBox = document.getElementById('mon-risk-box');
const monClass = document.getElementById('mon-class');
const monRisk = document.getElementById('mon-risk');
const monRiskChip = document.getElementById('mon-risk-chip');
const monP1 = document.getElementById('mon-p1-val');
const monP2 = document.getElementById('mon-p2-val');
const monP1Bar = document.getElementById('mon-p1-bar');
const monP2Bar = document.getElementById('mon-p2-bar');
const pulseWrapper = document.getElementById('pulse-wrapper');
const lastEventDetails = document.getElementById('last-event-details');
const alertModal = document.getElementById('alert-modal');
const alertHeader = document.getElementById('alert-header');
const alertBox = document.getElementById('alert-box');
const alertTitle = document.getElementById('alert-title');
const alertRiskScore = document.getElementById('alert-risk-score');
const alertRiskLvl = document.getElementById('alert-risk-lvl');
const alertRiskRingFill = document.getElementById('alert-risk-ring-fill');
const alertP1 = document.getElementById('alert-p1');
const alertP2 = document.getElementById('alert-p2');
const alertGuidanceList = document.getElementById('alert-guidance-list');
const alertPlacesContainer = document.getElementById('alert-places-container');
const dismissAlertBtn = document.getElementById('dismiss-alert-btn');
const sensitivitySlider = document.getElementById('sensitivity-slider');
const sensitivityVal = document.getElementById('sensitivity-val');
const contactsContainer = document.getElementById('contacts-container');
const saveContactBtn = document.getElementById('save-contact-btn');
const contactNameInput = document.getElementById('contact-name');
const contactPhoneInput = document.getElementById('contact-phone');
const contactRelationInput = document.getElementById('contact-relation');
const contactTelegramInput = document.getElementById('contact-telegram');
const contactPriorityInput = document.getElementById('contact-priority');
const contactNotifyCall = document.getElementById('contact-notify-call');
const contactNotifyTelegram = document.getElementById('contact-notify-telegram');
const findChatsBtn = document.getElementById('find-chats-btn');
const chatPicker = document.getElementById('chat-picker');
const sendTestAlertBtn = document.getElementById('send-test-alert-btn');
const testAlertResult = document.getElementById('test-alert-result');
const historyContainer = document.getElementById('history-items-container');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const micPermissionStatus = document.getElementById('mic-permission-status');
const locationPermissionStatus = document.getElementById('location-permission-status');
const downloadReportBtn = document.getElementById('download-report-btn');
let latestIncident = null;

// Load configurations
fetch('guidance_rules.json')
    .then(res => res.json())
    .then(data => {
        guidanceRules = data;
    })
    .catch(() => showToast("Could not load guidance text. Alerts will still work, without recommended-actions copy.", "error"));

// Update Status Time
function updateTime() {
    const now = new Date();
    document.getElementById('status-time').innerText = now.toTimeString().slice(0, 5);
}
setInterval(updateTime, 1000);
updateTime();

// Screen Navigation
const SCREEN_TITLES = { home: 'Overview', monitor: 'Live monitor', history: 'Event history', contacts: 'Trusted contacts', demo: 'Demo lab', settings: 'Settings' };
navItems.forEach(item => {
    item.addEventListener('click', () => {
        const targetScreen = item.getAttribute('data-screen');
        switchScreen(targetScreen);
    });
});

function switchScreen(screenId) {
    screens.forEach(s => s.classList.remove('active'));
    navItems.forEach(n => n.classList.remove('active'));

    document.getElementById(`screen-${screenId}`).classList.add('active');
    const matchingNav = document.querySelector(`.nav-item[data-screen="${screenId}"]`);
    if (matchingNav) matchingNav.classList.add('active');
    if (topbarTitle && SCREEN_TITLES[screenId]) topbarTitle.textContent = SCREEN_TITLES[screenId];

    currentScreen = screenId;

    if (screenId === 'history') {
        loadHistory();
    } else if (screenId === 'contacts') {
        loadContacts();
    } else if (screenId === 'home') {
        loadReadiness();
    }
}

function sensitivityThreshold() {
    // 1 is least sensitive (70% confidence); 9 is most sensitive (30%).
    return Number((0.75 - Number(sensitivitySlider.value) * 0.05).toFixed(2));
}

// Sensitivity control
sensitivitySlider.addEventListener('input', (e) => {
    const val = e.target.value;
    const threshold = sensitivityThreshold().toFixed(2);
    let label = `Medium (${threshold})`;
    if (val < 4) label = `Low (${threshold})`;
    else if (val > 7) label = `High (${threshold})`;
    sensitivityVal.innerText = label;
});

// START/STOP Microphone Monitoring
startBtn.addEventListener('click', () => {
    if (isMonitoring) {
        stopMonitoring();
    } else {
        startMonitoring();
    }
});

async function startMonitoring() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission().catch(() => {});
        }
        isMonitoring = true;

        startBtn.innerText = "STOP MONITORING";
        startBtn.classList.add('listening');
        systemStatusBadge.innerText = "Active";
        systemStatusBadge.classList.add('active');
        micStatusIndicator.className = "signal-dot green";
        micStatusText.innerText = "Monitoring";
        micPermissionStatus.innerText = "Granted";

        setupVisualizer();
        startPipelineLoop();
        return true;
    } catch (err) {
        micPermissionStatus.innerText = "Denied or unavailable";
        showToast("Microphone permission was denied or the device is busy. Monitoring did not start.", "error");
        console.error(err);
        return false;
    }
}

async function logVerifiedEvent(data) {
    if (!data.verified) return;
    const response = await fetch("/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id: userId,
            class_name: data.candidate,
            primary_conf: data.primary_confidence,
            verification_conf: data.verification_confidence,
            risk_score: data.risk_score,
            risk_level: data.risk_level
        })
    });
    if (!response.ok) throw new Error("Could not save the verified event.");
}

function notifyUrgentIncident(data) {
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification("Echo: verified high-risk sound", {
            body: `${data.candidate} detected. Risk score ${data.risk_score}. Review guidance now.`
        });
    }
}

// --- Emergency contact escalation ---------------------------------------
// This is what actually calls/messages the saved contacts. `triggerAlertModal`
// creates a real incident (with the audio clip that triggered it) before
// showing the modal, then polls the incident until it dispatches or is
// cancelled -- the countdown ring, the escalation copy, and the per-contact
// per-channel result list are all driven off that same poll.
let escalationPollTimer = null;
let currentIncidentId = null;
let escalationTotalWindow = 12;

function getCurrentLocation() {
    return new Promise((resolve) => {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }),
            () => resolve(null),
            { timeout: 6000 }
        );
    });
}

async function createIncidentAndEscalate(data, clipBlob) {
    const position = await getCurrentLocation();
    const formData = new FormData();
    formData.append("user_id", userId);
    formData.append("class_name", data.candidate);
    formData.append("raw_class", data.raw_candidate || data.candidate);
    formData.append("profile", data.profile || "real");
    formData.append("primary_conf", data.primary_confidence ?? 0);
    formData.append("verification_conf", data.verification_confidence ?? 0);
    formData.append("risk_score", data.risk_score ?? 0);
    formData.append("risk_level", data.risk_level ?? "NORMAL");
    formData.append("verified", "true");
    formData.append("user_label", displayName);
    if (position) {
        formData.append("latitude", position.lat);
        formData.append("longitude", position.lng);
        formData.append("accuracy_m", position.accuracy);
        // No place_label sent from here on purpose: the backend resolves a
        // real street-level address from lat/lng at dispatch time (see
        // backend/geocode.py) rather than us sending a placeholder string.
    }
    if (clipBlob) {
        formData.append("clip", clipBlob, "incident.wav");
    }
    const res = await fetch("/incidents", { method: "POST", body: formData });
    if (!res.ok) {
        if (res.status === 429) throw new Error("Too many alerts too quickly -- please wait a moment.");
        throw new Error(`Could not create incident (${res.status})`);
    }
    return res.json();
}

function renderEscalationAttempts(attempts, container) {
    container.innerHTML = "";
    if (!attempts.length) {
        container.innerHTML = "<li class='empty'>No contacts were attempted.</li>";
        return;
    }
    attempts.forEach(a => {
        const li = document.createElement('li');
        const channelLabel = a.channel === 'voice_call' ? 'Automated call' : a.channel === 'telegram' ? 'Telegram' : a.channel;
        li.innerHTML = `
            <div>
                <div class="chan"><strong>${a.contact_name || 'Contact'}</strong> · ${channelLabel}</div>
                <div class="detail">${a.detail || ''}</div>
            </div>
            <span class="esc-status ${a.status}">${a.status}</span>
        `;
        container.appendChild(li);
    });
}

function stopEscalationTimers() {
    if (escalationPollTimer) clearInterval(escalationPollTimer);
    escalationPollTimer = null;
}

function setCountdownRing(secondsLeft, totalSeconds) {
    const ring = document.getElementById('escalation-ring-fill');
    const circumference = 326.7; // 2 * pi * 52
    const pct = totalSeconds > 0 ? Math.max(0, Math.min(1, secondsLeft / totalSeconds)) : 0;
    if (ring) ring.style.strokeDashoffset = String(circumference * (1 - pct));
    const numberEl = document.getElementById('escalation-countdown');
    const inlineEl = document.getElementById('escalation-countdown-inline');
    const rounded = Math.ceil(secondsLeft);
    if (numberEl) numberEl.textContent = rounded;
    if (inlineEl) inlineEl.textContent = rounded;
}

function showEscalationState(incident) {
    const pendingEl = document.getElementById('escalation-pending');
    const resultEl = document.getElementById('escalation-result');
    const noneEl = document.getElementById('escalation-none');
    const locationEl = document.getElementById('escalation-location');
    pendingEl.hidden = true;
    resultEl.hidden = true;
    noneEl.hidden = true;

    if (!incident) {
        noneEl.hidden = false;
        noneEl.querySelector('p').textContent = "Could not reach the backend to alert your contacts.";
        return;
    }

    if (incident.state === 'PENDING') {
        pendingEl.hidden = false;
        setCountdownRing(incident.seconds_to_dispatch || 0, escalationTotalWindow);
        return;
    }
    if (incident.state === 'SUPPRESSED') {
        noneEl.hidden = false;
        noneEl.querySelector('p').textContent = incident.gate_reason || "This detection did not meet the escalation policy.";
        return;
    }
    if (incident.state === 'NO_CONTACTS') {
        noneEl.hidden = false;
        noneEl.querySelector('p').textContent = "No emergency contact is saved — nobody could be alerted. Add one on the Trusted contacts tab.";
        return;
    }
    if (incident.state === 'CANCELLED') {
        noneEl.hidden = false;
        noneEl.querySelector('p').textContent = "Alert cancelled — nobody was called or messaged.";
        return;
    }
    // DISPATCHED (or DISPATCHING mid-flight)
    resultEl.hidden = false;
    if (incident.place_label) {
        locationEl.hidden = false;
        locationEl.textContent = `Location sent: ${incident.place_label}`;
    } else {
        locationEl.hidden = true;
    }
    renderEscalationAttempts(incident.attempts || [], document.getElementById('escalation-attempts-list'));
}

async function pollIncident(incidentId) {
    try {
        const res = await fetch(`/incidents/${incidentId}`);
        if (!res.ok) return;
        const incident = await res.json();
        showEscalationState(incident);
        if (incident.state !== 'PENDING' && incident.state !== 'DISPATCHING') {
            stopEscalationTimers();
        }
    } catch (e) {
        console.error("Incident poll error:", e);
    }
}

async function startEscalation(data, clipBlob) {
    currentIncidentId = null;
    showEscalationState({ state: 'PENDING', seconds_to_dispatch: 0 });
    try {
        const incident = await createIncidentAndEscalate(data, clipBlob);
        currentIncidentId = incident.id;
        escalationTotalWindow = (escalationStatus && escalationStatus.cancel_window_seconds) || incident.seconds_to_dispatch || 12;
        if (!incident.escalation_armed) {
            showEscalationState({ state: 'SUPPRESSED', gate_reason: incident.gate_reason });
            return;
        }
        showEscalationState(incident);
        stopEscalationTimers();
        escalationPollTimer = setInterval(() => pollIncident(incident.id), 1000);
    } catch (e) {
        console.error("Escalation error:", e);
        showToast(e.message || "Could not arm contact escalation.", "error");
        showEscalationState(null);
    }
}

document.getElementById('escalation-cancel-btn').addEventListener('click', async () => {
    if (!currentIncidentId) return;
    try {
        const res = await fetch(`/incidents/${currentIncidentId}/cancel`, {
            method: 'POST',
            body: new URLSearchParams({ user_id: userId, note: "Marked safe by the user." })
        });
        const data = await res.json();
        stopEscalationTimers();
        showEscalationState(data.incident || { state: 'CANCELLED' });
        showToast("Cancelled — nobody was called or messaged.", "success");
    } catch (e) {
        console.error("Cancel error:", e);
        showToast("Could not cancel — the request failed. Try again.", "error");
    }
});

function downloadIncidentReport() {
    if (!latestIncident) return;
    const decision = latestIncident.decision || {};
    const report = [
        "ECHO INCIDENT REPORT", `Generated: ${new Date().toISOString()}`,
        `Detected sound: ${latestIncident.candidate}`,
        `Primary confidence: ${(latestIncident.primary_confidence * 100).toFixed(1)}%`,
        `Verification confidence: ${(latestIncident.verification_confidence * 100).toFixed(1)}%`,
        `Risk score: ${latestIncident.risk_score} (${latestIncident.risk_level})`,
        `Decision: ${decision.state || "NOT AVAILABLE"}`,
        `Rationale: ${decision.rationale || "No decision rationale available."}`,
        "Audio was not retained by Echo.",
        "This report is user-generated evidence, not a police report or emergency dispatch request."
    ].join("\n");
    const url = URL.createObjectURL(new Blob([report], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `echo-incident-${Date.now()}.txt`;
    link.click();
    URL.revokeObjectURL(url);
}

downloadReportBtn.addEventListener("click", downloadIncidentReport);

function stopMonitoring() {
    isMonitoring = false;
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
    }
    if (recordingInterval) clearInterval(recordingInterval);
    recordingInterval = null;
    pipelineBusy = false;
    if (animationFrameId) cancelAnimationFrame(animationFrameId);

    startBtn.innerText = "START MONITORING";
    startBtn.classList.remove('listening');
    systemStatusBadge.innerText = "Off";
    systemStatusBadge.classList.remove('active');
    micStatusIndicator.className = "signal-dot red";
    micStatusText.innerText = "Idle";

    // Clear Visualizer Canvas
    if (typeof threeScene !== 'undefined' && threeScene) {
        while(threeScene.children.length > 0){ 
            threeScene.remove(threeScene.children[0]); 
        }
        if (typeof threeRenderer !== 'undefined') {
            threeRenderer.clear();
        }
    }
}

let threeScene, threeCamera, threeRenderer, threeMeshes = [];
// Web Audio API Visualizer Setup
function setupVisualizer() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioContext.createMediaStreamSource(mediaStream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 64; // Smaller FFT size for thicker 3D bars
    source.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const container = document.getElementById('three-canvas');
    const width = container.clientWidth || (window.innerWidth > 900 ? window.innerWidth - 300 : window.innerWidth - 48);
    const height = container.clientHeight || 260;

    if (!threeRenderer) {
        threeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        threeRenderer.setSize(width, height);
        threeRenderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(threeRenderer.domElement);
    }
    
    threeScene = new THREE.Scene();
    threeCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    threeCamera.position.set(0, 30, 40);
    threeCamera.lookAt(0, 0, 0);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    threeScene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(20, 40, 20);
    threeScene.add(dirLight);

    threeMeshes = [];
    const barWidth = 1.2;
    const spacing = 1.8;
    const totalWidth = bufferLength * spacing;
    const startX = -totalWidth / 2;

    const material = new THREE.MeshPhongMaterial({ color: 0xFFD700, shininess: 80 });
    for (let i = 0; i < bufferLength; i++) {
        const geometry = new THREE.BoxGeometry(barWidth, 1, barWidth);
        const mesh = new THREE.Mesh(geometry, material.clone());
        mesh.position.set(startX + i * spacing, 0.5, 0);
        threeScene.add(mesh);
        threeMeshes.push(mesh);
    }

    const grid = new THREE.GridHelper(totalWidth + 10, 20, 0xe5e7eb, 0xe5e7eb);
    grid.position.y = 0;
    threeScene.add(grid);

    function draw() {
        if (!isMonitoring) return;
        animationFrameId = requestAnimationFrame(draw);

        analyser.getByteFrequencyData(dataArray);

        // Gentle camera rotation
        const time = Date.now() * 0.0003;
        threeCamera.position.x = Math.sin(time) * 45;
        threeCamera.position.z = Math.cos(time) * 45;
        threeCamera.lookAt(0, 0, 0);

        for (let i = 0; i < bufferLength; i++) {
            let val = dataArray[i] / 5.0; // Scale down
            if (val < 0.1) val = 0.1;
            
            // Smoothly interpolate current scale to new scale
            threeMeshes[i].scale.y += (val - threeMeshes[i].scale.y) * 0.3;
            threeMeshes[i].position.y = threeMeshes[i].scale.y / 2;
            
            // Color shifts based on intensity (Yellow to Red/Orange)
            const intensity = val / 25;
            threeMeshes[i].material.color.setHSL(Math.max(0, 0.14 - intensity * 0.14), 1, 0.55);
        }

        threeRenderer.render(threeScene, threeCamera);
    }

    draw();
}

// Pipeline Recording / Inference loop
let audioChunks = [];
let mediaRecorder = null;

function startPipelineLoop() {
    // Record a 2-second window every 2.5 seconds, never overlapping a verification.
    runPipelinePass1();
    recordingInterval = setInterval(() => {
        if (!isMonitoring || pipelineBusy) return;
        runPipelinePass1();
    }, 2500);
}

async function runPipelinePass1() {
    if (!mediaStream || pipelineBusy) return;
    pipelineBusy = true;
    let handedOffToVerification = false;

    // Set up brief 2-second recorder using Web Audio script processor to convert to WAV
    const recorderContext = new AudioContext({ sampleRate: 16000 });
    const source = recorderContext.createMediaStreamSource(mediaStream);
    const processor = recorderContext.createScriptProcessor(4096, 1, 1);

    let leftChannel = [];

    processor.onaudioprocess = (e) => {
        const left = e.inputBuffer.getChannelData(0);
        leftChannel.push(new Float32Array(left));
    };

    source.connect(processor);
    processor.connect(recorderContext.destination);

    // Stop recording after 2 seconds
    setTimeout(async () => {
        if (!isMonitoring) {
            pipelineBusy = false;
            return;
        }
        source.disconnect();
        processor.disconnect();
        await recorderContext.close();

        // Merge chunks
        let flattened = mergeBuffers(leftChannel);
        let wavBlob = bufferToWav(flattened, 16000);

        // Send to backend Pass 1
        const formData = new FormData();
        formData.append("file", wavBlob, "chunk_2s.wav");
        formData.append("duration", 2.0);
        formData.append("media_playback", document.getElementById('ctx-media').checked);
        formData.append("sudden_motion", document.getElementById('ctx-motion').checked);
        formData.append("sensitivity_threshold", sensitivityThreshold());
        formData.append("user_id", userId);
        formData.append("context_source", "browser_manual");
        formData.append("profile", modelProfile);

        try {
            const res = await fetch("/detect", { method: "POST", body: formData });
            if (!res.ok) throw new Error(`Detection failed (${res.status})`);
            const data = await res.json();

            if (data.has_candidate) {
                if (data.immediate_verification) {
                    updateUIForClass(
                        data.candidate,
                        data.primary_confidence,
                        data.verification_confidence,
                        data.risk_score,
                        data.risk_level
                    );

                    if (data.verified) {
                        await logVerifiedEvent(data);
                    }
                    if (data.verified && data.should_alert) {
                        triggerAlertModal(data, wavBlob);
                    } else if (data.media_suppressed) {
                        lastEventDetails.innerText = "Verified sound recorded as likely media playback; no critical alert shown.";
                    }
                } else {
                    // Trigger Pass 2: Verify candidate over a 5s window
                    micStatusIndicator.className = "signal-dot orange";
                    micStatusText.innerText = "Verifying...";
                    handedOffToVerification = true;
                    runPipelinePass2(data.candidate, data.confidence);
                    return;
                }
            } else {
                updateUIForClass("normal", data.confidence, 0.0, 0, "NORMAL");
            }
        } catch (e) {
            console.error("Pass 1 Detection error:", e);
            showToast("Lost contact with the backend during monitoring. Retrying next cycle.", "error", 3000);
        } finally {
            if (!handedOffToVerification) pipelineBusy = false;
        }
    }, 2000);
}

async function runPipelinePass2(candidate, p1Conf) {
    if (!mediaStream) return;
    pipelineBusy = true;
    const recorderContext = new AudioContext({ sampleRate: 16000 });
    const source = recorderContext.createMediaStreamSource(mediaStream);
    const processor = recorderContext.createScriptProcessor(4096, 1, 1);

    let leftChannel = [];
    processor.onaudioprocess = (e) => {
        leftChannel.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    source.connect(processor);
    processor.connect(recorderContext.destination);

    // Record for 5 seconds for full verification
    setTimeout(async () => {
        if (!isMonitoring) {
            pipelineBusy = false;
            return;
        }
        source.disconnect();
        processor.disconnect();
        await recorderContext.close();

        let flattened = mergeBuffers(leftChannel);
        let wavBlob = bufferToWav(flattened, 16000);

        const mediaPlayback = document.getElementById('ctx-media').checked;
        const suddenMotion = document.getElementById('ctx-motion').checked;

        const formData = new FormData();
        formData.append("file", wavBlob, "chunk_5s.wav");
        formData.append("duration", 5.0);
        formData.append("media_playback", mediaPlayback);
        formData.append("sudden_motion", suddenMotion);
        formData.append("primary_candidate", candidate);
        formData.append("primary_confidence", p1Conf);
        formData.append("sensitivity_threshold", sensitivityThreshold());
        formData.append("user_id", userId);
        formData.append("context_source", "browser_manual");
        formData.append("profile", modelProfile);

        try {
            const res = await fetch("/detect", { method: "POST", body: formData });
            if (!res.ok) throw new Error(`Verification failed (${res.status})`);
            const data = await res.json();

            micStatusIndicator.className = "signal-dot green";
            micStatusText.innerText = "Monitoring";

            updateUIForClass(
                data.candidate,
                data.primary_confidence,
                data.verification_confidence,
                data.risk_score,
                data.risk_level
            );

            if (data.verified) {
                await logVerifiedEvent(data);
            }
            if (data.verified && data.should_alert) {
                triggerAlertModal(data, wavBlob);
            } else if (data.verified && data.media_suppressed) {
                lastEventDetails.innerText = "Verified sound recorded as likely media playback; no critical alert shown.";
            }
        } catch (e) {
            console.error("Pass 2 Verification error:", e);
            showToast("Verification pass failed to reach the backend.", "error", 3000);
        } finally {
            pipelineBusy = false;
        }
    }, 5000);
}

// WAV encoding helper logic
function mergeBuffers(channelBuffer) {
    let resultLen = 0;
    for (let i = 0; i < channelBuffer.length; i++) {
        resultLen += channelBuffer[i].length;
    }
    let result = new Float32Array(resultLen);
    let offset = 0;
    for (let i = 0; i < channelBuffer.length; i++) {
        result.set(channelBuffer[i], offset);
        offset += channelBuffer[i].length;
    }
    return result;
}

function bufferToWav(buffer, sampleRate) {
    let bufferLen = buffer.length;
    let writeBuffer = new ArrayBuffer(44 + bufferLen * 2);
    let view = new DataView(writeBuffer);

    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + bufferLen * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM Format
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // Byte rate
    view.setUint16(32, 2, true); // Block align
    view.setUint16(34, 16, true); // Bits per sample
    writeString(view, 36, 'data');
    view.setUint32(40, bufferLen * 2, true);

    // Float to 16bit PCM conversion
    let offset = 44;
    for (let i = 0; i < buffer.length; i++, offset += 2) {
        let s = Math.max(-1, Math.min(1, buffer[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Blob([writeBuffer], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// Update Dashboard Stats UI
function updateUIForClass(cls, p1, p2, risk, level) {
    monClass.innerText = cls.toUpperCase();
    monRisk.innerText = risk;
    monP1.innerText = `${((p1 || 0) * 100).toFixed(1)}%`;
    monP2.innerText = p2 > 0 ? `${(p2 * 100).toFixed(1)}%` : "0.0%";
    if (monP1Bar) monP1Bar.style.width = `${Math.max(0, Math.min(100, (p1 || 0) * 100))}%`;
    if (monP2Bar) monP2Bar.style.width = `${Math.max(0, Math.min(100, (p2 || 0) * 100))}%`;

    const normalizedLevel = normalizeRiskLevel(level);
    applyRiskAttr(monClassBox, normalizedLevel);
    applyRiskAttr(monRiskBox, normalizedLevel);
    if (monRiskChip) monRiskChip.textContent = normalizedLevel.replace('_', ' ');
    if (pulseWrapper) pulseWrapper.className = 'pulse-wrapper risk-' + normalizedLevel.toLowerCase();

    if (cls !== "normal") {
        lastEventDetails.innerHTML = `
            <strong>${cls.toUpperCase()}</strong><br>
            Risk Score: ${risk} (${level})<br>
            Conf: P1=${(p1 * 100).toFixed(0)}%, P2=${(p2 * 100).toFixed(0)}%
        `;
    }
}

// Trigger Alert View Overlay
async function triggerAlertModal(data, clipBlob) {
    latestIncident = data;
    notifyUrgentIncident(data);
    const normalizedLevel = normalizeRiskLevel(data.risk_level);
    applyRiskAttr(alertHeader, normalizedLevel);
    document.getElementById('alert-badge').textContent = normalizedLevel === 'HIGH_RISK' ? 'CRITICAL ALERT' : normalizedLevel === 'POSSIBLE_DANGER' ? 'ALERT' : 'REVIEW';
    alertTitle.innerText = guidanceRules[data.candidate]?.title || "Acoustic Threat Detected";
    const rawClassEl = document.getElementById('alert-raw-class');
    if (data.alias_applied && data.raw_candidate) {
        rawClassEl.hidden = false;
        rawClassEl.textContent = `Raw acoustic class: ${data.raw_candidate}${data.profile === 'demo' ? ' (demo profile)' : ''}`;
    } else {
        rawClassEl.hidden = true;
    }
    alertRiskScore.innerText = data.risk_score;
    alertRiskLvl.innerText = `(${data.risk_level})`;
    alertP1.innerText = `${(data.primary_confidence * 100).toFixed(0)}%`;
    alertP2.innerText = `${(data.verification_confidence * 100).toFixed(0)}%`;
    if (alertRiskRingFill) {
        const circumference = 169.6; // 2 * pi * 27
        const pct = Math.max(0, Math.min(100, data.risk_score || 0)) / 100;
        alertRiskRingFill.style.strokeDashoffset = String(circumference * (1 - pct));
    }

    // Arms the real countdown -> automated call + Telegram to saved contacts.
    startEscalation(data, clipBlob);

    // Guidance Rules display
    alertGuidanceList.innerHTML = "";
    const instructions = guidanceRules[data.candidate]?.instructions || [];
    instructions.forEach(step => {
        const li = document.createElement('li');
        li.innerText = step;
        alertGuidanceList.appendChild(li);
    });

    // Query maps proxy nearby emergency services
    alertPlacesContainer.innerHTML = "<div class='place-card'>Fetching nearby emergency facilities...</div>";

    // San Francisco coords default, tries to get real geolocation
    let lat = 37.7749;
    let lng = -122.4194;

    const getPlaces = (latitude, longitude) => {
        const type = (data.candidate === "fire_alarm") ? "fire" : (data.candidate === "gunshot" || data.candidate === "glass_breaking" || data.candidate === "shouting") ? "police" : "hospital";
        fetch(`/nearby?lat=${latitude}&lng=${longitude}&type=${type}`)
            .then(res => res.json())
            .then(resData => {
                alertPlacesContainer.innerHTML = "";
                if (resData.results && resData.results.length > 0) {
                    resData.results.slice(0, 3).forEach(place => {
                        const card = document.createElement('div');
                        card.className = 'place-card';
                        const name = document.createElement('div');
                        name.className = 'name';
                        name.textContent = place.name;
                        const address = document.createElement('div');
                        address.className = 'addr';
                        address.textContent = place.address;
                        card.append(name, address);
                        alertPlacesContainer.appendChild(card);
                    });
                } else {
                    alertPlacesContainer.innerHTML = "<div class='place-card'>No emergency facilities found nearby.</div>";
                }
            })
            .catch(() => {
                alertPlacesContainer.innerHTML = "<div class='place-card'>Nearby locations lookup failed.</div>";
            });
    };

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition((pos) => {
            locationPermissionStatus.innerText = "Granted";
            getPlaces(pos.coords.latitude, pos.coords.longitude);
        }, () => {
            locationPermissionStatus.innerText = "Unavailable — using fallback";
            getPlaces(lat, lng);
        });
    } else {
        getPlaces(lat, lng);
    }

    alertModal.classList.add('show');
}

dismissAlertBtn.addEventListener('click', async () => {
    // "I'm safe" also cancels a still-pending escalation -- closing the modal
    // must not leave a countdown silently running in the background.
    if (currentIncidentId) {
        try {
            await fetch(`/incidents/${currentIncidentId}/cancel`, {
                method: 'POST',
                body: new URLSearchParams({ user_id: userId, note: "Dismissed by the user." })
            });
        } catch (e) {
            console.error("Cancel-on-dismiss error:", e);
        }
    }
    stopEscalationTimers();
    currentIncidentId = null;
    alertModal.classList.remove('show');
});

// HISTORY PERSISTENCE
function loadHistory() {
    fetch(`/events/${userId}`)
        .then(res => res.json())
        .then(data => {
            historyContainer.innerHTML = "";
            if (data.length === 0) {
                historyContainer.innerHTML = "<div class='empty-state'>No events recorded.</div>";
                return;
            }
            data.forEach(item => {
                const date = new Date(item.timestamp * 1000).toLocaleString();
                const level = normalizeRiskLevel(item.risk_level);
                const card = document.createElement('div');
                card.className = 'history-card';
                card.setAttribute('data-risk', level);
                card.innerHTML = `
                    <div class="meta">
                        <strong>${item.class_name.toUpperCase()}</strong>
                        <span class="time-stamp">${date}</span>
                    </div>
                    <span class="risk-pill">${item.risk_score} · ${level.replace('_', ' ')}</span>
                `;
                historyContainer.appendChild(card);
            });
        })
        .catch(() => { historyContainer.innerHTML = "<div class='empty-state'>Could not load history.</div>"; });
}

clearHistoryBtn.addEventListener('click', async () => {
    historyContainer.innerHTML = "<div class='empty-state'>Clearing history...</div>";
    try {
        const response = await fetch(`/events/${userId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Could not clear history');
        loadHistory();
        showToast("History cleared.", "success");
    } catch (error) {
        historyContainer.innerHTML = "<div class='empty-state'>Could not clear history. Please try again.</div>";
        showToast("Could not clear history.", "error");
    }
});

// EMERGENCY CONTACTS CRUD
function loadContacts() {
    fetch(`/contacts-detail/${userId}`)
        .then(res => res.ok ? res.json() : fetch(`/contacts/${userId}`).then(r => r.json()))
        .then(data => {
            contactsContainer.innerHTML = "";
            if (data.length === 0) {
                contactsContainer.innerHTML = "<div class='empty-state'>No trusted contacts added yet. Add one below, then send a test alert to confirm it works.</div>";
                return;
            }
            data.forEach(contact => {
                const card = document.createElement('div');
                card.className = 'contact-card';
                const callOn = contact.notify_call === undefined ? true : !!contact.notify_call;
                const tgOn = contact.notify_telegram === undefined ? true : !!contact.notify_telegram;
                const badges = [
                    callOn ? '<span class="chan-pill live">Call</span>' : '<span class="chan-pill">Call off</span>',
                    (tgOn && contact.telegram_chat_id) ? '<span class="chan-pill live">Telegram</span>' : tgOn ? '<span class="chan-pill sim">Telegram (no chat id)</span>' : '<span class="chan-pill">Telegram off</span>',
                ].join(' ');
                card.innerHTML = `
                    <div class="info">
                        <h4>${contact.name}${contact.relation ? ` (${contact.relation})` : ''}</h4>
                        <p>${contact.phone}</p>
                        <p>${badges}</p>
                    </div>
                    <button class="delete-btn" onclick="deleteContact(${contact.id})">Delete</button>
                `;
                contactsContainer.appendChild(card);
            });
        })
        .catch(() => { contactsContainer.innerHTML = "<div class='empty-state'>Could not load contacts.</div>"; });
}

saveContactBtn.addEventListener('click', () => {
    const name = contactNameInput.value.trim();
    const phone = contactPhoneInput.value.trim();
    const relation = contactRelationInput.value.trim();
    const telegramChatId = contactTelegramInput.value.trim();
    const priority = Number(contactPriorityInput.value) || 100;

    if (!name || !phone) {
        showToast("Enter a name and phone number.", "error");
        return;
    }

    fetch('/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: userId, name, phone, relation,
            telegram_chat_id: telegramChatId || null,
            priority,
            notify_call: contactNotifyCall.checked,
            notify_telegram: contactNotifyTelegram.checked,
        })
    })
    .then(res => { if (!res.ok) throw new Error(); return res.json(); })
    .then(() => {
        contactNameInput.value = "";
        contactPhoneInput.value = "";
        contactRelationInput.value = "";
        contactTelegramInput.value = "";
        contactNotifyCall.checked = true;
        contactNotifyTelegram.checked = true;
        chatPicker.hidden = true;
        loadContacts();
        loadReadiness();
        showToast(`${name} added to your safety network.`, "success");
    })
    .catch(() => showToast("Could not save that contact. Check the backend is running.", "error"));
});

window.deleteContact = function(id) {
    fetch(`/contacts/${id}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
        .then(() => { loadContacts(); loadReadiness(); showToast("Contact removed.", "info"); })
        .catch(() => showToast("Could not remove that contact.", "error"));
};

findChatsBtn.addEventListener('click', async () => {
    findChatsBtn.disabled = true;
    findChatsBtn.textContent = "Looking…";
    try {
        const res = await fetch('/telegram/chats');
        const data = await res.json();
        chatPicker.innerHTML = "";
        chatPicker.hidden = false;
        if (!data.configured) {
            chatPicker.innerHTML = "<div class='empty'>Telegram bot token isn't configured on the backend yet — paste TELEGRAM_BOT_TOKEN into backend/.env and restart.</div>";
        } else if (!data.chats || data.chats.length === 0) {
            chatPicker.innerHTML = `<div class="empty">${data.hint || "No chats yet — have your contact press Start on your bot, then try again."}</div>`;
        } else {
            data.chats.forEach(chat => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = `${chat.name}${chat.username ? ' (@' + chat.username + ')' : ''} — ${chat.chat_id}`;
                btn.addEventListener('click', () => {
                    contactTelegramInput.value = chat.chat_id;
                    chatPicker.hidden = true;
                });
                chatPicker.appendChild(btn);
            });
        }
    } catch (e) {
        showToast("Could not reach the backend to list Telegram chats.", "error");
    } finally {
        findChatsBtn.disabled = false;
        findChatsBtn.textContent = "Find chats that started my bot";
    }
});

sendTestAlertBtn.addEventListener('click', async () => {
    sendTestAlertBtn.disabled = true;
    sendTestAlertBtn.textContent = "Sending…";
    testAlertResult.innerHTML = "";
    try {
        const res = await fetch('/escalation/test', {
            method: 'POST',
            body: new URLSearchParams({ user_id: userId, user_label: displayName }),
        });
        if (res.status === 400) {
            showToast("Add a contact first — there's nobody to test-alert yet.", "error");
            return;
        }
        if (res.status === 429) {
            showToast("A test alert already went out in the last minute. Wait before sending another.", "error");
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const incident = await res.json();
        const list = document.createElement('ul');
        list.className = 'escalation-attempts';
        renderEscalationAttempts(incident.attempts || [], list);
        testAlertResult.appendChild(list);
        showToast("Test alert sent — check the results below.", "success");
    } catch (e) {
        showToast("Test alert failed to reach the backend.", "error");
    } finally {
        sendTestAlertBtn.disabled = false;
        sendTestAlertBtn.textContent = "Send test alert to my contacts";
    }
});

// DEMO MODE DIRECT FILE INJECTION (Method B)
const demoWavButtons = document.querySelectorAll('.wav-btn');

demoWavButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
        const soundClass = btn.getAttribute('data-sound');

        try {
            // Fetch WAV file blob from static mounted /data endpoint
            let res = await fetch(`/data/processed/${soundClass}/${soundClass}_esc50_000.wav`);
            if (!res.ok) {
                res = await fetch(`/data/synthetic/${soundClass}/${soundClass}_000.wav`);
                if (!res.ok) throw new Error("Could not find WAV file in processed or synthetic folders.");
            }

            const wavBlob = await res.blob();

            // Play audio natively in browser so the user can hear the demo
            const audioUrl = URL.createObjectURL(wavBlob);
            const audio = new Audio(audioUrl);
            audio.play().catch(e => console.warn("Audio playback failed (browser auto-play policy):", e));

            const mediaPlayback = document.getElementById('ctx-media').checked;
            const suddenMotion = document.getElementById('ctx-motion').checked;

            // Post direct into inference pipeline
            const formData = new FormData();
            formData.append("file", wavBlob, "inject.wav");
            formData.append("duration", 5.0); // Send 5s to run full pipeline
            formData.append("media_playback", mediaPlayback);
            formData.append("sudden_motion", suddenMotion);
            formData.append("sensitivity_threshold", sensitivityThreshold());
            formData.append("user_id", userId);
            formData.append("context_source", "browser_manual");
            formData.append("profile", modelProfile);

            // Switch screen to Monitor to show live changes
            switchScreen('monitor');
            monClass.innerText = "ANALYZING...";

            const detectRes = await fetch("/detect", { method: "POST", body: formData });
            if (!detectRes.ok) throw new Error(`Detection failed (${detectRes.status})`);
            const data = await detectRes.json();

            updateUIForClass(
                data.candidate,
                data.primary_confidence,
                data.verification_confidence,
                data.risk_score,
                data.risk_level
            );

            if (data.verified) {
                await logVerifiedEvent(data);
            }
            if (data.verified && data.should_alert) {
                setTimeout(() => triggerAlertModal(data, wavBlob), 800);
            } else if (data.verified && data.media_suppressed) {
                lastEventDetails.innerText = "Verified demo sound recorded as likely media playback; no critical alert shown.";
            }
        } catch (e) {
            showToast(`Sample injection failed: ${e.message}`, "error");
        }
    });
});

// Demo Mic mode trigger
const demoMicBtn = document.getElementById('demo-mic-btn');
let demoMicActive = false;

demoMicBtn.addEventListener('click', async () => {
    if (demoMicActive) {
        demoMicActive = false;
        demoMicBtn.innerText = "Start Live Demo Listening";
        demoMicBtn.classList.remove('active');
        stopMonitoring();
    } else {
        switchScreen('monitor');
        const started = await startMonitoring();
        if (started) {
            demoMicActive = true;
            demoMicBtn.innerText = "Listening... Click to Stop";
            demoMicBtn.classList.add('active');
        }
    }
});
