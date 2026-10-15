/**
 * LAMMPS AI Research Suite — Client Logic, WebGL2 Liquid Sphere, Drag & Drop Files & Motion Primitives
 */

// Attach the per-session CSRF token (minted into index.html by the local server) to every
// same-origin API request. The server rejects state-changing requests without it.
(function installSessionTokenFetch() {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const url = typeof input === "string" ? input : (input && input.url) || "";
        const sameOriginApi = url.startsWith("/api/") || url.startsWith(window.location.origin + "/api/");
        if (sameOriginApi) {
            init = Object.assign({}, init || {});
            const headers = new Headers(init.headers || {});
            if (!headers.has("X-Session-Token")) headers.set("X-Session-Token", window.__SESSION_TOKEN__ || "");
            init.headers = headers;
        }
        return nativeFetch(input, init);
    };
})();

let activeConversationId = null;
let currentPendingScript = null;
let currentAssumptions = [];
let currentPlotData = null;
let activeTab = "tab-overview";
let attachedChatFile = null;

let currentSimParams = {
    material: "Aluminum", element: "Al", lattice_a: 4.05, mass: 26.9815,
    pot_file: "Al_zhou.eam.alloy", temp_target: 900, temp_start: 300,
    dt: 0.001, steps: 2000, ensemble: "NVT", lattice_size: 4
};

let orbit3D = {
    rotX: 0.45, rotY: -0.65, zoom: 1.0, isDragging: false,
    lastMouseX: 0, lastMouseY: 0, autoRotate: true,
    atoms: []
};

let runnerChartMode = "Temp";

// =========================================================================
// Initialization
// =========================================================================

window.addEventListener("DOMContentLoaded", () => {
    initTopSlidingDock();
    initMotionPrimitives();
    initFileDropzones();
    initSpotlightCards();
    initScrollReveal();
    initExactKiddybankSphere();
    fetchSystemStatus();
    loadConversations();
    initWorkspace();
    updateParamPreview();
    updateDoctorLineCount();
    updateStandalone3D();
    switchOsTab('win');

    const textarea = document.getElementById("user-prompt");
    if (textarea) {
        textarea.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitUserMessage();
            }
        });
    }
});

// =========================================================================
// Top Sliding Glass Capsule Pill Dock
// =========================================================================

function initTopSlidingDock() {
    const pill = document.getElementById("nav-pill-active");
    const items = document.querySelectorAll(".dock-text-item");
    if (!pill || !items.length) return;

    function positionPill(activeItem) {
        if (!activeItem) return;
        pill.style.left = `${activeItem.offsetLeft}px`;
        pill.style.width = `${activeItem.offsetWidth}px`;
    }

    const activeInitial = document.querySelector(".dock-text-item.active");
    if (activeInitial) positionPill(activeInitial);

    window.activateTab = function(tabId) {
        activeTab = tabId;
        document.querySelectorAll(".tab-view").forEach(v => v.classList.remove("active"));
        items.forEach(i => i.classList.remove("active"));

        const targetView = document.getElementById(tabId);
        if (targetView) targetView.classList.add("active");

        const matchingDockItem = document.querySelector(`.dock-text-item[data-tab="${tabId}"]`);
        if (matchingDockItem) {
            matchingDockItem.classList.add("active");
            positionPill(matchingDockItem);
        }

        if (tabId === "tab-visualizer") {
            setTimeout(updateStandalone3D, 50);
        }
        if (tabId === "tab-runner") {
            setTimeout(initTrajViewerIfNeeded, 50);
        }

        window.scrollTo({ top: 0, behavior: "smooth" });
    };
    window.switchTab = window.activateTab;

    items.forEach(item => {
        item.addEventListener("click", () => {
            activateTab(item.dataset.tab);
        });
    });

    document.querySelectorAll("[data-tab]").forEach(el => {
        if (!el.classList.contains("dock-text-item")) {
            el.addEventListener("click", (e) => {
                e.preventDefault();
                activateTab(el.dataset.tab);
            });
        }
    });

    window.addEventListener("resize", () => {
        const active = document.querySelector(".dock-text-item.active");
        if (active) positionPill(active);
    });
}

function switchStudioSubtab(subtabId) {
    document.querySelectorAll(".subtab-panel").forEach(p => {
        p.classList.remove("active");
        p.style.display = "none";
    });
    document.querySelectorAll(".sub-dock-item").forEach(b => b.classList.remove("active"));

    const targetSubtab = document.getElementById(subtabId);
    if (targetSubtab) {
        targetSubtab.classList.add("active");
        targetSubtab.style.display = "block";
    }

    const btn = document.querySelector(`.sub-dock-item[data-subtab="${subtabId}"]`);
    if (btn) btn.classList.add("active");
}

// =========================================================================
// Drag & Drop File Upload System
// =========================================================================

function initFileDropzones() {
    // 1. Script Doctor Dropzone
    const docDropzone = document.getElementById("doctor-dropzone");
    if (docDropzone) {
        ["dragenter", "dragover"].forEach(eventName => {
            docDropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                docDropzone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach(eventName => {
            docDropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                docDropzone.classList.remove("drag-over");
            });
        });

        docDropzone.addEventListener("drop", (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                processDoctorFile(files[0]);
            }
        });
    }

    // 2. Chat Prompt Dropzone
    const chatDropzone = document.getElementById("chat-dropzone");
    if (chatDropzone) {
        ["dragenter", "dragover"].forEach(eventName => {
            chatDropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                chatDropzone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach(eventName => {
            chatDropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                chatDropzone.classList.remove("drag-over");
            });
        });

        chatDropzone.addEventListener("drop", (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                processChatFile(files[0]);
            }
        });
    }
}

function handleDoctorFileInput(e) {
    const file = e.target.files?.[0];
    if (file) processDoctorFile(file);
}

function processDoctorFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        const textarea = document.getElementById("doctor-input");
        if (textarea) {
            textarea.value = content;
            updateDoctorLineCount();
        }

        const infoDiv = document.getElementById("doctor-drop-file-info");
        const nameSpan = document.getElementById("doctor-drop-filename");
        const sizeSpan = document.getElementById("doctor-drop-filesize");

        if (infoDiv && nameSpan && sizeSpan) {
            infoDiv.classList.remove("hidden");
            nameSpan.innerText = file.name;
            sizeSpan.innerText = `${(file.size / 1024).toFixed(1)} KB`;
        }

        showToast(`Loaded ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);
    };
    reader.readAsText(file);
}

function handleChatFileInput(e) {
    const file = e.target.files?.[0];
    if (file) processChatFile(file);
}

function processChatFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        attachedChatFile = { name: file.name, size: file.size, content: content };

        const badge = document.getElementById("chat-file-badge");
        const nameSpan = document.getElementById("chat-file-name");
        const sizeSpan = document.getElementById("chat-file-size");

        if (badge && nameSpan && sizeSpan) {
            badge.classList.remove("hidden");
            badge.classList.add("flex");
            nameSpan.innerText = file.name;
            sizeSpan.innerText = `(${(file.size / 1024).toFixed(1)} KB)`;
        }

        const promptInput = document.getElementById("user-prompt");
        if (promptInput && !promptInput.value.trim()) {
            promptInput.value = `Please analyze and diagnose this attached LAMMPS script:`;
        }

        showToast(`Attached ${file.name}`);
    };
    reader.readAsText(file);
}

function removeChatAttachedFile() {
    attachedChatFile = null;
    const badge = document.getElementById("chat-file-badge");
    if (badge) {
        badge.classList.add("hidden");
        badge.classList.remove("flex");
    }
    const fileInput = document.getElementById("chat-file-input");
    if (fileInput) fileInput.value = "";
}

function handleRunnerFileInput(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
        const content = evt.target.result;
        showToast(`Loaded script ${file.name} — starting execution`);
        executeFromChat(content);
    };
    reader.readAsText(file);
}

function updateDoctorLineCount() {
    const textarea = document.getElementById("doctor-input");
    const countSpan = document.getElementById("doctor-line-counter");
    if (textarea && countSpan) {
        const lines = textarea.value ? textarea.value.split("\n").length : 0;
        countSpan.innerText = `${lines} ${lines === 1 ? 'line' : 'lines'}`;
    }
}

function clearDoctorInput() {
    const input = document.getElementById("doctor-input");
    if (input) input.value = "";
    updateDoctorLineCount();

    const infoDiv = document.getElementById("doctor-drop-file-info");
    if (infoDiv) infoDiv.classList.add("hidden");

    const resultCard = document.getElementById("doctor-result-card");
    if (resultCard) resultCard.style.display = "none";
}

// =========================================================================
// Motion Primitives: Counters, 3D Tilt & Magnetic Physics
// =========================================================================

function initMotionPrimitives() {
    initMagneticButtons();
    init3DTilt();
}

function initMagneticButtons() {
    document.querySelectorAll(".magnetic-btn").forEach(btn => {
        btn.addEventListener("mousemove", (e) => {
            const rect = btn.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            btn.style.transform = `translate(${x * 0.25}px, ${y * 0.25}px)`;
        });
        btn.addEventListener("mouseleave", () => {
            btn.style.transform = "translate(0px, 0px)";
        });
    });
}

function init3DTilt() {
    document.querySelectorAll(".tilt-card").forEach(card => {
        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;
            const tiltX = (x - 0.5) * 2;
            const tiltY = (y - 0.5) * 2;
            card.style.setProperty("--tilt-x", tiltX.toFixed(3));
            card.style.setProperty("--tilt-y", tiltY.toFixed(3));
        });
        card.addEventListener("mouseleave", () => {
            card.style.setProperty("--tilt-x", "0");
            card.style.setProperty("--tilt-y", "0");
        });
    });
}

function animateMotionCounters() {
    document.querySelectorAll(".motion-counter").forEach(counter => {
        const target = parseFloat(counter.getAttribute("data-target"));
        const prefix = counter.getAttribute("data-prefix") || "";
        const suffix = counter.getAttribute("data-suffix") || "";
        const duration = 1400;
        const startTime = performance.now();

        function update(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1.0);
            const easeOut = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(target * easeOut);

            counter.innerText = `${prefix}${current}${suffix}`;

            if (progress < 1.0) {
                requestAnimationFrame(update);
            } else {
                counter.innerText = `${prefix}${target}${suffix}`;
            }
        }
        requestAnimationFrame(update);
    });
}

function initSpotlightCards() {
    document.querySelectorAll(".glass-card").forEach(card => {
        card.addEventListener("mousemove", e => {
            const rect = card.getBoundingClientRect();
            card.style.setProperty("--mouse-x", `${((e.clientX - rect.left) / rect.width) * 100}%`);
            card.style.setProperty("--mouse-y", `${((e.clientY - rect.top) / rect.height) * 100}%`);
        });
    });
}

function initScrollReveal() {
    let countersAnimated = false;
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("revealed");
                if (!countersAnimated && entry.target.classList.contains("stats-banner")) {
                    animateMotionCounters();
                    countersAnimated = true;
                }
            }
        });
    }, { threshold: 0.12 });

    document.querySelectorAll(".scroll-reveal, .text-reveal-blur").forEach(el => observer.observe(el));
}

// =========================================================================
// System Status & Sessions
// =========================================================================

async function fetchSystemStatus() {
    try {
        const res = await fetch("/api/status", { method: "POST" });
        const data = await res.json();
        const statusText = document.getElementById("api-status-text");
        const statusDot = document.getElementById("api-status-dot");
        if (statusText) {
            if (data.gemini_ready) {
                statusText.innerText = `● Gemini Online (${data.gemini_model || "gemini-2.5-flash"})`;
                statusText.style.color = "#34d399";
                if (statusDot) statusDot.style.background = "#34d399";
            } else if (data.llm_available) {
                statusText.innerText = `● LLM Online (${data.llm_model})`;
                statusText.style.color = "#34d399";
                if (statusDot) statusDot.style.background = "#34d399";
            } else {
                statusText.innerText = "⚠️ Gemini Key Needed";
                statusText.style.color = "#fbbf24";
                if (statusDot) statusDot.style.background = "#fbbf24";
            }
        }
    } catch (e) {
        console.warn("Status check:", e);
    }
}

function openApiKeyModal() {
    const modal = document.getElementById("api-key-modal");
    if (modal) {
        modal.classList.remove("hidden");
        const input = document.getElementById("input-gemini-key");
        if (input) setTimeout(() => input.focus(), 50);
    }
}

function closeApiKeyModal() {
    const modal = document.getElementById("api-key-modal");
    if (modal) modal.classList.add("hidden");
    const status = document.getElementById("api-key-test-status");
    if (status) status.innerText = "";
}

async function saveApiKey() {
    const input = document.getElementById("input-gemini-key");
    const status = document.getElementById("api-key-test-status");
    const btn = document.getElementById("btn-save-key");
    const key = input?.value?.trim() || "";

    if (!key || key.length < 10) {
        if (status) {
            status.innerText = "Please enter a valid key";
            status.style.color = "#f87171";
        }
        return;
    }

    if (btn) btn.innerText = "Connecting...";
    if (status) {
        status.innerText = "Verifying...";
        status.style.color = "#94a3b8";
    }

    try {
        const res = await fetch("/api/key/set", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key, model: "gemini-2.5-flash" })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast("Gemini API Key connected successfully!", "success");
            closeApiKeyModal();
            fetchSystemStatus();
        } else {
            if (status) {
                status.innerText = data.detail || "Connection failed";
                status.style.color = "#f87171";
            }
            showToast("Failed to save API key", "error");
        }
    } catch (err) {
        if (status) {
            status.innerText = "Network error";
            status.style.color = "#f87171";
        }
        showToast("Error updating API key", "error");
    } finally {
        if (btn) btn.innerText = "Connect & Save";
    }
}

async function loadConversations() {
    try {
        const res = await fetch("/api/conversations");
        const data = await res.json();
    } catch (e) {
        console.warn(e);
    }
}

function startNewConversation() {
    activeConversationId = null;
    currentPendingScript = null;
    removeChatAttachedFile();
    activateTab("tab-chatbot");
    const viewport = document.getElementById("chat-messages");
    viewport.innerHTML = `
        <div class="glass-card">
          <h3 class="text-base font-bold text-white mb-2">New Research Session Started</h3>
          <p class="text-sm text-gray-300 leading-relaxed mb-4">
            What material, ensemble, or physical process would you like to simulate today?
          </p>
          <div class="grid-2">
            <button class="quick-prompt-card" onclick="askPredefined('Simulate molten aluminum at 1000 K using an NVT ensemble')">
              <span class="text-xl">⚛</span>
              <div class="text-left"><div class="text-xs font-bold text-white">Molten Aluminum</div><div class="text-[11px] text-gray-400">Post-melt NVT liquid equilibration</div></div>
            </button>
            <button class="quick-prompt-card" onclick="askPredefined('Simulate rigid SPC/E water at 300 K in NVT ensemble')">
              <span class="text-xl">💧</span>
              <div class="text-left"><div class="text-xs font-bold text-white">SPC/E Water Liquid</div><div class="text-[11px] text-gray-400">Rigid SHAKE + Coulombic solver</div></div>
            </button>
          </div>
        </div>
    `;
}

function askPredefined(text) {
    activateTab("tab-chatbot");
    document.getElementById("user-prompt").value = text;
    submitUserMessage();
}

// =========================================================================
// AI Chat Engine & Thinking Animation
// =========================================================================

let thinkingIntervalId = null;

function showThinkingIndicator() {
    const viewport = document.getElementById("chat-messages");
    if (!viewport) return;

    removeThinkingIndicator();

    const div = document.createElement("div");
    div.className = "flex justify-start max-w-2xl";
    div.id = "chat-thinking-indicator";
    div.innerHTML = `
        <div class="thinking-card w-full p-4 space-y-3">
          <div class="thinking-shimmer-bar"></div>
          
          <div class="flex items-center justify-between border-b border-white/[0.08] pb-2">
            <div class="flex items-center gap-2.5">
              <div class="pulse-orb"></div>
              <span class="text-xs font-bold text-white tracking-wide">LAMMPS Assistant</span>
              <span class="text-[10px] font-mono text-purple-300 bg-purple-500/20 border border-purple-500/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                <span>✨</span> Cloud Gemini
              </span>
            </div>
            <div class="thinking-dots-wave">
              <span class="thinking-dot"></span>
              <span class="thinking-dot"></span>
              <span class="thinking-dot"></span>
              <span class="thinking-dot"></span>
            </div>
          </div>

          <div class="flex items-center gap-3.5 py-1">
            <div class="thinking-atom-spinner flex-shrink-0">
              <div class="thinking-atom-ring"></div>
              <div class="thinking-atom-ring"></div>
              <div class="thinking-atom-core"></div>
            </div>
            <div class="space-y-0.5 min-w-0 flex-1">
              <div class="text-xs font-semibold text-gray-200 flex items-center gap-1.5">
                <span>Reasoning over liquid-state physics</span>
                <span class="inline-block animate-pulse text-accent">...</span>
              </div>
              <div class="thinking-step-text truncate" id="thinking-step-label">
                Analyzing simulation intent & material parameters...
              </div>
            </div>
          </div>
        </div>
    `;

    viewport.appendChild(div);
    viewport.scrollTop = viewport.scrollHeight;

    const sendBtn = document.getElementById("btn-send");
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.classList.add("opacity-70", "cursor-not-allowed");
        sendBtn.innerHTML = `
          <span class="inline-block animate-spin text-sm">⚛</span>
          <span>Thinking...</span>
        `;
    }

    const steps = [
        "Analyzing simulation intent & material parameters...",
        "Querying Google Cloud Gemini (gemini-2.5-flash)...",
        "Retrieving liquid potential styles & ensemble constraints...",
        "Formulating molecular dynamics input syntax...",
        "Validating numerical stability & physical parameters..."
    ];
    let stepIndex = 0;
    thinkingIntervalId = setInterval(() => {
        stepIndex = (stepIndex + 1) % steps.length;
        const label = document.getElementById("thinking-step-label");
        if (label) {
            label.style.opacity = "0";
            setTimeout(() => {
                label.innerText = steps[stepIndex];
                label.style.opacity = "1";
            }, 180);
        }
    }, 1500);
}

function removeThinkingIndicator() {
    if (thinkingIntervalId) {
        clearInterval(thinkingIntervalId);
        thinkingIntervalId = null;
    }
    const indicator = document.getElementById("chat-thinking-indicator");
    if (indicator) {
        indicator.remove();
    }
    const sendBtn = document.getElementById("btn-send");
    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.classList.remove("opacity-70", "cursor-not-allowed");
        sendBtn.innerHTML = `<span>Send ⚡</span>`;
    }
}

async function submitUserMessage() {
    const promptInput = document.getElementById("user-prompt");
    let text = promptInput?.value?.trim() || "";

    if (attachedChatFile) {
        text = `${text}\n\n\`\`\`lammps\n# [Attached: ${attachedChatFile.name}]\n${attachedChatFile.content}\n\`\`\``;
        removeChatAttachedFile();
    }

    if (!text) return;

    appendUserMessage(text);
    if (promptInput) promptInput.value = "";

    showThinkingIndicator();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                conversation_id: activeConversationId,
                message: text
            })
        });

        const data = await res.json();
        activeConversationId = data.conversation_id;
        removeThinkingIndicator();
        appendAssistantMessage(data);
        loadConversations();
    } catch (err) {
        removeThinkingIndicator();
        showToast("Error communicating with assistant", "error");
    } finally {
        removeThinkingIndicator();
    }
}

function appendUserMessage(text) {
    const viewport = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = "flex justify-end";
    div.innerHTML = `
        <div class="max-w-2xl bg-gradient-to-r from-purple/40 to-accent/30 border border-accent/40 rounded-2xl rounded-tr-sm px-5 py-3.5 text-sm text-white shadow-lg">
            ${renderMarkdown(text)}
        </div>
    `;
    viewport.appendChild(div);
    viewport.scrollTop = viewport.scrollHeight;
}

function appendAssistantMessage(data) {
    const viewport = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = "flex justify-start max-w-3xl";

    let html = `<div class="glass-card w-full space-y-3">`;

    // Header
    html += `
        <div class="flex items-center justify-between border-b border-white/[0.06] pb-2">
            <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-accent"></span>
                <span class="text-xs font-bold text-white">LAMMPS Assistant</span>
            </div>
            ${data.source ? `<span class="text-[10px] font-mono text-gray-400 uppercase">${data.source}</span>` : ''}
        </div>
    `;

    // Markdown Answer
    if (data.answer) {
        html += `<div class="text-sm text-gray-200 leading-relaxed space-y-2">${renderMarkdown(data.answer)}</div>`;
    }

    // Generated / Repaired Script
    if (data.script) {
        html += `
            <div class="mt-3">
                <div class="flex items-center justify-between mb-1.5">
                    <span class="text-xs font-bold text-accent font-mono">LAMMPS INPUT SCRIPT</span>
                    <button class="text-xs text-gray-400 hover:text-white" onclick="navigator.clipboard.writeText(\`${escapeHtml(data.script)}\`); showToast('Copied to clipboard!');">📋 Copy</button>
                </div>
                <pre class="code-block text-xs">${escapeHtml(data.script)}</pre>
            </div>
        `;
    }

    // Execution Confirmation Action Button
    if (data.script && (data.requires_confirmation || (data.validation && data.validation.valid))) {
        currentPendingScript = data.script;
        html += `
            <div class="mt-4 pt-3 border-t border-white/[0.06] flex items-center justify-between">
                <span class="text-xs text-emerald font-mono">✓ Static Validation Passed</span>
                <button class="btn btn-primary btn-sm" onclick="executeFromChat(\`${escapeHtml(data.script)}\`)">
                    <span>⚡ Authorize & Run Simulation</span>
                </button>
            </div>
        `;
    }

    // Citations
    if (data.citations && data.citations.length > 0) {
        html += `
            <div class="text-[11px] text-gray-400 pt-2 border-t border-white/[0.06]">
                <span>Sources: </span>
                ${data.citations.map(c => `<span class="font-mono text-gray-300 mr-2">[${escapeHtml(c)}]</span>`).join('')}
            </div>
        `;
    }

    html += `</div>`;
    div.innerHTML = html;
    viewport.appendChild(div);
    viewport.scrollTop = viewport.scrollHeight;
}

// =========================================================================
// Interactive Parameter Builder
// =========================================================================

function updateParamPreview() {
    const temp = parseFloat(document.getElementById("param-temp-slider")?.value || 900);
    const tstart = parseFloat(document.getElementById("param-tstart-slider")?.value || 300);
    const dt = document.getElementById("param-dt-select")?.value || "0.001";
    const steps = parseInt(document.getElementById("param-steps-slider")?.value || 2000);
    const lat = parseInt(document.getElementById("param-lattice-slider")?.value || 4);

    const tempDisp = document.getElementById("val-temp-display");
    if (tempDisp) tempDisp.innerText = `${temp} K`;
    const tstartDisp = document.getElementById("val-tstart-display");
    if (tstartDisp) tstartDisp.innerText = `${tstart} K`;
    const stepsDisp = document.getElementById("val-steps-display");
    if (stepsDisp) stepsDisp.innerText = `${steps} steps`;
    const latDisp = document.getElementById("val-lat-display");
    if (latDisp) latDisp.innerText = `${lat} × ${lat} × ${lat} (${lat*lat*lat*4} atoms)`;

    currentSimParams.temp_target = temp;
    currentSimParams.temp_start = tstart;
    currentSimParams.dt = parseFloat(dt);
    currentSimParams.steps = steps;
    currentSimParams.lattice_size = lat;

    const script = generateClientScript(currentSimParams);
    const codeEl = document.getElementById("param-script-code");
    if (codeEl) codeEl.innerText = script;
}

function selectEnsemble(ens) {
    currentSimParams.ensemble = ens;
    document.querySelectorAll(".ensemble-btn").forEach(b => b.classList.remove("active"));
    const btn = document.querySelector(`.ensemble-btn[data-ensemble="${ens}"]`);
    if (btn) btn.classList.add("active");
    updateParamPreview();
}

function generateClientScript(p) {
    let fixLine = "";
    if (p.ensemble === "NVE") fixLine = "fix             1 all nve";
    else if (p.ensemble === "NPT") fixLine = `fix             1 all npt temp ${p.temp_start} ${p.temp_target} 0.1 iso 0.0 0.0 1.0`;
    else fixLine = `fix             1 all nvt temp ${p.temp_start} ${p.temp_target} 0.1`;

    return `# ${p.material}: ${p.temp_start} K -> ${p.temp_target} K heating run (${p.ensemble}), starting from a crystal
# NOTE: a single short ramp from a perfect crystal does not guarantee a liquid; a periodic
# crystal superheats well past T_m. Ask the assistant for a "molten" script for a full melt protocol.
units           metal
boundary        p p p
atom_style      atomic

lattice         fcc ${p.lattice_a}
region          simbox block 0 ${p.lattice_size} 0 ${p.lattice_size} 0 ${p.lattice_size}
create_box      1 simbox
create_atoms    1 box
mass            1 ${p.mass}

velocity        all create ${p.temp_start} 4928459 rot yes mom yes dist gaussian

pair_style      eam/alloy
pair_coeff      * * ${p.pot_file} ${p.element}

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

timestep        ${p.dt}

thermo_style    custom step temp pe ke etotal press vol
thermo          50

${fixLine}

run             ${p.steps}
`;
}

// =========================================================================
// Diagnostic Error Analyzer & Script Doctor
// =========================================================================

function openErrorAnalyzer() {
    activateTab("tab-studio");
    switchStudioSubtab("studio-doctor");
    const input = document.getElementById("doctor-input");
    if (input && !input.value.trim()) {
        loadDoctorPreset("lost_atoms");
    }
    const container = document.getElementById("studio-doctor");
    if (container) container.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openScriptDoctor() {
    activateTab("tab-studio");
    switchStudioSubtab("studio-doctor");
    const input = document.getElementById("doctor-input");
    if (input && !input.value.trim()) {
        loadDoctorPreset("timestep");
    }
    const container = document.getElementById("studio-doctor");
    if (container) container.scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadDoctorPreset(type) {
    const input = document.getElementById("doctor-input");
    if (!input) return;

    if (type === "timestep") {
        input.value = `# Broken: Dangerous timestep in metal units (0.08 ps will explode)
units           metal
atom_style      atomic
lattice         fcc 4.05
region          box block 0 4 0 4 0 4
create_box      1 box
create_atoms    1 box
mass            1 26.98
pair_style      eam/alloy
pair_coeff      * * Al_zhou.eam.alloy Al
timestep        0.08
run             500`;
    } else if (type === "missing_pot") {
        input.value = `# Broken: Missing pair_coeff command and missing boundary condition
units           metal
atom_style      atomic
lattice         fcc 3.615
region          box block 0 4 0 4 0 4
create_box      1 box
create_atoms    1 box
pair_style      eam/alloy
run             100`;
    } else if (type === "lost_atoms") {
        input.value = `ERROR: Lost atoms: original 256 current 238
Last thermo step:
Step Temp E_pair E_mol TotEng Press
50 2400.2 -782.1 0.0 -740.2 4892.1
Simulation terminated prematurely due to unphysical atomic velocities.`;
    }
    updateDoctorLineCount();
}

async function submitDoctorScript() {
    const input = document.getElementById("doctor-input");
    const script = input?.value?.trim();
    if (!script) {
        showToast("Please drop or paste a script or traceback first", "error");
        return;
    }

    const btn = document.getElementById("btn-doctor-run");
    const resultCard = document.getElementById("doctor-result-card");
    const diagText = document.getElementById("doctor-diagnosis-text");
    const fixedCode = document.getElementById("doctor-fixed-code");
    const statusTitle = document.getElementById("doctor-status-title");

    if (btn) btn.innerHTML = `<span>⏳ Analyzing & Repairing...</span>`;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                conversation_id: activeConversationId,
                message: script
            })
        });

        const data = await res.json();
        activeConversationId = data.conversation_id;

        if (btn) btn.innerHTML = `<span>🔍 Analyze & Automatically Fix Script</span>`;

        if (resultCard) {
            resultCard.style.display = "block";
            resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }

        if (statusTitle) {
            statusTitle.innerText = data.script ? "Diagnosis Complete — Repaired Script Ready" : "Diagnostic Analysis Results";
        }

        if (diagText) {
            diagText.innerHTML = renderMarkdown(data.answer || "Diagnostic review generated.");
        }

        if (fixedCode) {
            fixedCode.innerText = data.script || script;
        }

        showToast("Doctor analysis complete!");
    } catch (e) {
        if (btn) btn.innerHTML = `<span>🔍 Analyze & Automatically Fix Script</span>`;
        showToast("Error running Script Doctor: " + e.message, "error");
    }
}

// =========================================================================
// Simulation Execution & Runner
// =========================================================================

async function executeCustomizedSimulation() {
    const script = generateClientScript(currentSimParams);
    executeFromChat(script);
}

async function executeFromChat(script, startRun) {
    activateTab("tab-runner");
    const statusPill = document.getElementById("runner-status-pill");
    const outContainer = document.getElementById("runner-output-container");
    const terminalPre = document.getElementById("runner-terminal-pre");
    const terminalStatus = document.getElementById("runner-terminal-status");
    const syntheticBanner = document.getElementById("runner-synthetic-banner");
    const ovitoCard = document.getElementById("runner-ovito-card");

    statusPill.className = "badge badge-info";
    statusPill.innerText = "RUNNING";
    // Reset the synthetic-data banner; it is re-shown only if this run's handshake says so
    if (syntheticBanner) syntheticBanner.classList.add("hidden");

    if (terminalPre) terminalPre.innerText = "┌──(lammps㉿wsl2)-[~/simulations]\n└─$ lmp -in in.run -log log.lammps\n[Live stdout mirror connected via Server-Sent Events]\n══════════════════════════════════════════════════════════════════════════════════════════════\n";
    if (terminalStatus) terminalStatus.innerText = "Running...";
    if (syntheticBanner) syntheticBanner.classList.add("hidden");
    if (ovitoCard) ovitoCard.classList.add("hidden");

    const btnSim = document.getElementById("btn-traj-run-sim");
    if (btnSim) {
        btnSim.disabled = true;
        btnSim.innerHTML = `<span class="inline-block animate-spin">⚡</span><span>Running Live...</span>`;
    }

    // Initialize WebGL2 Trajectory Viewer if needed
    initTrajViewerIfNeeded();
    if (window.activeTrajViewer) {
        window.activeTrajViewer.reset();
        const playIcon = document.getElementById("traj-play-icon");
        if (playIcon) playIcon.innerText = "▶ Play";
    }

    outContainer.innerHTML = `
        <div class="molecular-loader-stage flex flex-col items-center justify-center py-8 space-y-4">
            <div class="molecular-skeleton-spinner relative w-20 h-20 flex items-center justify-center">
                <div class="mol-ring ring-1"></div>
                <div class="mol-ring ring-2"></div>
                <div class="mol-ring ring-3"></div>
                <div class="atom-center">⚛</div>
            </div>
            <div class="text-center space-y-1">
                <div class="text-xs font-bold text-white font-mono flex items-center justify-center gap-2">
                    <span class="animate-pulse text-accent">⚡</span>
                    <span id="runner-stage-text">Initializing Molecular Dynamics Engine...</span>
                </div>
                <div class="text-[11px] text-gray-400 font-mono">Live stream connected via Server-Sent Events</div>
            </div>
        </div>
    `;

    try {
        const sessionToken = window.__SESSION_TOKEN__ || "";
        // startRun (optional): starts the run another way, e.g. the Parameter Runs tab
        const res = startRun ? await startRun(sessionToken) : await fetch("/api/run", {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "X-Session-Token": sessionToken
            },
            body: JSON.stringify({ script: script, session_token: sessionToken })
        });
        const data = await res.json();

        if (!res.ok || !data.run_id) {
            statusPill.className = "badge badge-danger";
            statusPill.innerText = "FAILED";
            outContainer.innerHTML = `
                <div class="p-3 bg-red-950/30 border border-red-500/30 rounded-lg text-xs font-mono text-red-300">
                    Execution error: ${escapeHtml(data.error || data.detail || "Unable to start simulation")}
                </div>
            `;
            showToast("Failed to start run: " + (data.error || "Error"), "error");
            return;
        }

        const runId = data.run_id;
        const sseUrl = `/api/run/stream?run_id=${encodeURIComponent(runId)}&token=${encodeURIComponent(sessionToken)}`;
        const es = new EventSource(sseUrl);

        es.addEventListener("handshake", (e) => {
            try {
                const handshake = JSON.parse(e.data);
                if (terminalStatus) terminalStatus.innerText = `Connected: ${handshake.engine}`;
                if (handshake.is_synthetic && syntheticBanner) {
                    syntheticBanner.classList.remove("hidden");
                }
                if (window.activeTrajViewer) {
                    window.activeTrajViewer.setMetadata({
                        ...(handshake.visual_metadata || {}),
                        units: handshake.units,
                        available_fields: handshake.available_fields,
                        is_synthetic: handshake.is_synthetic
                    });
                }
                updateTrajFieldModeButtons(handshake.available_fields, handshake.is_synthetic);
            } catch (err) {
                console.warn("Handshake parse error", err);
            }
        });

        es.addEventListener("log", (e) => {
            try {
                const logData = JSON.parse(e.data);
                if (terminalPre && logData.line) {
                    terminalPre.innerText += logData.line + "\n";
                    terminalPre.scrollTop = terminalPre.scrollHeight;
                }
            } catch (err) {
                console.warn("Log parse error", err);
            }
        });

        es.addEventListener("frame", (e) => {
            try {
                const frameData = JSON.parse(e.data);
                if (window.activeTrajViewer) {
                    window.activeTrajViewer.addFrame(frameData);
                }
            } catch (err) {
                console.warn("Frame parse error", err);
            }
        });

        es.addEventListener("done", (e) => {
            es.close();
            try {
                const doneData = JSON.parse(e.data);
                handleRunDone(doneData);
            } catch (err) {
                console.warn("Done parse error", err);
            }
        });

        es.onerror = (err) => {
            console.warn("SSE stream closed or error", err);
            es.close();
        };

    } catch (e) {
        statusPill.className = "badge badge-danger";
        statusPill.innerText = "ERROR";
        outContainer.innerHTML = `<div class="text-xs text-red-400 font-mono p-3">Communication Error: ${escapeHtml(e.message)}</div>`;
        showToast("Communication error: " + e.message, "error");
    }
}

function handleRunDone(data) {
    const statusPill = document.getElementById("runner-status-pill");
    const outContainer = document.getElementById("runner-output-container");
    const terminalStatus = document.getElementById("runner-terminal-status");
    const syntheticBanner = document.getElementById("runner-synthetic-banner");
    const ovitoCard = document.getElementById("runner-ovito-card");

    if (data.is_synthetic && syntheticBanner) {
        syntheticBanner.classList.remove("hidden");
    }

    if (data.status === "completed") {
        statusPill.className = "badge badge-success";
        statusPill.innerText = "COMPLETED";
        if (terminalStatus) terminalStatus.innerText = `Completed in ${data.runtime_seconds}s`;

        if (data.thermo && data.thermo.parsed) {
            currentPlotData = data.thermo.time_series;
            let headerInfo = `
                <div class="mb-3 flex items-center justify-between text-xs font-mono border-b border-white/10 pb-2">
                    <span class="text-emerald-400 font-bold">✓ Simulation Completed (${data.runtime_seconds}s)</span>
                    <span class="text-gray-400 font-bold">${data.engine || "Local LAMMPS Engine"}</span>
                </div>
            `;
            outContainer.innerHTML = headerInfo + renderThermoTable(data.thermo.summary);
            drawRunnerChart(runnerChartMode);
        } else {
            outContainer.innerHTML = `
                <div class="mb-2 text-xs font-mono text-emerald-400 font-bold">✓ Execution Succeeded (${data.runtime_seconds}s)</div>
                <div class="text-xs text-gray-400 font-mono">Output logged to live mirror above.</div>
            `;
        }

        // Render OVITO card if available
        if (data.render_available && data.render_url && ovitoCard) {
            ovitoCard.classList.remove("hidden");
            const img = document.getElementById("runner-ovito-image");
            if (img) img.src = data.render_url;
            const histEl = document.getElementById("runner-ovito-hist");
            if (histEl && data.coordination_histogram) {
                let html = "<div class='grid grid-cols-4 gap-2 text-center'>";
                for (const [cn, count] of Object.entries(data.coordination_histogram)) {
                    html += `<div class='bg-white/5 p-1.5 rounded'><div class='text-accent font-bold'>CN ${cn}</div><div class='text-gray-300'>${count}</div></div>`;
                }
                html += "</div>";
                histEl.innerHTML = html;
            }
        }

        const btnSim = document.getElementById("btn-traj-run-sim");
        if (btnSim) {
            btnSim.disabled = false;
            btnSim.innerHTML = `<span>🚀 Run WebGL Simulation</span>`;
        }

        if (window.activeTrajViewer && window.activeTrajViewer.frames.length > 1) {
            window.activeTrajViewer.play();
            const playIcon = document.getElementById("traj-play-icon");
            if (playIcon) playIcon.innerText = "⏸ Pause";
        }

        showToast("Simulation completed successfully!", "success");
    } else {
        const btnSim = document.getElementById("btn-traj-run-sim");
        if (btnSim) {
            btnSim.disabled = false;
            btnSim.innerHTML = `<span>🚀 Run WebGL Simulation</span>`;
        }
        statusPill.className = "badge badge-danger";
        statusPill.innerText = (data.status || "FAILED").toUpperCase();
        if (terminalStatus) terminalStatus.innerText = `Failed: ${data.error || "Error"}`;
        outContainer.innerHTML = `
            <div class="space-y-3">
                <div class="text-xs font-bold text-red-400 font-mono flex items-center gap-2">
                    <span>⚠️ Execution Terminated</span>
                    <span class="text-gray-400 font-normal">(${data.runtime_seconds || 0}s)</span>
                </div>
                <div class="text-xs text-red-300 font-mono bg-red-950/30 border border-red-500/30 rounded-lg p-3">
                    ${escapeHtml(data.error || "Simulation could not complete.")}
                </div>
            </div>
        `;
        showToast("Simulation run error: " + (data.error || "Failed"), "error");
    }
}

function toggleTrajectoryPlay() {
    if (!window.activeTrajViewer) return;
    window.activeTrajViewer.togglePlay();
    const icon = document.getElementById("traj-play-icon");
    if (icon) {
        icon.innerText = window.activeTrajViewer.isPlaying ? "⏸ Pause" : "▶ Play";
    }
}

function scrubTrajectory(val) {
    if (!window.activeTrajViewer) return;
    window.activeTrajViewer.pause();
    window.activeTrajViewer.seek(parseInt(val, 10));
    const icon = document.getElementById("traj-play-icon");
    if (icon) icon.innerText = "▶ Play";
}

function switchRunnerChartMode(mode) {
    runnerChartMode = mode;
    document.querySelectorAll("#runner-chart-modes .pill-tab-btn").forEach(b => b.classList.remove("active"));
    event.target.classList.add("active");
    drawRunnerChart(mode);
}

function drawRunnerChart(mode) {
    const canvas = document.getElementById("runner-chart-canvas");
    if (!canvas || !currentPlotData) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width, height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    let xData = currentPlotData["Step"] || [];
    let yData = currentPlotData[mode] || [];
    let lineColor = "#e040fb";

    if (mode === "Temp") { yData = currentPlotData["Temp"] || []; lineColor = "#ff4081"; }
    else if (mode === "Energy") { yData = currentPlotData["TotEng"] || currentPlotData["PotEng"] || []; lineColor = "#38bdf8"; }
    else if (mode === "Press") { yData = currentPlotData["Press"] || []; lineColor = "#34d399"; }
    else if (mode === "Density") {
        yData = currentPlotData["Density"] || currentPlotData["Density"] || currentPlotData["vol"] || currentPlotData["Volume"] || [];
        lineColor = "#fbbf24";
    }

    if (yData.length < 2) {
        ctx.fillStyle = "#64748b";
        ctx.font = "12px 'Plus Jakarta Sans'";
        ctx.fillText("Insufficient data points for curve plotting.", 30, 40);
        return;
    }

    const padding = { left: 60, right: 30, top: 30, bottom: 40 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const minX = Math.min(...xData), maxX = Math.max(...xData);
    const minY = Math.min(...yData), maxY = Math.max(...yData);
    const rangeX = (maxX - minX) || 1, rangeY = (maxY - minY) || 1;

    // Grid lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        ctx.fillStyle = "#64748b";
        ctx.font = "10px 'JetBrains Mono'";
        ctx.fillText((maxY - (rangeY / 4) * i).toFixed(2), 10, y + 4);
    }

    // Line curve
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    for (let i = 0; i < yData.length; i++) {
        const x = padding.left + ((xData[i] - minX) / rangeX) * chartW;
        const y = padding.top + chartH - ((yData[i] - minY) / rangeY) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
}

// =========================================================================
// 3D Orbital Liquid & Molecular Structure Visualizer
// =========================================================================

function updateStandalone3D() {
    const matSelect = document.getElementById("vis-mat-select");
    const tempSlider = document.getElementById("vis-temp-slider");
    const gridSlider = document.getElementById("vis-grid-slider");

    if (!matSelect || !tempSlider || !gridSlider) return;

    const mat = matSelect.value;
    const temp = parseFloat(tempSlider.value);
    const grid = parseInt(gridSlider.value);

    document.getElementById("vis-temp-display").innerText = `${temp} K`;
    document.getElementById("vis-grid-display").innerText = `${grid} × ${grid} × ${grid}`;

    const meltingPoints = {
        "Water": 273.15, "Argon": 83.8, "LJ": 1.0,
        "Aluminum": 933.47, "Copper": 1357.77, "Iron": 1811.0, "Nickel": 1728.0
    };
    const tmelt = meltingPoints[mat] || 900.0;
    const isMelted = temp >= tmelt || mat === "Water" || mat === "LJ" || mat === "Argon";

    const canvas = document.getElementById("standalone-vis-canvas");
    if (!canvas) return;

    orbit3D.atoms = [];
    orbit3D.bonds = [];
    let atomCount = 0;

    if (mat === "Water") {
        // Molecular Liquid: H2O triplets with covalent bonds
        const numMols = Math.max(8, grid * grid * 2);
        const boxSpan = 2.4;
        const spacing = (boxSpan * 2) / Math.cbrt(numMols);

        let mIdx = 0;
        const nSide = Math.ceil(Math.cbrt(numMols));
        for (let x = 0; x < nSide; x++) {
            for (let y = 0; y < nSide; y++) {
                for (let z = 0; z < nSide; z++) {
                    if (mIdx >= numMols) break;
                    mIdx++;

                    const ox = -boxSpan + (x + 0.5) * spacing + (Math.sin(x * 3 + y * 7 + z) * 0.15);
                    const oy = -boxSpan + (y + 0.5) * spacing + (Math.cos(y * 5 + z * 3) * 0.15);
                    const oz = -boxSpan + (z + 0.5) * spacing + (Math.sin(z * 4 + x * 2) * 0.15);

                    // Oxygen atom
                    atomCount++;
                    const oId = atomCount;
                    orbit3D.atoms.push({
                        id: oId,
                        x: ox, y: oy, z: oz,
                        baseX: ox, baseY: oy, baseZ: oz,
                        realX: (ox * 3.5).toFixed(2), realY: (oy * 3.5).toFixed(2), realZ: (oz * 3.5).toFixed(2),
                        element: "O", material: "Water (H2O)", role: "Oxygen (Center)",
                        color: "#ef4444", radiusScale: 1.15,
                        temp: temp.toFixed(1),
                        ke: ((3 / 2) * 8.617e-5 * temp).toFixed(4)
                    });

                    // Random orientation for the H2O triangle
                    const ang1 = mIdx * 1.618;
                    const ang2 = mIdx * 2.718;
                    const hDist = 0.35; // bond length scaled for visualization
                    const h1x = ox + hDist * Math.cos(ang1);
                    const h1y = oy + hDist * Math.sin(ang1);
                    const h1z = oz + hDist * 0.3;

                    const h2x = ox + hDist * Math.cos(ang1 + 1.82); // ~104.5 deg angle
                    const h2y = oy + hDist * Math.sin(ang1 + 1.82);
                    const h2z = oz - hDist * 0.2;

                    // Hydrogen 1
                    atomCount++;
                    const h1Id = atomCount;
                    orbit3D.atoms.push({
                        id: h1Id,
                        x: h1x, y: h1y, z: h1z,
                        baseX: h1x, baseY: h1y, baseZ: h1z,
                        realX: (h1x * 3.5).toFixed(2), realY: (h1y * 3.5).toFixed(2), realZ: (h1z * 3.5).toFixed(2),
                        element: "H", material: "Water (H2O)", role: "Hydrogen (Rigid SHAKE)",
                        color: "#f8fafc", radiusScale: 0.65,
                        temp: temp.toFixed(1),
                        ke: ((3 / 2) * 8.617e-5 * temp).toFixed(4)
                    });

                    // Hydrogen 2
                    atomCount++;
                    const h2Id = atomCount;
                    orbit3D.atoms.push({
                        id: h2Id,
                        x: h2x, y: h2y, z: h2z,
                        baseX: h2x, baseY: h2y, baseZ: h2z,
                        realX: (h2x * 3.5).toFixed(2), realY: (h2y * 3.5).toFixed(2), realZ: (h2z * 3.5).toFixed(2),
                        element: "H", material: "Water (H2O)", role: "Hydrogen (Rigid SHAKE)",
                        color: "#f8fafc", radiusScale: 0.65,
                        temp: temp.toFixed(1),
                        ke: ((3 / 2) * 8.617e-5 * temp).toFixed(4)
                    });

                    // Covalent bonds O-H1 and O-H2
                    orbit3D.bonds.push([oId, h1Id]);
                    orbit3D.bonds.push([oId, h2Id]);
                }
            }
        }
    } else {
        // Atomic Fluid / Molten Metal: FCC lattice below Tmelt; liquid disorder at or above Tmelt
        const elemColors = {
            "Argon": "#a855f7", "LJ": "#06b6d4",
            "Aluminum": "#38bdf8", "Copper": "#f97316",
            "Iron": "#eab308", "Nickel": "#10b981"
        };
        const elemSymbols = {
            "Argon": "Ar", "LJ": "LJ",
            "Aluminum": "Al", "Copper": "Cu",
            "Iron": "Fe", "Nickel": "Ni"
        };

        const col = elemColors[mat] || "#a855f7";
        const sym = elemSymbols[mat] || "M";
        const bound = Math.floor(grid / 2);
        const spacing = 1.35;

        for (let x = -bound; x <= bound; x++) {
            for (let y = -bound; y <= bound; y++) {
                for (let z = -bound; z <= bound; z++) {
                    if ((Math.abs(x + y + z) % 2 === 0)) {
                        atomCount++;
                        let ax = x * spacing;
                        let ay = y * spacing;
                        let az = z * spacing;

                        // If melted into liquid phase, apply liquid disorder
                        if (isMelted) {
                            const disorder = Math.min(0.7, 0.2 + (temp - tmelt) * 0.0004);
                            ax += (Math.sin(atomCount * 4.1 + x) - 0.5) * disorder;
                            ay += (Math.cos(atomCount * 2.7 + y) - 0.5) * disorder;
                            az += (Math.sin(atomCount * 3.3 + z) - 0.5) * disorder;
                        }

                        const phaseDesc = isMelted ? `Liquid (T >= Tmelt)` : `FCC Crystal (T < Tmelt)`;
                        orbit3D.atoms.push({
                            id: atomCount,
                            x: ax, y: ay, z: az,
                            baseX: ax, baseY: ay, baseZ: az,
                            realX: (ax * 3.8).toFixed(2), realY: (ay * 3.8).toFixed(2), realZ: (az * 3.8).toFixed(2),
                            element: sym, material: mat, role: phaseDesc,
                            color: col, radiusScale: 1.0,
                            temp: temp.toFixed(1),
                            ke: ((3 / 2) * 8.617e-5 * temp).toFixed(4)
                        });
                    }
                }
            }
        }
    }

    setup3DControls(canvas);
    render3DScene(canvas);
}

function setup3DControls(canvas) {
    canvas.onmousedown = (e) => {
        orbit3D.isDragging = true;
        orbit3D.autoRotate = false;
        orbit3D.lastMouseX = e.clientX;
        orbit3D.lastMouseY = e.clientY;
    };

    window.onmouseup = () => { orbit3D.isDragging = false; };

    canvas.onmousemove = (e) => {
        if (orbit3D.isDragging) {
            const dx = e.clientX - orbit3D.lastMouseX;
            const dy = e.clientY - orbit3D.lastMouseY;
            orbit3D.rotY += dx * 0.008;
            orbit3D.rotX += dy * 0.008;
            orbit3D.lastMouseX = e.clientX;
            orbit3D.lastMouseY = e.clientY;
            render3DScene(canvas);
        } else {
            const rect = canvas.getBoundingClientRect();
            checkAtomHover(e.clientX - rect.left, e.clientY - rect.top, e.clientX, e.clientY, canvas);
        }
    };

    canvas.onwheel = (e) => {
        e.preventDefault();
        orbit3D.zoom = Math.max(0.4, Math.min(3.0, orbit3D.zoom * (e.deltaY > 0 ? 0.9 : 1.1)));
        render3DScene(canvas);
    };

    canvas.onmouseleave = () => {
        document.getElementById("atom-tooltip-hud").style.display = "none";
    };
}

function render3DScene(canvas) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width, height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    const cx = width / 2, cy = height / 2;
    const scale = 40 * orbit3D.zoom;

    const cosX = Math.cos(orbit3D.rotX), sinX = Math.sin(orbit3D.rotX);
    const cosY = Math.cos(orbit3D.rotY), sinY = Math.sin(orbit3D.rotY);

    function transform(x, y, z) {
        const x1 = x * cosY + z * sinY;
        const z1 = -x * sinY + z * cosY;
        const y2 = y * cosX - z1 * sinX;
        const z2 = y * sinX + z1 * cosX;
        return { screenX: cx + x1 * scale, screenY: cy + y2 * scale, depth: z2 };
    }

    // Wireframe Box
    const b = 2.8;
    const corners = [
        [-b, -b, -b], [b, -b, -b], [b, b, -b], [-b, b, -b],
        [-b, -b, b], [b, -b, b], [b, b, b], [-b, b, b]
    ].map(c => transform(c[0], c[1], c[2]));

    const edges = [
        [0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],
        [0,4],[1,5],[2,6],[3,7]
    ];

    ctx.strokeStyle = "rgba(224, 64, 251, 0.22)";
    ctx.lineWidth = 1;
    edges.forEach(([i, j]) => {
        ctx.beginPath();
        ctx.moveTo(corners[i].screenX, corners[i].screenY);
        ctx.lineTo(corners[j].screenX, corners[j].screenY);
        ctx.stroke();
    });

    // Map atoms to projected screen coordinates
    const projectedMap = {};
    const projected = orbit3D.atoms.map(a => {
        const tr = transform(a.x, a.y, a.z);
        const item = { ...a, ...tr };
        projectedMap[a.id] = item;
        return item;
    });

    // Draw Molecular Covalent Bonds (e.g. O-H in water)
    if (orbit3D.bonds && orbit3D.bonds.length > 0) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
        ctx.lineWidth = Math.max(1.5, 2.5 * orbit3D.zoom);
        orbit3D.bonds.forEach(([i, j]) => {
            const p1 = projectedMap[i];
            const p2 = projectedMap[j];
            if (p1 && p2) {
                ctx.beginPath();
                ctx.moveTo(p1.screenX, p1.screenY);
                ctx.lineTo(p2.screenX, p2.screenY);
                ctx.stroke();
            }
        });
    }

    // Render depth-sorted atoms
    projected.sort((a, b) => a.depth - b.depth);

    projected.forEach(atom => {
        const baseR = (atom.radiusScale || 1.0) * 8.5;
        const radius = Math.max(3, baseR * (1 + atom.depth * 0.15) * orbit3D.zoom);

        const grad = ctx.createRadialGradient(
            atom.screenX - radius * 0.35, atom.screenY - radius * 0.35, radius * 0.1,
            atom.screenX, atom.screenY, radius
        );
        grad.addColorStop(0, "#ffffff");
        grad.addColorStop(0.3, atom.color || "#e040fb");
        grad.addColorStop(1, "#0a0512");

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(atom.screenX, atom.screenY, radius, 0, Math.PI * 2);
        ctx.fill();
    });
}

function checkAtomHover(mouseX, mouseY, clientX, clientY, canvas) {
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const scale = 40 * orbit3D.zoom;
    const cosX = Math.cos(orbit3D.rotX), sinX = Math.sin(orbit3D.rotX);
    const cosY = Math.cos(orbit3D.rotY), sinY = Math.sin(orbit3D.rotY);

    let closest = null;
    let minDist = 16;

    orbit3D.atoms.forEach(atom => {
        const x1 = atom.x * cosY + atom.z * sinY;
        const z1 = -atom.x * sinY + atom.z * cosY;
        const y2 = atom.y * cosX - z1 * sinX;
        const screenX = cx + x1 * scale;
        const screenY = cy + y2 * scale;
        const dist = Math.hypot(mouseX - screenX, mouseY - screenY);
        if (dist < minDist) {
            minDist = dist;
            closest = atom;
        }
    });

    const hud = document.getElementById("atom-tooltip-hud");
    if (closest && hud) {
        hud.style.display = "block";
        hud.style.left = `${clientX + 14}px`;
        hud.style.top = `${clientY + 14}px`;
        document.getElementById("hud-id").innerText = `Atom #${closest.id}`;
        document.getElementById("hud-elem").innerText = `${closest.element} (${closest.material})`;
        document.getElementById("hud-pos").innerText = `${closest.realX}, ${closest.realY}, ${closest.realZ} Å`;
        document.getElementById("hud-temp").innerText = `${closest.temp} K`;
        document.getElementById("hud-ke").innerText = `${closest.ke} eV`;
    } else if (hud) {
        hud.style.display = "none";
    }
}

function toggleStandaloneAutoRotate() {
    orbit3D.autoRotate = !orbit3D.autoRotate;
    if (orbit3D.autoRotate) requestAnimationFrame(autoRotateLoop);
}

function autoRotateLoop() {
    if (orbit3D.autoRotate) {
        orbit3D.rotY += 0.005;
        const canvas = document.getElementById("standalone-vis-canvas");
        if (canvas) render3DScene(canvas);
        requestAnimationFrame(autoRotateLoop);
    }
}

function adjustStandaloneZoom(factor) {
    orbit3D.zoom = Math.max(0.4, Math.min(3.0, orbit3D.zoom * factor));
    const canvas = document.getElementById("standalone-vis-canvas");
    if (canvas) render3DScene(canvas);
}

function resetStandaloneView() {
    orbit3D.rotX = 0.45;
    orbit3D.rotY = -0.65;
    orbit3D.zoom = 1.0;
    const canvas = document.getElementById("standalone-vis-canvas");
    if (canvas) render3DScene(canvas);
}

// =========================================================================
// EXACT 1:1 KIDDYBANK LIQUID NOISE-DISPLACED SPHERE & PARTICLE REVOLUTION
// =========================================================================

function initExactKiddybankSphere() {
    const canvas = document.getElementById("gl");
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", { antialias: true, alpha: true });
    if (!gl) return;

    // Minimal Mat4 Math
    const mat4 = {
        create() { return new Float32Array(16); },
        identity(o) { o.fill(0); o[0]=o[5]=o[10]=o[15]=1; return o; },
        perspective(o, fovy, aspect, near, far) {
            const f = 1.0 / Math.tan(fovy / 2), nf = 1 / (near - far);
            o.fill(0);
            o[0]=f/aspect; o[5]=f; o[10]=(far+near)*nf; o[11]=-1;
            o[14]=2*far*near*nf; return o;
        },
        lookAt(o, eye, center, up) {
            let z0=eye[0]-center[0], z1=eye[1]-center[1], z2=eye[2]-center[2];
            let len = Math.hypot(z0,z1,z2)||1e-6; z0/=len; z1/=len; z2/=len;
            let x0=up[1]*z2-up[2]*z1, x1=up[2]*z0-up[0]*z2, x2=up[0]*z1-up[1]*z0;
            len = Math.hypot(x0,x1,x2)||1e-6; x0/=len; x1/=len; x2/=len;
            const y0=z1*x2-z2*x1, y1=z2*x0-z0*x2, y2=z0*x1-z1*x0;
            o[0]=x0;o[1]=y0;o[2]=z0;o[3]=0;
            o[4]=x1;o[5]=y1;o[6]=z1;o[7]=0;
            o[8]=x2;o[9]=y2;o[10]=z2;o[11]=0;
            o[12]=-(x0*eye[0]+x1*eye[1]+x2*eye[2]);
            o[13]=-(y0*eye[0]+y1*eye[1]+y2*eye[2]);
            o[14]=-(z0*eye[0]+z1*eye[1]+z2*eye[2]);
            o[15]=1; return o;
        },
        normalFromMat4(o3, m) {
            o3[0]=m[0]; o3[1]=m[1]; o3[2]=m[2];
            o3[3]=m[4]; o3[4]=m[5]; o3[5]=m[6];
            o3[6]=m[8]; o3[7]=m[9]; o3[8]=m[10]; return o3;
        }
    };

    function buildIcosphere(subdivisions) {
        const t = (1 + Math.sqrt(5)) / 2;
        let verts = [
            [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
            [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
            [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
        ].map(v => { const l = Math.hypot(...v); return [v[0]/l, v[1]/l, v[2]/l]; });

        let faces = [
            [0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],
            [1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
            [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],
            [4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1],
        ];

        const midCache = new Map();
        function midpoint(i1, i2) {
            const key = i1 < i2 ? `${i1}_${i2}` : `${i2}_${i1}`;
            if (midCache.has(key)) return midCache.get(key);
            const a = verts[i1], b = verts[i2];
            let m = [(a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2];
            const l = Math.hypot(...m);
            m = [m[0]/l, m[1]/l, m[2]/l];
            verts.push(m);
            const idx = verts.length - 1;
            midCache.set(key, idx);
            return idx;
        }

        for (let s = 0; s < subdivisions; s++) {
            const newFaces = [];
            for (const [a, b, c] of faces) {
                const ab = midpoint(a, b), bc = midpoint(b, c), ca = midpoint(c, a);
                newFaces.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]);
            }
            faces = newFaces;
        }

        const positions = new Float32Array(verts.length * 3);
        const normals = new Float32Array(verts.length * 3);
        verts.forEach((v, i) => {
            positions[i*3]=v[0]; positions[i*3+1]=v[1]; positions[i*3+2]=v[2];
            normals[i*3]=v[0]; normals[i*3+1]=v[1]; normals[i*3+2]=v[2];
        });
        const indices = new Uint32Array(faces.length * 3);
        faces.forEach((f, i) => { indices[i*3]=f[0]; indices[i*3+1]=f[1]; indices[i*3+2]=f[2]; });

        return { positions, normals, indices };
    }

    function buildParticles(count) {
        const starts = new Float32Array(count * 3);
        const normals = new Float32Array(count * 3);
        const seeds = new Float32Array(count);
        for (let i = 0; i < count; i++) {
            const u = Math.random(), v = Math.random();
            const theta = 2 * Math.PI * u, phi = Math.acos(2 * v - 1);
            const nx = Math.sin(phi) * Math.cos(theta);
            const ny = Math.sin(phi) * Math.sin(theta);
            const nz = Math.cos(phi);

            const r = 3.0 + Math.pow(Math.random(), 0.5) * 7.0;
            starts[i*3]   = nx * r + (Math.random()-0.5) * 1.5;
            starts[i*3+1] = ny * r + (Math.random()-0.5) * 1.5;
            starts[i*3+2] = nz * r + (Math.random()-0.5) * 1.5;

            normals[i*3]=nx; normals[i*3+1]=ny; normals[i*3+2]=nz;
            seeds[i] = Math.random();
        }
        return { starts, normals, seeds, count };
    }

    const commonNoiseGLSL = `
        vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
        vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
        vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
        vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
        float snoise(vec3 v){
            const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
            vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
            vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
            vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
            i=mod289(i);
            vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
            float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
            vec4 j=p-49.0*floor(p*ns.z*ns.z);
            vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
            vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
            vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
            vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
            vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
            vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
            vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
            p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
            vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
            return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
        }
        float ridged(vec3 p){ return 1.0 - abs(snoise(p)); }
        float fbmRidged(vec3 p){
            vec3 warp = vec3(
                snoise(p * 0.45 + vec3(11.0, 2.0, 7.0)),
                snoise(p * 0.45 + vec3(31.0, 5.0, 19.0)),
                snoise(p * 0.45 + vec3(53.0, 9.0, 41.0))
            );
            vec3 pw = p + warp * 0.6;

            float sum=0.0, amp=0.75, freq=1.0;
            for (int i=0;i<3;i++){
                float r = ridged(pw*freq);
                r = pow(r, 1.15);
                sum += r*amp; freq *= 1.8; amp *= 0.32;
            }
            return sum;
        }
    `;

    const vertSrc = `#version 300 es
        precision highp float;
        layout(location=0) in vec3 aPosition;
        layout(location=1) in vec3 aNormal;
        uniform mat4 uModel, uView, uProjection;
        uniform mat3 uNormalMat;
        uniform float uTime, uAmplitude, uFrequency;
        out vec3 vNormalW, vPosW;
        out float vElevation;
        ${commonNoiseGLSL}
        vec3 displace(vec3 n, out float elev) {
            vec3 p = n * uFrequency + vec3(0.0, 0.0, uTime * 0.045);
            elev = fbmRidged(p) * uAmplitude;
            return aPosition + n * elev;
        }
        void main() {
            float elevation;
            vec3 displaced = displace(aNormal, elevation);

            float eps = 0.012;
            vec3 tangent = normalize(cross(aNormal, vec3(0.0, 1.0, 0.73)));
            vec3 bitangent = normalize(cross(aNormal, tangent));

            vec3 nT = normalize(aNormal + tangent * eps);
            vec3 dispT = aPosition + tangent * eps + aNormal * (fbmRidged(nT*uFrequency+vec3(0.0,0.0,uTime*0.045))*uAmplitude);
            vec3 nB = normalize(aNormal + bitangent * eps);
            vec3 dispB = aPosition + bitangent * eps + aNormal * (fbmRidged(nB*uFrequency+vec3(0.0,0.0,uTime*0.045))*uAmplitude);

            vec3 newNormal = normalize(cross(dispT - displaced, dispB - displaced));
            if (dot(newNormal, aNormal) < 0.0) newNormal = -newNormal;

            vElevation = elevation;
            vNormalW = normalize(uNormalMat * newNormal);
            vec4 worldPos = uModel * vec4(displaced, 1.0);
            vPosW = worldPos.xyz;
            gl_Position = uProjection * uView * worldPos;
        }
    `;

    const fragSrc = `#version 300 es
        precision highp float;
        in vec3 vNormalW, vPosW;
        in float vElevation;
        out vec4 fragColor;
        uniform vec3 uCameraPos, uLowColor, uMidColor, uHighColor, uLightDir;
        uniform float uOpacity;
        void main() {
            vec3 N = normalize(vNormalW);
            vec3 V = normalize(uCameraPos - vPosW);
            vec3 L = normalize(uLightDir);
            float h = clamp(vElevation * 1.9 + 0.28, 0.0, 1.0);
            vec3 base = mix(uLowColor, uMidColor, smoothstep(0.0, 0.55, h));
            base = mix(base, uHighColor, smoothstep(0.86, 1.0, h));

            float diff = max(dot(N, L), 0.0);
            vec3 halfV = normalize(L + V);
            float spec = pow(max(dot(N, halfV), 0.0), 40.0);
            float spec2 = pow(max(dot(N, halfV), 0.0), 180.0);
            float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.0);

            vec3 color = base * (0.5 + 0.65 * diff);
            color += vec3(1.0, 0.85, 1.0) * spec * 0.4;
            color += vec3(1.0) * spec2 * 0.6;
            color += uHighColor * fresnel * 0.5;

            fragColor = vec4(color, uOpacity);
        }
    `;

    const particleVertSrc = `#version 300 es
        precision highp float;
        layout(location=0) in vec3 aStart;
        layout(location=1) in vec3 aNormal;
        layout(location=2) in float aSeed;
        uniform mat4 uModel, uView, uProjection;
        uniform float uTime, uAmplitude, uFrequency, uProgress, uPixelRatio;
        out float vSeed, vProgress;
        ${commonNoiseGLSL}
        float easeOutCubic(float x) { return 1.0 - pow(1.0 - x, 3.0); }
        void main() {
            vec3 p = aNormal * uFrequency + vec3(0.0, 0.0, uTime * 0.045);
            float elev = fbmRidged(p) * uAmplitude;
            vec3 target = aNormal * (2.2 + elev * 2.2);
            float localT = clamp(uProgress * 1.35 - aSeed * 0.35, 0.0, 1.0);
            float e = easeOutCubic(localT);
            vec3 mid = mix(aStart, target, 0.5) + aNormal * (0.6 * sin(3.14159 * e) * (1.0 - e));
            vec3 pos = mix(mix(aStart, mid, min(e*2.0,1.0)), target, max(e*2.0-1.0,0.0));
            vSeed = aSeed; vProgress = e;
            vec4 worldPos = uModel * vec4(pos, 1.0);
            gl_Position = uProjection * uView * worldPos;
            float dist = -(uView * worldPos).z;
            gl_PointSize = uPixelRatio * mix(5.0, 1.6, e) * (300.0 / max(dist, 0.1)) * 0.06;
        }
    `;

    const particleFragSrc = `#version 300 es
        precision highp float;
        in float vSeed, vProgress;
        out vec4 fragColor;
        uniform float uOpacity;
        void main() {
            vec2 c = gl_PointCoord - 0.5;
            float d = length(c);
            if (d > 0.5) discard;
            float falloff = smoothstep(0.5, 0.0, d);
            vec3 hot = vec3(1.0, 0.9, 1.0);
            vec3 cool = vec3(0.85, 0.2, 0.95);
            vec3 col = mix(cool, hot, vProgress * 0.7 + 0.15 * vSeed);
            fragColor = vec4(col * falloff, falloff * uOpacity);
        }
    `;

    const glowVertSrc = `#version 300 es
        precision highp float;
        layout(location=0) in vec3 aPosition;
        layout(location=1) in vec3 aNormal;
        uniform mat4 uModel, uView, uProjection;
        uniform mat3 uNormalMat;
        out vec3 vN, vP;
        void main(){
            vN = normalize(uNormalMat * aNormal);
            vec4 wp = uModel * vec4(aPosition, 1.0);
            vP = wp.xyz;
            gl_Position = uProjection * uView * wp;
        }
    `;
    const glowFragSrc = `#version 300 es
        precision highp float;
        in vec3 vN, vP;
        uniform vec3 uCameraPos;
        out vec4 fragColor;
        void main(){
            vec3 V = normalize(uCameraPos - vP);
            float f = pow(1.0 - max(dot(normalize(vN), V), 0.0), 3.0);
            fragColor = vec4(vec3(0.85, 0.25, 1.0) * f, f * 0.65);
        }
    `;

    function compile(src, type) {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        return s;
    }
    function link(vs, fs) {
        const p = gl.createProgram();
        gl.attachShader(p, compile(vs, gl.VERTEX_SHADER));
        gl.attachShader(p, compile(fs, gl.FRAGMENT_SHADER));
        gl.linkProgram(p);
        return p;
    }

    function makeMesh(data) {
        const vao = gl.createVertexArray();
        gl.bindVertexArray(vao);
        const pb = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, pb);
        gl.bufferData(gl.ARRAY_BUFFER, data.positions, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

        const nb = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, nb);
        gl.bufferData(gl.ARRAY_BUFFER, data.normals, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(1);
        gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

        const ib = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, data.indices, gl.STATIC_DRAW);
        return { vao, count: data.indices.length };
    }

    function makeParticleMesh(data) {
        const vao = gl.createVertexArray();
        gl.bindVertexArray(vao);
        const sb = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, sb);
        gl.bufferData(gl.ARRAY_BUFFER, data.starts, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

        const nb = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, nb);
        gl.bufferData(gl.ARRAY_BUFFER, data.normals, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(1);
        gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

        const seedb = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, seedb);
        gl.bufferData(gl.ARRAY_BUFFER, data.seeds, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(2);
        gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 0, 0);
        return { vao, count: data.count };
    }

    const sphereGeom = buildIcosphere(6);
    const glowGeom = buildIcosphere(3);
    for (let i = 0; i < glowGeom.positions.length; i++) glowGeom.positions[i] *= 1.16;

    const sphereMesh = makeMesh(sphereGeom);
    const glowMesh = makeMesh(glowGeom);
    const particleMesh = makeParticleMesh(buildParticles(9000));

    const mainProgram = link(vertSrc, fragSrc);
    const glowProgram = link(glowVertSrc, glowFragSrc);
    const particleProgram = link(particleVertSrc, particleFragSrc);

    function uniLoc(prog, name) { return gl.getUniformLocation(prog, name); }
    const mainU = {
        model: uniLoc(mainProgram,'uModel'), view: uniLoc(mainProgram,'uView'), proj: uniLoc(mainProgram,'uProjection'),
        normalMat: uniLoc(mainProgram,'uNormalMat'), time: uniLoc(mainProgram,'uTime'),
        amplitude: uniLoc(mainProgram,'uAmplitude'), frequency: uniLoc(mainProgram,'uFrequency'),
        cameraPos: uniLoc(mainProgram,'uCameraPos'), lowColor: uniLoc(mainProgram,'uLowColor'),
        midColor: uniLoc(mainProgram,'uMidColor'), highColor: uniLoc(mainProgram,'uHighColor'), lightDir: uniLoc(mainProgram,'uLightDir'),
        opacity: uniLoc(mainProgram,'uOpacity'),
    };
    const glowU = {
        model: uniLoc(glowProgram,'uModel'), view: uniLoc(glowProgram,'uView'), proj: uniLoc(glowProgram,'uProjection'),
        normalMat: uniLoc(glowProgram,'uNormalMat'), cameraPos: uniLoc(glowProgram,'uCameraPos'),
    };
    const particleU = {
        model: uniLoc(particleProgram,'uModel'), view: uniLoc(particleProgram,'uView'), proj: uniLoc(particleProgram,'uProjection'),
        time: uniLoc(particleProgram,'uTime'), amplitude: uniLoc(particleProgram,'uAmplitude'),
        frequency: uniLoc(particleProgram,'uFrequency'), progress: uniLoc(particleProgram,'uProgress'),
        pixelRatio: uniLoc(particleProgram,'uPixelRatio'), opacity: uniLoc(particleProgram,'uOpacity'),
    };

    let azimuth = 0.4, elevation = 0.15, distance = 8.2;
    let autoRotate = true;
    let dragging = false, lastX = 0, lastY = 0;

    canvas.addEventListener('pointerdown', e => { dragging = true; autoRotate = false; lastX = e.clientX; lastY = e.clientY; });
    window.addEventListener('pointerup', () => dragging = false);
    window.addEventListener('pointermove', e => {
        if (!dragging) return;
        azimuth += (e.clientX - lastX) * 0.006;
        elevation = Math.max(-1.2, Math.min(1.2, elevation + (e.clientY - lastY) * 0.006));
        lastX = e.clientX; lastY = e.clientY;
    });

    function resize() {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = window.innerWidth * dpr;
        canvas.height = window.innerHeight * dpr;
        gl.viewport(0, 0, canvas.width, canvas.height);
    }
    window.addEventListener("resize", resize);
    resize();

    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0, 0, 0, 0);

    const model = mat4.create(), view = mat4.create(), proj = mat4.create();
    let smoothScrollProgress = 0.0;
    let lastFrameTime = performance.now();
    let simTime = 0.0;

    function frame() {
        requestAnimationFrame(frame);
        const now = performance.now();
        const deltaSeconds = Math.min((now - lastFrameTime) / 1000, 0.1);
        lastFrameTime = now;

        const isOverview = (activeTab === "tab-overview");

        // On non-overview tabs (Workspace, Chat, Studio, Runner, etc.), slow down dramatically (calm, non-distracting ambient drift)
        const rotationSpeed = isOverview ? 0.0032 : 0.00035;
        const timeScale = isOverview ? 1.0 : 0.08;

        simTime += deltaSeconds * timeScale;
        const t = simTime;

        if (autoRotate) azimuth += rotationSpeed;

        const eye = [
            distance * Math.cos(elevation) * Math.sin(azimuth),
            distance * Math.sin(elevation),
            distance * Math.cos(elevation) * Math.cos(azimuth),
        ];
        mat4.lookAt(view, eye, [0, -0.45, 0], [0, 1, 0]);
        mat4.perspective(proj, 38 * Math.PI / 180, canvas.width / canvas.height, 0.1, 100);
        mat4.identity(model);

        // Window scroll reading calibrated for a stable, fixed centerpiece
        const scrollY = window.scrollY;
        const maxScroll = 550;
        const targetRatio = Math.min(1.0, Math.max(0.0, scrollY / maxScroll));

        smoothScrollProgress += (targetRatio - smoothScrollProgress) * 0.09;

        const convergeProgress = Math.min(1.0, smoothScrollProgress / 0.55);
        const crossfadeT = Math.min(1.0, Math.max(0.0, (smoothScrollProgress - 0.18) / 0.40));

        if (isOverview) {
            const mainText = document.getElementById("hero-main-text");
            const scrollText = document.getElementById("hero-scroll-text");
            if (mainText && scrollText) {
                if (smoothScrollProgress < 0.18) {
                    // Stage 1: Initial headline fading out
                    const fade = Math.min(1.0, smoothScrollProgress / 0.18);
                    mainText.style.display = "block";
                    mainText.style.opacity = (1.0 - fade).toFixed(3);
                    mainText.style.filter = `blur(${fade * 5}px)`;
                    mainText.style.transform = `translate(-50%, calc(-50% - ${fade * 18}px))`;
                    mainText.style.pointerEvents = fade > 0.5 ? "none" : "auto";

                    scrollText.style.display = "none";
                    scrollText.style.opacity = "0";
                } else if (smoothScrollProgress >= 0.18 && smoothScrollProgress <= 0.85) {
                    // Stage 2: Centerpiece STAYS FIXED, SOLID & READABLE for the long scroll
                    mainText.style.display = "none";
                    mainText.style.opacity = "0";

                    const revealT = Math.min(1.0, (smoothScrollProgress - 0.18) / 0.12);
                    scrollText.style.display = "block";
                    scrollText.style.opacity = revealT.toFixed(3);
                    scrollText.style.filter = `blur(${(1.0 - revealT) * 6}px)`;
                    scrollText.style.transform = `translate(-50%, -50%) scale(${0.96 + 0.04 * revealT})`;
                    scrollText.style.pointerEvents = "auto";
                } else {
                    // Stage 3: Smooth exit only when reaching the stats banner
                    mainText.style.display = "none";
                    mainText.style.opacity = "0";

                    const exitT = Math.min(1.0, (smoothScrollProgress - 0.85) / 0.15);
                    scrollText.style.display = "block";
                    scrollText.style.opacity = Math.max(0, 1.0 - exitT).toFixed(3);
                    scrollText.style.filter = `blur(${exitT * 5}px)`;
                    scrollText.style.transform = `translate(-50%, calc(-50% - ${exitT * 18}px))`;
                    scrollText.style.pointerEvents = exitT > 0.5 ? "none" : "auto";
                }
            }
        }

        const sphereOpacity = isOverview ? crossfadeT : 0.0;
        const particleOpacity = isOverview ? (1.0 - crossfadeT) : 0.40;
        const showParticles = particleOpacity > 0.001;
        const showSphere = sphereOpacity > 0.001;

        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        const dpr = Math.min(window.devicePixelRatio || 1, 2);

        if (showSphere) {
            const revealEase = 1 - Math.pow(1 - sphereOpacity, 3);
            const revealScale = 0.15 + 0.85 * revealEase;
            const sphereModel = mat4.create();
            sphereModel.set(model);
            for (let i = 0; i < 12; i++) sphereModel[i] *= revealScale;
            sphereModel[15] = 1;

            const sphereNormalMat = new Float32Array(9);
            mat4.normalFromMat4(sphereNormalMat, sphereModel);

            gl.useProgram(mainProgram);
            gl.bindVertexArray(sphereMesh.vao);
            gl.uniformMatrix4fv(mainU.model, false, sphereModel);
            gl.uniformMatrix4fv(mainU.view, false, view);
            gl.uniformMatrix4fv(mainU.proj, false, proj);
            gl.uniformMatrix3fv(mainU.normalMat, false, sphereNormalMat);
            gl.uniform1f(mainU.time, t);
            gl.uniform1f(mainU.amplitude, 0.22);
            gl.uniform1f(mainU.frequency, 1.35);
            gl.uniform3fv(mainU.cameraPos, eye);
            gl.uniform3fv(mainU.lowColor, [0.227, 0.039, 0.333]);
            gl.uniform3fv(mainU.midColor, [0.690, 0.125, 0.878]);
            gl.uniform3fv(mainU.highColor, [1.0, 0.851, 1.0]);
            gl.uniform3fv(mainU.lightDir, [0.6, 0.8, 0.9]);
            gl.uniform1f(mainU.opacity, 1.0);
            gl.drawElements(gl.TRIANGLES, sphereMesh.count, gl.UNSIGNED_INT, 0);

            gl.enable(gl.BLEND);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
            gl.depthMask(false);
            gl.useProgram(glowProgram);
            gl.bindVertexArray(glowMesh.vao);
            gl.uniformMatrix4fv(glowU.model, false, sphereModel);
            gl.uniformMatrix4fv(glowU.view, false, view);
            gl.uniformMatrix4fv(glowU.proj, false, proj);
            gl.uniformMatrix3fv(glowU.normalMat, false, sphereNormalMat);
            gl.uniform3fv(glowU.cameraPos, eye);
            gl.drawElements(gl.TRIANGLES, glowMesh.count, gl.UNSIGNED_INT, 0);
            gl.depthMask(true);
            gl.disable(gl.BLEND);
        }

        if (showParticles) {
            gl.enable(gl.BLEND);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
            gl.depthMask(false);
            gl.useProgram(particleProgram);
            gl.bindVertexArray(particleMesh.vao);
            gl.uniformMatrix4fv(particleU.model, false, model);
            gl.uniformMatrix4fv(particleU.view, false, view);
            gl.uniformMatrix4fv(particleU.proj, false, proj);
            gl.uniform1f(particleU.time, t);
            gl.uniform1f(particleU.amplitude, isOverview ? 0.22 : 0.08);
            gl.uniform1f(particleU.frequency, 1.35);
            gl.uniform1f(particleU.progress, isOverview ? convergeProgress : 0.0);
            gl.uniform1f(particleU.pixelRatio, dpr);
            gl.uniform1f(particleU.opacity, particleOpacity);
            gl.drawArrays(gl.POINTS, 0, particleMesh.count);
            gl.depthMask(true);
            gl.disable(gl.BLEND);
        }
    }
    frame();
}

// =========================================================================
// OS Documentation Switcher
// =========================================================================

function switchOsTab(os) {
    document.querySelectorAll("#tab-docs .sub-dock-item").forEach(b => b.classList.remove("active"));
    event?.target?.classList?.add("active");

    const content = document.getElementById("os-tab-content");
    if (!content) return;

    if (os === "win") {
        content.innerHTML = `
            <h3 class="text-base font-bold text-white mb-3">Windows Installation</h3>
            <pre class="code-block text-xs">
# Option 1: Official Windows Installer (Pre-built)
# Download installer from https://rpm.lammps.org/windows/
# Run LAMMPS-64bit-latest.exe and select PATH environment variable

# Option 2: Conda-Forge
conda create -n lammps-env -c conda-forge lammps
conda activate lammps-env

# Test execution:
lmp -in in.script</pre>
        `;
    } else if (os === "linux") {
        content.innerHTML = `
            <h3 class="text-base font-bold text-white mb-3">Linux (Ubuntu / Debian / Fedora)</h3>
            <pre class="code-block text-xs">
# Ubuntu / Debian
sudo apt update && sudo apt install -y lammps

# Fedora / RHEL
sudo dnf install -y lammps

# Build from source with CMake
git clone -b stable https://github.com/lammps/lammps.git
cd lammps && mkdir build && cd build
cmake ../cmake -DPKG_MANYBODY=yes -DPKG_MOLECULE=yes -DPKG_KSPACE=yes
cmake --build . -j $(nproc)</pre>
        `;
    } else if (os === "mac") {
        content.innerHTML = `
            <h3 class="text-base font-bold text-white mb-3">macOS (Apple Silicon & Intel)</h3>
            <pre class="code-block text-xs">
# Homebrew installation
brew install lammps

# Test installation
lmp -h</pre>
        `;
    } else if (os === "conda") {
        content.innerHTML = `
            <h3 class="text-base font-bold text-white mb-3">Conda / Python Environment</h3>
            <pre class="code-block text-xs">
# Create dedicated research environment
conda create -n md-env -c conda-forge lammps numpy scipy matplotlib
conda activate md-env

# Python Interface Test
python -c "from lammps import lammps; lmp = lammps(); lmp.command('units metal'); print('LAMMPS Python Loaded!')"</pre>
        `;
    }
}

// =========================================================================
// Utilities
// =========================================================================

function renderThermoTable(summary) {
    let html = `<div class="overflow-x-auto"><table class="w-full text-xs font-mono border-collapse my-3">
        <thead>
            <tr class="text-gray-400 border-b border-white/[0.08] text-left">
                <th class="py-2 px-3">Property</th>
                <th class="py-2 px-3">Initial</th>
                <th class="py-2 px-3">Final</th>
                <th class="py-2 px-3">Min</th>
                <th class="py-2 px-3">Max</th>
                <th class="py-2 px-3">Mean</th>
                <th class="py-2 px-3">Std Dev</th>
            </tr>
        </thead>
        <tbody>`;

    for (const [col, stats] of Object.entries(summary)) {
        html += `<tr class="border-b border-white/[0.04] hover:bg-white/[0.02]">
            <td class="py-2 px-3 text-accent font-bold">${escapeHtml(col)}</td>
            <td class="py-2 px-3">${stats.initial}</td>
            <td class="py-2 px-3">${stats.final}</td>
            <td class="py-2 px-3">${stats.min}</td>
            <td class="py-2 px-3">${stats.max}</td>
            <td class="py-2 px-3 font-semibold text-white">${stats.mean}</td>
            <td class="py-2 px-3 text-gray-400">${stats.std_dev}</td>
        </tr>`;
    }

    html += `</tbody></table></div>`;
    return html;
}

function renderMarkdown(md) {
    if (!md) return "";
    let html = escapeHtml(md);

    html = html.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre class="code-block my-2"><code>${code}</code></pre>`;
    });

    html = html.replace(/`([^`]+)`/g, "<code class='px-1.5 py-0.5 rounded bg-white/10 text-accent font-mono text-xs'>$1</code>");
    html = html.replace(/^### (.*$)/gim, "<h4 class='text-sm font-bold text-white mt-2 mb-1'>$1</h4>");
    html = html.replace(/^## (.*$)/gim, "<h3 class='text-base font-bold text-white mt-3 mb-1'>$1</h3>");
    html = html.replace(/^# (.*$)/gim, "<h2 class='text-lg font-extrabold text-white mt-3 mb-2'>$1</h2>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong class='text-white font-semibold'>$1</strong>");
    html = html.replace(/^\- (.*$)/gim, "<li class='ml-4 list-disc text-gray-300'>$1</li>");
    html = html.replace(/\n\n/g, "</p><p class='mt-2'>");

    return `<p>${html}</p>`;
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = "toast-msg flex items-center gap-2";
    toast.innerHTML = `<span>${type === "error" ? "⚠️" : "✓"}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3500);
}

// =========================================================================
// Project Workspace & Codebase RAG Client Engine
// =========================================================================

let currentWorkspaceFile = null;

async function initWorkspace() {
    refreshWorkspaceStatus();
}

async function refreshWorkspaceStatus() {
    try {
        const res = await fetch("/api/project/status");
        if (!res.ok) return;
        const data = await res.json();

        const badge = document.getElementById("ws-badge");
        const statFiles = document.getElementById("ws-stat-files");
        const statChunks = document.getElementById("ws-stat-chunks");
        const statScripts = document.getElementById("ws-stat-scripts");
        const statPotentials = document.getElementById("ws-stat-potentials");
        const statRoot = document.getElementById("ws-stat-root");
        const chatStatus = document.getElementById("chat-workspace-status");

        if (data.active && data.summary) {
            if (badge) {
                badge.textContent = `Active: ${data.name}`;
                badge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
            }
            if (statFiles) statFiles.textContent = data.summary.total_files || 0;
            if (statChunks) statChunks.textContent = data.summary.total_chunks || 0;
            if (statScripts) statScripts.textContent = (data.summary.lammps_scripts || []).length;
            if (statPotentials) statPotentials.textContent = (data.summary.potential_files || []).length + (data.summary.data_files || []).length;
            if (statRoot) statRoot.textContent = data.name || "Active";
            if (chatStatus) chatStatus.textContent = `Workspace: ${data.name} (${data.summary.total_files} files)`;
            loadWorkspaceTree();
        } else {
            if (badge) {
                badge.textContent = "Ready to Index";
                badge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40";
            }
            if (chatStatus) chatStatus.textContent = "Workspace: Click to Open";
        }
    } catch (e) {
        console.error("Failed to fetch workspace status", e);
    }
}

async function handleOpenWorkspaceFromInput() {
    const input = document.getElementById("ws-folder-path-input");
    if (!input) return;
    const folderPath = input.value.trim();

    showToast("Scanning and indexing project files into RAG...", "info");

    try {
        const res = await fetch("/api/project/open", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder_path: folderPath })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`Indexed ${data.files_count} files (${data.chunks_count} code chunks) in '${data.workspace_name}'!`, "success");
            refreshWorkspaceStatus();
        } else {
            showToast(data.error || "Failed to open folder", "error");
        }
    } catch (e) {
        showToast("Error opening project folder: " + e.message, "error");
    }
}

async function loadWorkspaceTree() {
    try {
        const res = await fetch("/api/project/tree");
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById("ws-tree-container");
        if (!container) return;

        if (!data.tree || !data.tree.children || data.tree.children.length === 0) {
            container.innerHTML = `<div class="text-xs text-gray-500 py-6 text-center">No supported code files found in workspace.</div>`;
            return;
        }

        container.innerHTML = renderTreeHtml(data.tree);
    } catch (e) {
        console.error("Failed to load workspace tree", e);
    }
}

function renderTreeHtml(node) {
    if (node.type === "directory") {
        const childrenHtml = (node.children || []).map(child => renderTreeHtml(child)).join("");
        return `
            <div class="tree-folder">
                <div class="tree-folder-title">
                    <span>📁</span>
                    <span>${escapeHtml(node.name)}</span>
                </div>
                <div class="tree-children">
                    ${childrenHtml}
                </div>
            </div>
        `;
    } else {
        const icon = getFileIcon(node.ext);
        const escapedPath = escapeHtml(node.path).replace(/'/g, "\\'");
        const escapedName = escapeHtml(node.name).replace(/'/g, "\\'");
        return `
            <div class="tree-file" onclick="loadWorkspaceFilePreview('${escapedPath}', '${escapedName}')" id="tree-file-${escapedPath.replace(/[^a-zA-Z0-9_-]/g, '_')}">
                <div class="flex items-center gap-2 truncate">
                    <span>${icon}</span>
                    <span class="truncate">${escapeHtml(node.name)}</span>
                </div>
                <span class="text-[9px] text-gray-500 font-mono">${node.line_count || 0}L</span>
            </div>
        `;
    }
}

function getFileIcon(ext) {
    switch ((ext || "").toLowerCase()) {
        case ".in":
        case ".lmp":
        case ".lammps":
            return "⚛";
        case ".py":
            return "🐍";
        case ".data":
        case ".dat":
            return "🌐";
        case ".eam":
        case ".tersoff":
        case ".sw":
            return "⚡";
        case ".md":
        case ".txt":
            return "📄";
        case ".log":
        case ".out":
            return "📋";
        default:
            return "📄";
    }
}

async function loadWorkspaceFilePreview(relPath, filename) {
    currentWorkspaceFile = { relPath, filename };
    
    // Highlight active tree file
    document.querySelectorAll(".tree-file").forEach(el => el.classList.remove("active"));
    const activeEl = document.getElementById(`tree-file-${relPath.replace(/[^a-zA-Z0-9_-]/g, '_')}`);
    if (activeEl) activeEl.classList.add("active");

    const iconEl = document.getElementById("ws-viewer-icon");
    const nameEl = document.getElementById("ws-viewer-filename");
    const linesEl = document.getElementById("ws-viewer-lines");
    const codeEl = document.getElementById("ws-code-content");
    const askBtn = document.getElementById("btn-ws-ask-ai");
    const viewerCard = document.getElementById("ws-viewer-card");
    const searchResultsCard = document.getElementById("ws-search-results-card");

    if (searchResultsCard) searchResultsCard.classList.add("hidden");
    if (viewerCard) viewerCard.classList.remove("hidden");

    if (nameEl) nameEl.textContent = relPath;
    if (iconEl) iconEl.textContent = getFileIcon(relPath.substring(relPath.lastIndexOf('.')));
    if (askBtn) askBtn.classList.remove("hidden");

    try {
        const res = await fetch("/api/project/read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rel_path: relPath })
        });
        const data = await res.json();
        if (data.content !== undefined) {
            if (linesEl) linesEl.textContent = `(${data.lines} lines)`;
            if (codeEl) {
                // Add line numbers to code
                const lines = data.content.split('\n');
                const numbered = lines.map((l, i) => `${String(i + 1).padStart(4, ' ')} | ${l}`).join('\n');
                codeEl.textContent = numbered;
            }
        }
    } catch (e) {
        if (codeEl) codeEl.textContent = `// Error loading file: ${e.message}`;
    }
}

async function handleWorkspaceSearch() {
    const input = document.getElementById("ws-search-input");
    if (!input) return;
    const query = input.value.trim();
    if (!query) return;

    try {
        const res = await fetch("/api/project/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query })
        });
        const data = await res.json();
        const hitsCard = document.getElementById("ws-search-results-card");
        const hitsList = document.getElementById("ws-search-hits-list");
        const countEl = document.getElementById("ws-search-hits-count");
        const viewerCard = document.getElementById("ws-viewer-card");

        if (hitsCard && hitsList) {
            hitsCard.classList.remove("hidden");
            if (countEl) countEl.textContent = `Found ${data.results.length} relevant code chunks for "${escapeHtml(query)}"`;

            if (data.results.length === 0) {
                hitsList.innerHTML = `<div class="text-xs text-gray-500 py-3 text-center">No matching code chunks found in active workspace.</div>`;
                return;
            }

            hitsList.innerHTML = data.results.map(hit => `
                <div class="ws-search-hit-item" onclick="loadWorkspaceFilePreview('${escapeHtml(hit.file_path)}', '${escapeHtml(hit.filename)}')">
                    <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-1.5 font-mono text-xs text-accent font-bold">
                            <span>📄 ${escapeHtml(hit.file_path)}</span>
                            <span class="text-gray-400 font-normal text-[10px]">(Lines ${hit.start_line}-${hit.end_line})</span>
                        </div>
                        <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-white/10 text-gray-300">${escapeHtml(hit.block_type)}</span>
                    </div>
                    <pre class="text-[11px] font-mono text-gray-300 bg-black/40 p-2 rounded overflow-x-auto whitespace-pre-wrap">${escapeHtml(hit.snippet)}</pre>
                </div>
            `).join("");
        }
    } catch (e) {
        showToast("Search failed: " + e.message, "error");
    }
}

function closeWorkspaceSearchResults() {
    const hitsCard = document.getElementById("ws-search-results-card");
    if (hitsCard) hitsCard.classList.add("hidden");
}

function askAiAboutCurrentFile() {
    if (!currentWorkspaceFile) return;
    const promptText = `Please analyze the simulation file '${currentWorkspaceFile.relPath}' from my project workspace. Explain its physical setup, potential styles, and check for any parameter issues.`;
    switchTab("tab-chatbot");
    const textarea = document.getElementById("user-prompt");
    if (textarea) {
        textarea.value = promptText;
        textarea.focus();
    }
}

// =========================================================================
// WebGL2 Trajectory Viewer Controls & Event Wiring
// =========================================================================

function initTrajViewerIfNeeded() {
    if (!window.activeTrajViewer) {
        const canvas = document.getElementById("trajectory-canvas");
        if (canvas && window.TrajectoryViewer) {
            window.activeTrajViewer = new TrajectoryViewer(canvas, {
                onFrameChange: (idx, total) => {
                    const counter = document.getElementById("traj-frame-counter");
                    if (counter) counter.innerText = `Frame ${idx + 1} / ${total}`;
                    const scrub = document.getElementById("traj-scrubber");
                    if (scrub) {
                        scrub.max = Math.max(0, total - 1);
                        scrub.value = idx;
                    }
                    const scrubInd = document.getElementById("traj-scrub-indicator");
                    if (scrubInd) scrubInd.innerText = `${idx + 1} / ${total}`;
                },
                onTimestepChange: (ts, isInterpolated) => {
                    const badge = document.getElementById("traj-timestep-badge");
                    if (badge) {
                        if (isInterpolated) {
                            badge.className = "px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1.5 shadow-[0_0_8px_rgba(245,158,11,0.2)]";
                            badge.innerText = `◌ Timestep ${ts} (INTERPOLATED)`;
                        } else {
                            badge.className = "px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 shadow-[0_0_8px_rgba(52,211,153,0.2)]";
                            badge.innerText = `● Timestep ${ts} (SIMULATED)`;
                        }
                    }
                },
                onColorbarChange: (info) => {
                    updateTrajColorbarUI(info);
                }
            });
        }
    }
}

function toggleTrajectoryPlay() {
    if (!window.activeTrajViewer) return;
    window.activeTrajViewer.togglePlay();
    const playIcon = document.getElementById("traj-play-icon");
    if (playIcon) {
        playIcon.innerText = window.activeTrajViewer.isPlaying ? "⏸ Pause" : "▶ Play";
    }
}

function scrubTrajectory(val) {
    if (!window.activeTrajViewer) return;
    const fIdx = parseFloat(val);
    window.activeTrajViewer.pause();
    window.activeTrajViewer.isLiveFollowing = false;
    window.activeTrajViewer.seek(fIdx);
    const playIcon = document.getElementById("traj-play-icon");
    if (playIcon) playIcon.innerText = "▶ Play";
}

function setTrajColorMode(mode) {
    if (!window.activeTrajViewer) return;
    window.activeTrajViewer.setColorMode(mode);

    const btnElem = document.getElementById("btn-color-element");
    const btnKe = document.getElementById("btn-color-ke");
    const btnStress = document.getElementById("btn-color-stress");
    const normControls = document.getElementById("traj-norm-controls");

    if (btnElem) btnElem.classList.toggle("active", mode === "element");
    if (btnKe) btnKe.classList.toggle("active", mode === "kinetic_energy");
    if (btnStress) btnStress.classList.toggle("active", mode === "von_mises_stress");

    if (normControls) {
        if (mode === "element") {
            normControls.classList.add("hidden");
        } else {
            normControls.classList.remove("hidden");
        }
    }
}

function setTrajNormMode(norm) {
    if (!window.activeTrajViewer) return;
    window.activeTrajViewer.setNormMode(norm);

    const btnFrame = document.getElementById("btn-norm-frame");
    const btnRun = document.getElementById("btn-norm-run");
    if (btnFrame) btnFrame.classList.toggle("active", norm === "frame");
    if (btnRun) btnRun.classList.toggle("active", norm === "run");
}

function updateTrajFieldModeButtons(availableFields, isSynthetic) {
    const btnKe = document.getElementById("btn-color-ke");
    const btnStress = document.getElementById("btn-color-stress");
    const fields = availableFields || ["element"];

    const hasKe = fields.includes("kinetic_energy");
    const hasStress = fields.includes("von_mises_stress");

    if (btnKe) {
        btnKe.disabled = !hasKe;
        btnKe.style.opacity = hasKe ? "1" : "0.4";
        btnKe.title = hasKe ? "Color atoms by kinetic energy" : "No kinetic energy data in trajectory dump";
    }
    if (btnStress) {
        btnStress.disabled = !hasStress;
        btnStress.style.opacity = hasStress ? "1" : "0.4";
        btnStress.title = hasStress ? "Color atoms by Von Mises stress" : "No stress data in trajectory dump";
    }
}

function updateTrajColorbarUI(info) {
    const container = document.getElementById("traj-colorbar-container");
    if (!container) return;

    if (!info || info.colorMode === "element") {
        container.classList.add("hidden");
        return;
    }

    container.classList.remove("hidden");

    const titleEl = document.getElementById("traj-colorbar-title");
    const normDescEl = document.getElementById("traj-colorbar-norm-desc");
    const synBadgeEl = document.getElementById("traj-colorbar-synthetic-badge");
    const minEl = document.getElementById("traj-colorbar-min");
    const midEl = document.getElementById("traj-colorbar-mid");
    const maxEl = document.getElementById("traj-colorbar-max");

    const isKe = (info.colorMode === "kinetic_energy");
    const titleText = isKe ? "Kinetic Energy" : "Von Mises Stress";
    const unit = info.unitSymbol ? ` [${info.unitSymbol}]` : "";

    if (titleEl) titleEl.innerText = `${titleText}${unit}`;
    if (normDescEl) {
        normDescEl.innerText = (info.normMode === "run") ? "(Run Normalization)" : "(Frame Normalization)";
    }
    if (synBadgeEl) {
        if (info.isSynthetic) {
            synBadgeEl.classList.remove("hidden");
        } else {
            synBadgeEl.classList.add("hidden");
        }
    }

    const fmt = (v) => {
        if (v === null || v === undefined || isNaN(v)) return "0.00";
        const absVal = Math.abs(v);
        if (absVal >= 10000 || (absVal > 0 && absVal < 0.01)) {
            return v.toExponential(2);
        }
        return v.toFixed(2);
    };

    if (minEl) minEl.innerText = `${fmt(info.min)} ${info.unitSymbol || ""}`;
    if (midEl) midEl.innerText = `${fmt(info.mid)} ${info.unitSymbol || ""}`;
    if (maxEl) maxEl.innerText = `${fmt(info.max)} ${info.unitSymbol || ""}`;
}

// =========================================================================
// Big Linux Terminal Mirror Window Controls
// =========================================================================

function toggleTerminalExpand() {
    const pre = document.getElementById("runner-terminal-pre");
    const icon = document.getElementById("terminal-expand-icon");
    if (!pre) return;
    if (pre.classList.contains("expanded")) {
        pre.classList.remove("expanded");
        if (icon) icon.innerText = "⛶ Expand";
    } else {
        pre.classList.remove("compact");
        pre.classList.add("expanded");
        if (icon) icon.innerText = "↙ Collapse";
    }
}

function setTerminalHeight(mode) {
    const pre = document.getElementById("runner-terminal-pre");
    const icon = document.getElementById("terminal-expand-icon");
    if (!pre) return;
    if (mode === "compact") {
        pre.classList.remove("expanded");
        pre.classList.toggle("compact");
        if (icon) icon.innerText = "⛶ Expand";
    }
}

function clearTerminalOutput() {
    const pre = document.getElementById("runner-terminal-pre");
    if (pre) {
        pre.innerText = "┌──(lammps㉿wsl2)-[~/simulations]\n└─$ lmp -in in.run -log log.lammps\n[Console mirror cleared]\n";
    }
    showToast("Terminal console cleared");
}

function copyTerminalOutput() {
    const pre = document.getElementById("runner-terminal-pre");
    if (!pre) return;
    navigator.clipboard.writeText(pre.innerText)
        .then(() => showToast("Terminal log copied to clipboard!", "success"))
        .catch(() => showToast("Could not copy to clipboard", "error"));
}

// =========================================================================
// 3D Atomic Trajectory Runner & Direct WebGL Simulation Launcher
// =========================================================================

function toggleTrajViewerExpand() {
    const canvas = document.getElementById("trajectory-canvas");
    const icon = document.getElementById("traj-expand-icon");
    if (!canvas) return;
    canvas.classList.toggle("expanded");
    if (icon) {
        icon.innerText = canvas.classList.contains("expanded") ? "↙ Collapse" : "⛶ Expand";
    }
    if (window.activeTrajViewer) {
        window.activeTrajViewer._resize();
    }
}

function resetTrajCamera() {
    if (window.activeTrajViewer) {
        window.activeTrajViewer.resetCamera();
        showToast("3D camera orbit reset");
    }
}

function setTrajSpeed(speed, btn) {
    if (window.activeTrajViewer) {
        window.activeTrajViewer.setPlaybackSpeed(speed);
        const container = btn?.parentElement;
        if (container) {
            container.querySelectorAll("button").forEach(b => {
                b.className = "text-[11px] px-1 text-gray-300 hover:text-white";
            });
            btn.className = "text-[11px] px-1 text-accent font-bold";
        }
    }
}

async function runWebGL3DRunnerSimulation(forcedPreset) {
    const presetSelect = document.getElementById("traj-sim-preset-select");
    const preset = forcedPreset || (presetSelect ? presetSelect.value : "lj_benchmark");
    const btn = document.getElementById("btn-traj-run-sim");

    let script = "";
    if (["lj_benchmark", "molten_al", "water_liquid"].includes(preset)) {
        // Presets come from the server's validated template generator (single source of truth)
        try {
            const res = await fetch("/api/preset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preset })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
            script = data.script;
        } catch (err) {
            showToast(`Could not load preset script: ${err.message}`, "error");
            return;
        }
    } else {
        const studioCode = document.getElementById("studio-code-input")?.value?.trim();
        if (studioCode) {
            script = studioCode;
        } else {
            script = generateClientScript(currentSimParams);
        }
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="inline-block animate-spin">⚡</span><span>Running Live...</span>`;
    }

    const card = document.getElementById("runner-trajectory-card");
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });

    showToast(`Launching ${preset.replace(/_/g, ' ')} WebGL2 simulation...`, "info");
    try {
        await executeFromChat(script);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span>🚀 Run WebGL Simulation</span>`;
        }
    }
}

function launchVisualizerInWebGLRunner() {
    const matSelect = document.getElementById("vis-mat-select");
    const mat = matSelect ? matSelect.value : "LJ";

    let preset = "lj_benchmark";
    if (mat === "Water") preset = "water_liquid";
    else if (mat === "LJ" || mat === "Argon") preset = "lj_benchmark";
    else preset = "molten_al";

    activateTab("tab-runner");
    const sel = document.getElementById("traj-sim-preset-select");
    if (sel) sel.value = preset;

    runWebGL3DRunnerSimulation(preset);
}

