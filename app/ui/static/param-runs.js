// Parameter Runs tab: edit a lecturer script's variable values, preview the edited copy,
// then run it through the existing Runner (terminal, thermo, 3D viewer via /api/run/stream).
(function () {
    const NUMBER_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
    const SAFE_RE = /^[A-Za-z0-9_.\-/]{1,64}$/;
    let scripts = [];
    let previewTimer = null;

    const $ = (id) => document.getElementById(id);
    const current = () => scripts.find((s) => s.id === $("prun-select").value);

    function checkValue(v, raw) {
        const s = String(raw).trim();
        if (v.type === "int" || v.type === "float") {
            if (!NUMBER_RE.test(s) || !Number.isFinite(Number(s))) return "must be a finite number";
            if (v.type === "int" && !Number.isInteger(Number(s))) return "must be a whole number";
            return null;
        }
        if (!SAFE_RE.test(s) || s.startsWith("/") || s.split("/").includes("..")) return "letters, digits, _ . - / only";
        return null;
    }

    function values() {
        const out = {};
        for (const v of current().variables) {
            if (v.editable) out[v.name] = $(`prun-f-${v.name}`).value.trim();
        }
        return out;
    }

    function validateForm() {
        let ok = true;
        for (const v of current().variables) {
            if (!v.editable) continue;
            const err = checkValue(v, $(`prun-f-${v.name}`).value);
            $(`prun-e-${v.name}`).textContent = err || "";
            if (err) ok = false;
        }
        $("prun-run-btn").disabled = !ok;
        return ok;
    }

    function buildForm() {
        const s = current();
        const box = $("prun-fields");
        box.innerHTML = "";
        if (!s) return;
        if (s.error) { box.innerHTML = `<div class="text-xs text-red-300 font-mono">${escapeHtml(s.error)}</div>`; return; }
        const note = $("prun-viewer-note");
        note.classList.toggle("hidden", !s.viewer.message);
        note.textContent = s.viewer.message || "";
        for (const v of s.variables) {
            const wrap = document.createElement("div");
            wrap.innerHTML = `
              <label class="flex justify-between gap-2 text-xs font-bold text-gray-200 mb-1" for="prun-f-${v.name}">
                <span class="font-mono">${escapeHtml(v.name)} <span class="text-gray-500 font-normal">(${v.style})</span></span>
                ${v.editable ? "" : '<span class="text-gray-500 font-normal">fixed</span>'}
              </label>
              <input id="prun-f-${v.name}" class="input-glass w-full font-mono text-xs" type="text" spellcheck="false"
                     value="${escapeHtml(v.default)}" ${v.editable ? "" : "disabled"}>
              ${v.label ? `<div class="text-[11px] text-gray-400 mt-1">${escapeHtml(v.label)}</div>` : ""}
              <div id="prun-e-${v.name}" class="text-[11px] text-red-300 mt-1"></div>`;
            box.appendChild(wrap);
            wrap.querySelector("input").addEventListener("input", onChange);
        }
        onChange();
    }

    function onChange() {
        $("prun-error").classList.add("hidden");
        if (!validateForm()) return;
        clearTimeout(previewTimer);
        previewTimer = setTimeout(preview, 250);
    }

    function showError(data) {
        const fields = data.fields || {};
        for (const [k, msg] of Object.entries(fields)) {
            const el = $(`prun-e-${k}`);
            if (el) el.textContent = msg;
        }
        $("prun-error").textContent = data.error || "Request failed";
        $("prun-error").classList.remove("hidden");
    }

    async function post(body) {
        const token = window.__SESSION_TOKEN__ || "";
        return fetch("/api/param-scripts/run", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Session-Token": token },
            body: JSON.stringify({ ...body, session_token: token }),
        });
    }

    async function preview() {
        const s = current();
        const res = await post({ file_id: s.id, params: values(), dry_run: true });
        const data = await res.json();
        if (!res.ok) { showError(data); return; }
        const changed = new Set(data.changed_lines);
        $("prun-preview").innerHTML = data.script.split("\n").map((line, i) => {
            const n = String(i + 1).padStart(3, " ");
            const cls = changed.has(i + 1) ? ' class="bg-amber-400/25 text-amber-100"' : "";
            return `<span${cls}><span class="text-gray-600 select-none">${n}  </span>${escapeHtml(line)}</span>`;
        }).join("\n");
        const first = $("prun-preview").querySelector(".bg-amber-400\\/25");
        if (first) first.scrollIntoView({ block: "nearest" });
    }

    window.prunReset = buildForm;

    window.prunRun = function () {
        if (!validateForm()) return;
        const s = current();
        const body = { file_id: s.id, params: values() };
        // Reuse the existing Runner: same terminal, thermo display and 3D trajectory viewer
        executeFromChat(null, () => post(body));
    };

    async function load() {
        const sel = $("prun-select");
        if (!sel) return;
        try {
            const res = await fetch("/api/param-scripts", { headers: { "X-Session-Token": window.__SESSION_TOKEN__ || "" } });
            const data = await res.json();
            scripts = data.scripts || [];
        } catch (e) {
            $("prun-fields").innerHTML = `<div class="text-xs text-red-300 font-mono">Could not load scripts: ${escapeHtml(e.message)}</div>`;
            return;
        }
        sel.innerHTML = scripts.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.title)} (${escapeHtml(s.file || "")})</option>`).join("");
        sel.addEventListener("change", buildForm);
        buildForm();
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
    else load();
})();
