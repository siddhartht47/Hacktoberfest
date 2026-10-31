/* Ollama Setup Buddy: plain JavaScript, no build step.
 * All text from the server is inserted with textContent, never innerHTML. */
(function () {
  "use strict";

  const STORE_KEY = "osb-state-v1";
  const TAG_RE = /^[A-Za-z0-9][A-Za-z0-9._\-\/]{0,80}(:[A-Za-z0-9._\-]{1,40})?$/;
  const $ = (sel) => document.querySelector(sel);

  // Base URL for API calls. When opened directly from a file or another dev port (e.g. VS Code Live Server on 5500),
  // route API requests to the FastAPI backend running on port 8000.
  const API_BASE = (window.location.protocol === "file:" || (window.location.port !== "8000" && window.location.port !== ""))
    ? "http://127.0.0.1:8000"
    : "";

  const state = {
    screen: "computer",
    os: detectOS(),
    specs: { ram: "", vram: "", disk: "", goal: "chat" },
    models: [],
    recommended: null,
    model: null,      // chosen tag
    modelName: "",
    plan: [],
    idx: 0,
    helper: { online: false, model_ready: false, model: "gemma3:1b" },
    hardwareHelp: {},
  };

  /* ------------------------------------------------------------ helpers */
  function detectOS() {
    const ua = (navigator.userAgent || "").toLowerCase();
    if (ua.includes("win")) return "windows";
    if (ua.includes("mac")) return "macos";
    return "linux";
  }

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  /* Text with `backticks` becomes text with <code> pieces (safe, no innerHTML). */
  function rich(text) {
    const frag = document.createDocumentFragment();
    String(text || "").split("`").forEach((part, i) => {
      if (!part) return;
      frag.append(i % 2 ? h("code", { class: "inline" }, part) : document.createTextNode(part));
    });
    return frag;
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = h("textarea", { style: "position:fixed;opacity:0" });
      ta.value = text;
      document.body.append(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
      ta.remove();
      return ok;
    }
  }

  function cmdBlock(cmd) {
    const btn = h("button", { type: "button", class: "btn ghost small" }, "Copy");
    btn.addEventListener("click", async () => {
      const ok = await copyText(cmd);
      btn.textContent = ok ? "Copied" : "Select and press Ctrl+C";
      setTimeout(() => { btn.textContent = "Copy"; }, 1600);
    });
    return h("div", { class: "cmd" }, h("code", {}, cmd), btn);
  }

  async function api(path, body) {
    const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
    const opts = body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      throw new Error("Cannot reach backend at " + (API_BASE || "http://127.0.0.1:8000") + ". Is the server running? (run 'start.bat' or 'python run.py')");
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === "string" ? detail : "Please check the values you entered.");
    }
    return data;
  }

  function showError(sel, msg) {
    const el = $(sel);
    el.textContent = msg || "";
    el.hidden = !msg;
  }

  /* ------------------------------------------------------------ persistence */
  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({
        screen: state.screen, os: state.os, specs: state.specs,
        model: state.model, idx: state.idx,
      }));
    } catch (e) { /* storage may be blocked */ }
  }

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (!saved) return null;
      if (["windows", "macos", "linux"].includes(saved.os)) state.os = saved.os;
      if (saved.specs) state.specs = Object.assign(state.specs, saved.specs);
      return saved;
    } catch (e) { return null; }
  }

  function wipe() {
    try { localStorage.removeItem(STORE_KEY); } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------ screens */
  function show(name) {
    state.screen = name;
    for (const s of ["computer", "model", "setup", "done"]) {
      $("#screen-" + s).hidden = s !== name;
    }
    $("#help").hidden = name !== "setup";
    const crumbScreen = name === "done" ? "setup" : name;
    document.querySelectorAll("#crumbs li").forEach((li) => {
      if (li.dataset.screen === crumbScreen) li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });
    save();
    window.scrollTo(0, 0);
  }

  /* ------------------------------------------------------------ helper status */
  async function refreshHealth() {
    const el = $("#helper-status");
    let backendOffline = false;
    try {
      state.helper = await api("/api/health");
    } catch (e) {
      state.helper = { online: false, model_ready: false, model: "gemma3:1b" };
      backendOffline = true;
    }
    const hp = state.helper;
    if (backendOffline) {
      el.textContent = "Backend offline (start server: start.bat or python run.py)";
    } else if (hp.online && hp.model_ready) {
      el.textContent = "Helper AI: " + hp.model + " is ready";
    } else if (hp.online) {
      el.textContent = "Helper AI: run  ollama pull " + hp.model + "  to enable it";
    } else {
      el.textContent = "Helper AI offline: built-in rules only";
    }
    $("#use-ai").checked = hp.online && hp.model_ready;
  }

  /* ------------------------------------------------------------ screen 1 */
  function renderHardwareHelp() {
    const list = $("#hw-help");
    clear(list);
    (state.hardwareHelp[state.os] || []).forEach((line) => list.append(h("li", {}, rich(line))));
  }

  function initComputerForm() {
    document.querySelectorAll('input[name="os"]').forEach((r) => {
      r.checked = r.value === state.os;
      r.addEventListener("change", () => {
        state.os = r.value;
        renderHardwareHelp();
        save();
      });
    });
    $("#ram").value = state.specs.ram;
    $("#vram").value = state.specs.vram;
    $("#disk").value = state.specs.disk;
    $("#goal").value = state.specs.goal;

    $("#form-computer").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const ram = parseFloat($("#ram").value);
      const vramRaw = $("#vram").value.trim();
      const diskRaw = $("#disk").value.trim();
      const vram = vramRaw === "" ? 0 : parseFloat(vramRaw);
      const disk = diskRaw === "" ? null : parseFloat(diskRaw);

      if (!(ram > 0)) return showError("#computer-error", "Please enter your RAM in GB (for example 8).");
      if (Number.isNaN(vram) || vram < 0) return showError("#computer-error", "GPU memory must be 0 or more.");
      if (disk !== null && (Number.isNaN(disk) || disk < 0)) return showError("#computer-error", "Free disk space must be 0 or more.");
      showError("#computer-error", "");

      state.specs = { ram: $("#ram").value, vram: $("#vram").value, disk: $("#disk").value, goal: $("#goal").value };
      try {
        const data = await api("/api/recommend", { ram_gb: ram, vram_gb: vram, disk_gb: disk, goal: state.specs.goal });
        state.models = data.models;
        state.recommended = data.recommended;
        state.model = null;
        renderModels();
        show("model");
      } catch (e) {
        showError("#computer-error", e.message);
      }
    });
  }

  /* ------------------------------------------------------------ screen 2 */
  function renderModels() {
    const list = $("#model-list");
    clear(list);
    $("#custom-tag").value = "";
    const selected = state.model || state.recommended || (state.models[0] && state.models[0].tag);

    state.models.forEach((m) => {
      const radio = h("input", { type: "radio", name: "model", value: m.tag });
      radio.checked = m.tag === selected;
      radio.addEventListener("change", () => { $("#custom-tag").value = ""; });
      const title = h("div", { class: "model-title" },
        h("strong", {}, m.name),
        h("code", { class: "inline" }, m.tag),
        m.recommended ? h("span", { class: "badge" }, "Recommended") : null);
      const meta = h("div", { class: "model-meta" },
        m.size_gb + " GB download · about " + m.min_ram_gb + " GB RAM · " + m.blurb);
      const fit = h("div", { class: "fit fit-" + m.fit }, m.label);
      list.append(h("label", { class: "model-row" }, radio, h("div", { class: "model-body" }, title, meta, fit)));
    });
  }

  function chosenTag() {
    const custom = $("#custom-tag").value.trim();
    if (custom) {
      if (!TAG_RE.test(custom)) return { error: "That model name does not look valid. Example: mistral:7b" };
      return { tag: custom };
    }
    const checked = document.querySelector('input[name="model"]:checked');
    if (!checked) return { error: "Please choose a model." };
    return { tag: checked.value };
  }

  async function startSetup(tag) {
    const data = await api("/api/plan", { os: state.os, model: tag });
    state.model = tag;
    state.modelName = data.model.name;
    state.plan = data.steps;
    renderSetup();
    show("setup");
  }

  function initModelScreen() {
    $("#btn-model-back").addEventListener("click", () => show("computer"));
    $("#custom-tag").addEventListener("input", () => {
      if ($("#custom-tag").value.trim()) {
        document.querySelectorAll('input[name="model"]').forEach((r) => { r.checked = false; });
      }
    });
    $("#btn-start").addEventListener("click", async () => {
      const pick = chosenTag();
      if (pick.error) return showError("#model-error", pick.error);
      showError("#model-error", "");
      state.idx = 0;
      try {
        await startSetup(pick.tag);
      } catch (e) {
        showError("#model-error", e.message);
      }
    });
  }

  /* ------------------------------------------------------------ screen 3 */
  function renderSetup() {
    const step = state.plan[state.idx];
    $("#step-count").textContent = "Step " + (state.idx + 1) + " of " + state.plan.length;
    $("#model-label").textContent = state.modelName + " · " + state.os;
    $("#bar-fill").style.width = (state.idx / state.plan.length) * 100 + "%";

    const title = $("#step-title");
    clear(title);
    title.append(step.title);
    if (step.optional) title.append(h("span", { class: "tag-optional" }, "Optional"));

    $("#step-explain").textContent = step.explain;

    const cmds = $("#step-commands");
    clear(cmds);
    step.commands.forEach((c) => cmds.append(cmdBlock(c)));

    const note = $("#step-note");
    clear(note);
    if (step.note) note.append(rich(step.note));
    note.hidden = !step.note;

    $("#step-expected").textContent = step.expected;
    $("#output").value = "";
    clear($("#result"));
    $("#btn-prev").hidden = state.idx === 0;
    $("#btn-skip").textContent = state.idx === state.plan.length - 1 ? "Finish without checking" : "Skip this step";
    save();
  }

  function advance() {
    if (state.idx < state.plan.length - 1) {
      state.idx += 1;
      renderSetup();
      window.scrollTo(0, 0);
    } else {
      renderDone();
      show("done");
    }
  }

  function aiBox(ai) {
    if (!ai) return null;
    const box = h("div", { class: "ai-box" },
      h("div", { class: "label" }, "In plain words (helper AI)"));
    if (ai.explanation) box.append(h("p", {}, rich(ai.explanation)));
    if (ai.next_steps && ai.next_steps.length) {
      box.append(h("ol", {}, ai.next_steps.map((s) => h("li", {}, rich(s)))));
    }
    box.append(h("p", { class: "disclaimer" }, "AI-written and can be wrong. The checked steps above come first."));
    return box;
  }

  function renderResult(r) {
    const out = $("#result");
    clear(out);
    const box = h("div", { class: "result " + r.status }, h("h3", {}, r.headline));
    if (r.explanation) box.append(h("p", {}, rich(r.explanation)));
    if (r.fix && r.fix.length) {
      box.append(h("div", { class: "label" }, "What to try"));
      box.append(h("ol", {}, r.fix.map((f) => h("li", {}, rich(f)))));
    }
    if (r.also_possible && r.also_possible.length) {
      box.append(h("p", { class: "muted small" }, "Other possibilities: " + r.also_possible.join("; ")));
    }
    const ai = aiBox(r.ai);
    if (ai) box.append(ai);

    if (r.status === "success") {
      const last = state.idx === state.plan.length - 1;
      box.append(h("div", { class: "actions" },
        h("button", { type: "button", class: "btn primary", onclick: advance }, last ? "Finish" : "Next step →")));
    }
    out.append(box);
  }

  async function checkOutput() {
    const step = state.plan[state.idx];
    const text = $("#output").value;
    const btn = $("#btn-check");
    if (!text.trim()) {
      return renderResult({ status: "empty", headline: "Nothing to check yet",
        explanation: "Paste the text your terminal printed after you ran the command, then press Check.", fix: [] });
    }
    btn.disabled = true;
    btn.textContent = "Checking…";
    const out = $("#result");
    clear(out);
    if ($("#use-ai").checked) {
      out.append(h("p", { class: "pending" }, "Reading your output. If the helper AI is used, this can take a little while on slower computers."));
    }
    try {
      const r = await api("/api/check", {
        os: state.os, model: state.model, step_id: step.id, output: text, use_ai: $("#use-ai").checked,
      });
      renderResult(r);
    } catch (e) {
      renderResult({ status: "problem", headline: "Something went wrong in the app", explanation: e.message, fix: [] });
    } finally {
      btn.disabled = false;
      btn.textContent = "Check my output";
    }
  }

  async function askForHelp() {
    const q = $("#question").value.trim();
    const out = $("#answer");
    clear(out);
    if (q.length < 3) {
      out.append(h("p", { class: "error" }, "Describe the problem in a few words first."));
      return;
    }
    const btn = $("#btn-ask");
    btn.disabled = true;
    out.append(h("p", { class: "pending" }, "Looking through known problems…"));
    try {
      const step = state.plan[state.idx];
      const r = await api("/api/ask", {
        os: state.os, model: state.model, question: q,
        step_id: step ? step.id : null, use_ai: $("#use-ai").checked,
      });
      clear(out);
      const box = h("div", { class: "result unclear" });
      if (!r.matches.length && !r.ai) {
        box.append(h("h3", {}, "No match yet"));
        box.append(h("p", {}, "Add the exact error text or what you saw on screen. You can also search the error on ollama.com or in the Ollama GitHub issues."));
      }
      r.matches.forEach((m) => {
        box.append(h("h3", {}, m.title));
        box.append(h("p", {}, rich(m.cause)));
        box.append(h("ol", {}, m.fix.map((f) => h("li", {}, rich(f)))));
      });
      const ai = aiBox(r.ai);
      if (ai) box.append(ai);
      out.append(box);
    } catch (e) {
      clear(out);
      out.append(h("p", { class: "error" }, e.message));
    } finally {
      btn.disabled = false;
    }
  }

  function initSetupScreen() {
    $("#btn-check").addEventListener("click", checkOutput);
    $("#btn-skip").addEventListener("click", advance);
    $("#btn-prev").addEventListener("click", () => {
      if (state.idx > 0) { state.idx -= 1; renderSetup(); }
    });
    $("#btn-ask").addEventListener("click", askForHelp);
  }

  /* ------------------------------------------------------------ screen 4 */
  function renderDone() {
    $("#done-text").textContent = "If every step passed, " + state.modelName + " now runs on your own computer, offline and for free.";
    const box = $("#done-commands");
    clear(box);
    [
      ["Chat with the model", "ollama run " + state.model],
      ["See downloaded models", "ollama list"],
      ["See what is running", "ollama ps"],
      ["Delete a model to free space", "ollama rm " + state.model],
    ].forEach(([label, cmd]) => {
      box.append(h("p", { class: "muted small" }, label));
      box.append(cmdBlock(cmd));
    });
    box.append(h("p", { class: "muted small" }, "Local API address for your own programs: http://localhost:11434"));
    $("#bar-fill").style.width = "100%";
  }

  function initDoneScreen() {
    $("#btn-restart").addEventListener("click", () => {
      wipe();
      state.model = null;
      state.plan = [];
      state.idx = 0;
      show("computer");
    });
  }

  /* ------------------------------------------------------------ start */
  async function init() {
    const saved = load();
    initComputerForm();
    initModelScreen();
    initSetupScreen();
    initDoneScreen();

    try {
      const cfg = await api("/api/config");
      state.hardwareHelp = cfg.hardware_help || {};
    } catch (e) {
      showError("#computer-error", e.message);
    }
    renderHardwareHelp();
    refreshHealth();

    if (saved && saved.model && (saved.screen === "setup" || saved.screen === "done")) {
      try {
        await startSetup(saved.model);
        state.idx = Math.min(Math.max(parseInt(saved.idx, 10) || 0, 0), state.plan.length - 1);
        renderSetup();
        show("setup");
        return;
      } catch (e) { /* fall through to the first screen */ }
    }
    show("computer");
  }

  init();
})();
