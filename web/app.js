/* Crease IQ: single-page UI (no build step, no dependencies). */
(() => {
  "use strict";

  // ------------------------------------------------------------------ constants
  const TEAM_STYLE = {
    CSK: ["Chennai Super Kings", "#f2b705", "#d97904"], DC: ["Delhi Capitals", "#17479e", "#d71920"],
    GT: ["Gujarat Titans", "#1b2133", "#b8955a"], KKR: ["Kolkata Knight Riders", "#3a225d", "#7b55c7"],
    LSG: ["Lucknow Super Giants", "#0057e2", "#a72056"], MI: ["Mumbai Indians", "#004ba0", "#2f8ff0"],
    PBKS: ["Punjab Kings", "#dd1f2d", "#8f1018"], RR: ["Rajasthan Royals", "#ea1a85", "#254aa5"],
    RCB: ["Royal Challengers Bengaluru", "#c8102e", "#2b2b2b"], SRH: ["Sunrisers Hyderabad", "#f26522", "#b8331a"],
    IND: ["India", "#0a4fa3", "#ff9933"], AUS: ["Australia", "#00843d", "#e0b000"], ENG: ["England", "#012169", "#c8102e"],
    PAK: ["Pakistan", "#01411c", "#2e8b57"], NZ: ["New Zealand", "#111111", "#5c5c5c"], SA: ["South Africa", "#007749", "#e0a21a"],
    SL: ["Sri Lanka", "#0b2a6f", "#e0a200"], WI: ["West Indies", "#7b0041", "#d99a00"], BAN: ["Bangladesh", "#006a4e", "#f42a41"],
    AFG: ["Afghanistan", "#0b3d91", "#d32011"], ZIM: ["Zimbabwe", "#c40000", "#e8b900"], IRE: ["Ireland", "#169b62", "#0b5e36"],
    SCO: ["Scotland", "#0065bd", "#1b2f5c"], NED: ["Netherlands", "#ff6600", "#21468b"],
  };
  const NAME_TO_CODE = Object.fromEntries(Object.entries(TEAM_STYLE).map(([code, [name]]) => [name, code]));
  const MODEL_CLASS = { original_formula: "m0", logistic_regression: "m1", lightgbm: "m2", ensemble_lr_lgbm: "m3" };
  const FEATURE_NAMES = {
    runs_vs_par: "Runs compared with par", elo_diff: "Team rating gap (Elo)", kal_diff: "Team rating gap (Kalman)", kal_unc: "How sure the team ratings are", kal_diff_chase: "Team rating gap (Kalman)", chase_xi_bat: "Chasing XI batting strength",
    bat_xi_exp: "Batting XI experience", chase_xi_exp: "Chasing XI experience", wickets: "Wickets lost",
    bat_xi_bat: "Batting XI batting strength", runs: "Runs scored", run_rate: "Run rate",
    bat_xi_bowl_econ: "Batting side's bowling economy", chase_xi_bowl_econ: "Chasing side's bowling economy",
    venue_avg: "Venue average score", is_club: "IPL or international", is_odi: "T20 or ODI", balls_left_frac: "Overs remaining",
  };
  // ------------------------------------------------------------------ cricket badge icons (18 Nov 2026)
  // Each icon: [colour, filled shapes, ink lines, accent lines]. Drawn on a 24 grid, then shrunk into a soft
  // coloured circle (the badge). cq(name, true) gives the "mini" version (no circle) for small pills.
  const CQ = {
    ball: ["var(--ball)", '<circle cx="12" cy="12" r="7.5"/>', "", '<path d="M8.2 6c2.2 3.7 2.2 8.3 0 12M15.8 6c-2.2 3.7-2.2 8.3 0 12"/>'],
    whiteball: ["var(--cq-slate)", '<circle cx="12" cy="12" r="7.5"/>', "", '<path d="M8.2 6c2.2 3.7 2.2 8.3 0 12M15.8 6c-2.2 3.7-2.2 8.3 0 12"/>'],
    bat: ["var(--cq-wood)", '<path d="M14.2 3.8l6 6-8.6 8.6a2 2 0 0 1-2.8 0l-3.2-3.2a2 2 0 0 1 0-2.8z"/>', '<path d="M6.6 17.4l-3.1 3.1"/>', '<path d="M15.6 8.4l-6 6"/>'],
    stumps: ["var(--gold)", "", '<path d="M7 7.5v13M12 7.5v13M17 7.5v13M4 20.5h16"/>', '<path d="M6 5.6l5-1.4M13 4.2l5 1.4"/>'],
    helmet: ["var(--pitch)", '<path d="M4 14a8 8 0 0 1 16 0v1.2H4z"/>', '<path d="M12 6v3"/>', '<path d="M8 15.2v4.3h8v-4.3M10.7 15.2v4.3M13.3 15.2v4.3"/>'],
    duel: ["var(--ball)", '<circle cx="17" cy="7" r="3.6"/><path d="M9.6 8.4l4 4-6.3 6.3a1.6 1.6 0 0 1-2.3 0l-1.7-1.7a1.6 1.6 0 0 1 0-2.3z"/>', '<path d="M4.6 19.4L3 21"/>', '<path d="M15.5 4.5c1.2 1.4 1.2 3.6 0 5"/>'],
    scoreboard: ["var(--pitch)", '<rect x="3" y="4" width="18" height="12.5" rx="2"/>', '<path d="M8 16.5v4M16 16.5v4"/>', '<path d="M6.5 8.5h3v4.5h-3zM13.5 8.5h4M17.5 8.5v4.5h-4"/>'],
    scorebook: ["var(--cq-slate)", '<path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v13H7.5A2.5 2.5 0 0 1 5 17.5z"/>', '<path d="M5 17.5A2.5 2.5 0 0 1 7.5 15H18"/>', '<path d="M9 8h5.5M9 11h3.5"/>'],
    rewind: ["var(--cq-plum)", '<circle cx="12" cy="12" r="3.8"/>', '<path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4.5h4.5"/>', '<path d="M10.5 9.2c.9 1.7.9 3.9 0 5.6"/>'],
    tree: ["var(--pitch)", '<path d="M12 3l6 7h-3l4 5H5l4-5H6z"/>', '<path d="M12 15v6"/>', '<path d="M9.5 21h5"/>'],
    trophy: ["var(--gold)", '<path d="M7 4h10v4.5a5 5 0 0 1-10 0z"/>', '<path d="M12 13.5v3.5M8 20.5h8M9.5 17h5"/>', '<path d="M7 6H4.5v1a3 3 0 0 0 3 3M17 6h2.5v1a3 3 0 0 1-3 3"/>'],
    flame: ["var(--cq-ember)", '<path d="M12 3c1 3.2 5 5.4 5 10a5 5 0 0 1-10 0c0-2.4 1.2-3.8 2.4-5 .2 1.8 1 2.8 2 3.2C11 8.7 11 5.6 12 3z"/>', "", '<path d="M12 20.6a2.1 2.1 0 0 1-2.1-2.1c0-1.4 1.1-2.2 2.1-3.5 1 1.3 2.1 2.1 2.1 3.5a2.1 2.1 0 0 1-2.1 2.1z"/>'],
    stadium: ["var(--pitch)", '<ellipse cx="12" cy="13" rx="9" ry="6.5"/>', '<path d="M7 5.5l1 2M17 5.5l-1 2M12 4v2.5"/>', '<rect x="10.4" y="9.2" width="3.2" height="7.6" rx=".6"/>'],
    gauge: ["var(--gold)", '<circle cx="12" cy="16" r="1.8"/>', '<path d="M4 16a8 8 0 0 1 16 0M3.5 19.5h17"/>', '<path d="M12.9 14.6l3.6-4.4"/>'],
    cycle: ["var(--pitch)", '<circle cx="12" cy="12" r="3"/>', '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8M4 3v5h5M4 13a8 8 0 0 0 14.6 4.5L20 16M20 21v-5h-5"/>', '<path d="M11 10.2c.6 1.1.6 2.5 0 3.6"/>'],
    finger: ["var(--ball)", "", '<path d="M9.5 12V5a1.5 1.5 0 0 1 3 0v6M12.5 10.5a1.5 1.5 0 0 1 3 0v1M15.5 11.2a1.5 1.5 0 0 1 3 0v3.3a6.5 6.5 0 0 1-6.5 6.5h-.5a6 6 0 0 1-5.5-3.6L5 15.2a1.5 1.5 0 0 1 2.6-1.4l1.9 2.2"/>', '<path d="M15.8 3.6l1.1-1.1M17.6 6.4h1.6"/>'],
    laptop: ["var(--cq-slate)", '<rect x="4" y="5" width="16" height="10.5" rx="1.6"/>', '<path d="M2.5 19h19"/>', '<circle cx="12" cy="10.2" r="2.2"/>'],
  };
  function cq(name, mini = false) {
    const [c, f, l, a] = CQ[name] || CQ.ball;
    const art = `<g class="cq-f">${f}</g><g class="cq-l">${l}</g><g class="cq-a">${a}</g>`;
    return mini
      ? `<svg class="cq cq-mini" viewBox="0 0 24 24" style="--c:${c}" aria-hidden="true">${art}</svg>`
      : `<svg class="cq" viewBox="0 0 24 24" style="--c:${c}" aria-hidden="true"><circle class="cq-bg" cx="12" cy="12" r="11.5"/><g transform="translate(3.6 3.6) scale(.7)">${art}</g></svg>`;
  }
  // placeholders in the page: <i data-cq="ball"></i> (add data-mini for the small version)
  document.querySelectorAll("i[data-cq]").forEach((el) => { el.outerHTML = cq(el.dataset.cq, el.hasAttribute("data-mini")); });
  const ICONS = { score: cq("scoreboard"), rating: cq("trophy"), xi: cq("helmet") };

  // ------------------------------------------------------------------ helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(`cwp.${k}`); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(`cwp.${k}`, JSON.stringify(v)); } catch { /* storage unavailable */ } },
    del(k) { try { localStorage.removeItem(`cwp.${k}`); } catch { /* storage unavailable */ } },
  };
  // public (online) copy: no shared files on the server; saved predictions live in this browser
  const PUBLIC = document.documentElement.classList.contains("public");
  // while the "server isn't running" bar shows, check every 3 s and reload the page by itself once the server answers
  // (e.g. the page was opened while the app was still starting)
  function watchServer() {
    if (watchServer.timer) return;
    const note = () => document.getElementById("server-watch");
    const bar = document.getElementById("server-down");
    if (bar && !note()) bar.querySelector("span")?.insertAdjacentHTML("beforeend", ` <i id="server-watch">Checking again every few seconds: the page will reload by itself.</i>`);
    watchServer.timer = setInterval(async () => {
      try {
        const r = await fetch("/api/settings", { cache: "no-store" });
        if (r.ok) { clearInterval(watchServer.timer); if (note()) note().textContent = "Server found. Reloading…"; location.reload(); }
      } catch { /* still not there */ }
    }, 3000);
  }
  async function api(path, body) {
    if (path.startsWith("/api/history") && typeof histSource === "string" && histSource !== "both") {
      if (body === undefined) path += `${path.includes("?") ? "&" : "?"}source=${histSource}`;
      else body = { ...body, source: histSource };
    }
    if (PUBLIC && body && (body.save === true || path.startsWith("/api/history"))) body = { ...body, client_history: store.get("pub.history", []) };
    let res;
    try {
      res = await fetch(path, body === undefined ? {} : {
        method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body),
      });
    } catch (err) {  // no answer at all: the server isn't running (or is still starting)
      const bar = document.getElementById("server-down"); if (bar) bar.hidden = false;
      watchServer();
      throw new Error("the Crease IQ server isn't running");
    }
    const bar = document.getElementById("server-down"); if (bar && !bar.hidden) bar.hidden = true;
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    if (PUBLIC && Array.isArray(data.client_history)) { store.set("pub.history", data.client_history); delete data.client_history; }
    return data;
  }
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false; t.classList.remove("has-undo");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.hidden = true; }, 2600);
  }
  // message with an Undo button (stays ~8 s); onUndo runs once if it's clicked
  function toastUndo(msg, onUndo) {
    const t = $("#toast");
    t.innerHTML = `<span>${esc(msg)}</span><button type="button" class="toast-undo">Undo</button>`;
    t.hidden = false; t.classList.add("has-undo");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.hidden = true; t.classList.remove("has-undo"); }, 8000);
    t.querySelector(".toast-undo").addEventListener("click", () => {
      clearTimeout(toast.timer); t.hidden = true; t.classList.remove("has-undo"); onUndo();
    }, { once: true });
  }
  function teamStyle(codeOrName) {
    const code = TEAM_STYLE[codeOrName] ? codeOrName : NAME_TO_CODE[codeOrName];
    if (code) return { code, c1: TEAM_STYLE[code][1], c2: TEAM_STYLE[code][2] };
    const initials = String(codeOrName || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 3).toUpperCase();
    return { code: initials, c1: "#3d4a43", c2: "#6c7c72" };
  }
  // cut-out team logos (web/img/logos, from scripts/team_logos.py), keyed by team code
  const LOGOS = {}; const LOGO_IMG = {};
  const logoOf = (code) => LOGOS[code] || null;
  function paintBadge(el, codeOrName) {
    const s = teamStyle(codeOrName); const logo = logoOf(s.code);
    el.textContent = s.code; el.style.setProperty("--c1", s.c1); el.style.setProperty("--c2", s.c2);
    el.classList.toggle("has-logo", !!logo);
    if (logo) el.style.setProperty("--logo", `url("${logo}")`); else el.style.removeProperty("--logo");
    el.title = team(s.code)?.name || s.code;
  }
  const badgeHTML = (codeOrName, size = "sm") => {
    const s = teamStyle(codeOrName); const logo = logoOf(s.code);
    return `<span class="team-badge ${size}${logo ? " has-logo" : ""}" style="--c1:${s.c1};--c2:${s.c2}${logo ? `;--logo:url('${logo}')` : ""}">${esc(s.code)}</span>`;
  };

  // ------------------------------------------------------------------ state
  const state = {
    mode: store.get("mode", "ipl") === "international" ? "international" : "ipl",
    config: null, format: "t20", batting: null, chasing: null, venue: null, country: "all",
    runs: 175, wickets: 6, balls: 120, par: null, xi: { bat: [], chase: [] }, hasResult: false,
    order: { bat: false, chase: false },  // true once you drag a Selected XI into your own batting order
  };
  const maxBalls = () => (state.format === "odi" ? 300 : 120);
  const oversText = (balls) => `${Math.floor(balls / 6)}.${balls % 6}`;
  const team = (code) => state.config?.teams.find((t) => t.code === code) || { code, name: code || "", squad: [], latest_xi: {} };  // safe before the team list loads
  const venue = () => {
    if (String(state.venue).startsWith("custom:")) {  // a ground that isn't in the data yet
      const name = state.venue.slice(7); const cp = state.config.custom_par;
      const note = "Not in the match data yet, so the recent average for this format is used. Set your own par under Playing XIs & par score.";
      return { code: state.venue, name, city: "", country: "", matches: 0, par_t20: cp.t20, par_odi: cp.odi, par_t20_note: note, par_odi_note: note, custom: true };
    }
    return state.config.venues.find((v) => v.code === state.venue) || state.config.venues[0];
  };
  const autoPar = () => venue()[`par_${state.format}`];
  // conditions you set from the pitch report (same numbers as the server)
  const PITCH = { balanced: ["Balanced", 1.0], flat: ["Flat / batting", 1.08], green: ["Green / grassy", 0.94], dry: ["Dry / turning", 0.93], slow: ["Slow / low", 0.91] };
  const DEW = { none: ["No effect", 0], light: ["Light dew", 3], heavy: ["Heavy dew", 6], slowing: ["Pitch slows / no dew", -4] };  // points at 50/50 (Tuning can change them)
  state.pitch = "balanced"; state.dew = "none";
  const modelPar = () => Math.round(autoPar() * PITCH[state.pitch][1]);  // venue par, scaled by the pitch you chose
  const currentPar = () => state.par || modelPar();

  // ------------------------------------------------------------------ router
  const VIEWS = ["home", "predict", "accuracy", "replay", "history", "data"];
  function markTabs() {
    const tab = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "home";
    $$(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tabAlias === "chase"
      ? tab === "predict" && state.stage === "chase"
      : a.dataset.tab === tab && !(tab === "predict" && state.stage === "chase")));
  }
  function route() {
    // online copy: no Data page, and no Replay (its match archive isn't uploaded and wouldn't fit the free plan's memory)
    if (PUBLIC && (location.hash === "#data" || location.hash === "#replay")) { location.hash = "#home"; return; }
    const tab = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "home";
    VIEWS.forEach((v) => { $(`#view-${v}`).hidden = v !== tab; });
    $("#insights").hidden = tab !== "predict";
    markTabs();
    if (tab === "accuracy") loadAccuracy();
    if (tab === "history") loadHistory();
    if (tab === "replay") openReplay(); else pauseReplay();
    if (tab === "data") loadData();
    if (tab !== "data") stopPolling();
    window.scrollTo({ top: 0 });
  }

  // ------------------------------------------------------------------ mode
  async function setMode(mode) {
    state.mode = mode; store.set("mode", mode);
    document.documentElement.dataset.mode = mode;
    $$(".mode-switch button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    $("#predict-eyebrow").textContent = mode === "ipl" ? "IPL 2026 · T20 & ODI" : "International cricket · T20 & ODI";
    $("#brand-sub").textContent = mode === "ipl" ? "Match intelligence · IPL" : "Match intelligence · International";
    applyPhotos();
    loadTopTeams(mode); renderScorecard();
    try {
      state.config = await api(`/api/config?mode=${mode}`);
    } catch (err) { showError(`Could not load teams: ${err.message}`); return; }
    const d = state.config.defaults;
    state.batting = d.batting; state.chasing = d.chasing; state.venue = d.venue; state.par = null; state.country = "all";
    fillSelects(); resetXI(); syncPar(); renderCountries();
    state.runs = autoPar(); state.wickets = 6; state.balls = maxBalls();
    syncScore(); clearResult();
    if (state.stage === "chase") setStage("chase");
  }

  // ------------------------------------------------------------------ predict form
  function fillSelects() {
    const opts = state.config.teams.map((t) => `<option value="${esc(t.code)}">${esc(t.name)}</option>`).join("");
    $("#batting-select").innerHTML = opts; $("#chasing-select").innerHTML = opts;
    $("#batting-select").value = state.batting; $("#chasing-select").value = state.chasing;
    $("#venue-input").value = venueLabel(venue());
    paintTeams();
  }

  // ---------- venue search (hundreds of grounds, so a search box instead of a dropdown)
  const venueLabel = (v) => (v.city && !v.name.includes(v.city) ? `${v.name}, ${v.city}` : v.name);
  const fold = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ");
  let comboItems = []; let comboActive = -1;
  // ---------- country filter for grounds
  const venuesInCountry = () => (state.country === "all" ? state.config.venues : state.config.venues.filter((v) => v.country === state.country));
  function countryCounts() {
    const counts = {};
    state.config.venues.forEach((v) => { counts[v.country] = (counts[v.country] || 0) + 1; });
    return counts;
  }
  function renderCountries() {
    const counts = countryCounts();
    const countries = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));
    $("#country-select").innerHTML = `<option value="all">All countries (${state.config.venues.length} grounds)</option>`
      + countries.map((c) => `<option value="${esc(c)}">${esc(c)} (${counts[c]})</option>`).join("");
    $("#country-select").value = state.country;
    // quick buttons: the two teams' home countries (international) or the IPL host countries
    const quick = state.mode === "international"
      ? [team(state.batting).name, team(state.chasing).name].filter((c, i, a) => counts[c] && a.indexOf(c) === i)
      : countries.slice(0, 3);
    $("#country-chips").innerHTML = ["all", ...quick].map((c) => `<button type="button" data-country="${esc(c)}" class="${c === state.country ? "active" : ""}">${c === "all" ? "All" : esc(c)}<small>${c === "all" ? state.config.venues.length : counts[c]}</small></button>`).join("")
      + (state.country !== "all" && !quick.includes(state.country) ? `<button type="button" class="active" data-country="${esc(state.country)}">${esc(state.country)}<small>${counts[state.country]}</small></button>` : "");
  }
  function setCountry(country, openList = true) {
    state.country = country;
    const pool = venuesInCountry();
    if (state.country !== "all" && !pool.some((v) => v.code === state.venue)) {
      const busiest = [...pool].sort((a, b) => b.matches - a.matches)[0];
      if (busiest) state.venue = busiest.code;
    }
    renderCountries(); syncPar(); $("#venue-input").value = venueLabel(venue()); livePredict();
    if (openList) $("#venue-input").focus();
  }

  // other names a ground is known by (sponsor names change; broadcasters use the old name): extra search words only,
  // the ground and its data stay as they are
  const VENUE_ALIASES = [
    [/metricon|heritage bank|people first|carrara/i, "carrara oval gold coast"],  // the Gold Coast's ground (Carrara)
  ];
  const aliasWords = (v) => VENUE_ALIASES.filter(([re]) => re.test(`${v.name} ${v.city}`)).map(([, w]) => w).join(" ");
  function venueMatches(query) {
    const venues = venuesInCountry();
    const words = fold(query).split(/\s+/).filter(Boolean);
    if (!words.length) return [...venues].sort((a, b) => b.matches - a.matches).slice(0, state.country === "all" ? 30 : 200);
    return venues
      .map((v) => {
        const hay = fold(`${v.name} ${v.city} ${v.country} ${aliasWords(v)}`);
        if (!words.every((w) => hay.includes(w))) return null;
        const name = fold(v.name);
        const score = (name.startsWith(words[0]) ? 2000 : 0) + (fold(v.city).startsWith(words[0]) ? 1000 : 0) + v.matches;
        return { v, score };
      })
      .filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 40).map((x) => x.v);
  }
  function renderCombo(query) {
    comboItems = venueMatches(query); comboActive = comboItems.length ? 0 : -1;
    const list = $("#venue-list");
    const where = state.country === "all" ? "" : ` in ${state.country}`;
    const head = fold(query).trim()
      ? `${comboItems.length} match${comboItems.length === 1 ? "" : "es"}${where}`
      : state.country === "all" ? `Most-used grounds · ${state.config.venues.length} in total · pick a country to see them all` : `All ${comboItems.length} grounds${where}`;
    list.innerHTML = `<li class="combo-head" role="presentation">${esc(head)}</li>`
      + (comboItems.length ? comboItems.map((v, i) => `
        <li role="option" id="venue-opt-${i}" data-i="${i}" aria-selected="${i === comboActive}">
          <span><b>${esc(v.name)}</b>${v.city && !v.name.includes(v.city) ? ` <span class="combo-city">· ${esc(v.city)}</span>` : ""}</span>
          <small>${v.matches ? `${v.matches} games · last ${esc((v.last || "").slice(0, 4))}` : "preset"}</small>
        </li>`).join("") : `<li class="combo-empty" role="presentation">No ground in the data matches “${esc(query)}”.</li>`)
      + (fold(query).trim() ? `<li role="option" id="venue-opt-custom" data-custom="1" aria-selected="${comboItems.length ? "false" : "true"}">
          <span>Use <b>“${esc(query.trim())}”</b> <span class="combo-city">· a new ground</span></span><small>par = recent average</small></li>` : "");
    if (!comboItems.length && fold(query).trim()) { comboItems = [{ code: `custom:${query.trim()}` }]; comboActive = 0; }
    list.hidden = false; $("#venue-input").setAttribute("aria-expanded", "true");
  }
  function moveCombo(step) {
    if (!comboItems.length) return;
    comboActive = (comboActive + step + comboItems.length) % comboItems.length;
    $$("#venue-list [role=option]").forEach((li, i) => li.setAttribute("aria-selected", String(i === comboActive)));
    const active = $(`#venue-opt-${comboActive}`); active?.scrollIntoView({ block: "nearest" });
    $("#venue-input").setAttribute("aria-activedescendant", active ? active.id : "");
  }
  function closeCombo() {
    $("#venue-list").hidden = true; $("#venue-input").setAttribute("aria-expanded", "false");
    $("#venue-input").value = venueLabel(venue());
  }
  function chooseVenue(v) {
    if (state.par && v.code !== state.venue) toast("New ground, so par is back to the model's value");
    if (v.code !== state.venue) state.par = null;
    state.venue = v.code; closeCombo(); syncPar(); livePredict(); scheduleInsights();
  }
  function bindVenueCombo() {
    const input = $("#venue-input");
    input.addEventListener("focus", () => { input.select(); renderCombo(""); });
    input.addEventListener("input", () => renderCombo(input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); if ($("#venue-list").hidden) renderCombo(input.value); else moveCombo(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveCombo(-1); }
      else if (e.key === "Enter") { e.preventDefault(); if (comboItems[comboActive]) chooseVenue(comboItems[comboActive]); }
      else if (e.key === "Escape") { closeCombo(); input.blur(); }
    });
    input.addEventListener("blur", () => setTimeout(closeCombo, 150));
    $("#venue-list").addEventListener("mousedown", (e) => {
      const li = e.target.closest("[role=option]"); if (!li) return;
      e.preventDefault();
      chooseVenue(li.dataset.custom ? { code: `custom:${input.value.trim()}` } : comboItems[Number(li.dataset.i)]);
      input.blur();
    });
  }
  function paintTeams() {
    paintBadge($("#batting-badge"), state.batting); paintBadge($("#chasing-badge"), state.chasing);
    $("#xi-bat-title").textContent = `${team(state.batting).name} XI`;
    $("#xi-chase-title").textContent = `${team(state.chasing).name} XI`;
    if (state.config && state.country !== undefined) renderCountries();  // quick country buttons follow the teams
  }
  // XI = the team's latest real XI in this format (from the match data), else a balanced pick
  // one date format everywhere: "3 Nov 2026", or "18 Nov 2026, 21:58" with a time. Takes 2026-11-03, 2026-11-03 21:58[:02],
  // 2026-11-03T21:58 or 03-11-2026 21:58:00; anything else is shown as it came.
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fd(v) {
    const s = String(v ?? "").trim();
    let m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?$/);
    if (m) return `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[1]}${m[4] ? `, ${m[4]}:${m[5]}` : ""}`;
    m = s.match(/^(\d{2})-(\d{2})-(\d{4})(?: (\d{2}):(\d{2})(?::\d{2})?)?$/);
    if (m) return `${+m[1]} ${MONTHS[+m[2] - 1]} ${m[3]}${m[4] ? `, ${m[4]}:${m[5]}` : ""}`;
    return s;
  }
  const fmtDate = fd;
  // pages full of server-written dates (Data): reformat any date in their text as it renders
  const DATE_IN_TEXT = /\b(?:\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d{2}-\d{2}-\d{4}(?: \d{2}:\d{2}(?::\d{2})?)?)\b/g;
  function fdText(root) {
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement?.closest("pre, input, textarea, script, style")) continue;  // logs stay as written
      const out = n.nodeValue.replace(DATE_IN_TEXT, (m) => fd(m));
      if (out !== n.nodeValue) n.nodeValue = out;
    }
  }
  function keepDatesTidy(el) {
    if (!el) return;
    fdText(el);
    new MutationObserver(() => fdText(el)).observe(el, { childList: true, subtree: true });
  }
  function suggestedXI(code) {
    const t = team(code); const latest = t.latest_xi?.[state.format] || t.latest_xi?.t20;
    return latest ? [...latest.xi] : [...t.balanced_xi];
  }
  // ---- IPL Impact Player: one substitute per side who can come in at any point (a 12th player for the model)
  state.impact = { bat: { in: "", out: "" }, chase: { in: "", out: "" } };
  // ---- who is at the crease (optional): [{name, balls}, ...] per side
  state.crease = { bat: [{ name: "", balls: "" }, { name: "", balls: "" }], chase: [{ name: "", balls: "" }, { name: "", balls: "" }] };
  const creaseOf = (side) => state.crease[side].filter((c) => c.name).map((c) => ({ name: c.name, balls: c.balls === "" ? null : Number(c.balls) }));
  function renderCrease() {
    for (const side of ["bat", "chase"]) {
      const box = $(`#crease-${side}`); if (!box) continue;
      const xi = [...state.xi[side], ...(state.mode === "ipl" && state.impact[side].in ? [state.impact[side].in] : [])];
      state.crease[side].forEach((c) => { if (c.name && !xi.includes(c.name)) { c.name = ""; c.balls = ""; } });
      state.crease[side].forEach((c, i) => {
        const other = state.crease[side][1 - i].name;
        $(`[data-crease-name="${side}|${i}"]`).innerHTML = `<option value="">${i ? "Non-striker" : "Batter"}…</option>` +
          xi.filter((n) => n !== other).map((n) => `<option value="${esc(n)}" ${n === c.name ? "selected" : ""}>${esc(n)}</option>`).join("");
        const ballsBox = $(`[data-crease-balls="${side}|${i}"]`); if (ballsBox) ballsBox.value = c.balls;
      });
      const set = creaseOf(side);
      $(`#crease-${side}-sum`).textContent = set.length
        ? set.map((c) => `${c.name}${c.balls != null ? ` (${c.balls})` : ""}`).join(" & ")
        : "Guessing from the batting order";
      box.classList.toggle("on", set.length > 0);
    }
  }
  function bindCrease() {
    document.addEventListener("change", (e) => {
      const n = e.target.closest?.("[data-crease-name]"); const b = e.target.closest?.("[data-crease-balls]");
      if (!n && !b) return;
      const [side, i] = (n || b).dataset[n ? "creaseName" : "creaseBalls"].split("|");
      if (n) state.crease[side][i].name = n.value;
      if (b) state.crease[side][i].balls = b.value === "" ? "" : Math.max(0, parseInt(b.value, 10) || 0);
      renderCrease();
      if (side === "chase") predictChase(false); else livePredict();
    });
    $$("[data-crease-clear]").forEach((btn) => btn.addEventListener("click", () => {
      const side = btn.dataset.creaseClear;
      state.crease[side] = [{ name: "", balls: "" }, { name: "", balls: "" }];
      renderCrease(); if (side === "chase") predictChase(false); else livePredict();
    }));
  }
  const xiPayload = () => ({
    pitch: state.pitch, dew: state.dew, pitch_report: state.pitchReport || null,
    batting_crease: creaseOf("bat"), chasing_crease: creaseOf("chase"),
    batting_xi: state.xi.bat, chasing_xi: state.xi.chase,
    batting_order_set: state.order.bat, chasing_order_set: state.order.chase,
    batting_impact: state.mode === "ipl" && state.impact.bat.in ? state.impact.bat : null,
    chasing_impact: state.mode === "ipl" && state.impact.chase.in ? state.impact.chase : null,
  });
  function latestImpact(code) {
    const t = team(code); const latest = t?.latest_xi?.[state.format] || t?.latest_xi?.t20;
    const imp = latest?.impact; if (!imp || !t.squad.some((p) => p.name === imp.in)) return { in: "", out: "" };
    return { in: imp.in, out: imp.out && latest.xi.includes(imp.out) ? imp.out : "" };
  }
  function renderImpact() {
    for (const [side, code] of [["bat", state.batting], ["chase", state.chasing]]) {
      const row = $(`#impact-${side}`); if (!row) continue;
      row.hidden = state.mode !== "ipl";
      if (row.hidden) continue;
      const t = team(code); const xi = new Set(state.xi[side]); const imp = state.impact[side];
      if (imp.in && xi.has(imp.in)) imp.in = "";        // ticked into the XI: no longer the substitute
      if (imp.out && !xi.has(imp.out)) imp.out = "";
      const bench = t.squad.filter((p) => !xi.has(p.name));
      $(`[data-impact-in="${side}"]`).innerHTML = `<option value="">None</option>` + bench.map((p) =>
        `<option value="${esc(p.name)}" ${p.name === imp.in ? "selected" : ""}>${esc(p.name)}${p.role_label ? ` · ${esc(p.role_label)}` : ""}</option>`).join("");
      $(`[data-impact-out="${side}"]`).innerHTML = `<option value="">Not yet / nobody</option>` + state.xi[side].map((n) =>
        `<option value="${esc(n)}" ${n === imp.out ? "selected" : ""}>${esc(n)}</option>`).join("");
      $(`[data-impact-out="${side}"]`).disabled = !imp.in;
      row.classList.toggle("on", !!imp.in);
    }
  }
  function bindImpact() {
    document.addEventListener("change", (e) => {
      const tin = e.target.closest?.("[data-impact-in]"); const tout = e.target.closest?.("[data-impact-out]");
      if (!tin && !tout) return;
      const side = (tin || tout).dataset.impactIn || (tin || tout).dataset.impactOut;
      if (tin) { state.impact[side].in = tin.value; if (!tin.value) state.impact[side].out = ""; }
      if (tout) state.impact[side].out = tout.value;
      renderImpact(); livePredict();
      const imp = state.impact[side]; const tname = team(side === "bat" ? state.batting : state.chasing).name;
      toast(imp.in ? `Impact: ${imp.in}${imp.out ? ` in for ${imp.out}` : " ready to come in"} (${tname})` : `No impact player for ${tname}`);
    });
  }
  // useSaved: bring back the XI and batting order you last set for that team (this browser), unless the team has
  // played a newer real match since; "Latest XI" passes false to get the real latest XI instead
  function resetXI(side, useSaved = true) {
    for (const s of side ? [side] : ["bat", "chase"]) {
      const code = s === "bat" ? state.batting : state.chasing;
      state.xi[s] = suggestedXI(code);
      state.impact[s] = latestImpact(code);
      state.order[s] = false;
      const saved = useSaved ? savedXI(code) : null;
      if (saved) { state.xi[s] = [...saved.xi]; state.order[s] = !!saved.order; }
    }
    renderXI();
  }
  // ---- your own XIs, remembered per team, format and IPL / International (so a refresh doesn't lose them)
  const xiKey = (code) => `xi.${state.mode}.${state.format}.${code}`;
  const latestXIDate = (code) => { const t = team(code); return String((t.latest_xi?.[state.format] || t.latest_xi?.t20)?.date || ""); };
  function savedXI(code) {
    const s = code ? store.get(xiKey(code), null) : null;
    if (!s || !Array.isArray(s.xi) || !s.xi.length) return null;
    if (latestXIDate(code) > String(s.latest || "")) return null;  // a newer real XI since you saved: use that instead
    const squad = team(code).squad;
    return s.xi.every((n) => squad.some((p) => p.name === n)) ? s : null;
  }
  function rememberXI() {  // only your own picks are kept; the latest real XI needs no saving
    if (!state.config) return;
    for (const [side, code] of [["bat", state.batting], ["chase", state.chasing]]) {
      if (!code) continue;
      const xi = state.xi[side];
      const own = xi.length > 0 && (state.order[side] || !sameXI(xi, suggestedXI(code)));
      if (own) store.set(xiKey(code), { xi: [...xi], order: state.order[side], latest: latestXIDate(code) });
      else store.del(xiKey(code));
    }
  }
  // batting order: until you drag the Selected XI, it follows each player's usual position (the model's own guess)
  const sameXI = (a, b) => a.length === b.length && [...a].sort().join() === [...b].sort().join();
  function usualOrder(side) {
    if (state.order[side]) return;
    const squad = team(side === "bat" ? state.batting : state.chasing).squad;
    const pos = new Map(squad.map((p) => [p.name, p.pos?.[state.format] ?? 8]));
    const was = new Map(state.xi[side].map((n, i) => [n, i]));
    state.xi[side].sort((a, b) => (pos.get(a) ?? 8) - (pos.get(b) ?? 8) || was.get(a) - was.get(b));
  }
  function moveInXI(side, from, to, keepFocus = false) {
    const list = state.xi[side];
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
    const [nm] = list.splice(from, 1); list.splice(to, 0, nm);
    state.order[side] = true; renderXI(); livePredict();
    // arrows: keep focus on the same arrow of the moved player, so repeated presses keep moving them
    const dir = to < from ? -1 : 1;
    const btn = $(`[data-xi-move="${side}"][data-from="${to}"][data-to="${to + dir}"]`);
    if (keepFocus && btn && !btn.disabled) btn.focus();
  }
  function xiSourceText(code) {
    const t = team(code); const own = t.latest_xi?.[state.format]; const any = own || t.latest_xi?.t20;
    if (!any) return "Balanced pick (no recent match in the data)";
    const fmtName = own ? state.format.toUpperCase() : "T20";
    return `Latest ${fmtName} XI · v ${any.opponent} · ${fmtDate(any.date)}`;
  }
  function renderXI() {
    prefetchPar(); if (typeof renderFlow === "function") renderFlow();
    for (const [side, code] of [["bat", state.batting], ["chase", state.chasing]]) {
      usualOrder(side);
      const chosen = new Set(state.xi[side]);
      const squad = team(code).squad;
      // players chosen but no longer in the squad list (shouldn't happen, but never hide a ticked box)
      const extra = state.xi[side].filter((n) => !squad.some((p) => p.name === n)).map((n) => ({ name: n, role_label: "", recent: true, in_data: true, games: 0 }));
      const items = [...extra, ...squad];
      const firstOld = items.findIndex((p) => !p.recent);
      const listEl = $(`#xi-${side}`); const keepScroll = listEl.scrollTop;  // don't jump to the top on every tick
      requestAnimationFrame(() => { listEl.scrollTop = keepScroll; });
      listEl.innerHTML = items.map((p, i) => `
        ${i === firstOld ? `<li class="xi-divider">Not picked in the ${esc(team(code).squad_window || "recent matches")}</li>` : ""}
        <li class="${p.recent ? "" : "old"}"><label>
          <input type="checkbox" data-side="${side}" value="${esc(p.name)}" ${chosen.has(p.name) ? "checked" : ""}>
          <span class="dot ${p.in_data ? "found" : ""}" title="${p.in_data ? "Has match record" : "No match record found"}"></span>
          <span>${esc(p.name)}</span>
          <span class="role">${esc(p.role_label)}${p.recent && p.games ? ` · ${p.games} gm` : ""}</span>
        </label></li>`).join("");
      renderPicked(side, items);
      const count = $(`#xi-${side}-count`);
      count.textContent = `${state.xi[side].length}/11`;
      count.classList.toggle("warn", state.xi[side].length !== 11);
      $(`#xi-${side}-source`).textContent = xiSourceText(code);
    }
    const isLatest = (s) => sameXI(state.xi[s], suggestedXI(s === "bat" ? state.batting : state.chasing));
    $("#xi-summary").textContent = isLatest("bat") && isLatest("chase") ? "Latest real XIs" : "Your own selection";
    applyXIFilter("bat"); applyXIFilter("chase"); renderImpact(); renderCrease(); refreshDrops(); rememberXI();
    for (const s of ["bat", "chase"]) {  // a suggestion for other teams / format is stale: hide it
      const box = $(`#xi-${s}-suggest`); if (box && !box.hidden && box.dataset.key !== suggestKey(s)) box.hidden = true;
    }
    scheduleInsights();  // matchups & form follow the ticked XIs
  }

  // ------------------------------------------------------------------ share card (feature 12)
  // Drawn straight onto a canvas (no libraries, works offline): 1080 x 1350, the 4:5 size social apps like.
  const CARD_W = 1080, CARD_H = 1350;
  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function fitFont(ctx, text, weight, size, family, maxW) {
    let px = size;
    do { ctx.font = `${weight} ${px}px ${family}`; px -= 2; } while (ctx.measureText(text).width > maxW && px > 14);
  }
  function wrapLines(ctx, text, maxW) {
    const words = String(text).split(/\s+/); const lines = []; let line = "";
    for (const w of words) {
      const test = line ? `${line} ${w}` : w;
      if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; } else line = test;
    }
    if (line) lines.push(line);
    return lines;
  }
  function cardData(kind) {
    const v = venue(); const modeLabel = state.mode === "ipl" ? "IPL" : "International";
    const today = new Date().toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    if (kind === "chase") {
      const r = state.lastChase; if (!r) return null; const e = r.equation;
      const live = r.status === "live";
      const label = (x) => (live ? Math.min(99, Math.max(1, Math.round(x))) : Math.round(x));
      const pts = (x) => (x == null ? null : x);  // positive = chasing side
      return {
        kind, eyebrow: live ? `LIVE CHASE · ${r.verdict}` : "RESULT",
        headline: live ? r.winner : r.verdict,
        headCode: r.winner === r.chasing_team ? r.chasing_code : r.winner === r.batting_team ? r.batting_code : null,
        sub: live ? `${label(Math.max(r.chase_pct, 100 - r.chase_pct))}% chance to win` : "",
        left: { name: r.batting_team, code: r.batting_code, pct: label(100 - r.chase_pct), caption: "defending" },
        right: { name: r.chasing_team, code: r.chasing_code, pct: label(r.chase_pct), caption: "chasing" },
        lines: live ? [`${r.chasing_team} ${e.runs}/${e.wickets} (${e.overs_text} ov) chasing ${e.target}`,
          `Need ${e.runs_needed} off ${e.balls_left} balls · RRR ${e.required_rate ?? "–"} · CRR ${e.current_rate ?? "–"} · ${e.wickets_in_hand} wkts left`]
          : [String($("#c-equation").textContent || "")],
        worm: { tl: chase.timeline, code: r.chasing_code, name: r.chasing_team },
        factors: live ? [
          ["The equation", `Runs, balls and wickets alone give ${r.chasing_team}`, `${Math.round(r.simple_pct)}%`],
          ["Team ratings", `Elo ${r.bat_elo ?? "–"} v ${r.chase_elo ?? "–"}`, pts(r.factors?.team_ratings)],
          ["Playing XI records", "Career + recent form of both XIs", pts(r.factors?.playing_xi)],
        ] : [],
        positiveCode: r.chasing_code, negativeCode: r.batting_code,
        model: `Live chase model (${r.model_label || "ensemble"})${r.test_accuracy ? ` · right ${(r.test_accuracy * 100).toFixed(1)}% of the time on unseen 2025–26 chases` : ""}`,
        meta: `${modeLabel} · ${String(r.format || state.format).toUpperCase()} · ${v.name} · ${today}`,
        file: `chase-${r.chasing_code || "team"}-v-${r.batting_code || "team"}`,
      };
    }
    const r = state.lastFirst; if (!r) return null;
    const d = r.details || {}; const f = d.factors || {}; const inp = r.input;
    const balls = Math.round(Math.floor(inp.overs) * 6 + Math.round((inp.overs % 1) * 10));
    const winPct = Math.max(r.batting_pct, r.chasing_pct);
    const lines = [balls ? `${r.batting_team} ${inp.runs}/${inp.wickets} after ${oversText(balls)} overs · par ${inp.par}` : `Before the match · par ${inp.par}`];
    if (r.projection) lines.push(`Projected total ${r.projection.mid} (likely ${r.projection.low}–${r.projection.high})`);
    const diff = inp.runs - (d.par ?? inp.par);
    return {
      kind, eyebrow: `${r.verdict}`.toUpperCase(), headline: r.winner,
      headCode: r.winner === r.batting_team ? r.batting_code : r.chasing_code,
      sub: `${winPct.toFixed(0)}% chance to win`,
      left: { name: r.batting_team, code: r.batting_code, pct: Math.round(r.batting_pct), caption: "bats first" },
      right: { name: r.chasing_team, code: r.chasing_code, pct: Math.round(r.chasing_pct), caption: "chasing" },
      lines,
      worm: { tl: first.timeline, code: r.batting_code, name: r.batting_team },
      factors: d.engine === "ml" ? [
        ["Score vs par", `${inp.runs} v par ${d.par} at this stage (${diff >= 0 ? "+" : ""}${diff})`, f.score_vs_par],
        ["Team ratings", `Elo ${d.bat_elo ?? "–"} v ${d.chase_elo ?? "–"}`, f.team_ratings],
        ["Playing XI records", "Real career stats of both XIs", f.playing_xi],
      ] : [["Original formula", "The ML model doesn't cover this case", null]],
      positiveCode: r.batting_code, negativeCode: r.chasing_code,
      model: d.engine === "ml" ? `${d.model_label} model${d.test_accuracy_innings_break ? ` · right ${(d.test_accuracy_innings_break * 100).toFixed(1)}% at the innings break on unseen 2025–26 matches` : ""}` : "Original formula",
      meta: `${modeLabel} · ${inp.format.toUpperCase()} · ${v.name} · ${today}`,
      file: `prediction-${r.batting_code || "team"}-v-${r.chasing_code || "team"}`,
    };
  }
  async function drawCard(kind) {
    const c = cardData(kind); if (!c) return null;
    try { await document.fonts.ready; } catch { /* fonts API unavailable */ }
    const cv = document.createElement("canvas"); cv.width = CARD_W; cv.height = CARD_H + 400;  // cropped to the content at the end
    const ctx = cv.getContext("2d");
    const css = getComputedStyle(document.documentElement);
    const accent = css.getPropertyValue("--accent").trim() || "#5b1f73";
    const SANS = '"Inter", "Segoe UI", sans-serif', CONDENSED = '"Big Shoulders Display", "Segoe UI", sans-serif';
    const ink = "#1d1d1a", muted = "#74746a", line = "#e2e0d8";

    // background + header: the home page's hero photo for this mode under an olive wash, then the wordmark
    ctx.fillStyle = "#efeee9"; ctx.fillRect(0, 0, cv.width, cv.height);
    const HEAD = 250;
    const photo = (state.mode === "ipl" && PHOTOS["ipl:hero"]) || PHOTOS.hero;
    const img = photo ? await new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(null); im.src = photo; }) : null;
    if (img) {
      const scale = Math.max(CARD_W / img.naturalWidth, HEAD / img.naturalHeight);
      const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, CARD_W, HEAD); ctx.clip();  // keep the photo inside the header
      ctx.drawImage(img, (CARD_W - w) / 2, (HEAD - h) * 0.35, w, h);
      ctx.restore();
    }
    const wash = ctx.createLinearGradient(0, 0, CARD_W, 0);
    wash.addColorStop(0, "rgba(46,46,34,0.94)"); wash.addColorStop(0.55, "rgba(46,46,34,0.72)"); wash.addColorStop(1, "rgba(46,46,34,0.35)");
    ctx.fillStyle = img ? wash : "#2e2e22"; ctx.fillRect(0, 0, CARD_W, HEAD);
    // brand mark: stumps in an olive tile
    rr(ctx, 60, 58, 76, 76, 20); ctx.fillStyle = "#c9cab3"; ctx.fill();
    ctx.fillStyle = "#2e2e22";
    for (const x of [82, 98, 114]) { rr(ctx, x - 3, 80, 6, 38, 3); ctx.fill(); }
    rr(ctx, 76, 72, 44, 6, 3); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.textBaseline = "alphabetic";
    ctx.font = `800 54px ${CONDENSED}`; ctx.fillText("Crease", 160, 112);
    const cw = ctx.measureText("Crease").width;
    rr(ctx, 160 + cw + 10, 74, 62, 42, 10); ctx.fillStyle = "#c9cab3"; ctx.fill();
    ctx.fillStyle = "#2e2e22"; ctx.font = `800 30px ${CONDENSED}`; ctx.fillText("IQ", 160 + cw + 22, 106);
    ctx.fillStyle = "rgba(255,255,255,.82)"; fitFont(ctx, c.meta, 500, 26, SANS, CARD_W - 160 - 60); ctx.fillText(c.meta, 160, 158);
    ctx.fillStyle = "rgba(255,255,255,.6)"; ctx.font = `700 20px ${SANS}`;
    ctx.fillText(c.kind === "chase" ? "LIVE CHASE PREDICTION" : "MATCH PREDICTION", 160, 200);
    ctx.save(); ctx.translate(0, 30);  // everything below sits a little lower than before

    // team badges
    const badge = (cx, cy, code, name, caption) => {
      const st = teamStyle(code || name);
      const g = ctx.createLinearGradient(cx - 70, cy - 70, cx + 70, cy + 70); g.addColorStop(0, st.c1); g.addColorStop(1, st.c2);
      ctx.save(); ctx.shadowColor = "rgba(20,24,40,.25)"; ctx.shadowBlur = 24; ctx.shadowOffsetY = 8;
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, 70, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      const lg = LOGO_IMG[st.code];
      if (lg && lg.complete && lg.naturalWidth) {
        ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, 70, 0, Math.PI * 2); ctx.clip(); ctx.drawImage(lg, cx - 70, cy - 70, 140, 140); ctx.restore();
      } else { ctx.fillStyle = "#fff"; ctx.textAlign = "center"; fitFont(ctx, st.code, 700, 46, CONDENSED, 120); ctx.fillText(st.code, cx, cy + 16); }
      ctx.textAlign = "center";
      ctx.fillStyle = ink; fitFont(ctx, name, 700, 30, SANS, 380); ctx.fillText(name, cx, cy + 118);
      ctx.fillStyle = muted; ctx.font = `500 22px ${SANS}`; ctx.fillText(caption, cx, cy + 150);
      ctx.textAlign = "left";
    };
    badge(250, 350, c.left.code, c.left.name, c.left.caption);
    badge(830, 350, c.right.code, c.right.name, c.right.caption);
    ctx.fillStyle = muted; ctx.textAlign = "center"; ctx.font = `700 40px ${CONDENSED}`; ctx.fillText("v", 540, 366); ctx.textAlign = "left";

    // verdict
    ctx.textAlign = "center";
    ctx.fillStyle = accent; fitFont(ctx, c.eyebrow, 700, 26, SANS, 900); ctx.fillText(c.eyebrow, 540, 572);
    ctx.fillStyle = ink; fitFont(ctx, c.headline, 700, 76, CONDENSED, 960); ctx.fillText(c.headline, 540, 650);
    if (c.sub) { ctx.fillStyle = muted; ctx.font = `600 30px ${SANS}`; ctx.fillText(c.sub, 540, 698); }
    ctx.textAlign = "left";

    // probability bar
    const px = 90, pw = 900, py = 730, ph = 64;
    const ls = teamStyle(c.left.code || c.left.name), rs = teamStyle(c.right.code || c.right.name);
    const lw = Math.max(0, Math.min(pw, pw * c.left.pct / 100));
    ctx.save(); rr(ctx, px, py, pw, ph, 32); ctx.clip();
    let g = ctx.createLinearGradient(px, 0, px + lw, 0); g.addColorStop(0, ls.c1); g.addColorStop(1, ls.c2);
    ctx.fillStyle = g; ctx.fillRect(px, py, lw, ph);
    g = ctx.createLinearGradient(px + lw, 0, px + pw, 0); g.addColorStop(0, rs.c2); g.addColorStop(1, rs.c1);
    ctx.fillStyle = g; ctx.fillRect(px + lw, py, pw - lw, ph);
    ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillRect(px + lw - 2, py, 4, ph);
    ctx.restore();
    ctx.fillStyle = "#fff"; ctx.font = `700 34px ${CONDENSED}`;
    if (c.left.pct >= 12) ctx.fillText(`${c.left.pct}%`, px + 24, py + 45);
    ctx.textAlign = "right"; if (c.right.pct >= 12) ctx.fillText(`${c.right.pct}%`, px + pw - 24, py + 45); ctx.textAlign = "left";

    // situation box
    let y = 830;
    ctx.fillStyle = "#fff"; rr(ctx, 60, y, 960, 40 + c.lines.length * 44, 22); ctx.fill();
    ctx.strokeStyle = line; ctx.lineWidth = 2; ctx.stroke();
    c.lines.forEach((t, i) => {
      ctx.fillStyle = i === 0 ? ink : muted; fitFont(ctx, t, i === 0 ? 700 : 600, 30, SANS, 900);
      ctx.fillText(t, 90, y + 56 + i * 44);
    });
    y += 40 + c.lines.length * 44 + 30;

    // win-chance chart (if the innings was followed ball by ball)
    const tl = c.worm.tl || [];
    if (tl.length >= 2) {
      const cx0 = 110, cw = 880, ch = 150, cy0 = y + 40;
      // x axis: the overs followed so far (at least 5), so a short spell isn't squashed into a corner
      const last = tl[tl.length - 1].balls; const mb = Math.min(maxBalls(), Math.max(30, Math.ceil(last / 6) * 6));
      const ovStep = mb / 6 > 30 ? 10 : mb / 6 > 10 ? 5 : 1;
      ctx.fillStyle = muted; ctx.font = `500 18px ${SANS}`; ctx.textAlign = "center";
      for (let o = 0; o <= mb / 6; o += ovStep) ctx.fillText(String(o), cx0 + (o * 6 / mb) * cw, cy0 + ch + 28);
      ctx.textAlign = "left";
      ctx.fillStyle = muted; ctx.font = `700 22px ${SANS}`;
      ctx.fillText(`WIN CHANCE THROUGH THE ${c.kind === "chase" ? "CHASE" : "INNINGS"} · ${c.worm.name.toUpperCase()}`, 60, y + 20);
      const X = (b) => cx0 + (b / mb) * cw, Y = (pct) => cy0 + (1 - pct / 100) * ch;
      ctx.strokeStyle = line; ctx.lineWidth = 2; ctx.setLineDash([6, 8]);
      ctx.beginPath(); ctx.moveTo(cx0, Y(50)); ctx.lineTo(cx0 + cw, Y(50)); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = muted; ctx.font = `500 18px ${SANS}`; ctx.textAlign = "right";
      [0, 50, 100].forEach((v) => ctx.fillText(`${v}%`, cx0 - 12, Y(v) + 6)); ctx.textAlign = "left";
      const st = teamStyle(c.worm.code || c.worm.name);
      const area = ctx.createLinearGradient(0, cy0, 0, cy0 + ch); area.addColorStop(0, `${st.c1}55`); area.addColorStop(1, `${st.c1}05`);
      ctx.beginPath(); ctx.moveTo(X(tl[0].balls), Y(0)); tl.forEach((p) => ctx.lineTo(X(p.balls), Y(p.pct))); ctx.lineTo(X(tl[tl.length - 1].balls), Y(0)); ctx.closePath();
      ctx.fillStyle = area; ctx.fill();
      ctx.beginPath(); tl.forEach((p, i) => (i ? ctx.lineTo(X(p.balls), Y(p.pct)) : ctx.moveTo(X(p.balls), Y(p.pct))));
      ctx.strokeStyle = st.c1; ctx.lineWidth = 5; ctx.lineJoin = "round"; ctx.stroke();
      tl.forEach((p, i) => {
        if (i > 0 && p.wickets > tl[i - 1].wickets) { ctx.fillStyle = "#dc2626"; ctx.beginPath(); ctx.arc(X(p.balls), Y(p.pct), 8, 0, Math.PI * 2); ctx.fill(); }
      });
      y = cy0 + ch + 56;
    }

    // factors
    if (c.factors.length) {
      ctx.fillStyle = muted; ctx.font = `700 22px ${SANS}`; ctx.fillText("WHAT MOVED THE NEEDLE", 60, y + 10); y += 30;
      const rowH = tl.length >= 2 ? 64 : 78;
      c.factors.forEach(([title, subText, pts]) => {
        ctx.fillStyle = "#fff"; rr(ctx, 60, y, 960, rowH - 10, 16); ctx.fill(); ctx.strokeStyle = line; ctx.lineWidth = 2; ctx.stroke();
        ctx.fillStyle = ink; ctx.font = `700 26px ${SANS}`; ctx.fillText(title, 86, y + (rowH - 10) / 2 + 9);
        const tw = ctx.measureText(title).width;
        ctx.fillStyle = muted; fitFont(ctx, subText, 500, 22, SANS, 960 - tw - 260); ctx.fillText(subText, 86 + tw + 18, y + (rowH - 10) / 2 + 8);
        let pill = "neutral", pc = ["#e9ebf0", "#e9ebf0"], tc = muted;
        if (typeof pts === "string") { pill = pts; tc = ink; }
        else if (pts != null && Math.abs(pts) >= 0.5) {
          const s = teamStyle(pts > 0 ? c.positiveCode : c.negativeCode);
          pill = `+${Math.abs(pts).toFixed(1)} ${s.code}`; pc = [s.c1, s.c2]; tc = "#fff";
        }
        ctx.font = `700 22px ${SANS}`; const pwid = ctx.measureText(pill).width + 32;
        const pg = ctx.createLinearGradient(0, 0, pwid, 0); pg.addColorStop(0, pc[0]); pg.addColorStop(1, pc[1]);
        ctx.fillStyle = pg; rr(ctx, 1020 - 22 - pwid, y + (rowH - 10) / 2 - 20, pwid, 40, 20); ctx.fill();
        ctx.fillStyle = tc; ctx.fillText(pill, 1020 - 22 - pwid + 16, y + (rowH - 10) / 2 + 8);
        y += rowH;
      });
    }

    ctx.restore(); y += 30;
    // footer: at the bottom of a 1080x1350 card, or lower if the content needs the room
    const H = Math.max(CARD_H, y + 20 + 120);
    ctx.fillStyle = "#efeee9"; ctx.fillRect(0, y + 10, CARD_W, cv.height - y - 10);
    ctx.fillStyle = "#e4e2d8"; ctx.fillRect(0, H - 120, CARD_W, 120);
    ctx.fillStyle = ink; ctx.font = `600 22px ${SANS}`;
    const ml = wrapLines(ctx, c.model, 960).slice(0, 2);
    ml.forEach((t, i) => ctx.fillText(t, 60, H - 76 + i * 30 - (ml.length - 1) * 12));
    ctx.fillStyle = muted; ctx.font = `500 20px ${SANS}`;
    ctx.fillText("A prediction from past data, not a guarantee.", 60, H - 24);
    const out = document.createElement("canvas"); out.width = CARD_W; out.height = H;
    out.getContext("2d").drawImage(cv, 0, 0);
    return { canvas: out, data: c };
  }
  const toBlob = (cv) => new Promise((res) => cv.toBlob(res, "image/png"));
  function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }
  async function shareAction(kind, action, btn) {
    btn.disabled = true;
    try {
      const card = await drawCard(kind);
      if (!card) { toast("Make a prediction first."); return; }
      const name = `${card.data.file}-${new Date().toISOString().slice(0, 10)}.png`;
      const blob = await toBlob(card.canvas);
      if (action === "png") { downloadBlob(blob, name); toast("Image saved to your downloads"); return; }
      if (action === "share") {
        const file = new File([blob], name, { type: "image/png" });
        try { await navigator.share({ files: [file], title: "Crease IQ", text: `${card.data.headline}: ${card.data.sub || card.data.eyebrow}` }); }
        catch (err) { if (err && err.name !== "AbortError") { downloadBlob(blob, name); toast("Sharing isn't available here, so the image was downloaded instead."); } }
        return;
      }
      // PDF: print just the card; the browser's print dialog offers "Save as PDF"
      const url = card.canvas.toDataURL("image/png");
      const frame = document.createElement("iframe");
      frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
      document.body.appendChild(frame);
      const doc = frame.contentDocument;
      doc.open();
      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(card.data.file)}</title><style>@page{size:A4 portrait;margin:12mm}html,body{margin:0;background:#fff}img{display:block;width:100%;max-height:270mm;object-fit:contain;margin:0 auto}</style></head><body><img alt="Prediction card" src="${url}"></body></html>`);
      doc.close();
      const img = doc.querySelector("img");
      const go = () => { frame.contentWindow.focus(); frame.contentWindow.print(); setTimeout(() => frame.remove(), 60000); };
      if (img.complete) go(); else img.onload = go;
      toast("Choose \u201cSave as PDF\u201d in the print dialog");
    } catch (err) {
      toast(`Couldn't make the image (${err.message || err}).`);
    } finally { btn.disabled = false; }
  }
  function bindShare() {
    const canShareFiles = (() => {
      try { return !!navigator.canShare && navigator.canShare({ files: [new File([new Blob(["x"])], "t.png", { type: "image/png" })] }); } catch { return false; }
    })();
    $$(".share-row").forEach((row) => {
      const kind = row.dataset.shareKind;
      row.querySelectorAll("[data-share]").forEach((b) => {
        if (b.dataset.share === "share") b.hidden = !canShareFiles;
        b.addEventListener("click", () => shareAction(kind, b.dataset.share, b));
      });
    });
  }


  // ------------------------------------------------------------------ home page
  // Go to the Predict page, then run `after` once it is showing (route() scrolls to the top first).
  function goPredict(after) {
    const already = location.hash === "#predict";
    if (!already) location.hash = "#predict";
    setTimeout(() => after && after(), already ? 0 : 90);
  }
  function homeGo(what) {
    if (what === "accuracy") { location.hash = "#accuracy"; return; }
    if (what === "t20" || what === "odi") {
      goPredict(() => { $(`.segmented [data-format="${what}"]`)?.click(); $("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" }); });
      return;
    }
    if (what === "chase") { goPredict(() => { setStage("chase"); $("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" }); }); return; }
    if (what === "xi") {
      goPredict(() => {
        if (state.stage !== "first") setStage("first");
        const btn = $('[data-suggest-xi="bat"]'); btn?.click();
        setTimeout(() => $("#xi-bat-suggest")?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
      });
      return;
    }
    if (what === "matchups") { goPredict(() => $("#insights").scrollIntoView({ behavior: "smooth", block: "start" })); }
  }
  async function loadTopTeams(mode) {
    const row = $("#team-row"); if (!row) return;
    row.innerHTML = `<div class="loading">Loading teams…</div>`;
    try {
      const r = await api(`/api/top-teams?mode=${mode}`);
      if (mode !== state.mode) return;
      row.innerHTML = r.teams.map((t, i) => {
        const st = teamStyle(t.code); const last = [...t.last5].reverse();  // oldest → newest
        const wins = t.last5.filter((x) => x === "W").length;
        const tag = i === 0 ? `<span class="tc-tag">No. 1</span>` : wins >= 4 ? `<span class="tc-tag hot">In form</span>` : "";
        return `<button type="button" class="team-card" data-team="${esc(t.code)}" style="--i:${i}">
          <span class="tc-top">${tag}<span class="tc-rank">#${i + 1}</span>
            <span class="tc-badge${logoOf(t.code) ? " has-logo" : ""}" style="${logoOf(t.code) ? `--logo:url('${logoOf(t.code)}')` : `background:linear-gradient(135deg, ${st.c1}, ${st.c2})`}">${esc(st.code)}</span></span>
          <span class="tc-name">${esc(t.name)}</span>
          <span class="tc-sub">Team rating (Elo)</span>
          <span class="tc-bottom"><b>${t.elo}</b>
            <span class="tc-form" title="Last 5 T20 results, oldest to newest">${last.map((x) => `<i class="${x === "W" ? "w" : x === "L" ? "l" : "n"}">${esc(x || "–")}</i>`).join("")}</span></span>
        </button>`;
      }).join("") || `<div class="loading">No team ratings yet.</div>`;
      $("#proof-faces").innerHTML = r.teams.slice(0, 3).map((t) => {
        const st = teamStyle(t.code); const lg = logoOf(t.code);
        return `<i class="${lg ? "has-logo" : ""}" style="${lg ? `--logo:url('${lg}')` : `background:linear-gradient(135deg, ${st.c1}, ${st.c2})`}">${esc(st.code)}</i>`;
      }).join("");
    } catch (err) { row.innerHTML = `<div class="loading">Couldn't load teams (${esc(err.message)}).</div>`; }
  }
  // Photos: web/img/<name>.jpg|.jpeg|.webp|.png, dropped in by the user. Until then a soft placeholder shows.
  let PHOTOS = {};
  async function loadPhotos() {
    try { PHOTOS = await api("/api/photos"); } catch { PHOTOS = {}; }
    for (const [k, v] of Object.entries(PHOTOS)) {
      if (!k.startsWith("logo:")) continue;
      const code = k.slice(5); LOGOS[code] = v;
      const im = new Image(); im.src = v; LOGO_IMG[code] = im;  // also drawn on the share card
    }
    return PHOTOS;
  }
  function applyPhotos() {
    $$(".photo-slot[data-photo]").forEach((el) => {
      const slot = el.dataset.photo;
      const src = (state.mode === "ipl" && PHOTOS[`ipl:${slot}`]) || PHOTOS[slot];
      if (!src) { el.classList.remove("has-photo"); return; }
      if (el.dataset.src === src) return;
      el.dataset.src = src;
      const img = new Image();
      img.onload = () => {
        if (el.dataset.src !== src) return;  // the switch moved on meanwhile
        el.style.setProperty("--photo", `url("${src}")`); el.classList.add("has-photo");
        el.classList.remove("swap"); void el.offsetWidth; el.classList.add("swap");  // soft fade between IPL and International photos
      };
      img.src = src;
    });
  }

  // ------------------------------------------------------------------ scroll motion
  // Sections rise in as they scroll into view, photos drift at their own speed (parallax),
  // the stadium numbers count up, and a thin line at the top shows how far down the page you are.
  const NO_MOTION = (() => { try { return matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; } })();
  function countUp(el) {
    const target = Number(el.dataset.count) || 0;
    if (NO_MOTION) { el.textContent = target.toLocaleString(); return; }
    const t0 = performance.now(), dur = 1600;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur); const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(target * eased).toLocaleString();
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  function initMotion() {
    if (NO_MOTION) document.documentElement.classList.add("no-motion");
    // stagger the items of a row so they arrive one after another
    for (const group of [".feature-grid > .feature", ".tech-row > .tech", ".band-stats > div"]) {
      $$(group).forEach((el, i) => el.style.setProperty("--rd", `${i * 90}ms`));
    }
    const reveal = (el) => {
      el.classList.add("in");
      el.querySelectorAll("[data-count]").forEach((n) => { if (!n.dataset.counted) { n.dataset.counted = "1"; countUp(n); } });
    };
    const targets = $$("[data-reveal]");
    if (NO_MOTION || !("IntersectionObserver" in window)) { targets.forEach(reveal); }
    else {
      // whatever is already on screen when the page opens shows at once (no fade from blank); the rest fades in on scroll
      targets.forEach((el) => {
        if (el.offsetParent !== null && el.getBoundingClientRect().top < innerHeight) { el.classList.add("now"); reveal(el); }
      });
      const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => { if (e.isIntersecting) { reveal(e.target); io.unobserve(e.target); } });
      }, { threshold: 0.14, rootMargin: "0px 0px -6% 0px" });
      targets.forEach((el) => { if (!el.classList.contains("in")) io.observe(el); });
    }
    // parallax + progress line, one frame at a time
    const bar = $("#scroll-progress");
    let ticking = false;
    const update = () => {
      ticking = false;
      const max = document.documentElement.scrollHeight - innerHeight;
      if (bar) bar.style.setProperty("--p", max > 0 ? (scrollY / max).toFixed(4) : 0);
      // anything already scrolled past (a fast fling, the End key, a jump link) shows too
      targets.forEach((el) => { if (!el.classList.contains("in") && el.offsetParent !== null && el.getBoundingClientRect().top < innerHeight) reveal(el); });
      if (NO_MOTION) return;
      $$("[data-parallax]").forEach((el) => {
        if (el.offsetParent === null) return;  // in a hidden view
        const f = Number(el.dataset.parallax) || 0;
        const r = el.getBoundingClientRect();
        if (r.bottom < -200 || r.top > innerHeight + 200) return;
        const shift = el.classList.contains("hero2-bg") ? Math.min(scrollY * f, 160) : -(r.top + r.height / 2 - innerHeight / 2) * f;
        el.style.translate = `0 ${shift.toFixed(1)}px`;
      });
      $$(".band.has-photo").forEach((el) => {
        if (el.offsetParent === null) return;
        const r = el.getBoundingClientRect();
        const k = Math.max(0, Math.min(1, (innerHeight - r.top) / (innerHeight + r.height)));  // 0 entering, 1 leaving
        el.style.setProperty("--shift", `${((k - 0.5) * -90).toFixed(1)}px`);
      });
    };
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    addEventListener("hashchange", () => setTimeout(update, 60));
    update();
  }




  // ------------------------------------------------------------------ match preview (first tab of Matchups & form)
  // Before a ball is bowled: the toss call (model, both teams, your pitch / dew), head-to-head, form, the ground, the key
  // battles and each side's phase specialists, in one place. Uses data the other tabs already load, plus /api/toss.
  let tossData = null; let teamsData = null; let tossSeq = 0;
  async function loadToss() {
    const seq = ++tossSeq;
    try {
      const r = await api("/api/toss", { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing,
        venue: state.venue, par: state.par || null, ...xiPayload() });
      if (seq === tossSeq) { tossData = r; renderPreview(); }
    } catch { if (seq === tossSeq) { tossData = null; renderPreview(); } }
  }
  function renderPreview() {
    const el = $("#pv-body"); if (!el || !state.config) return;
    const A = team(state.batting), B = team(state.chasing); const sa = teamStyle(state.batting), sb = teamStyle(state.chasing);
    const v = venue(); const fmt = state.format === "odi" ? "ODI" : "T20";
    const pill = (code) => { const s = teamStyle(code); return `<span class="pv-team" style="--c1:${s.c1};--c2:${s.c2}">${esc(code)}</span>`; };
    const parts = [];
    // toss
    const t = tossData;
    if (t?.available) {
      const ta = t.teams.a, tb = t.teams.b; const choice = ta.choice; const close = ta.close;
      const pre = SC?.groups && (state.mode === "ipl" ? SC.groups.IPL : null);
      parts.push(`<div class="pv-card pv-toss">
        <div class="pv-kicker">The toss</div>
        <h3>${close ? "Too close to call: either is fine" : `Win the toss? <b>${choice === "bowl" ? "Bowl first" : "Bat first"}</b>`}</h3>
        <p class="pv-lede">${close ? "Batting first and chasing come out level for these two teams here." : `Whoever wins the toss gains about <b>${ta.edge.toFixed(0)} points</b> by choosing to ${choice === "bowl" ? "chase" : "bat first"}.`}
          ${t.dew ? ` Includes your call: <b>${esc(t.dew.toLowerCase())}</b>.` : ""}</p>
        <div class="pv-toss-grid">${[[ta, sa], [tb, sb]].map(([x, s]) => `
          <div class="pv-toss-team" style="--c1:${s.c1};--c2:${s.c2}">
            <b>${esc(x.name)}</b>
            <div class="pv-opt ${x.choice === "bat" ? "best" : ""}"><span>Bat first</span><i style="--v:${x.bat / 100}"></i><em>${x.bat.toFixed(0)}%</em></div>
            <div class="pv-opt ${x.choice === "bowl" ? "best" : ""}"><span>Chase</span><i style="--v:${x.chase / 100}"></i><em>${x.chase.toFixed(0)}%</em></div>
          </div>`).join("")}</div>
        <p class="pv-note">${t.venue ? `At ${esc(t.venue.name)} the side batting first has won <b>${t.venue.bat_first_win_pct ?? "–"}%</b> of ${t.venue.matches} games${t.venue.toss?.chose_bowl_pct != null ? `; toss winners chose to bowl ${t.venue.toss.chose_bowl_pct}% of the time and won ${t.venue.toss.winner_won_pct}%` : ""}. ` : ""}
          Before-the-match calls are the model's least certain${pre?.pre_match?.pct ? ` (right ${pre.pre_match.pct}% of unseen IPL games)` : ""}, so read this as a lean, not a lock.</p>
      </div>`);
    } else parts.push(`<div class="pv-card pv-toss"><div class="pv-kicker">The toss</div><p class="muted">${tossData === null ? "Working out the toss call…" : "No toss call for this match setup."}</p></div>`);
    // head-to-head + form
    const d = teamsData;
    if (d?.h2h) {
      const h = d.h2h; const [na, nb] = h.teams; const wa = h.wins?.[na] ?? 0, wb = h.wins?.[nb] ?? 0;
      const last = h.last_n || {}; const meets = (h.meetings || []).slice(0, 3);
      parts.push(`<div class="pv-card"><div class="pv-kicker">Head-to-head · ${fmt}</div>
        ${h.played ? `<div class="pv-h2h"><span>${pill(state.batting)} <b>${wa}</b></span><div class="pv-split"><i style="width:${(wa / Math.max(1, wa + wb)) * 100}%;background:linear-gradient(90deg,${sa.c1},${sa.c2})"></i><i style="width:${(wb / Math.max(1, wa + wb)) * 100}%;background:linear-gradient(90deg,${sb.c1},${sb.c2})"></i></div><span><b>${wb}</b> ${pill(state.chasing)}</span></div>
          <p class="pv-small">${h.played} meetings since ${esc((h.first_met || "").slice(0, 4))} · last ${last.n || 0}: ${esc(state.batting)} ${last[na] ?? 0}, ${esc(state.chasing)} ${last[nb] ?? 0} · batting first won ${h.bat_first_won} of ${h.decided}</p>
          <ul class="pv-list">${meets.map((m) => `<li>${esc(fd(m.date))} · <b>${esc(m.winner ? (m.winner === na ? state.batting : m.winner === nb ? state.chasing : m.winner) : "No result")}</b> ${esc(m.margin || "")} <span class="muted">${esc(m.venue || "")}</span></li>`).join("")}</ul>`
          : `<p class="muted">They haven't met in ${fmt} in the data.</p>`}
      </div>`);
      const form = (side, code, s) => { const f = d.form?.[side]; if (!f) return "";
        return `<div class="pv-form"><div>${pill(code)} <b>${f.wins}/${f.decided}</b> <span class="muted small">last ${f.decided}</span></div>
          <div class="pv-chips">${(f.games || []).slice(0, 10).map((g) => `<i class="r-${g.result === "W" ? "w" : g.result === "L" ? "l" : "n"}" title="${esc(fd(g.date))} v ${esc(g.opponent)}: ${esc(g.result)} ${esc(g.margin || "")}">${esc(g.result)}</i>`).join("")}</div></div>`; };
      parts.push(`<div class="pv-card"><div class="pv-kicker">Recent form</div>${form("bat", state.batting, sa)}${form("chase", state.chasing, sb)}
        <p class="pv-small">Newest on the left. W won · L lost.</p></div>`);
    }
    // ground
    const vd = venueData;
    if (vd?.available) {
      parts.push(`<div class="pv-card"><div class="pv-kicker">The ground</div><h4>${esc(vd.name || v.name || "")}</h4>
        <div class="pv-stats">
          <div><b>${vd.par ?? "–"}</b><span>par score</span></div>
          <div><b>${vd.bat_first_win_pct ?? "–"}%</b><span>bat-first wins</span></div>
          <div><b>${vd.highest_chased ?? "–"}</b><span>highest chased</span></div>
          <div><b>${vd.matches ?? "–"}</b><span>matches</span></div>
        </div></div>`);
    }
    // key battles + phase specialists
    const bt = ins.data?.battles; const top = [...(bt?.bat_v_chase || []), ...(bt?.chase_v_bat || [])]
      .filter((x) => x.balls >= 12 && x.edge !== "even").sort((a, b2) => b2.balls - a.balls).slice(0, 4);
    if (top.length) {
      parts.push(`<div class="pv-card"><div class="pv-kicker">Battles to watch</div><ul class="pv-list">${top.map((x) => `<li><b>${esc(x.batter)}</b> v <b>${esc(x.bowler)}</b>:
        ${x.runs} off ${x.balls}${x.outs ? `, out ${x.outs}` : ""} <i class="pv-edge ${x.edge}">${x.edge === "batter" ? "batter on top" : "bowler on top"}</i></li>`).join("")}</ul></div>`);
    }
    const ph = phaseData?.teams;
    if (ph) {
      const sp = (side, code) => { const c = ph[side]?.callouts || {}; const row = (k, label, val) => (c[k] ? `<li><span>${label}</span><b>${esc(c[k].name)}</b> <em>${val(c[k])}</em></li>` : "");
        return `<div class="pv-spec">${pill(code)}<ul>${row("pp_hitter", "Powerplay hitter", (x) => `SR ${x.sr}`)}${row("death_hitter", "Death hitter", (x) => `SR ${x.sr}`)}${row("pp_bowler", "New-ball bowler", (x) => `econ ${x.econ}`)}${row("death_bowler", "Death bowler", (x) => `econ ${x.econ}`)}</ul></div>`; };
      parts.push(`<div class="pv-card"><div class="pv-kicker">Phase specialists</div><div class="pv-specs">${sp("bat", state.batting)}${sp("chase", state.chasing)}</div></div>`);
    }
    el.innerHTML = `<div class="pv-head"><span>${pill(state.batting)} v ${pill(state.chasing)}</span><small class="muted">${esc(v.name || "")} · ${fmt} · from the XIs ticked above</small></div>
      <div class="pv-grid">${parts.join("")}</div>`;
  }


  // ------------------------------------------------------------------ liquid switches
  // Every pill switch (IPL / International, T20 / ODI, First innings / Live chase, the small tab bars) gets one
  // "droplet" behind its active button. Changing the choice stretches the droplet toward the new option (front edge
  // first), squashes it a little, overshoots and settles. Switches that are redrawn from scratch keep their droplet's
  // last position (remembered by a key), so they animate too. Still and instant with "reduce motion".
  const LQ_SEL = ".mode-switch, .segmented, .seg-tabs, .stage-toggle";
  const lqLast = new Map(); let lqFrame = 0;
  const lqKey = (el) => `${el.parentElement?.id || el.parentElement?.className || ""}|${el.id}|${el.className.replace(/\blq-on\b/, "").trim()}|${el.dataset.rtabs || el.dataset.parEven || ""}`;
  function lqSync() {
    lqFrame = 0;
    for (const el of $$(LQ_SEL)) {
      if (el.offsetParent === null) continue;  // hidden right now
      const active = [...el.children].find((c) => c.classList.contains("active") && c.tagName === "BUTTON");
      let pill = el.querySelector(":scope > .lq-pill");
      if (!active) { if (pill) pill.style.opacity = "0"; continue; }
      if (!pill) { pill = document.createElement("span"); pill.className = "lq-pill"; pill.setAttribute("aria-hidden", "true"); el.prepend(pill); }
      if (!el.classList.contains("lq-on")) el.classList.add("lq-on");
      const r = { x: active.offsetLeft, y: active.offsetTop, w: active.offsetWidth, h: active.offsetHeight };
      const key = lqKey(el); const prev = pill._r || lqLast.get(key);
      pill._r = r; lqLast.set(key, r);
      const place = (q) => Object.assign(pill.style, { left: `${q.x}px`, top: `${q.y}px`, width: `${q.w}px`, height: `${q.h}px`, opacity: "1" });
      const same = prev && prev.x === r.x && prev.y === r.y && prev.w === r.w && prev.h === r.h;
      if (!prev || same || NO_MOTION || !pill.animate) { if (!pill._anim || same === false) place(r); continue; }
      // the droplet: stretch over both, squash, overshoot, settle
      const right = r.x > prev.x; const left0 = Math.min(prev.x, r.x); const span = Math.max(prev.x + prev.w, r.x + r.w) - left0;
      const over = Math.max(3, Math.min(10, Math.abs(r.x - prev.x) * 0.08)) * (right ? 1 : -1);
      pill._anim?.cancel();
      place(r);
      pill._anim = pill.animate([
        { left: `${prev.x}px`, top: `${prev.y}px`, width: `${prev.w}px`, height: `${prev.h}px`, transform: "scale(1, 1)" },
        { left: `${right ? prev.x : left0}px`, top: `${(prev.y + r.y) / 2}px`, width: `${span}px`, height: `${(prev.h + r.h) / 2}px`, transform: "scale(1, 0.84)", offset: 0.42 },
        { left: `${r.x + over}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px`, transform: "scale(1.04, 0.94)", offset: 0.72 },
        { left: `${r.x - over * 0.3}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px`, transform: "scale(0.99, 1.03)", offset: 0.88 },
        { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px`, transform: "scale(1, 1)" },
      ], { duration: 560, easing: "cubic-bezier(.3,.7,.2,1)" });
      pill._anim.onfinish = () => { pill._anim = null; };
    }
  }
  const lqSchedule = () => { if (!lqFrame) lqFrame = requestAnimationFrame(lqSync); };
  function initLiquid() {
    new MutationObserver(lqSchedule).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "hidden"] });
    addEventListener("resize", () => { for (const p of $$(".lq-pill")) p._r = null; lqLast.clear(); lqSchedule(); });
    lqSchedule();
  }


  // ------------------------------------------------------------------ glass result card (round 1 of the glass design)
  // The verdict, the favourite's name and the situation sit on a frosted glass card floating over big shapes in the
  // favourite's team colours (IPL and international alike). The shapes drift slowly, the card floats and a light sheen
  // crosses it; when the favourite changes, the colours blend to the new team.
  function brightOf(cs) {  // the brighter of a team's two colours, lifted if both are dark (for glows on dark glass)
    const lum = (h) => { const n = parseInt(h.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255; };
    const pick = lum(cs.c1) >= lum(cs.c2) ? cs.c1 : cs.c2;
    if (lum(pick) >= 0.42) return pick;
    const n = parseInt(pick.slice(1), 16); const mix = (v) => Math.round(v + (255 - v) * 0.45);
    return `rgb(${mix(n >> 16)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
  }
  function initHeroCards() {
    for (const [kind, root, nodes] of [["first", "#result", ["#r-verdict", "#result .r-winner", "#r-situation"]],
                                      ["chase", "#chase-result", ["#c-verdict", "#chase-result .r-winner", "#c-equation"]]]) {
      const r = $(root); if (!r || r.querySelector(".rhero")) continue;
      const hero = document.createElement("div"); hero.className = "rhero"; hero.id = `${kind}-hero`;
      hero.innerHTML = `<span class="rh-orb a" aria-hidden="true"></span><span class="rh-orb b" aria-hidden="true"></span><span class="rh-orb c" aria-hidden="true"></span>
        <div class="rh-glass"><div class="rh-pct" aria-hidden="true"></div></div>`;
      r.prepend(hero);
      const glass = hero.querySelector(".rh-glass");
      for (const sel of nodes) { const el = $(sel); if (el) glass.insertBefore(el, glass.querySelector(".rh-pct")); }
      if ("IntersectionObserver" in window) new IntersectionObserver(([e]) => hero.classList.toggle("paused", !e.isIntersecting)).observe(hero);
    }
  }
  function setHero(kind, code, pct) {
    const hero = $(`#${kind}-hero`); if (!hero) return;
    const cs = teamStyle(code || "");
    hero.style.setProperty("--t1", cs.c1); hero.style.setProperty("--t2", cs.c2); hero.style.setProperty("--tb", brightOf(cs));
    hero.querySelector(".rh-pct").textContent = pct == null ? "" : `${Math.round(pct)}%`;
  }

  // ------------------------------------------------------------------ result layout: summary strip + tabs + Simple / Detailed
  // The result panels used to be one long scroll. Now: a strip with the four numbers that matter during a match, then
  // tabs (Par & phases · Players · Projection / Next over · Why). The existing sections are moved into the tabs, so they
  // keep working exactly as before. Simple view = strip + win bar only.
  const RTABS = {
    first: { root: "#result", tabs: [["par", "Par & phases"], ["players", "Players"], ["proj", "Projection"], ["why", "Why"]],
      panes: { par: ["#first-phases", "#first-pargrid"], players: ["#first-res"], proj: ["#r-proj", "#r-worm-wrap"],
        why: ["@needle:#r-factors", "#r-factors", ".whatif", "#first-why", "details.why"] } },
    chase: { root: "#chase-result", tabs: [["par", "Par & phases"], ["players", "Players"], ["next", "Next over"], ["why", "Why"]],
      panes: { par: ["#chase-phases", "#chase-pargrid"], players: ["#chase-res"], next: ["#c-need", "@needle:#c-worm", "#c-worm"],
        why: ["@needle:#c-factors", "#c-factors", "#chase-why"] } },
  };
  const STRIP = { first: {}, chase: {} };
  let simpleView = store.get("view.simple", true);  // Simple first: a new visitor sees the answer, not every panel (their choice is remembered)
  function initResultTabs() {
    for (const [kind, cfg] of Object.entries(RTABS)) {
      const root = $(cfg.root); if (!root || root.querySelector(".rtabs")) continue;
      const prob = root.querySelector(".prob");
      const strip = document.createElement("div"); strip.className = "rstrip"; strip.id = `${kind}-strip`; prob.after(strip);
      const bar = document.createElement("div"); bar.className = "seg-tabs rtabs"; bar.dataset.rtabs = kind;
      bar.innerHTML = cfg.tabs.map(([k, l]) => `<button type="button" data-rtab="${k}">${l}</button>`).join("");
      strip.after(bar);
      let after = bar;
      for (const [k] of cfg.tabs) {
        const pane = document.createElement("div"); pane.className = "rpane"; pane.dataset.pane = k; pane.dataset.kind = kind;
        after.after(pane); after = pane;
        for (const sel of cfg.panes[k]) {
          // "@needle:#x" = the small heading just before #x (e.g. "What moved the needle")
          const el = sel.startsWith("@needle:") ? root.querySelector(sel.slice(8))?.previousElementSibling : root.querySelector(sel);
          if (el && el.tagName === "H3" || (el && !sel.startsWith("@needle:"))) pane.append(el);
        }
      }
      showTab(kind, store.get(`rtab.${kind}`, "par"));
      // sections appear / disappear as data arrives (players, projection…): keep the dimming and notes up to date
      let pend = 0;
      new MutationObserver(() => { if (!pend) pend = setTimeout(() => { pend = 0; markEmptyTabs(kind); }, 0); })
        .observe(root, { subtree: true, attributes: true, attributeFilter: ["hidden"] });
    }
    applySimple();
    document.addEventListener("click", (e) => {
      const t = e.target.closest?.("[data-rtab]");
      if (t) { const kind = t.closest("[data-rtabs]").dataset.rtabs; showTab(kind, t.dataset.rtab, true); return; }
      const g = e.target.closest?.("[data-go-tab]");
      if (g) { const kind = g.closest(".rstrip").id.replace("-strip", ""); if (simpleView) { simpleView = false; store.set("view.simple", false); applySimple(); } showTab(kind, g.dataset.goTab, true); return; }
      const v = e.target.closest?.("[data-view-mode]");
      if (v) { simpleView = v.dataset.viewMode === "simple"; store.set("view.simple", simpleView); applySimple(); }
    });
  }
  function showTab(kind, tab, user = false) {
    const cfg = RTABS[kind]; if (!cfg.tabs.some(([k]) => k === tab)) tab = "par";
    $$(`.rpane[data-kind="${kind}"]`).forEach((p) => p.classList.toggle("on", p.dataset.pane === tab));
    $$(`[data-rtabs="${kind}"] [data-rtab]`).forEach((b) => b.classList.toggle("active", b.dataset.rtab === tab));
    if (user) store.set(`rtab.${kind}`, tab);
    if (tab === "proj" && state.lastFirst && user) renderFirstWorm(state.lastFirst);  // charts measure their width when shown
    if (tab === "next" && state.lastChase && user && typeof renderWorm === "function") renderWorm(state.lastChase);
  }
  function applySimple() {
    for (const kind of Object.keys(RTABS)) { const root = $(RTABS[kind].root); if (root) root.classList.toggle("simple", simpleView); paintStrip(kind); }
  }
  function setStrip(kind, field, val) { STRIP[kind][field] = val; paintStrip(kind); }
  function paintStrip(kind) {
    const el = $(`#${kind}-strip`); if (!el) return;
    const s = STRIP[kind]; const chips = [];
    const sign = (n) => `${n >= 0 ? "+" : "−"}${Math.abs(n)}`;
    if (s.par) {
      const ok = s.par.diff >= -2;
      chips.push(`<button type="button" class="rchip ${ok ? "ok" : "bad"}" data-go-tab="par"><small>${s.par.goal} · ${s.par.wk} down · ${s.par.even ? "even teams" : "these teams"}</small>
        <b>${s.par.now}</b><em>${Math.abs(s.par.diff) <= 2 ? "on par" : `${sign(s.par.diff)} ${s.par.diff > 0 ? "ahead" : "behind"}`}</em></button>`);
    }
    if (s.mom) {
      chips.push(`<button type="button" class="rchip ${s.mom.swing > 3 ? "ok" : s.mom.swing < -3 ? "bad" : ""}" data-go-tab="par"><small>Momentum · last ${s.mom.span}</small>
        <b>${esc(s.mom.lead || "Even")}</b><em>${esc(s.mom.bat)} ${sign(s.mom.swing)} vs par</em></button>`);
    }
    if (kind === "first" && s.proj) chips.push(`<button type="button" class="rchip" data-go-tab="proj"><small>Projected total</small><b>${s.proj.mid}</b><em>${s.proj.low}–${s.proj.high}</em></button>`);
    if (kind === "chase" && s.need) {
      const n = s.need;
      chips.push(`<button type="button" class="rchip ${n.r50 === 0 ? "ok" : n.r50 == null ? "bad" : ""}" data-go-tab="next"><small>${esc(n.span)} for 50/50</small>
        <b>${n.r50 == null ? "–" : n.r50 === 0 ? "any" : n.r50}</b><em>${n.r50 == null ? "long shot" : n.r50 === 0 ? "ahead even on a maiden" : "runs, no wicket"}</em></button>`);
    }
    el.innerHTML = `<div class="rchips">${chips.join("") || `<span class="muted small">Key numbers appear here as the match goes on.</span>`}</div>
      <div class="seg-tabs small rview"><button type="button" data-view-mode="simple" class="${simpleView ? "active" : ""}">Simple</button><button type="button" data-view-mode="detailed" class="${simpleView ? "" : "active"}">Detailed</button></div>
      ${simpleView ? `<button type="button" class="rmore" data-view-mode="detailed">See the full analysis <span>par by wickets · players · ${kind === "first" ? "projection" : "next over"} · why</span><i aria-hidden="true">→</i></button>` : ""}`;
    markEmptyTabs(kind);
  }
  // the main section of each tab: when it is hidden the tab is dimmed and explains why (it stays clickable)
  const RMAIN = { first: { players: "#first-res", proj: "#r-proj" }, chase: { players: "#chase-res", next: "#c-need" } };
  const REMPTY = {
    first: {
      players: "No players to show right now. Who is still to bat (and each bowler's overs left) appears while an innings is in progress: when the innings is over (20 overs bowled or all out) there's no one left to come. Tap <b>New innings (0/0, live)</b>, or enter a score before the last over.",
      proj: "The projected total is for an innings still in progress. This innings is complete, so its score is the final total; the chart below shows how it was built.",
    },
    chase: {
      players: "No players to show right now. Who is still to bat (and each bowler's overs left) appears while the chase is live.",
      next: "“Next over” shows while the chase is live: it is hidden once the chase is won or lost.",
    },
  };
  function markEmptyTabs(kind) {  // dim a tab whose main section is hidden right now (e.g. Players after the innings)
    $$(`.rpane[data-kind="${kind}"]`).forEach((p) => {
      const key = p.dataset.pane; const main = RMAIN[kind]?.[key] ? $(RMAIN[kind][key]) : null;
      const has = main ? !main.hidden : [...p.children].some((c) => !c.hidden && c.tagName !== "H3" && !c.classList.contains("rpane-empty"));
      $(`[data-rtabs="${kind}"] [data-rtab="${key}"]`)?.classList.toggle("empty", !has);
      let note = p.querySelector(":scope > .rpane-empty");
      if (!has && REMPTY[kind]?.[key]) {
        if (!note) { note = document.createElement("p"); note.className = "rpane-empty"; p.prepend(note); }
        if (note.dataset.key !== key) { note.innerHTML = REMPTY[kind][key]; note.dataset.key = key; }
        if (note.hidden) note.hidden = false;  // only real changes, so the watcher below doesn't wake itself up
      } else if (note && !note.hidden) note.hidden = true;
    });
  }

  // ------------------------------------------------------------------ model scorecard (Home)
  // How often the models were right on unseen matches: the headline is mid-innings (innings break), per competition
  // and season, plus your own saved predictions. Follows the IPL / International switch.
  let SC = null; let scTab = store.get("sc.tab", "All internationals");
  const SC_GROUPS = ["T20I · full members", "T20I · with associates", "ODI · full members", "ODI · with associates"];
  async function loadScorecard() {
    try { SC = await api("/api/scorecard"); } catch { SC = null; }
    renderScorecard();
  }
  function combine(parts) {  // add several competitions together (right / matches); in-play is weighted by matches
    const sum = (f) => parts.reduce((s, g) => s + (f(g) || 0), 0);
    const n = sum((g) => g.innings_break.n), np = sum((g) => g.pre_match.n), m = sum((g) => g.matches);
    const mid = m ? parts.reduce((s, g) => s + (g.mid_innings.pct || 0) * g.matches, 0) / m : null;
    return { matches: m, innings_break: { right: sum((g) => g.innings_break.right), n, pct: n ? Math.round(sum((g) => g.innings_break.right) * 1000 / n) / 10 : null },
      pre_match: { right: sum((g) => g.pre_match.right), n: np, pct: np ? Math.round(sum((g) => g.pre_match.right) * 1000 / np) / 10 : null },
      mid_innings: { pct: mid != null ? Math.round(mid * 10) / 10 : null },
      chase_10: (() => { const r = sum((g) => g.chase_10?.right), c = sum((g) => g.chase_10?.n); return { right: r, n: c, pct: c ? Math.round(r * 1000 / c) / 10 : null }; })() };
  }
  function scGroup() {
    const G = SC?.groups || {};
    if (state.mode === "ipl") return G.IPL ? { name: "IPL", label: "IPL", ...G.IPL } : null;
    if (scTab !== "All internationals" && G[scTab]) return { name: scTab, label: scTab, ...G[scTab] };
    const parts = SC_GROUPS.map((k) => G[k]).filter(Boolean); if (!parts.length) return null;
    const years = [...new Set(parts.flatMap((g) => Object.keys(g.seasons || {})))].sort();
    const chase = parts.filter((g) => g.chase_late != null);
    return { name: "All internationals", label: "international", ...combine(parts),
      seasons: Object.fromEntries(years.map((y) => [y, combine(parts.map((g) => g.seasons?.[y]).filter(Boolean))])),
      chase_late: chase.length ? Math.round(chase.reduce((s, g) => s + g.chase_late * g.matches, 0) / chase.reduce((s, g) => s + g.matches, 0) * 10) / 10 : null };
  }
  function renderScorecard() {
    const body = $("#sc-body"); if (!body) return;
    const tabs = $("#sc-tabs"); tabs.hidden = state.mode === "ipl";
    if (state.mode !== "ipl") tabs.innerHTML = ["All internationals", ...SC_GROUPS].map((k) => `<button type="button" data-sc-tab="${esc(k)}" class="${k === scTab ? "active" : ""}">${esc(k.replace(" · ", " "))}</button>`).join("");
    const g = scGroup();
    if (!g || !g.innings_break?.n) { body.innerHTML = `<div class="sc-card sc-empty">No scorecard yet: it's made after the models are trained (Data → Retrain).</div>`; return; }
    const ib = g.innings_break, years = Object.keys(g.seasons || {}).sort();
    const period = years.length ? `${years[0]}${years.length > 1 ? `–${years[years.length - 1].slice(2)}` : ""}` : "";
    $("#sc-sub").innerHTML = `Every number below is from matches the model <b>never saw</b> while learning (it learned from matches before ${esc((SC.trained_before || "2024").slice(0, 4))}; tested on ${period}). A coin flip would be right 50% of the time.`;
    const C = 2 * Math.PI * 54;
    const bar = (pct, label, sub, cls = "") => `<div class="sc-bar ${cls}"><div class="sc-bar-top"><span>${label}</span><b data-pct="${pct ?? ""}">${pct != null ? pct.toFixed(1) : "–"}%</b></div>
      <div class="sc-meter"><i style="--v:${pct != null ? pct / 100 : 0}"></i><em title="Coin flip (50%)"></em></div>${sub ? `<small>${sub}</small>` : ""}</div>`;
    const yours = SC.yours;
    body.innerHTML = `
      <div class="sc-card sc-hero">
        <div class="sc-ring"><svg viewBox="0 0 128 128" aria-hidden="true"><circle cx="64" cy="64" r="54" class="sc-ring-bg"/>
          <circle cx="64" cy="64" r="54" class="sc-ring-v" style="--v:${ib.pct / 100};stroke-dasharray:${C.toFixed(1)};--c:${C.toFixed(1)}"/></svg>
          <div class="sc-ring-num"><b data-pct="${ib.pct}">${ib.pct.toFixed(1)}%</b><small>right</small></div></div>
        <div class="sc-hero-copy"><span class="sc-kicker">At mid-innings · the main target</span>
          <h3><b>${ib.right}</b> of <b>${ib.n}</b> ${esc(g.label)} matches called right</h3>
          <p>First innings done, total known: who wins? Checked against the real result of every match.</p></div>
      </div>
      <div class="sc-card sc-stats"><h4>Every stage of the match</h4>
        ${bar(ib.pct, "At mid-innings (innings break)", `${ib.right} of ${ib.n} matches`, "main")}
        ${g.chase_10?.n ? bar(g.chase_10.pct, `Live chase, after ${state.mode === "ipl" || scTab.startsWith("T20I") ? "10 overs" : scTab.startsWith("ODI") ? "25 overs" : "10 overs (ODI 25)"}`, `${g.chase_10.right} of ${g.chase_10.n} chases still going at that point`, "main chase10") : ""}
        ${bar(g.pre_match.pct, "Before the match", `${g.pre_match.right} of ${g.pre_match.n} matches`)}
        ${bar(g.mid_innings.pct, "During the 1st innings", "every over of every match, each match counted once")}
        ${g.chase_late != null ? bar(g.chase_late, "Live chase, last quarter", "the second-innings model near the finish") : ""}
      </div>
      <div class="sc-card sc-seasons"><h4>Season by season (bar = mid-innings)</h4>
        ${years.map((y) => { const s = g.seasons[y]; return bar(s.innings_break.pct, `${y} <small>${s.matches} matches</small>`, `${s.innings_break.right} of ${s.innings_break.n} right · chase after 10 overs <b>${s.chase_10?.pct ?? "–"}%</b> · before the match ${s.pre_match.pct ?? "–"}%`); }).join("")}
      </div>
      <div class="sc-card sc-yours"><h4>Your saved predictions</h4>
        ${yours && yours.checked ? `<div class="sc-yours-num"><b data-pct="${yours.pct}">${yours.pct.toFixed(1)}%</b><span>${yours.right} of ${yours.checked} checked predictions were right</span></div>`
          : `<p class="muted">None checked yet. Predictions you save are checked against real results after each data update (History tab).</p>`}
        <a class="sc-link" href="#accuracy">Full accuracy details →</a>
      </div>`;
    if ($("#scorecard").classList.contains("in")) animateScorecard();
  }
  function animateScorecard() {
    if (NO_MOTION) return;
    $$("#sc-body [data-pct]").forEach((el) => {
      const target = Number(el.dataset.pct); if (!Number.isFinite(target)) return;
      const t0 = performance.now(), dur = 1400;
      const tick = (t) => { const k = Math.min(1, (t - t0) / dur); const v = target * (1 - Math.pow(1 - k, 3)); el.textContent = `${v.toFixed(1)}%`; if (k < 1) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
  }
  function bindScorecard() {
    $("#sc-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sc-tab]"); if (!b) return;
      scTab = b.dataset.scTab; store.set("sc.tab", scTab); renderScorecard();
    });
    const sc = $("#scorecard");
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => { if (entries[0].isIntersecting) { io.disconnect(); setTimeout(animateScorecard, 120); } }, { threshold: 0.2 });
      io.observe(sc);
    }
    loadScorecard();
  }

  // ------------------------------------------------------------------ glass motion
  // light follows the pointer over glass cards, and cards tilt a little; off on low-power PCs / reduce motion
  function initGlass() {
    const lowPower = NO_MOTION || (navigator.hardwareConcurrency || 8) <= 2 || (navigator.deviceMemory || 8) <= 2
      || !(window.CSS && CSS.supports && (CSS.supports("backdrop-filter", "blur(2px)") || CSS.supports("-webkit-backdrop-filter", "blur(2px)")));
    if (lowPower) { document.documentElement.classList.add("no-glass"); return; }

    // the hero spotlight follows the pointer (and roams by itself when the pointer is elsewhere)
    const hero = document.querySelector(".hero2");
    if (hero) {
      let hf = 0, he = null;
      hero.addEventListener("pointermove", (e) => {
        if (e.pointerType === "touch") return;
        he = e; hero.classList.add("tracking");
        if (!hf) hf = requestAnimationFrame(() => {
          hf = 0; const r = hero.getBoundingClientRect(); const light = hero.querySelector(".hero-light");
          if (light) light.style.transform = `translate(${Math.round(he.clientX - r.left)}px, ${Math.round(he.clientY - r.top)}px)`;
        });
      }, { passive: true });
      hero.addEventListener("pointerleave", () => {
        hero.classList.remove("tracking"); const light = hero.querySelector(".hero-light"); if (light) light.style.transform = "";
      });
      if ("IntersectionObserver" in window) {  // no hero motion while it's scrolled out of view
        new IntersectionObserver(([e]) => hero.classList.toggle("paused", !e.isIntersecting)).observe(hero);
      }
    }
    const SEL = ".team-card, .tech, .feature, .float-card, .fd-card, .sc-card, .mp-order, .mp-turn, .result-panel, .input-panel, .panel.section, .score-card, .page-head, .hist-item";
    const TILT = ".team-card, .tech, .feature, .mp-order";
    let active = null, frame = 0, last = null;
    const paint = () => {
      frame = 0; if (!active || !last) return;
      const r = active.getBoundingClientRect();
      const x = (last.clientX - r.left) / r.width, y = (last.clientY - r.top) / r.height;
      active.style.setProperty("--mx", `${(x * 100).toFixed(1)}%`); active.style.setProperty("--my", `${(y * 100).toFixed(1)}%`);
      if (active.matches(TILT)) {
        const max = active.classList.contains("feature") ? 2.5 : 5;
        active.style.transform = `perspective(900px) rotateX(${((0.5 - y) * max).toFixed(2)}deg) rotateY(${((x - 0.5) * max).toFixed(2)}deg) translateY(-4px)`;
      }
    };
    document.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") return;
      const el = e.target.closest?.(SEL);
      if (el !== active) { if (active) active.style.transform = ""; active = el; }
      last = e;
      if (active && !frame) frame = requestAnimationFrame(paint);
    }, { passive: true });
    document.addEventListener("pointerleave", () => { if (active) active.style.transform = ""; active = null; }, true);
  }

  // live numbers on the home page (the counters animate to these when they scroll into view)
  function setStat(name, value) {
    const el = $(`.band-stats [data-stat="${name}"]`);
    if (!el || !value) return;
    el.dataset.count = value;
    if (el.dataset.counted) el.textContent = Number(value).toLocaleString();
  }
  function bindHome() {
    initMotion();
    initGlass();
    $$("[data-home-go]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); homeGo(a.dataset.homeGo); }));
    $$("[data-quick]").forEach((b) => b.addEventListener("click", () => homeGo(b.dataset.quick)));
    $("#team-row").addEventListener("click", (e) => {
      const card = e.target.closest("[data-team]"); if (!card) return;
      const code = card.dataset.team;
      goPredict(() => {
        if (state.stage !== "first") setStage("first");
        const sel = $("#batting-select");
        if (code !== state.batting) {
          if (code === state.chasing) $("#swap-btn").click();
          else { sel.value = code; sel.dispatchEvent(new Event("change", { bubbles: true })); }
        }
        $("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" });
        toast(`${team(code)?.name || code} picked to bat first`);
      });
    });
    $("#team-row-next").addEventListener("click", () => { const r = $("#team-row"); r.scrollBy({ left: r.clientWidth * 0.8, behavior: "smooth" }); });
    $("#home-search").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = $("#home-q").value.trim(); if (!q) return;
      const f = fold(q);
      const t = state.config?.teams.find((x) => fold(x.name).includes(f) || fold(x.code) === f);
      goPredict(() => {
        if (t) {
          const sel = $("#batting-select");
          if (t.code === state.chasing) $("#swap-btn").click();
          else if (t.code !== state.batting) { sel.value = t.code; sel.dispatchEvent(new Event("change", { bubbles: true })); }
          $("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" });
          toast(`${t.name} picked to bat first`);
          return;
        }
        const input = $("#venue-input"); input.value = q;
        input.scrollIntoView({ behavior: "smooth", block: "center" });
        input.focus(); input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
    api("/api/status").then((st) => {
      const n = st.store?.matches;
      if (n) { $("#hero-data").textContent = n.toLocaleString(); $("#home-matches").textContent = n.toLocaleString(); }
      setStat("matches", n); setStat("states", st.store?.states); setStat("players", st.players_tracked);
      if (st.store?.states) $("#tech-states").textContent = Number(st.store.states).toLocaleString();
    }).catch(() => {});
  }

  // ---- Suggested XI ----
  const suggestKey = (side) => [state.mode, state.format, state.batting, state.chasing, side].join("|");
  async function suggestXI(side) {
    const box = $(`#xi-${side}-suggest`); const key = suggestKey(side);
    box.hidden = false; box.dataset.key = key;
    box.innerHTML = `<div class="sg-loading">Picking the strongest XI…</div>`;
    try {
      const r = await api("/api/suggest-xi", { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing,
        venue: state.venue, par: state.par, side, ...xiPayload() });
      if (box.dataset.key !== key) return;  // teams changed while loading
      if (!r.available) { box.innerHTML = `<div class="sg-loading">No match data for this team yet.</div>`; return; }
      renderSuggest(box, r);
    } catch (err) { box.innerHTML = `<div class="sg-loading">Couldn't suggest an XI (${esc(err.message)}).</div>`; }
  }
  function renderSuggest(box, r) {
    const mc = r.model_check || {};
    const delta = mc.current != null && mc.suggested != null ? Math.round((mc.suggested - mc.current) * 10) / 10 : null;
    const check = mc.suggested == null ? "" : `<div class="sg-check">
        <span>Model's pre-match win chance for ${esc(r.team)}</span>
        <b>${mc.current != null ? `${mc.current}% → ` : ""}${mc.suggested}%</b>
        ${delta != null ? `<em class="${delta > 0 ? "up" : delta < 0 ? "down" : ""}">${delta > 0 ? "+" : ""}${delta} pts</em>` : ""}
      </div>`;
    const changes = r.same_as_current ? `<p class="sg-same">Your ticked XI already matches the suggestion.</p>`
      : `<div class="sg-changes">${r.changes.in.length ? `<span class="in">In: ${r.changes.in.map(esc).join(", ")}</span>` : ""}
         ${r.changes.out.length ? `<span class="out">Out: ${r.changes.out.map(esc).join(", ")}</span>` : ""}</div>`;
    box.innerHTML = `
      <div class="sg-head"><strong>Suggested XI · ${esc(r.team)}</strong>
        <button type="button" class="sg-close" aria-label="Close suggestion">&times;</button></div>
      <p class="sg-sub">${r.bowling_options} bowling options${r.overseas != null ? ` · ${r.overseas}/4 overseas` : ""}${r.matchups_used ? ` · matchups v ${esc(r.opponent)}'s ticked XI` : ""}</p>
      ${check}${changes}
      <ol class="sg-list">${r.picks.map((p, i) => `
        <li style="--i:${i}" class="${r.changes.in.includes(p.name) ? "new" : ""}">
          <span class="sg-slot s-${p.slot.toLowerCase()}">${esc(p.slot)}</span>
          <span class="sg-name">${esc(p.name)}${p.overseas ? ` <i class="os" title="Overseas player">OS</i>` : ""}</span>
          <small>${esc(p.reason)}</small></li>`).join("")}</ol>
      ${r.left_out.length ? `<details class="sg-bench"><summary>Next in line</summary><ul>${r.left_out.map((p) => `<li><b>${esc(p.name)}</b> <small>${esc(p.reason)}</small></li>`).join("")}</ul></details>` : ""}
      <div class="sg-actions">
        ${r.same_as_current ? "" : `<button type="button" class="sg-use">Use this XI</button>`}
        <button type="button" class="chip-btn sg-keep">${r.same_as_current ? "Close" : "Keep mine"}</button>
      </div>
      <p class="sg-note">A simple rule (half career, half last 10 innings / spells, nudged by matchups), not a trained model. The model's win chance above is the check.</p>`;
    box.querySelector(".sg-close").onclick = box.querySelector(".sg-keep").onclick = () => { box.hidden = true; };
    const use = box.querySelector(".sg-use");
    if (use) use.onclick = () => {
      state.xi[r.side] = [...r.xi]; state.order[r.side] = false; box.hidden = true; renderXI(); livePredict();
      toast(`Suggested XI ticked for ${r.team}`);
    };
  }
  // which players the tick list shows: all / only the ticked ones / only the ones still available
  const xiShow = { bat: "all", chase: "all" };
  function applyXIFilter(side) {
    const q = fold($(`[data-xi-find="${side}"]`).value).trim();
    const mode = xiShow[side]; let shown = 0;
    $$(`#xi-${side} li:not(.xi-none)`).forEach((li) => {
      const label = li.querySelector("label"); const box = li.querySelector("input");
      const byFind = Boolean(q) && (!label || !fold(label.textContent).includes(q));
      const byMode = mode !== "all" && (!box || (mode === "sel") !== box.checked);  // dividers hide while filtering
      li.classList.toggle("hidden-by-find", byFind || byMode);
      if (box && !(byFind || byMode)) shown += 1;
    });
    const list = $(`#xi-${side}`); let none = list.querySelector(".xi-none");
    if (!none) { none = document.createElement("li"); none.className = "xi-none"; list.append(none); }
    none.hidden = shown > 0;
    none.textContent = q ? "No player matches." : mode === "sel" ? "Nobody ticked yet." : "Everyone is ticked.";
  }
  // "Selected XI" box beside the tick list: who is in, in the order ticked, each with a button to take them out
  function renderPicked(side, items) {
    const el = $(`#xi-${side}-picked`); if (!el) return;
    const by = new Map(items.map((p) => [p.name, p]));
    const names = state.xi[side]; const n = names.length;
    const tally = {};
    names.forEach((nm) => { const r = by.get(nm)?.role_label || "Other"; tally[r] = (tally[r] || 0) + 1; });
    const order = ["Batter", "All-rounder", "Bowler", "Keeper", "Other"];
    const plural = (r, c) => (c === 1 ? r.toLowerCase() : `${r.toLowerCase()}s`);
    const balance = order.filter((r) => tally[r]).map((r) => `${tally[r]} ${plural(r, tally[r])}`).join(" · ");
    const mine = state.order[side];
    el.innerHTML = `
      <div class="xp-head"><strong>Batting order</strong><span class="xp-count ${n === 11 ? "full" : ""}">${n} of 11</span></div>
      ${n ? `<p class="xp-how">${mine ? "Your order" : "Usual positions"} · drag <span aria-hidden="true">⠿</span> or use the arrows
        ${mine ? `<button type="button" class="xp-reset" data-xi-usual="${side}">Usual order</button>` : ""}</p>
        <ol class="xp-list" data-xi-order="${side}">${names.map((nm, i) => `<li data-i="${i}">
        <span class="xp-grip" data-xi-grip="${side}" title="Drag to move" aria-hidden="true">⠿</span>
        <span class="xp-n">${i + 1}</span><span class="xp-name" title="${esc(nm)}">${esc(nm)}</span>
        ${by.get(nm)?.role_label ? `<span class="xp-role">${esc(by.get(nm).role_label)}</span>` : ""}
        <span class="xp-move">
          <button type="button" data-xi-move="${side}" data-from="${i}" data-to="${i - 1}" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(nm)} up to number ${i}" title="Up">↑</button>
          <button type="button" data-xi-move="${side}" data-from="${i}" data-to="${i + 1}" ${i === n - 1 ? "disabled" : ""} aria-label="Move ${esc(nm)} down to number ${i + 2}" title="Down">↓</button>
        </span>
        <button type="button" class="xp-x" data-xi-drop="${side}" value="${esc(nm)}" aria-label="Take ${esc(nm)} out of the XI" title="Take out">&times;</button></li>`).join("")}</ol>`
        : `<p class="xp-empty">Tick players in the list to add them here.</p>`}
      ${n ? `<p class="xp-bal">${balance}${n < 11 ? ` · <b>${11 - n} more to pick</b>` : ""}</p>` : ""}`;
  }
  // drag a player by the ⠿ handle (mouse, pen or finger) to a new batting position
  // The real "Predict winner" button sits below both XI lists; while it's further down the page, a small floating
  // copy stays in the corner. Pressing it is the same as pressing the real one.
  function bindPredictShortcut() {
    const real = $("#predict-btn"); if (!real) return;
    const fab = document.createElement("button");
    fab.type = "button"; fab.className = "fab-predict"; fab.hidden = true;
    fab.innerHTML = `<span>Predict winner</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>`;
    fab.addEventListener("click", () => real.click());
    document.body.append(fab);
    const update = () => {  // cheap (one position read), so it runs straight on each scroll
      const onPredict = !$("#view-predict").hidden && real.offsetParent !== null && !real.disabled;
      fab.hidden = !(onPredict && real.getBoundingClientRect().top > innerHeight - 40);
    };
    const later = update;
    addEventListener("scroll", later, { passive: true }); addEventListener("resize", later); addEventListener("hashchange", () => setTimeout(update, 50));
    new MutationObserver(later).observe($("#view-predict"), { attributes: true, subtree: true, attributeFilter: ["hidden", "disabled"] });
    update();
  }
  // Nothing in the page moves until you let go: the row follows the pointer and the others slide aside (moving the
  // row itself mid-drag can make a touch browser drop the gesture, leaving it stuck).
  function bindXIOrderDrag() {
    let drag = null;
    const finish = (commit) => {
      if (!drag) return;
      const { side, from, to, rows, li, list } = drag; drag = null;
      rows.forEach((r) => { r.style.transform = ""; r.style.transition = ""; });
      li.classList.remove("dragging"); list.classList.remove("sorting");
      if (commit && from !== to) { moveInXI(side, from, to); toast(`${state.xi[side][to]} now bats at number ${to + 1}`); }
    };
    document.addEventListener("pointerdown", (e) => {
      const grip = e.target.closest?.("[data-xi-grip]"); if (!grip || e.button > 0) return;
      finish(true);  // a drag whose release never arrived: settle it first
      const li = grip.closest("li"); const list = li.parentElement;
      e.preventDefault();
      const rows = [...list.children]; const from = rows.indexOf(li);
      const mids = rows.map((r) => { const b = r.getBoundingClientRect(); return b.top + b.height / 2; });
      const step = li.getBoundingClientRect().height;  // the others slide by one row's height to open the gap
      drag = { side: grip.dataset.xiGrip, list, li, rows, mids, from, to: from, y0: e.clientY, step, id: e.pointerId };
      rows.forEach((r) => { if (r !== li) r.style.transition = "transform .15s ease"; });
      li.classList.add("dragging"); list.classList.add("sorting");
      try { grip.setPointerCapture(e.pointerId); } catch { /* not every browser */ }
    });
    document.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      e.preventDefault();
      const { rows, mids, from, li, step } = drag;
      li.style.transform = `translateY(${e.clientY - drag.y0}px)`;
      // new slot = how many other rows have their middle above the pointer
      const to = mids.reduce((n, m, i) => n + (i !== from && m < e.clientY ? 1 : 0), 0);
      if (to !== drag.to) {
        drag.to = to;
        rows.forEach((r, i) => {
          if (r === li) return;
          const shift = from < to && i > from && i <= to ? -step : to < from && i >= to && i < from ? step : 0;
          r.style.transform = shift ? `translateY(${shift}px)` : "";
        });
      }
    });
    document.addEventListener("pointerup", (e) => { if (drag && e.pointerId === drag.id) finish(true); });
    document.addEventListener("pointercancel", (e) => { if (drag && e.pointerId === drag.id) finish(true); });
  }
  function xiProblem() {
    for (const [side, code] of [["bat", state.batting], ["chase", state.chasing]]) {
      const n = state.xi[side].length;
      if (n !== 11) return `Tick exactly 11 players for ${team(code).name} (${n} ticked now).`;
    }
    return "";
  }
  function syncPar() {
    const v = venue();
    $("#par-chip").textContent = state.par ? `Your par ${state.par}` : `Par ${currentPar()}`;
    $("#par-chip").classList.toggle("mine", !!state.par);
    $("#par-auto").hidden = !state.par;
    const inp = $("#par-input");
    if (document.activeElement !== inp) inp.value = state.par || "";
    $("#par-note").textContent = state.par ? `Your own par (model says ${modelPar()}): used by the win %, the chase and the projected score`
      : state.pitch !== "balanced" ? `${PITCH[state.pitch][0]} pitch: ${autoPar()} × ${PITCH[state.pitch][1]} (${v[`par_${state.format}_note`]})`
      : v[`par_${state.format}_note`];
    inp.placeholder = String(modelPar());
  }
  // Strong / Lean / Toss-up, with how often that level was right in unseen matches at this stage (scripts/trust_levels.py)
  function paintTrust(sel, t) {
    const el = $(sel); if (!el) return;
    if (!t) { el.hidden = true; return; }
    el.hidden = false; el.className = `trust ${t.level === "toss-up" ? "tossup" : t.level}`;
    const where = t.competition === "unseen" ? "unseen matches" : `unseen ${t.competition} matches`;
    el.innerHTML = t.level === "toss-up"
      ? `<b>${esc(t.label)}</b><span>close to a coin flip: the favourite won ${Math.round(t.right_pct)}% ${esc(t.stage_text)}</span>`
      : `<b>${esc(t.label)}</b><span>right ${Math.round(t.right_pct)}% of the time ${esc(t.stage_text)}</span>`;
    el.title = `When the app gave the favourite this much of a chance ${t.stage_text}, the favourite won ${t.right_pct}% of ${t.matches} ${where} since ${t.test_from}`
      + (t.few ? ". Few matches, so treat this as a rough guide." : ".");
    if (t.few) el.insertAdjacentHTML("beforeend", `<i>few matches</i>`);
  }
  function syncScore() {
    state.runs = Math.max(0, Math.min(700, Math.round(state.runs || 0)));
    state.wickets = Math.max(0, Math.min(10, Math.round(state.wickets || 0)));
    state.balls = Math.max(0, Math.min(maxBalls(), state.balls));
    $("#runs-input").value = state.runs; $("#wickets-input").value = state.wickets; $("#overs-input").value = oversText(state.balls);
    renderFlow();
  }
  function parseOvers(text) {
    const [o, b = "0"] = String(text).trim().split(".");
    const overs = parseInt(o, 10); const balls = Math.min(5, parseInt(b.slice(0, 1) || "0", 10));
    return Number.isFinite(overs) ? overs * 6 + (Number.isFinite(balls) ? balls : 0) : state.balls;
  }
  function payload(save) {
    return {
      mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, venue: state.venue,
      runs: state.runs, wickets: state.wickets, overs: Number(oversText(state.balls)), par: state.par || null,
      ...xiPayload(), save,
    };
  }
  function showError(msg) { const e = $("#form-error"); e.textContent = msg; e.hidden = !msg; }

  let predictSeq = 0;
  async function predict(save = true, record = true) {
    showError("");
    if (state.batting === state.chasing) { showError("Pick two different teams."); return; }
    const problem = xiProblem();
    if (problem) { showError(problem); return; }
    const btn = $("#predict-btn"); btn.disabled = save;
    const seq = ++predictSeq;
    const at = { runs: state.runs, wickets: state.wickets, balls: state.balls };  // the score this prediction is for
    try {
      const r = await api("/api/predict", payload(save));
      if (record) recordFirstPoint(r, at, seq === predictSeq);  // "what if" previews don't go on the innings chart
      if (seq !== predictSeq) return;  // a newer ball was tapped while this was on its way: show only the latest
      renderResult(r); renderFirstWorm(r);
      if (save && window.matchMedia("(max-width: 1020px)").matches) $("#result-panel").scrollIntoView({ behavior: "smooth" });
    } catch (err) { showError(`Prediction failed: ${err.message}`); }
    finally { btn.disabled = false; }
  }
  let liveTimer = null;
  function livePredict() {
    if (state.stage === "chase") {  // live chase: teams / venue / format / XI changes refresh the chase
      if (chaseKey() !== chase.loadedKey) { restoreChase(); syncChase(); }
      scheduleChase(); return;
    }
    $("#chase-result").hidden = true;  // First innings never shows a chase card
    const mp = $("#match-preview"); if (mp && !mp.hidden && mp.dataset.key !== previewKey()) mp.hidden = true;  // preview was for other inputs
    if (!state.hasResult) { $("#result").hidden = true; $("#result-empty").hidden = false; return; }
    clearTimeout(liveTimer); liveTimer = setTimeout(() => predict(false), 350);
  }
  // what a match preview was made for (teams, ground, format, both XIs): a change hides the old preview
  const previewKey = () => JSON.stringify([state.batting, state.chasing, state.venue, state.format, state.xi.bat, state.xi.chase]);

  function clearResult() { state.hasResult = false; $("#result").hidden = true; $("#chase-result").hidden = true; $("#result-empty").hidden = false; }

  function renderResult(r) {
    // same for a first-innings answer that arrives after you moved to Live chase or picked other teams
    if (state.stage === "chase" || r.batting_code !== state.batting || r.chasing_code !== state.chasing) return;
    state.hasResult = true; state.lastFirst = r;
    $("#result-empty").hidden = true; $("#result").hidden = false;
    const winnerCode = r.winner === r.batting_team ? r.batting_code : r.chasing_code;
    const winPct = Math.max(r.batting_pct, r.chasing_pct);
    $("#r-verdict").textContent = `${r.verdict} · ${winPct.toFixed(0)}% chance`;
    paintTrust("#r-trust", r.trust);
    const sure = $("#r-sure-note");  // very sure ODI calls: how such calls really went (an honest note, see webapp.sure_odi_note)
    if (sure) { sure.hidden = !r.sure_note; sure.textContent = r.sure_note ? r.sure_note.text : ""; }
    paintBadge($("#r-badge"), winnerCode); setHero("first", winnerCode, winPct);
    $("#r-winner").textContent = r.winner;
    const fmt = r.input.format.toUpperCase();
    $("#r-situation").textContent = `${r.batting_team} ${r.input.runs}/${r.input.wickets} after ${oversText(Math.round(Math.floor(r.input.overs) * 6 + Math.round((r.input.overs % 1) * 10)))} overs · ${fmt} · par ${r.input.par}`;
    const impactNote = ["bat", "chase"].map((s) => state.mode === "ipl" && state.impact[s].in
      ? `${team(s === "bat" ? state.batting : state.chasing).name}: ${state.impact[s].in}${state.impact[s].out ? ` for ${state.impact[s].out}` : ""}` : "").filter(Boolean);
    if (impactNote.length) $("#r-situation").textContent += ` · Impact: ${impactNote.join(" · ")}`;
    $("#r-bat-name").textContent = r.batting_team; $("#r-chase-name").textContent = r.chasing_team;
    const bs = teamStyle(r.batting_code), cs = teamStyle(r.chasing_code);
    const bb = $("#r-bat-bar"), cb = $("#r-chase-bar");
    bb.style.setProperty("--c1", bs.c1); bb.style.setProperty("--c2", bs.c2);
    cb.style.setProperty("--c1", cs.c1); cb.style.setProperty("--c2", cs.c2);
    bb.style.width = `${r.batting_pct}%`; cb.style.width = `${r.chasing_pct}%`;
    $("#r-bat-pct").textContent = r.batting_pct >= 12 ? `${r.batting_pct.toFixed(0)}%` : "";
    $("#r-chase-pct").textContent = r.chasing_pct >= 12 ? `${r.chasing_pct.toFixed(0)}%` : "";

    const d = r.details || {};
    const f = d.factors || {};
    const toward = (pts) => {
      if (pts == null || Math.abs(pts) < 0.5) return `<span class="pill neutral">neutral</span>`;
      const s = pts > 0 ? bs : cs; const name = pts > 0 ? r.batting_team : r.chasing_team;
      return `<span class="pill" style="background:linear-gradient(135deg, ${s.c1}, ${s.c2})" title="toward ${esc(name)}">+${Math.abs(pts).toFixed(1)} ${esc(s.code)}</span>`;
    };
    if (d.engine === "ml") {
      const diff = r.input.runs - (d.par ?? r.input.par);
      const pf = d.players_found || {};
      $("#r-factors").innerHTML = [
        [ICONS.score, "Score vs par", `${r.input.runs} runs vs the straight-line par of ${d.par} the model reads at this stage (${diff >= 0 ? "+" : ""}${diff}). Par by wickets: Par & phases tab`, f.score_vs_par],
        [ICONS.rating, "Team ratings", `Elo ${d.bat_elo ?? "–"} vs ${d.chase_elo ?? "–"} from past results`, f.team_ratings],
        [ICONS.xi, "Playing XI records", `Real career stats · ${pf.batting?.[0] ?? "?"}/${pf.batting?.[1] ?? "?"} and ${pf.chasing?.[0] ?? "?"}/${pf.chasing?.[1] ?? "?"} players found`, f.playing_xi],
        ...(r.conditions?.pitch ? [[ICONS.score, `${r.conditions.pitch.label} pitch (your input)`, `Par ${r.conditions.pitch.par_from} → ${r.conditions.pitch.par}; its effect is inside "Score vs par"`, null,
          `<span class="pill neutral">par ${r.conditions.pitch.par - r.conditions.pitch.par_from >= 0 ? "+" : ""}${r.conditions.pitch.par - r.conditions.pitch.par_from}</span>`]] : []),
        ...(state.par ? [[ICONS.score, "Your own par (your input)", `Par ${modelPar()} → ${state.par}; its effect is inside "Score vs par"`, null,
          `<span class="pill neutral">par ${state.par - modelPar() >= 0 ? "+" : ""}${state.par - modelPar()}</span>`]] : []),
        ...(r.conditions?.dew ? [[ICONS.rating, `${r.conditions.dew.label} (your input)`, "Second-innings conditions you set", -r.conditions.dew.chase_pts]] : []),
      ].map(([icon, title, sub, pts, pill]) => `
        <li><span class="factor-icon">${icon}</span>
          <span class="factor-text"><strong>${title}</strong><span>${esc(sub)}</span></span>${pill || toward(pts)}</li>`).join("");
      const acc = d.test_accuracy_innings_break;
      $("#r-model").innerHTML = `Predicted by the <b>${esc(d.model_label)}</b> model${acc ? `, which picked the right winner in <b>${(acc * 100).toFixed(1)}%</b> of unseen 2025–26 matches at the innings break` : ""}. `
        + (d.formula_probability != null ? `The old formula would have said ${esc(r.batting_team)} ${d.formula_probability.toFixed(0)}%. ` : "")
        + `<a href="#accuracy">See all model accuracy →</a>`;
    } else {
      $("#r-factors").innerHTML = `<li><span class="factor-icon">${ICONS.score}</span><span class="factor-text"><strong>Original formula</strong><span>The ML model doesn't cover this case, so the hand-tuned formula was used.</span></span><span class="pill neutral">formula</span></li>`;
      $("#r-model").innerHTML = `Predicted by the <b>original formula</b>. <a href="#accuracy">See model accuracy →</a>`;
    }
    $("#r-explain").innerHTML = (r.explanation || []).map((t) => `<li>${esc(t)}</li>`).join("");
    renderProjection(r);
    renderPhaseTracker("first"); renderBowlLog("first"); scheduleResources("first"); schedulePar("first", PG.first ? 50 : 400);
    renderWhy("first", (r.details || {}).engine === "ml");
  }

  // projected first-innings total: middle estimate, 80% range, par and the "current rate" number on one scale
  function renderProjection(r) {
    const p = r.projection;
    $("#r-proj").hidden = !p;
    if (!p) { setStrip("first", "proj", null); return; }
    setStrip("first", "proj", { mid: p.mid, low: p.low, high: p.high });
    $("#p-mid").textContent = p.mid;
    $("#p-range").textContent = `likely ${p.low}–${p.high}`;
    $("#p-note").innerHTML = `At the current rate: <b>${p.current_rate}</b> · par here: <b>${p.par}</b>`
      + (p.typical_error ? `<br>Usually within about ±${Math.round(p.typical_error)} runs at this stage` : "");
    const lo = Math.min(p.low, p.par, p.current_rate) - 10; const hi = Math.max(p.high, p.par, p.current_rate) + 10;
    const pos = (v) => `${((v - lo) / (hi - lo)) * 100}%`;
    const step = hi - lo > 160 ? 50 : hi - lo > 80 ? 25 : 10;
    const ticks = []; for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
    $("#p-scale").innerHTML = `<div class="axis"></div>
      <div class="band" style="left:${pos(p.low)};width:calc(${pos(p.high)} - ${pos(p.low)})"></div>
      <div class="mark crr" style="left:${pos(p.current_rate)}" title="At the current rate: ${p.current_rate}"></div>
      <div class="mark par" style="left:${pos(p.par)}" title="Par here: ${p.par}"></div>
      <div class="mark mid" style="left:${pos(p.mid)}" title="Projected: ${p.mid}"></div>
      ${ticks.map((t) => `<span class="tick" style="left:${pos(t)}">${t}</span>`).join("")}`;
  }

  function bindPredict() {
    $("#batting-select").addEventListener("change", (e) => {
      state.batting = e.target.value; resetXI("bat");
      if (state.batting === state.chasing) { state.chasing = state.config.teams.find((t) => t.code !== state.batting).code; resetXI("chase"); }
      $("#chasing-select").value = state.chasing; paintTeams(); renderXI(); livePredict();
    });
    $("#chasing-select").addEventListener("change", (e) => {
      state.chasing = e.target.value; resetXI("chase");
      if (state.batting === state.chasing) { state.batting = state.config.teams.find((t) => t.code !== state.chasing).code; resetXI("bat"); }
      $("#batting-select").value = state.batting; paintTeams(); renderXI(); livePredict();
    });
    $$("[data-suggest-xi]").forEach((b) => b.addEventListener("click", () => suggestXI(b.dataset.suggestXi)));
    bindXIOrderDrag();
    bindPredictShortcut();
    bindShare();
    $$("[data-reset-xi]").forEach((b) => b.addEventListener("click", () => { resetXI(b.dataset.resetXi, false); livePredict(); toast("Latest XI selected"); }));
    $("#swap-btn").addEventListener("click", () => {
      [state.batting, state.chasing] = [state.chasing, state.batting];
      [state.xi.bat, state.xi.chase] = [state.xi.chase, state.xi.bat];
      [state.impact.bat, state.impact.chase] = [state.impact.chase, state.impact.bat];
      [state.order.bat, state.order.chase] = [state.order.chase, state.order.bat];
      $("#batting-select").value = state.batting; $("#chasing-select").value = state.chasing;
      paintTeams(); renderXI(); livePredict();
    });
    bindVenueCombo();
    $("#country-select").addEventListener("change", (e) => setCountry(e.target.value));
    $("#country-chips").addEventListener("click", (e) => { const b = e.target.closest("[data-country]"); if (b) setCountry(b.dataset.country); });
    $$("[data-clear-xi]").forEach((b) => b.addEventListener("click", () => {
      state.xi[b.dataset.clearXi] = []; state.order[b.dataset.clearXi] = false; renderXI(); toast("All players removed. Tick the 11 who are playing.");
    }));
    $$("[data-xi-find]").forEach((inp) => inp.addEventListener("input", () => applyXIFilter(inp.dataset.xiFind)));
    $$(".segmented [data-format]").forEach((b) => b.addEventListener("click", () => {
      const wasFull = state.balls === maxBalls();
      // sides still on their suggested XI follow the format (latest T20 XI vs latest ODI XI)
      const following = ["bat", "chase"].filter((s) => sameXI(state.xi[s], suggestedXI(s === "bat" ? state.batting : state.chasing)));
      state.format = b.dataset.format;
      $$(".segmented [data-format]").forEach((x) => x.classList.toggle("active", x === b));
      following.forEach((s) => resetXI(s)); renderXI();
      if (wasFull) state.balls = maxBalls();
      state.runs = Math.round(autoPar() * state.balls / maxBalls());
      syncPar(); syncScore(); livePredict();
    }));
    $$(".sb-btn").forEach((b) => b.addEventListener("click", () => {
      const delta = Number(b.dataset.delta);
      if (b.dataset.step === "runs") state.runs += delta;
      if (b.dataset.step === "wickets") state.wickets += delta;
      if (b.dataset.step === "overs") state.balls = state.balls % 6 && delta < 0 ? state.balls - (state.balls % 6) : state.balls + delta;
      syncScore(); livePredict();
    }));
    $("#runs-input").addEventListener("change", (e) => { state.runs = parseInt(e.target.value, 10) || 0; syncScore(); livePredict(); });
    $("#wickets-input").addEventListener("change", (e) => { state.wickets = parseInt(e.target.value, 10) || 0; syncScore(); livePredict(); });
    $("#overs-input").addEventListener("change", (e) => { state.balls = parseOvers(e.target.value); syncScore(); livePredict(); });
    $$(".sb-value").forEach((i) => i.addEventListener("focus", () => i.select()));
    $("#innings-over-btn").addEventListener("click", () => { state.balls = maxBalls(); syncScore(); livePredict(); });
    $("#pre-match-btn").addEventListener("click", () => { state.balls = 0; state.runs = 0; state.wickets = 0; syncScore(); livePredict(); });
    $("#at-par-btn").addEventListener("click", () => { state.runs = Math.round(currentPar() * state.balls / maxBalls()); syncScore(); livePredict(); });
    // your own par: type it, or step it from the model's par; "Use model par" goes back
    const setPar = (v) => {
      const lim = state.format === "odi" ? [100, 450] : [60, 300];
      v = Number.isFinite(v) && v > 0 ? Math.max(lim[0], Math.min(lim[1], Math.round(v))) : null;
      state.par = v && v !== modelPar() ? v : null;
      syncPar(); livePredict();
    };
    $("#par-input").addEventListener("change", (e) => { setPar(parseInt(e.target.value, 10)); e.target.blur(); });
    $("#par-input").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); } });
    $("#par-input").addEventListener("blur", () => syncPar());
    $$("[data-par-step]").forEach((b) => b.addEventListener("click", () => setPar(currentPar() + Number(b.dataset.parStep))));
    $("#par-auto").addEventListener("click", () => setPar(null));
    document.addEventListener("click", (e) => {
      const mv = e.target.closest?.("[data-xi-move]");
      if (mv) { moveInXI(mv.dataset.xiMove, Number(mv.dataset.from), Number(mv.dataset.to), true); return; }
      const us = e.target.closest?.("[data-xi-usual]");
      if (us) { state.order[us.dataset.xiUsual] = false; renderXI(); livePredict(); toast("Back to usual batting positions"); return; }
      const x = e.target.closest?.("[data-xi-drop]");
      if (x) {  // take a player out from the Selected XI box
        const list = state.xi[x.dataset.xiDrop]; const i = list.indexOf(x.value);
        if (i >= 0) { list.splice(i, 1); renderXI(); livePredict(); }
        return;
      }
      const f = e.target.closest?.("[data-xi-filter] [data-xf]"); if (!f) return;
      const side = f.closest("[data-xi-filter]").dataset.xiFilter; xiShow[side] = f.dataset.xf;
      $$(`[data-xi-filter="${side}"] [data-xf]`).forEach((b) => b.classList.toggle("active", b === f));
      applyXIFilter(side);
    });
    document.addEventListener("change", (e) => {
      const box = e.target.closest?.(".xi-list input[type=checkbox]"); if (!box) return;
      const list = state.xi[box.dataset.side];
      if (box.checked) {
        if (list.length >= 11) { box.checked = false; toast("An XI has 11 players. Untick someone first."); return; }
        list.push(box.value);
      } else list.splice(list.indexOf(box.value), 1);
      renderXI(); livePredict();
    });
    $$("[data-whatif]").forEach((b) => b.addEventListener("click", () => {
      const [field, delta] = b.dataset.whatif.split(":"); state[field] += Number(delta); syncScore(); predict(false, false);
    }));
    $("#predict-form").addEventListener("submit", (e) => { e.preventDefault(); if (state.stage === "chase") predictChase(true); else predict(true); });
  }





  // ------------------------------------------------------------------ par by wickets: the 50/50 score for every over × wickets down
  // From the model itself ("what if" over a grid of scores, nothing saved). First innings: the batting side's score that
  // makes it an even game. Chase: the score needed by then to be on track (50/50) for the target.
  const PG = { first: null, chase: null }; const pgTimer = { first: null, chase: null };
  const pgEven = { first: store.get("pg.even", false), chase: store.get("pg.even", false) };
  function pgRequest(kind) {
    const base = { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, venue: state.venue,
      par: state.par || null, ...xiPayload(), kind, even: pgEven[kind] };
    if (kind === "chase") base.target = chase.target;
    return base;
  }
  // get the grid ready as soon as teams / XIs / venue are set (before Predict), so its numbers appear straight away
  let pgPrefetchTimer = null;
  function prefetchPar() {
    clearTimeout(pgPrefetchTimer);
    pgPrefetchTimer = setTimeout(async () => {
      if (!state.config || !state.batting || !state.chasing) return;
      for (const kind of state.stage === "chase" ? ["chase", "first"] : ["first"]) {
        const req = pgRequest(kind); const key = JSON.stringify(req);
        if (PG[kind]?.key === key) continue;
        try { const r = await api("/api/par-grid", req); if (r.grid) PG[kind] = { key, data: r }; } catch { /* only a head start */ }
      }
    }, 1500);
  }
  function schedulePar(kind, delay = 500) { clearTimeout(pgTimer[kind]); pgTimer[kind] = setTimeout(() => loadPar(kind), delay); }
  async function loadPar(kind) {
    const box = $(`#${kind}-pargrid`); if (!box) return;
    const live = kind === "first" ? state.lastFirst : (state.lastChase?.status === "live" ? state.lastChase : null);
    if (!live) { box.hidden = true; return; }
    const req = pgRequest(kind); const key = JSON.stringify(req);
    if (PG[kind]?.key !== key) {
      if (!PG[kind]) { box.hidden = false; box.querySelector(".pg-headline").textContent = "Working out par for every over and wicket…"; }
      try { const r = await api("/api/par-grid", req); if (!r.grid) { box.hidden = true; return; } PG[kind] = { key, data: r }; }
      catch { box.hidden = true; return; }
    }
    renderPar(kind);
  }
  function parAt(data, balls, w) {
    const pts = Object.keys(data.grid).map(Number).filter((b) => b < data.max_balls).sort((a, b) => a - b);
    const val = (b) => data.grid[String(b)]?.[String(w)];
    if (!pts.length || balls < pts[0]) return null;
    if (balls >= pts[pts.length - 1]) return val(pts[pts.length - 1]);
    const hi = pts.find((b) => b >= balls); const lo = [...pts].reverse().find((b) => b <= balls);
    const a = val(lo), c = val(hi); if (a == null || c == null) return a ?? c ?? null;
    return lo === hi ? a : Math.round(a + (c - a) * (balls - lo) / (hi - lo));
  }

  // par-by-wickets chart: par lines for the current wickets (and one or two more down), the innings so far, and a
  // "you are here" dot that is green when on or ahead of par and red when behind
  let pgView = store.get("pg.view", "chart");
  const PG_AHEAD = "#2f8a3b", PG_BEHIND = "#c2412d";
  function drawParChart(el, d, kind, runs, wk, balls, now) {
    const narrow = window.matchMedia("(max-width: 560px)").matches;
    const W = narrow ? 380 : 560, H = narrow ? 330 : 300, L = 38, R = narrow ? 78 : 92, T = 18, B = 34;
    const maxB = d.max_balls;
    // zoom to the part of the innings that matters: the start to a few overs past now (whole innings once it's late)
    const ahead = d.format === "odi" ? 90 : 36;
    const endB = Math.min(maxB, Math.max(balls + ahead, d.format === "odi" ? 120 : 48));
    const back = d.format === "odi" ? 120 : 54;  // late in the innings, start the window ~9 overs (ODI 20) before now
    const fromB = balls > back + 6 ? Math.floor((balls - back) / 6) * 6 : 0;
    const pts = Object.keys(d.grid).map(Number).filter((b) => b < maxB && b >= fromB && b <= endB).sort((a, b) => a - b);
    const origin = fromB === 0 && kind === "first" ? [[0, 0]] : [];  // a chase par line from 0/0 would leap up: start at over 1
    const series = (w) => [...origin, ...pts.map((b) => [b, d.grid[String(b)]?.[String(w)]]).filter(([, v]) => v != null)];
    const live = wk < 10 && balls < maxB;
    const lines = (live ? [wk - 1, wk, wk + 1, wk + 2] : [2, 4, 6]).filter((w) => w >= 0 && w <= 9);
    const tl = ((kind === "first" ? first.timeline : chase.timeline) || []).filter((p) => p.balls > 0 && p.balls <= balls).sort((a, b) => a.balls - b.balls);
    const path = tl.filter((p) => p.balls !== balls).concat(balls > 0 ? [{ balls, runs, wickets: wk }] : []);
    const seen = [...lines.flatMap((w) => series(w).map(([, v]) => v)), ...path.filter((p) => p.balls >= fromB).map((p) => p.runs)];
    let ymax = Math.max(runs, ...seen, kind === "chase" ? d.target : 0) * 1.06;
    ymax = Math.max(60, Math.ceil(ymax / 20) * 20);
    const ymin = fromB > 0 || kind === "chase" ? Math.max(0, Math.floor(Math.min(runs, ...seen) * 0.9 / 20) * 20) : 0;
    const x = (b) => L + (W - L - R) * (b - fromB) / (endB - fromB);
    const y = (r) => H - B - (H - B - T) * (Math.min(Math.max(r, ymin), ymax) - ymin) / (ymax - ymin);
    const step = ymax - ymin > 260 ? 50 : ymax - ymin > 120 ? 25 : 20; const xStep = d.format === "odi" ? (endB > 150 ? 30 : 12) : (endB > 72 ? 12 : 6);
    let s = "";
    for (let r = Math.ceil(ymin / step) * step; r <= ymax; r += step) s += `<line x1="${L}" x2="${W - R}" y1="${y(r)}" y2="${y(r)}" style="stroke:var(--line)"/><text x="${L - 6}" y="${y(r) + 4}" text-anchor="end" class="pgc-ax">${r}</text>`;
    for (let b = fromB; b <= endB; b += xStep) s += `<text x="${x(b)}" y="${H - B + 16}" text-anchor="middle" class="pgc-ax">${b / 6}</text>`;
    s += `<text x="${(L + W - R) / 2}" y="${H - 2}" text-anchor="middle" class="pgc-ax">overs</text>`;
    if (kind === "chase") s += `<line x1="${L}" x2="${W - R}" y1="${y(d.target)}" y2="${y(d.target)}" class="pgc-target"/><text x="${W - R + 6}" y="${y(d.target) + 4}" class="pgc-lab">target ${d.target}</text>`;
    // par lines (label at the right end; labels pushed apart so they never overlap)
    const labels = [];
    for (const w of lines) {
      const ser = series(w); if (ser.length < 2) continue;
      const main = live && w === wk;
      s += `<polyline points="${ser.map(([b, v]) => `${x(b).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" class="pgc-par${main ? " main" : w < wk ? " fewer" : ""}"/>`;
      const [lb, lv] = ser[ser.length - 1]; labels.push({ y: y(lv), text: `${main ? "par · " : ""}${w} down`, main });
    }
    labels.sort((a, b) => a.y - b.y).forEach((l, i, arr) => { if (i && l.y - arr[i - 1].y < 15) l.y = arr[i - 1].y + 15; });
    labels.forEach((l) => { s += `<text x="${W - R + 6}" y="${l.y + 4}" class="pgc-lab${l.main ? " main" : ""}">${l.text}</text>`; });
    // the innings so far
    const shown = path.filter((p) => p.balls >= fromB);
    if (shown.length > 1 || (shown.length === 1 && fromB === 0 && kind === "first")) {  // no made-up straight line without real points
      s += `<polyline points="${[...(fromB === 0 && kind === "first" ? [[0, 0]] : []), ...shown.map((p) => [p.balls, p.runs])].map(([b, v]) => `${x(b).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" class="pgc-path"/>`;
      shown.slice(0, -1).forEach((p) => {
        const par = parAt(d, p.balls, p.wickets); const c = par == null ? "var(--muted)" : p.runs - par >= -2 ? PG_AHEAD : PG_BEHIND;
        s += `<circle cx="${x(p.balls)}" cy="${y(p.runs)}" r="3.5" style="fill:${c}"><title>${p.runs}/${p.wickets} after ${ovs(p.balls)}${par != null ? ` · par ${par}` : ""}</title></circle>`;
      });
    }
    // you are here
    if (balls > 0) {
      const diff = now != null ? runs - now : null; const c = diff == null ? "var(--accent)" : diff >= -2 ? PG_AHEAD : PG_BEHIND;
      const cx = x(balls), cy = y(runs);
      if (now != null) s += `<line x1="${cx}" x2="${cx}" y1="${y(now)}" y2="${cy}" style="stroke:${c};stroke-width:2;stroke-dasharray:3 3"/>`;
      s += `<circle cx="${cx}" cy="${cy}" r="13" style="fill:${c};opacity:.18" class="pgc-pulse"/><circle cx="${cx}" cy="${cy}" r="7.5" style="fill:${c};stroke:#fff;stroke-width:2"/>`;
      const tag = `${runs}/${wk}${diff == null ? "" : Math.abs(diff) <= 2 ? " · on par" : ` · ${Math.abs(diff)} ${diff > 0 ? "ahead" : "behind"}`}`;
      const tw = tag.length * 7.4 + 18;
      // try above, below, then left of the dot; keep the spot that covers the fewest par-line / path points
      const linePts = [...lines.flatMap((w) => series(w)), ...shown.map((p) => [p.balls, p.runs])].map(([b, v]) => [x(b), y(v)]);
      const fit = (px, py) => [Math.min(Math.max(px, L), W - R - tw), Math.min(Math.max(py, T), H - B - 24)];
      const spots = [fit(cx - tw / 2, cy - 34), fit(cx - tw / 2, cy + 16), fit(cx - tw - 16, cy - 30), fit(cx - tw - 16, cy + 8),
        fit(cx - tw - 16, cy + 34), fit(cx - tw / 2, cy + 44)];
      const hits = ([sx, sy]) => {
        let n = 0;
        for (let i = 0; i < linePts.length; i++) {
          const [ax, ay] = linePts[i]; if (ax >= sx - 4 && ax <= sx + tw + 4 && ay >= sy - 5 && ay <= sy + 27) n += 2;
          const nx = linePts[i + 1]; if (!nx) continue;  // also sample the middle of each segment
          const mx = (ax + nx[0]) / 2, my = (ay + nx[1]) / 2; if (mx >= sx - 4 && mx <= sx + tw + 4 && my >= sy - 5 && my <= sy + 27) n += 1;
        }
        if (cx >= sx - 9 && cx <= sx + tw + 9 && cy >= sy - 9 && cy <= sy + 31) n += 50;  // never on the dot itself
        return n;
      };
      const [tx, ty] = spots.reduce((best, sp) => (hits(sp) < hits(best) ? sp : best));
      s += `<rect x="${tx}" y="${ty}" width="${tw}" height="22" rx="11" style="fill:${c}"/><text x="${tx + tw / 2}" y="${ty + 15.5}" text-anchor="middle" class="pgc-tag">${tag}</text>`;
    }
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" aria-label="Score against par by wickets">${s}</svg>`;
  }

  // par ladder: this over's par for each number of wickets down on one line, with your score pinned on it
  function renderLadder(el, d, runs, wk, balls, now) {
    if (!el) return;
    if (now == null || balls >= maxBalls() || wk >= 10) { el.innerHTML = ""; el.hidden = true; return; }
    const span = window.matchMedia("(max-width: 560px)").matches ? 2 : 3;  // fewer marks on a phone so labels never collide
    const ws = []; for (let w = Math.max(0, wk - span); w <= Math.min(9, wk + span); w++) ws.push(w);
    const vals = ws.map((w) => [w, parAt(d, balls, w)]).filter(([, v]) => v != null);
    if (!vals.length) { el.hidden = true; return; }
    const all = [...vals.map(([, v]) => v), runs];
    const lo = Math.min(...all) - 6, hi = Math.max(...all) + 6;
    const pos = (v) => `${((v - lo) / (hi - lo) * 100).toFixed(2)}%`;
    const ok = runs - now >= -2; const col = ok ? PG_AHEAD : PG_BEHIND;
    const a = Math.min(runs, now), b = Math.max(runs, now);
    el.hidden = false;
    el.innerHTML = `<div class="pgl-title">After ${ovs(balls)}: par for each number of wickets down</div>
      <div class="pgl-track">
        <i class="pgl-gap" style="left:${pos(a)};width:calc(${pos(b)} - ${pos(a)});background:${col}"></i>
        ${vals.map(([w, v], i) => {
          const near = i > 0 && (v - vals[i - 1][1]) / (hi - lo) < (window.matchMedia("(max-width: 560px)").matches ? 0.14 : 0.08);
          const alt = near && !(i > 1 && (vals[i - 1][1] - vals[i - 2][1]) / (hi - lo) < 0.14 && i % 2 === 0) ? " alt" : "";
          return `<span class="pgl-tick${w === wk ? " cur" : ""}${alt}" style="left:${pos(v)}"><b>${v}</b><small>${w} down</small></span>`;
        }).join("")}
        <span class="pgl-you" style="left:${pos(runs)};--c:${col}"><em>${runs}/${wk}</em><i></i></span>
      </div>`;
  }

  function renderPar(kind) {
    const box = $(`#${kind}-pargrid`); const d = PG[kind]?.data; if (!box || !d) return;
    box.hidden = false;
    box.querySelectorAll(`[data-par-even="${kind}"] [data-even]`).forEach((b) => b.classList.toggle("active", (b.dataset.even === "1") === pgEven[kind]));
    const runs = kind === "first" ? state.runs : chase.runs; const wk = kind === "first" ? state.wickets : chase.wickets;
    const balls = inningsBalls(kind); const team = esc(kind === "first" ? state.lastFirst.batting_team : state.lastChase.chasing_team);
    const who = pgEven[kind] ? "for evenly matched teams" : "for these two teams";
    const head = box.querySelector(".pg-headline");
    const now = wk < 10 ? parAt(d, balls, wk) : null;
    const up = wk < 9 ? parAt(d, balls, wk + 1) : null; const down = wk > 0 ? parAt(d, balls, wk - 1) : null;
    const goal = kind === "first" ? "par" : `on track for ${d.target}`;
    if (balls >= maxBalls() || wk >= 10) {
      head.innerHTML = kind === "first"
        ? `The innings is over. For the total that makes it 50/50, tap <b>Ask why → What total makes it 50/50?</b> The table shows par by wickets through the innings.`
        : `The chase is over.`;
    } else if (now == null) {
      head.innerHTML = balls < 6 ? `Par by wickets starts after the first over. Below: the 50/50 score ${who} at each point.` : `No 50/50 score for ${wk} down here.`;
    } else {
      const diff = runs - now;
      head.innerHTML = `After ${ovs(balls)} with <b>${wk} down</b>, ${goal} is <b>${now}</b> ${who}.
        ${team} have <b>${runs}</b>: <b class="${diff >= 0 ? "ahead" : "behind"}">${Math.abs(diff) <= 2 ? "right on it" : `${Math.abs(diff)} ${diff > 0 ? "ahead" : "behind"}`}</b>.
        ${up != null ? `One more wicket and it becomes <b>${up}</b>` : ""}${up != null && down != null ? "; " : ""}${down != null ? `with ${wk - 1} down it would be <b>${down}</b>` : ""}${up != null || down != null ? "." : ""}`;
    }
    // table: a row every 2 overs (T20) / 5 overs (ODI), plus the current over; wickets 0–8
    const fam = d.format; const every = fam === "odi" ? 30 : 12;
    const rowsB = Object.keys(d.grid).map(Number).filter((b) => b < d.max_balls && (b % every === 0 || b === Math.floor(balls / 6) * 6)).sort((a, b) => a - b);
    const narrow = window.matchMedia("(max-width: 560px)").matches;  // phone: the 5 columns around the current wickets
    const lo = narrow ? Math.max(0, Math.min(wk, 9) - 2 - Math.max(0, Math.min(wk, 9) + 2 - 9)) : 0;
    const cols = narrow ? [lo, lo + 1, lo + 2, lo + 3, lo + 4] : [0, 1, 2, 3, 4, 5, 6, 7, 8];
    const curRow = Math.floor(balls / 6) * 6;
    const cell = (v) => (v == null ? "–" : v === 0 ? "any" : v);
    box.querySelector(".pg-table").innerHTML = `<thead><tr><th class="rowh">Overs ↓ · wickets →</th>${cols.map((w) => `<th class="${w === wk ? "cur" : ""}">${w}</th>`).join("")}</tr></thead><tbody>`
      + rowsB.map((b) => `<tr class="${b === curRow ? "cur" : ""}"><th class="rowh">${b / 6}</th>${cols.map((w) => {
        const v = d.grid[String(b)]?.[String(w)]; const here = b === curRow && w === wk && wk < 10 && balls < maxBalls();
        if (here && now != null) {
          const df = runs - now; const ok = df >= -2;
          return `<td class="here ${ok ? "ok" : "bad"}" title="You are here: ${runs}/${wk} after ${ovs(balls)}, par ${now}"><b>${runs}</b><small>par ${now} · ${Math.abs(df) <= 2 ? "on par" : `${df > 0 ? "+" : "−"}${Math.abs(df)}`}</small></td>`;
        }
        return `<td class="${here ? "here" : w === wk ? "curcol" : ""}">${cell(v)}</td>`;
      }).join("")}</tr>`).join("") + "</tbody>";
    const where = box.querySelector(".pg-where");
    if (now != null && balls < maxBalls() && wk < 10) {
      const df = runs - now; const ok = df >= -2;
      where.innerHTML = `<i class="pg-dot" style="background:${ok ? PG_AHEAD : PG_BEHIND}"></i>You are here: <b>${runs}/${wk}</b> after ${ovs(balls)} · ${Math.abs(df) <= 2 ? "<b>on par</b>" : `<b style="color:${ok ? PG_AHEAD : PG_BEHIND}">${Math.abs(df)} ${df > 0 ? "ahead" : "behind"}</b>`} (par ${now})`;
    } else where.textContent = "";
    renderLadder(box.querySelector(".pg-ladder"), d, runs, wk, balls, now);
    setStrip(kind, "par", now != null && balls < maxBalls() && wk < 10 ? { now, diff: runs - now, wk, goal: kind === "first" ? "Par" : `On track for ${d.target}`, even: !!d.even } : null);
    let mom = box.querySelector(".pg-mom");
    if (!mom) { mom = document.createElement("div"); mom.className = "pg-mom"; box.querySelector(".pg-ladder").after(mom); }
    mom.innerHTML = balls < maxBalls() && wk < 10 ? momentumHtml(kind, d, runs, wk, balls, now) : "";
    box.querySelectorAll("[data-pg-view] [data-view]").forEach((b2) => b2.classList.toggle("active", b2.dataset.view === pgView));
    box.querySelector(".pg-chart").hidden = pgView !== "chart"; box.querySelector(".pg-tablewrap").hidden = pgView !== "table";
    if (pgView === "chart") drawParChart(box.querySelector(".pg-chart"), d, kind, runs, wk, balls, now);
    box.querySelector(".pg-note").textContent = kind === "first"
      ? `Each number is the score that makes it 50/50 ${who} at this ground, from the same model as the win %. More wickets down means more runs needed to be level.`
      : `Each number is the score the chase needs by then to be 50/50 ${who}, chasing ${d.target}. "any" = level even on 0; "–" = can't be 50/50 from there.`;
  }
  function bindPar() {
    document.addEventListener("click", (e) => {
      const b = e.target.closest?.("[data-par-even] [data-even]"); if (!b) return;
      const kind = b.closest("[data-par-even]").dataset.parEven;
      pgEven.first = pgEven.chase = b.dataset.even === "1"; store.set("pg.even", pgEven[kind]);
      loadPar(kind);
    });
    document.addEventListener("click", (e) => {
      const b = e.target.closest?.("[data-pg-view] [data-view]"); if (!b) return;
      pgView = b.dataset.view; store.set("pg.view", pgView);
      if (PG.first && state.lastFirst) renderPar("first"); if (PG.chase && state.lastChase) renderPar("chase");
    });
    window.matchMedia("(max-width: 560px)").addEventListener("change", () => { if (PG.first && state.lastFirst) renderPar("first"); if (PG.chase && state.lastChase) renderPar("chase"); });
  }


  // ------------------------------------------------------------------ live extras: matchup alert, momentum, key moments
  const currentBowler = (kind) => getLog(kind)[Math.floor(inningsBalls(kind) / 6)] || null;  // the over being bowled now
  function matchupHtml(r) {
    if (!r.bowler_now) return `<div class="mu mu-empty">Tap the bowler under <b>Who bowled?</b> for this over to see how the batters have done against him.</div>`;
    const rows = (r.matchups || []).map((m) => {
      const who = esc(shortName(m.batter));
      if (!m.found) return `<li class="mu-row none"><span class="mu-st">${m.status}</span><b>${who}</b><span class="muted">no history against him</span></li>`;
      const edgeTxt = m.edge === "batter" ? "batter on top" : m.edge === "bowler" ? "bowler on top" : "even";
      return `<li class="mu-row ${m.edge}"><span class="mu-st">${m.status}</span><b>${who}</b>
        <span>${m.runs} off ${m.balls}${m.outs ? ` · out ${m.outs}` : " · never out"} · SR ${m.strike_rate ?? "–"}${m.sixes ? ` · ${m.sixes}×6` : ""}</span>
        <i class="mu-edge">${edgeTxt}</i></li>`;
    }).join("");
    return `<div class="mu"><div class="mu-head">Matchups now: <b>${esc(r.bowler_now)}</b> bowling</div><ul>${rows}</ul></div>`;
  }
  // momentum: how far the batting side's score-vs-par (par by wickets) moved in the last 3 overs (ODI: 5), and the win %
  function momentumHtml(kind, d, runs, wk, balls, now) {
    const span = d.format === "odi" ? 30 : 18;
    const tl = ((kind === "first" ? first.timeline : chase.timeline) || []).filter((p) => p.balls <= balls - span + 6 && p.balls >= balls - span - 6 && p.balls > 0 || (p.balls === 0 && balls - span <= 3));
    if (now == null || balls < span || !tl.length) { setStrip(kind, "mom", null); return ""; }
    const then = tl.reduce((best, p) => (Math.abs(p.balls - (balls - span)) < Math.abs(best.balls - (balls - span)) ? p : best), tl[0]);
    // before the first over the table has no point yet: scale over 1's par down to the balls bowled
    const p6 = parAt(d, 6, then.wickets);
    const parThen = then.balls === 0 ? 0 : then.balls < 6 ? (p6 == null ? null : p6 * then.balls / 6) : parAt(d, then.balls, then.wickets);
    if (parThen == null) return "";
    const swing = Math.round((runs - now) - (then.runs - parThen));
    const curPct = kind === "first" ? state.lastFirst?.batting_pct : state.lastChase?.chase_pct;
    const dPct = curPct != null && then.pct != null ? curPct - then.pct : null;
    const bat = kind === "first" ? state.lastFirst.batting_team : state.lastChase.chasing_team;
    const other = kind === "first" ? state.lastFirst.chasing_team : state.lastChase.batting_team;
    const lead = Math.abs(swing) <= 3 ? null : swing > 0 ? bat : other;
    setStrip(kind, "mom", { lead: lead ? (kind === "first" ? (swing > 0 ? state.batting : state.chasing) : (swing > 0 ? state.chasing : state.batting)) : null, swing, span: ovs(balls - then.balls),
      bat: kind === "first" ? state.batting : state.chasing });  // whose runs the swing is about (the batting side)
    const w = Math.min(1, Math.abs(swing) / 25) * 50;
    return `<div class="mom">
      <div class="mom-text">Last ${ovs(balls - then.balls)}: <b>${runs - then.runs}/${wk - then.wickets}</b> ·
        ${swing >= 0 ? "+" : "−"}${Math.abs(swing)} vs par${dPct != null ? ` · win chance ${dPct >= 0 ? "+" : "−"}${Math.abs(dPct).toFixed(0)} pts for ${esc(bat)}` : ""}
        → <b class="ans">${lead ? `momentum with ${esc(lead)}` : "evenly poised"}</b></div>
      <div class="mom-bar"><span class="mom-l">${esc(kind === "first" ? state.chasing : state.batting)}</span><div class="mom-track"><i class="mom-mid"></i>
        <i class="mom-fill" style="${swing >= 0 ? `left:50%;width:${w}%;background:${PG_AHEAD}` : `left:${50 - w}%;width:${w}%;background:${PG_BEHIND}`}"></i></div>
        <span class="mom-r">${esc(kind === "first" ? state.batting : state.chasing)}</span></div></div>`;
  }
  // key moments on the win-chance chart: wickets, big overs and changes of favourite, biggest swings first
  function keyMoments(tl, teamName) {
    const out = []; const big = state.format === "odi" ? 12 : 14;
    for (let i = 1; i < tl.length; i++) {
      const a = tl[i - 1], b = tl[i];
      if (b.wickets > a.wickets) out.push({ balls: b.balls, kind: "w", text: `Wicket at ${b.runs}/${b.wickets}`, d: b.pct - a.pct });
      if ((a.pct - 50) * (b.pct - 50) < 0) out.push({ balls: b.balls, kind: "lead", text: `${b.pct > 50 ? esc(teamName) : "The other side"} became favourites`, d: b.pct - a.pct });
    }
    for (const p of tl) {
      if (p.balls % 6 || p.balls < 6) continue;
      const prev = tl.find((q) => q.balls === p.balls - 6);
      if (prev && p.runs - prev.runs >= big) out.push({ balls: p.balls, kind: "big", text: `${p.runs - prev.runs}-run over (over ${p.balls / 6})`, d: p.pct - prev.pct });
    }
    return out;
  }
  function renderMoments(el, tl, teamName, x, y) {
    const ms = keyMoments(tl, teamName);
    const at = (b) => tl.find((p) => p.balls === b);
    const marks = ms.filter((m) => m.kind !== "w").map((m) => {
      const p = at(m.balls); if (!p) return "";
      return m.kind === "big"
        ? `<g><rect x="${x(m.balls) - 5}" y="${y(p.pct) - 5}" width="10" height="10" transform="rotate(45 ${x(m.balls)} ${y(p.pct)})" fill="#e0a526" stroke="#fff" stroke-width="1"/><title>${m.text}</title></g>`
        : `<g><line x1="${x(m.balls)}" x2="${x(m.balls)}" y1="${y(100)}" y2="${y(0)}" stroke="#8a92a0" stroke-dasharray="2 3"/><title>${m.text}</title></g>`;
    }).join("");
    let list = el.nextElementSibling?.classList?.contains("moments") ? el.nextElementSibling : null;
    if (!list) { list = document.createElement("div"); list.className = "moments"; el.after(list); }
    const top = ms.sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 5).sort((a, b) => a.balls - b.balls);
    list.innerHTML = top.length ? `<span class="moments-title">Key moments</span>${top.map((m) => `<span class="moment ${m.kind}"><i></i>${oversText(m.balls)} · ${m.text}
      <b class="${m.d >= 0 ? "up" : "down"}">${m.d >= 0 ? "+" : "−"}${Math.abs(m.d).toFixed(0)}</b></span>`).join("")}` : "";
    return marks;
  }

  // ------------------------------------------------------------------ still to come: batters yet to bat, bowlers' overs left
  // Batting order = the model's guess (usual positions) unless "At the crease" is set. Overs left need the optional
  // "Who bowled?" taps (one name per over, kept in order and trimmed to the overs actually bowled, so undo just works).
  const RES = { first: null, chase: null }; const resTimer = { first: null, chase: null };
  const bowlLog = { first: null, chase: null };
  const inningsKey = (kind) => `bowl:${kind === "first" ? firstKey() : chaseKey()}`;
  const inningsBalls = (kind) => (kind === "first" ? state.balls : chase.balls);
  function sideXI(side) {
    const xi = [...(state.xi[side] || [])]; const imp = state.mode === "ipl" ? state.impact[side] : null;
    if (imp?.in && !xi.includes(imp.in)) {  // the sub takes the replaced player's place in the batting order
      const i = imp.out ? xi.indexOf(imp.out) : -1;
      if (i >= 0) xi[i] = imp.in; else xi.push(imp.in);
    }
    return xi;
  }
  const fieldingSide = (kind) => (kind === "first" ? "chase" : "bat");
  function getLog(kind) {
    const key = inningsKey(kind);
    if (!bowlLog[kind] || bowlLog[kind].key !== key) bowlLog[kind] = { key, list: store.get(key, []) };
    const balls = inningsBalls(kind);
    const max = Math.min(Math.ceil(maxBalls() / 6), Math.floor(balls / 6) + (balls < maxBalls() ? 1 : 0));
    if (bowlLog[kind].list.length > max) { bowlLog[kind].list = bowlLog[kind].list.slice(0, max); store.set(key, bowlLog[kind].list); }
    return bowlLog[kind].list;
  }
  function bowledMap(kind) {
    const list = getLog(kind); const balls = inningsBalls(kind); const done = Math.floor(balls / 6); const out = {};
    list.forEach((name, i) => { out[name] = (out[name] || 0) + (i < done ? 6 : i === done ? balls % 6 : 0); });
    return out;
  }
  const shortName = (n) => { const parts = String(n).split(" "); return parts.length > 1 ? `${parts[0][0]} ${parts.slice(1).join(" ")}` : n; };
  function renderBowlLog(kind) {
    const box = $(`#bowl-log-${kind}`); if (!box) return;
    const xi = sideXI(fieldingSide(kind)); box.hidden = !xi.length; if (!xi.length) return;
    const list = getLog(kind); const balls = inningsBalls(kind); const done = Math.floor(balls / 6);
    const quota = state.format === "odi" ? 10 : 4;
    const counts = {}; list.forEach((n) => { counts[n] = (counts[n] || 0) + 1; });
    const main = (RES[kind]?.attack || []).filter((n) => xi.includes(n));  // fixed order, so chips never move under your finger
    const chips = [...new Set([...main, ...list.filter((n) => xi.includes(n))])];
    const rest = xi.filter((n) => !chips.includes(n));
    const missing = done - list.length;  // completed overs with no bowler logged
    box.classList.toggle("ask", list.length > 0 && missing > 0);
    const maxNow = Math.min(Math.ceil(maxBalls() / 6), done + (balls < maxBalls() ? 1 : 0));
    box.querySelector(".bowl-log-label").innerHTML = list.length && list.length >= maxNow
      ? `Who bowled? <small class="muted">all ${list.length} over${list.length === 1 ? "" : "s"} so far logged</small>`
      : list.length
      ? `Over ${Math.min(list.length + 1, Math.ceil(maxBalls() / 6))}: who bowled it? <small class="muted">${list.length} logged${missing > 0 ? `, ${missing} finished over${missing === 1 ? "" : "s"} not logged yet` : ""}</small>`
      : `Who bowled? <small class="muted">optional: tap the bowler each over to see overs left</small>`;
    box.querySelector(".bowl-chips").innerHTML = chips.map((n) => `<button type="button" class="chip-btn bowl-chip${(counts[n] || 0) >= quota ? " full" : ""}" data-bowl="${esc(n)}" title="${esc(n)}">${esc(shortName(n))}<b>${counts[n] || 0}</b></button>`).join("")
      + (rest.length ? `<select class="bowl-other" data-bowl-other aria-label="Another bowler"><option value="">Other…</option>${rest.map((n) => `<option>${esc(n)}</option>`).join("")}</select>` : "")
      + (list.length ? `<button type="button" class="chip-btn bowl-undo" data-bowl-undo title="Take back the last over logged">↶</button>` : "");
  }
  function logBowler(kind, name) {
    const list = getLog(kind); const balls = inningsBalls(kind);
    const max = Math.min(Math.ceil(maxBalls() / 6), Math.floor(balls / 6) + (balls < maxBalls() ? 1 : 0));
    const quota = state.format === "odi" ? 10 : 4;
    if (list.length >= max) { toast("Every over so far has a bowler. Add the next ball first."); return; }
    if (list.filter((n) => n === name).length >= quota) { toast(`${name} has bowled all ${quota} overs`); return; }
    if (list.length && list[list.length - 1] === name) { toast(`${name} bowled the last over, so can't bowl this one`); return; }
    list.push(name); store.set(inningsKey(kind), list);
    renderBowlLog(kind); scheduleResources(kind, 50);
  }
  function scheduleResources(kind, delay = 400) {
    clearTimeout(resTimer[kind]); resTimer[kind] = setTimeout(() => loadResources(kind), delay);
  }
  async function loadResources(kind) {
    const box = $(`#${kind}-res`); if (!box) return;
    const live = kind === "first" ? state.lastFirst : (state.lastChase?.status === "live" ? state.lastChase : null);
    if (!live) { box.hidden = true; return; }
    const wickets = kind === "first" ? state.wickets : chase.wickets;
    if (wickets >= 10 || inningsBalls(kind) >= maxBalls()) { box.hidden = true; renderBowlLog(kind); return; }
    try {
      const crease = (kind === "first" ? creaseOf("bat") : creaseOf("chase")) || [];
      const r = await api("/api/resources", {
        mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing,
        batting_xi: sideXI("bat"), chasing_xi: sideXI("chase"), side: kind, wickets, balls: inningsBalls(kind),
        batting_order_set: state.order.bat, chasing_order_set: state.order.chase,
        crease: crease.map((c) => c.name), bowled: bowledMap(kind), bowler: currentBowler(kind),
      });
      RES[kind] = r; renderResources(kind); renderBowlLog(kind);
    } catch { box.hidden = true; }
  }
  function renderResources(kind) {
    const r = RES[kind]; const box = $(`#${kind}-res`); if (!r || !box) return;
    box.hidden = false;
    const PH = { pp: "powerplay", mid: "middle", death: "death" };
    const nextPh = r.phase; const fmtSr = (v) => (v == null ? "–" : Math.round(v));
    let mu = box.querySelector(".mu-wrap");
    if (!mu) { mu = document.createElement("div"); mu.className = "mu-wrap"; box.querySelector(".res-cols").before(mu); }
    mu.innerHTML = matchupHtml(r);
    box.querySelector(".res-note").textContent = r.order_guessed ? "Batting order guessed from usual positions"
      : r.order_set && !(creaseOf(kind === "first" ? "bat" : "chase") || []).length ? "Using your batting order"
      : r.order_set ? "Using your “At the crease” batters, then your batting order" : "Using your “At the crease” batters";
    box.querySelector('[data-res-title="bat"]').innerHTML = `${esc(r.batting_team)} batting <small class="muted">${r.out.length ? `out: ${esc(r.out.map(shortName).join(", "))}` : ""}</small>`;
    const later = r.batters.filter((b) => b.status === "later");
    box.querySelector('[data-res-list="bat"]').innerHTML = r.batters.filter((b) => b.status !== "later").map((b) => `
      <li class="res-row ${b.status}">
        <span class="res-status">${b.status === "in" ? "in" : b.status === "next" ? "next" : "later"}</span>
        <span class="res-main"><b>${esc(b.name)}</b>${b.tags.map((t) => `<i class="res-tag">${esc(t)}</i>`).join("")}
          <small>SR ${fmtSr(b.career_sr)} career · ${b.form_sr != null ? `${fmtSr(b.form_sr)} last ${b.form_innings}` : "no recent innings"}${b.boundary_pct != null ? ` · ${b.boundary_pct}% boundaries` : ""}</small></span>
        <span class="res-num" title="Strike rate in the ${PH[nextPh]} overs">${fmtSr(b.phase_sr[nextPh])}<small>${PH[nextPh]} SR</small></span>
      </li>`).join("") + (later.length ? `<li class="res-later">Later: ${later.map((b) => `<b>${esc(shortName(b.name))}</b> ${b.career_sr != null ? `SR ${fmtSr(b.career_sr)}` : "(no record)"}`).join(" · ")}</li>` : "")
      || `<li class="muted">Nobody left to bat.</li>`;
    box.querySelector('[data-res-title="bowl"]').innerHTML = `${esc(r.fielding_team)} bowling <small class="muted">${r.tracked ? `overs left from your log` : "tap “Who bowled?” to count overs"}</small>`;
    const econ = (v) => (v == null ? "–" : v.toFixed(1));
    box.querySelector('[data-res-list="bowl"]').innerHTML = r.bowlers.map((b) => {
      const left = b.left != null ? b.left / 6 : null;
      return `<li class="res-row${left === 0 ? " done" : ""}">
        <span class="res-status">${left != null ? `${Number.isInteger(left) ? left : left.toFixed(1)}<small>ov left</small>` : "–"}</span>
        <span class="res-main"><b>${esc(b.name)}</b>${b.tags.map((t) => `<i class="res-tag">${esc(t)}</i>`).join("")}
          <small>Econ ${econ(b.career_econ)} career · ${b.form_econ != null ? `${econ(b.form_econ)} last ${b.form_spells} (${b.form_wkts} wkts)` : "no recent spells"} · death ${econ(b.phase_econ.death)}</small></span>
        <span class="res-num" title="Economy in the ${PH[nextPh]} overs">${econ(b.phase_econ[nextPh])}<small>${PH[nextPh]} econ</small></span>
      </li>`;
    }).join("") || `<li class="muted">No bowling records for this XI.</li>`;
  }
  function bindResources() {
    document.addEventListener("click", (e) => {
      const chip = e.target.closest?.("[data-bowl]"); const undo = e.target.closest?.("[data-bowl-undo]");
      const kind = (chip || undo)?.closest("[data-bowl-log]")?.dataset.bowlLog; if (!kind) return;
      if (chip) logBowler(kind, chip.dataset.bowl);
      else { const list = getLog(kind); list.pop(); store.set(inningsKey(kind), list); renderBowlLog(kind); scheduleResources(kind, 50); }
    });
    document.addEventListener("change", (e) => {
      const sel = e.target.closest?.("[data-bowl-other]"); if (!sel || !sel.value) return;
      logBowler(sel.closest("[data-bowl-log]").dataset.bowlLog, sel.value);
    });
  }

  // ------------------------------------------------------------------ phase tracker: ahead or behind par, phase by phase
  // Par curve from real innings since 2023 (scripts/phase_par.py): share of the total scored and wickets down after each
  // over. First innings: scaled to the par in use (your own par / pitch included). Chase: scaled to the target, so it
  // shows what being "on track" looks like.
  let PHASE_PAR = null;
  async function loadPhasePar() { try { PHASE_PAR = await api("/api/phase-par"); } catch { PHASE_PAR = null; } }
  function phaseGroup() {
    const key = state.format === "odi" ? "odi" : state.mode === "ipl" ? "ipl" : "t20i";
    return PHASE_PAR?.groups?.[key] || null;
  }
  function curveAt(arr, balls) {
    const k = Math.min(arr.length - 1, Math.floor(balls / 6)); const frac = (balls % 6) / 6;
    return k >= arr.length - 1 ? arr[arr.length - 1] : arr[k] + (arr[k + 1] - arr[k]) * frac;
  }
  function renderPhaseTracker(kind) {
    const box = $(`#${kind}-phases`); if (!box) return;
    const g = phaseGroup();
    let base, runs, wkts, balls, tl, team, goal;
    if (kind === "first") {
      const r = state.lastFirst; if (!r) { box.hidden = true; return; }
      const inp = r.input;
      base = inp.par; runs = inp.runs; wkts = inp.wickets; tl = first.timeline || []; team = esc(r.batting_team);
      balls = Math.round(Math.floor(inp.overs) * 6 + Math.round((inp.overs % 1) * 10)); goal = `par ${base}`;
    } else {
      const r = state.lastChase; const e = r?.equation;
      if (!e || r.status !== "live") { box.hidden = true; return; }
      base = e.target; runs = e.runs; wkts = e.wickets; balls = e.balls; tl = chase.timeline || []; team = esc(r.chasing_team);
      goal = `the target of ${base}`;
    }
    if (!g || !base) { box.hidden = true; return; }
    box.hidden = false;
    const phases = PHASE_PAR.phases[g.fam];
    const parR = (b) => Math.round(base * curveAt(g.share, b));
    const parW = (b) => curveAt(g.wkts, b);
    const wTxt = (w) => (Math.round(w * 2) / 2).toString().replace(".5", "½");  // nearest half wicket
    const done = balls >= maxBalls() || wkts >= 10;
    box.querySelector(".phases-src").textContent = `${g.innings} ${state.format === "odi" ? "ODI" : state.mode === "ipl" ? "IPL" : "T20I"} innings since ${PHASE_PAR.since.slice(0, 4)}`;
    // headline: where they stand now against the curve
    const head = box.querySelector(".phases-headline");
    if (balls === 0) {
      head.innerHTML = kind === "first"
        ? `Phase par for a total of <b>${base}</b>: ${phases.map(([n, , end]) => `${n.toLowerCase()} ${parR(end * 6)}/${wTxt(parW(end * 6))}`).join(" → ")}.`
        : `To chase <b>${base}</b> on a normal innings path: ${phases.map(([n, , end]) => `${n.toLowerCase()} ${parR(end * 6)}/${wTxt(parW(end * 6))}`).join(" → ")}.`;
    } else {
      const pr = parR(balls), pw = parW(balls); const dr = runs - pr; const dw = pw - wkts;  // dw > 0: fewer wickets down than par
      const runBit = Math.abs(dr) <= 3 ? "<b>right on par</b> for runs" : `<b class="${dr > 0 ? "ahead" : "behind"}">${Math.abs(dr)} runs ${dr > 0 ? "ahead" : "behind"}</b>`;
      const wBit = Math.abs(dw) < 0.75 ? "about par for wickets" : `<b class="${dw > 0 ? "ahead" : "behind"}">${Math.abs(Math.round(dw))} wicket${Math.abs(Math.round(dw)) === 1 ? "" : "s"} ${dw > 0 ? "better" : "worse"}</b> than par`;
      head.innerHTML = `${team} ${runs}/${wkts} after ${ovs(balls)}. ${kind === "first" ? "Phase par (by overs, before allowing for wickets)" : `On track for ${base} (by overs, before allowing for wickets)`} here is <b>${pr}/${wTxt(pw)}</b>:
        ${runBit}, ${wBit}.${done ? "" : ` (${goal}; innings are slower in the middle and fastest at the death, so this isn't a straight line.)`}`;
    }
    // one card per phase
    const pointAt = (b) => (b === balls ? { runs, wickets: wkts } : tl.find((p) => p.balls === b));
    box.querySelector(".phase-cols").innerHTML = phases.map(([name, from, to]) => {
      const startB = (from - 1) * 6, endB = to * 6;
      const parEnd = `${parR(endB)}/${wTxt(parW(endB))}`; const parPhase = parR(endB) - parR(startB);
      let state2, body;
      if (balls >= endB || (done && balls > startB)) {
        const endPt = pointAt(Math.min(endB, balls)); const startPt = startB === 0 ? { runs: 0, wickets: 0 } : pointAt(startB);
        state2 = "past";
        if (endPt) {
          const d = endPt.runs - parR(Math.min(endB, balls));
          const inPhase = startPt ? endPt.runs - startPt.runs : null;
          body = `<b class="big">${endPt.runs}/${endPt.wickets}</b><span>at the end · par ${parEnd}</span>
            <span class="pill-diff ${d >= 0 ? "ahead" : "behind"}">${d >= 0 ? "+" : "−"}${Math.abs(d)} runs</span>
            ${inPhase != null ? `<small>${inPhase} scored in the phase (par ${parPhase})${startPt ? `, ${endPt.wickets - startPt.wickets} wkt${endPt.wickets - startPt.wickets === 1 ? "" : "s"}` : ""}</small>` : ""}`;
        } else body = `<b class="big">–</b><span>par ${parEnd}</span><small>Score at the end of this phase wasn't recorded</small>`;
      } else if (balls > startB) {
        state2 = "now";
        const prog = (balls - startB) / (endB - startB);
        const needEnd = parR(endB) - runs; const left = endB - balls;
        body = `<b class="big">${runs}/${wkts}</b><span>now · par here ${parR(balls)}/${wTxt(parW(balls))}</span>
          <div class="phase-prog"><i style="width:${Math.round(prog * 100)}%"></i></div>
          <small>${needEnd > 0 ? `${needEnd} more in ${ovs(left)} to finish the phase on par (${parEnd})` : `Already past the phase-end par of ${parEnd}`}</small>`;
      } else {
        state2 = "next";
        body = `<b class="big">${parPhase}</b><span>par runs in the phase</span><small>Par at the end: ${parEnd}${kind === "chase" ? " to stay on track" : ""}</small>`;
      }
      return `<div class="phase ${state2}"><div class="phase-name">${name}<small>overs ${from}–${to}</small></div>${body}</div>`;
    }).join("");
  }

  // ------------------------------------------------------------------ "Ask why": plain-English answers from the app's own numbers
  // Every number comes from the model (what-ifs are extra predictions that aren't saved); no AI service, works offline.
  const WHY_QS = {
    first: [["why", "Why this %?"], ["heading", "Where is it heading?"], ["even", "What total makes it 50/50?"]],
    chase: [["why", "Why this %?"], ["change", "Why did it change?"], ["story", "How has the chase gone?"]],
  };
  const whyOpen = { first: null, chase: null };
  let whySeq = 0;
  const pts = (p) => `${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(1)} pts`;
  const pct0 = (p) => `${Math.round(p)}%`;
  const overText = (balls) => String(oversText(balls)).replace(/\.0$/, "");
  const ovs = (balls) => { const t = overText(balls); return `${t} over${t === "1" ? "" : "s"}`; };
  const atText = (pt) => (pt.balls ? `${pt.runs}/${pt.wickets} after ${ovs(pt.balls)}` : "the start");
  const signed = (n) => `${n >= 0 ? "+" : "−"}${Math.abs(n)}`;
  const runsWord = (n) => `${n} run${n === 1 ? "" : "s"}`;

  function renderWhy(kind, available) {
    const box = $(`#${kind}-why`); if (!box) return;
    box.hidden = !available; if (!available) return;
    box.querySelector(".why-qs").innerHTML = WHY_QS[kind].map(([k, label]) =>
      `<button type="button" class="chip-btn why-q${whyOpen[kind] === k ? " on" : ""}" data-why-q="${k}">${label}</button>`).join("");
    const open = whyOpen[kind];
    if (!open) return;
    // quick answers follow the score live; the ones that ask the model several what-ifs wait for a tap
    if (["why", "change", "story"].includes(open)) answerWhy(kind, open);
    else box.querySelector(".why-answer").innerHTML += `<p class="why-stale">The score has changed. <button type="button" class="link-btn" data-why-q="${open}">Update this answer</button></p>`;
  }

  async function answerWhy(kind, q) {
    const box = $(`#${kind}-why`); const out = box.querySelector(".why-answer");
    whyOpen[kind] = q;
    box.querySelectorAll(".why-q").forEach((b) => b.classList.toggle("on", b.dataset.whyQ === q));
    out.hidden = false;
    const seq = ++whySeq;
    try {
      const fn = kind === "first" ? whyFirst : whyChase;
      const html = await fn(q, (msg) => { if (seq === whySeq) out.innerHTML = `<p class="muted">${msg}</p>`; });
      if (seq === whySeq) out.innerHTML = html;
    } catch (err) { if (seq === whySeq) out.innerHTML = `<p class="muted">Couldn't work that out (${esc(err.message)}).</p>`; }
  }

  // assumed wickets at the end of the innings, for "if they finish on X" questions (stated in the answer)
  const endWickets = (w, ballsLeft) => Math.min(9, w + Math.round((10 - w) * 0.55 * ballsLeft / maxBalls()));
  async function firstAt(runs, wickets, balls) {
    const r = await api("/api/predict", { ...payload(false), runs, wickets, overs: Number(oversText(balls)) });
    return r.batting_pct;
  }

  async function whyFirst(q, progress) {
    const r = state.lastFirst; if (!r) return "";
    const d = r.details || {}; const f = d.factors || {}; const inp = r.input;
    const bat = esc(r.batting_team); const chs = esc(r.chasing_team);
    const balls = Math.round(Math.floor(inp.overs) * 6 + Math.round((inp.overs % 1) * 10));
    const left = maxBalls() - balls; const over = balls >= maxBalls();
    if (q === "why") {
      const parts = [];
      const diff = inp.runs - (d.par ?? inp.par);
      if (f.score_vs_par != null) parts.push([f.score_vs_par, balls === 0
        ? `<b>Venue par</b>: no ball bowled yet, so this is just the ground's par of ${inp.par}`
        : over ? `<b>Total vs par</b>: ${inp.runs} against a par of ${inp.par} here (${signed(diff)})`
        : `<b>Score vs par</b>: ${inp.runs}/${inp.wickets} after ${ovs(balls)}, where the model's straight-line par is about ${d.par} (${signed(diff)} runs, ${10 - inp.wickets} wickets in hand)`]);
      if (f.team_ratings != null) parts.push([f.team_ratings, `<b>Team ratings</b>: Elo ${d.bat_elo ?? "–"} (${bat}) v ${d.chase_elo ?? "–"} (${chs}), built from past results`]);
      if (f.playing_xi != null) parts.push([f.playing_xi, `<b>Playing XIs</b>: career batting and bowling records of the 22 (or 24) players picked`]);
      parts.sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]));
      const sum = parts.reduce((s, p) => s + p[0], 0); const rest = (r.batting_pct - 50) - sum;
      const mine = [];
      if (state.par) mine.push(`your own par of ${state.par} (the model's is ${modelPar()})`);
      if (r.conditions?.pitch) mine.push(`a ${esc(r.conditions.pitch.label.toLowerCase())} pitch`);
      if (r.conditions?.dew) mine.push(esc(r.conditions.dew.label.toLowerCase()));
      const top = parts[0];
      return `<p><b class="ans">${bat} ${pct0(r.batting_pct)}</b> · ${chs} ${pct0(r.chasing_pct)}. Starting from an even 50–50, here's what moved it (points toward ${bat}):</p>
        <ul class="why-list">${parts.map(([p, t]) => `<li><span class="why-pts ${p >= 0 ? "up" : "down"}">${pts(p)}</span><span>${t}</span></li>`).join("")}
        ${Math.abs(rest) >= 1 ? `<li><span class="why-pts ${rest >= 0 ? "up" : "down"}">${pts(rest)}</span><span><b>How these combine</b>: the model weighs them together (for example, runs matter more with wickets in hand)</span></li>` : ""}</ul>
        <p>${top && Math.abs(top[0]) >= 1 ? `The biggest reason is <b class="ans">${top[1].match(/<b>(.*?)<\/b>/)[1].toLowerCase()}</b> (${pts(top[0])}).` : "No single reason dominates: it's close on every count."}
        ${mine.length ? ` Your inputs are included: ${mine.join(", ")}.` : ""}</p>`;
    }
    const p = r.projection;
    if (q === "heading") {
      if (over) return `<p>The innings is over: <b>${inp.runs}</b> against a par of ${inp.par} here (${signed(inp.runs - inp.par)}). ${bat} have <b>${pct0(r.batting_pct)}</b> to defend it.</p>`;
      if (!p) return `<p class="muted">There's no score projection for this match.</p>`;
      progress("Asking the model about each finish…");
      const w = endWickets(inp.wickets, left);
      const finishes = [...new Set([p.low, p.mid, p.high])];
      const res = [];
      for (const t of finishes) res.push([t, await firstAt(t, w, maxBalls())]);
      const vsPar = p.mid - p.par;
      return `<p>Likely finish <b class="ans">${p.mid}</b> (80% range ${p.low}–${p.high}). At the current rate it would be ${p.current_rate}; par here is ${p.par},
        so the middle of the range is <b>${Math.abs(vsPar) <= 5 ? "about a par score" : vsPar > 0 ? `${vsPar} above par` : `${-vsPar} below par`}</b>.</p>
        <ul class="why-list">${res.map(([t, b]) => `<li><span class="why-pts ${b >= 50 ? "up" : "down"}">${pct0(b)}</span><span>If they finish on <b>${t}</b>${t === p.low ? " (a poor finish)" : t === p.high ? " (a strong finish)" : " (most likely)"}: ${bat} ${pct0(b)} to defend it</span></li>`).join("")}</ul>
        <p class="muted small">Assumes about ${w} wickets down at the end. Win % from the same model, asked “what if”.</p>`;
    }
    if (q === "even") {
      progress("Searching for the coin-flip total…");
      const w = over ? inp.wickets : endWickets(inp.wickets, left);
      let lo = Math.max(over ? 40 : inp.runs, 40), hi = Math.max(lo + 20, (inp.par || 170) + 140);
      const pLo = await firstAt(lo, w, maxBalls()); const pHi = await firstAt(hi, w, maxBalls());
      if (pLo >= 50) return `<p>${bat} are favourites at the end even on <b>${lo}</b> (${pct0(pLo)}), so almost any finish from here keeps them ahead.</p>`;
      if (pHi < 50) return `<p>Even <b>${hi}</b> would leave ${bat} at ${pct0(pHi)}. ${chs} are strong favourites whatever happens.</p>`;
      while (hi - lo > 2) {
        const mid = Math.round((lo + hi) / 2);
        if ((await firstAt(mid, w, maxBalls())) >= 50) hi = mid; else lo = mid;
      }
      const t = hi;
      if (over) return `<p>A total of about <b>${t}</b> would have made it a coin flip (par here ${inp.par}). ${bat} made <b>${inp.runs}</b>, ${inp.runs >= t ? `${inp.runs - t} more than that` : `${t - inp.runs} short of it`}.</p>`;
      const need = t - inp.runs; const rr = (need * 6 / Math.max(1, left)).toFixed(1);
      const crr = balls ? (inp.runs * 6 / balls).toFixed(1) : null;
      return `<p>About <b class="ans">${t}</b> makes it 50/50 (par here ${inp.par}).</p>
        <p>From ${inp.runs}/${inp.wickets} after ${ovs(balls)}, that's <b>${runsWord(need)} off ${left} balls</b>: ${rr} an over${crr ? ` (they're scoring ${crr} so far)` : ""}.
        Anything above it and ${bat} are favourites; below it, ${chs}.</p>
        <p class="muted small">Assumes about ${w} wickets down at the end. Found by asking the model “what if” at different totals.</p>`;
    }
    return "";
  }

  async function whyChase(q) {
    const r = state.lastChase; if (!r || !r.equation) return "";
    const e = r.equation; const chs = esc(r.chasing_team); const bat = esc(r.batting_team);
    if (q === "why") {
      if (r.status !== "live") return `<p>${esc(r.verdict)}.</p>`;
      const f = r.factors || {}; const gap = r.chase_pct - r.simple_pct;
      const known = (f.team_ratings || 0) + (f.playing_xi || 0); const rest = gap - known;
      const tvp = r.par ? (e.target - 1) - r.par : null;
      const list = [];
      if (f.team_ratings != null) list.push([f.team_ratings, `<b>Team ratings</b>: Elo ${r.chase_elo ?? "–"} (${chs}) v ${r.bat_elo ?? "–"} (${bat})`]);
      if (f.playing_xi != null) list.push([f.playing_xi, `<b>Playing XIs</b>: career records of both sides`]);
      if (Math.abs(rest) >= 0.5) list.push([rest, `<b>The rest of the picture</b>: ${tvp != null ? `a target of ${e.target} is ${Math.abs(tvp) <= 5 ? "about par" : `${Math.abs(tvp)} ${tvp > 0 ? "above" : "below"} par`} (${r.par}) at this ground, ` : ""}who's at the crease and still to come, the venue and format`]);
      list.sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]));
      return `<p>${chs} need <b>${e.runs_needed} off ${e.balls_left} balls</b> with ${e.wickets_in_hand} wickets left: ${e.required_rate} an over (${e.current_rate} so far).</p>
        <p>The equation alone (runs, balls, wickets) gives ${chs} <b>${pct0(r.simple_pct)}</b>, about what a TV predictor would say. The model says <b class="ans">${pct0(r.chase_pct)}</b> (${pts(gap)}):</p>
        <ul class="why-list">${list.map(([p, t]) => `<li><span class="why-pts ${p >= 0 ? "up" : "down"}">${pts(p)}</span><span>${t}</span></li>`).join("")}</ul>
        <p class="muted small">Points are toward ${chs}. For the next ball and next over, see “What they need” above.</p>`;
    }
    const tl = chase.timeline || [];
    if (q === "change") {
      if (tl.length < 2) return `<p>This is the first update of the chase. Tap the balls as they happen and ask again to see what moved it.</p>`;
      const a = tl[tl.length - 2], b = tl[tl.length - 1];
      const db = b.balls - a.balls, dr = b.runs - a.runs, dw = b.wickets - a.wickets, dp = b.pct - a.pct;
      const rr = (runs, balls) => (maxBalls() - balls > 0 ? ((e.target - runs) * 6 / (maxBalls() - balls)).toFixed(2) : "–");
      const fast = db > 0 && dr / db > (e.target - a.runs) / Math.max(1, maxBalls() - a.balls);
      const why = dw > 0 ? `the wicket${dw > 1 ? "s" : ""} hurt more than the runs helped` : fast ? "they scored faster than the rate they need" : db > 0 ? "they scored slower than the rate they need, so the asking rate went up" : "the score was corrected";
      return `<p>Since ${ovs(a.balls)}: <b>${runsWord(dr)}</b> off ${db} ball${db === 1 ? "" : "s"}${dw > 0 ? `, <b>${dw} wicket${dw > 1 ? "s" : ""}</b>` : ", no wicket"}.</p>
        <ul class="why-list"><li><span class="why-pts ${dp >= 0 ? "up" : "down"}">${pts(dp)}</span><span>${chs}: ${pct0(a.pct)} → <b class="ans">${pct0(b.pct)}</b></span></li>
        <li><span class="why-pts neutral">rate</span><span>Required rate ${rr(a.runs, a.balls)} → <b>${rr(b.runs, b.balls)}</b> an over</span></li></ul>
        <p>${Math.abs(dp) < 0.5 ? "Hardly any change: that's about what was expected." : `It ${dp > 0 ? "went up" : "went down"} because ${why}.`}</p>`;
    }
    if (q === "story") {
      if (tl.length < 2) return `<p>The chase has only just started. Ask again after a few overs.</p>`;
      const start = tl[0], now = tl[tl.length - 1];
      const hiP = tl.reduce((m, p) => (p.pct > m.pct ? p : m), tl[0]); const loP = tl.reduce((m, p) => (p.pct < m.pct ? p : m), tl[0]);
      let big = null;
      for (let i = 1; i < tl.length; i++) {
        const d2 = tl[i].pct - tl[i - 1].pct;
        if (!big || Math.abs(d2) > Math.abs(big.d)) big = { d: d2, a: tl[i - 1], b: tl[i] };
      }
      return `<ul class="why-list">
        <li><span class="why-pts neutral">start</span><span>${chs} began on <b>${pct0(start.pct)}</b> chasing ${e.target}</span></li>
        <li><span class="why-pts up">high</span><span>Best moment: <b>${pct0(hiP.pct)}</b> at ${atText(hiP)}</span></li>
        <li><span class="why-pts down">low</span><span>Worst moment: <b>${pct0(loP.pct)}</b> at ${atText(loP)}</span></li>
        ${big && Math.abs(big.d) >= 1 ? `<li><span class="why-pts ${big.d >= 0 ? "up" : "down"}">${pts(big.d)}</span><span>Biggest swing: ${overText(big.a.balls)} → ${ovs(big.b.balls)},
          ${runsWord(big.b.runs - big.a.runs)}${big.b.wickets > big.a.wickets ? ` and ${big.b.wickets - big.a.wickets} wicket${big.b.wickets - big.a.wickets > 1 ? "s" : ""}` : ""}</span></li>` : ""}
        <li><span class="why-pts ${now.pct >= start.pct ? "up" : "down"}">now</span><span><b>${pct0(now.pct)}</b> at ${atText(now)} (${pts(now.pct - start.pct)} since the start)</span></li></ul>`;
    }
    return "";
  }

  function bindWhy() {
    document.addEventListener("click", (ev) => {
      const b = ev.target.closest?.("[data-why-q]"); if (!b) return;
      const kind = b.closest("[data-why]")?.dataset.why; if (!kind) return;
      const q = b.dataset.whyQ;
      if (whyOpen[kind] === q && b.classList.contains("why-q")) {  // tap the open question again to close it
        whyOpen[kind] = null; b.classList.remove("on"); $(`#${kind}-why .why-answer`).hidden = true; return;
      }
      answerWhy(kind, q);
    });
  }

  // ------------------------------------------------------------------ live chase
  const chase = { target: 181, runs: 0, wickets: 0, balls: 0, undo: [], timeline: [], timer: null, last: null, seq: 0 };
  const chaseKey = () => `chase:${state.mode}:${state.format}:${state.batting}:${state.chasing}:${chase.target}`;
  function saveChase() { store.set(chaseKey(), { runs: chase.runs, wickets: chase.wickets, balls: chase.balls, timeline: chase.timeline }); }
  function restoreChase() {
    const saved = store.get(chaseKey(), null);
    Object.assign(chase, saved ? { runs: saved.runs, wickets: saved.wickets, balls: saved.balls, timeline: saved.timeline || [] } : { runs: 0, wickets: 0, balls: 0, timeline: [] });
    chase.undo = []; chase.loadedKey = chaseKey();
  }
  function syncChase() {
    chase.target = Math.max(1, Math.min(800, Math.round(chase.target || 1)));
    chase.runs = Math.max(0, Math.min(800, Math.round(chase.runs || 0)));
    chase.wickets = Math.max(0, Math.min(10, Math.round(chase.wickets || 0)));
    chase.balls = Math.max(0, Math.min(maxBalls(), chase.balls));
    $("#target-input").value = chase.target; $("#c-runs-input").value = chase.runs;
    $("#c-wickets-input").value = chase.wickets; $("#c-overs-input").value = oversText(chase.balls);
    $("#chase-team-note").textContent = `${team(state.chasing).name} chasing ${team(state.batting).name}`;
    renderFlow();
  }
  function snapshot() { chase.undo.push({ runs: chase.runs, wickets: chase.wickets, balls: chase.balls }); if (chase.undo.length > 300) chase.undo.shift(); }
  function addBall(kind) {
    if (kind === "undo") {
      const prev = chase.undo.pop(); if (!prev) { toast("Nothing to undo"); return; }
      Object.assign(chase, prev);
    } else {
      if (chase.wickets >= 10 || chase.balls >= maxBalls() || chase.runs >= chase.target) { toast("This chase is already finished. Press “New chase” to start again."); return; }
      snapshot();
      if (kind === "wd" || kind === "nb") chase.runs += 1;
      else if (kind === "W") { chase.wickets += 1; chase.balls += 1; }
      else { chase.runs += Number(kind); chase.balls += 1; }
      celebrate(kind, $("#chase-step .ball-pad"));
    }
    tapAnim($(`#chase-step [data-ball="${kind}"]`));
    syncChase(); scheduleChase(0);
  }
  function tapAnim(btn) { if (btn) { btn.classList.remove("tapped"); void btn.offsetWidth; btn.classList.add("tapped"); } }
  function celebrate(kind, pad) {
    if (kind === "4") burst("FOUR!", "four", pad); else if (kind === "6") burst("SIX!", "six", pad); else if (kind === "W") burst("OUT!", "wkt", pad);
  }
  function burst(text, kind, pad) {  // a short "FOUR!" / "SIX!" / "OUT!" pop above the ball buttons
    const el = document.createElement("div");
    el.className = `burst ${kind}`; el.textContent = text; el.setAttribute("aria-hidden", "true");
    (pad || $(".ball-pad")).appendChild(el); setTimeout(() => el.remove(), 950);
  }

  // ------------------------------------------------------------------ first innings, ball by ball
  const first = { undo: [], timeline: [], loadedKey: null, timer: null };
  const firstKey = () => `first:${state.mode}:${state.format}:${state.batting}:${state.chasing}`;
  function saveFirst() { store.set(firstKey(), { runs: state.runs, wickets: state.wickets, balls: state.balls, timeline: first.timeline }); }
  function restoreFirst() {
    const saved = store.get(firstKey(), null);
    first.timeline = saved?.timeline || []; first.undo = []; first.loadedKey = firstKey();
    if (saved && first.timeline.length) Object.assign(state, { runs: saved.runs, wickets: saved.wickets, balls: saved.balls });
  }
  function recordFirstPoint(r, at, latest = true) {
    if (first.loadedKey !== firstKey()) restoreFirst();
    if (latest) first.timeline = first.timeline.filter((p) => p.balls < at.balls);  // undo removes later points
    first.timeline = first.timeline.filter((p) => p.balls !== at.balls);
    first.timeline.push({ balls: at.balls, pct: r.batting_pct, wickets: at.wickets, runs: at.runs });
    first.timeline.sort((a, b) => a.balls - b.balls);
    saveFirst();
  }
  function renderFirstWorm(r) {
    const show = first.timeline.length >= 2;
    $("#r-worm-wrap").hidden = !show;
    if (!show) return;
    drawWorm($("#r-worm"), first.timeline, r.batting_code, r.batting_team, "first", "");
    const tl = first.timeline; const prev = tl[tl.length - 2]; const swing = tl[tl.length - 1].pct - prev.pct;
    $("#r-swing").textContent = Math.abs(swing) >= 0.5 ? `${swing > 0 ? "▲" : "▼"} ${Math.abs(swing).toFixed(1)} pts for ${r.batting_team} since last update` : "";
  }
  function addFirstBall(kind) {
    if (kind === "undo") {
      const prev = first.undo.pop(); if (!prev) { toast("Nothing to undo"); return; }
      Object.assign(state, prev);
    } else {
      if (state.wickets >= 10 || state.balls >= maxBalls()) { toast("The innings is over. Press “New innings” to start again, or switch to Live chase."); return; }
      first.undo.push({ runs: state.runs, wickets: state.wickets, balls: state.balls });
      if (kind === "wd" || kind === "nb") state.runs += 1;
      else if (kind === "W") { state.wickets += 1; state.balls += 1; }
      else { state.runs += Number(kind); state.balls += 1; }
      celebrate(kind, $("#first-ball-pad"));
    }
    tapAnim($(`#first-ball-pad [data-fball="${kind}"]`));
    syncScore();
    clearTimeout(first.timer); first.timer = setTimeout(() => predict(false, true), 0);
    if (state.wickets >= 10 || state.balls >= maxBalls()) {
      chase.target = state.runs + 1;  // ready for the chase
      toast(`Innings over: target ${chase.target}. Switch to Live chase to follow it.`);
    }
  }
  function bindFirstLive() {
    $$("#first-ball-pad [data-fball]").forEach((b) => b.addEventListener("click", () => addFirstBall(b.dataset.fball)));
    $("#first-live-start").addEventListener("click", () => {
      Object.assign(state, { runs: 0, wickets: 0, balls: 0 }); first.undo = []; first.timeline = []; first.loadedKey = firstKey();
      saveFirst(); syncScore(); predict(false, true); toast("New innings: tap a button for every ball");
    });
  }
  function scheduleChase(delay = 250) { clearTimeout(chase.timer); chase.timer = setTimeout(() => predictChase(false), delay); }

  async function predictChase(save) {
    showError("");
    if (state.batting === state.chasing) { showError("Pick two different teams."); return; }
    const problem = xiProblem(); if (problem) { showError(problem); return; }
    const seq = ++chase.seq;
    const at = { runs: chase.runs, wickets: chase.wickets, balls: chase.balls };  // the score this update is for
    try {
      const r = await api("/api/chase", {
        mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, venue: state.venue,
        par: state.par || null, target: chase.target, runs: at.runs, wickets: at.wickets, overs: Number(oversText(at.balls)),
        ...xiPayload(), save,
      });
      // timeline: one point per ball count, in ball order; going back (undo) removes later points
      if (seq === chase.seq) chase.timeline = chase.timeline.filter((p) => p.balls < at.balls);
      chase.timeline = chase.timeline.filter((p) => p.balls !== at.balls);
      chase.timeline.push({ balls: at.balls, pct: r.chase_pct, wickets: at.wickets, runs: at.runs });
      chase.timeline.sort((a, b) => a.balls - b.balls);
      saveChase();
      if (seq !== chase.seq) return;  // a newer ball was tapped while this was on its way: show only the latest
      saveChase(); chase.last = r; renderChase(r);
      if (save) toast("Saved to History");
      loadNeed(r, at, seq);
    } catch (err) { showError(`Chase update failed: ${err.message}`); }
  }

  // ---- "What they need": win chance after the next ball / next over, for different outcomes
  async function loadNeed(r, at, seq) {
    if (r.status !== "live") { $("#c-need").hidden = true; return; }
    try {
      const s = await api("/api/chase/scenarios", {
        mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, venue: state.venue,
        par: state.par || null, target: chase.target, runs: at.runs, wickets: at.wickets, overs: Number(oversText(at.balls)),
        ...xiPayload(),
      });
      if (seq !== chase.seq || !s.live) { if (!s.live) $("#c-need").hidden = true; return; }
      renderNeed(s, r);
    } catch { $("#c-need").hidden = true; }
  }
  function renderNeed(s, r) {
    const team = r.chasing_team; const n = s.over_balls; const span = n === 6 ? "the next over" : `the last ${n} ball${n === 1 ? "" : "s"}`;
    const p0 = s.grid["0"][0];
    let headline;
    if (s.runs_for_50 == null) headline = `Even ${s.grid_runs[s.grid_runs.length - 1]} off ${span} wouldn't lift ${esc(team)} to 50%. It's a long shot from here.`;
    else if (s.runs_for_50 === 0) headline = `${esc(team)} stay favourites even after a maiden (<b>${p0}%</b>). A wicket is the danger.`;
    else if (s.runs_for_50 >= s.runs_needed) headline = `${esc(team)} need <b>${s.runs_needed}</b> off ${span} to win it.`;
    else headline = `Score <b>${s.runs_for_50}</b> off ${span} without losing a wicket and ${esc(team)} are back to <b>50%+</b> (now ${s.now}%).`;
    $("#need-headline").innerHTML = headline;
    setStrip("chase", "need", { r50: s.runs_for_50 != null && s.runs_for_50 >= s.runs_needed ? s.runs_needed : s.runs_for_50, span: n === 6 ? "Next over" : `Last ${n} balls` });
    $("#need-balls").innerHTML = s.next_ball.map((b) => {
      const d = b.pct - s.now; const cls = Math.abs(d) < 0.5 ? "flat" : d > 0 ? "up" : "down";
      const label = b.label === "dot" ? "Dot" : b.label === "1 run" ? "Single" : b.label === "wicket" ? "Wicket" : b.label;
      const shown = b.pct >= 100 ? 100 : Math.min(99, Math.round(b.pct));  // only a winning ball shows 100%
      return `<div class="nb ${b.label === "wicket" ? "wk" : b.label === "6" ? "six" : ""}"><span>${label}</span><b>${shown}%</b>
        <small class="${cls}">${cls === "flat" ? "±0" : `${d > 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}`}</small></div>`;
    }).join("");
    $("#need-over-label").textContent = `Win chance after ${span}, by runs scored`;
    const cols = s.grid_runs.map((r2, i) => ({ r: r2, i })).filter((c) => c.r <= 24 && c.r % 4 === 0);
    const color = (p) => `hsl(${Math.round(p * 1.2)}, 62%, ${p >= 99.5 || p <= 0.5 ? 38 : 44}%)`;  // red -> amber -> green
    const markCol = s.runs_for_50 != null ? cols.find((c) => c.r >= s.runs_for_50)?.r : null;
    $("#need-grid").innerHTML = `<thead><tr><th class="rowh">Runs →</th>${cols.map((c) => `<th>${c.r}</th>`).join("")}</tr></thead><tbody>`
      + [["0", "No wicket"], ["1", "1 wicket"], ["2", "2 wickets"]].map(([w, label]) => `<tr><th class="rowh">${label}</th>${cols.map((c) => {
        const p = s.grid[w][c.i];
        return `<td class="${w === "0" && c.r === markCol ? "mark" : ""}" style="background:${color(p)}" title="${c.r} runs, ${label.toLowerCase()}: ${p}%">${Math.round(p)}</td>`;
      }).join("")}</tr>`).join("") + "</tbody>";
    $("#c-need").hidden = false;
  }

  // ---- match preview (before the first ball): batting order + ground + both ticked XIs + form -> winner, both innings
  async function matchPreview() {
    showError("");
    if (state.batting === state.chasing) { showError("Pick two different teams."); return; }
    const problem = xiProblem(); if (problem) { showError(problem); return; }
    const btn = $("#preview-btn"); btn.disabled = true; btn.classList.add("busy");
    const panel = $("#match-preview"); panel.hidden = false;
    const key = previewKey(); panel.dataset.key = key;
    $("#mp-body").innerHTML = `<div class="loading">Working out the match…</div>`;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const { runs, wickets, overs, save, ...rest } = payload(false);
      const r = await api("/api/preview", rest);
      if (panel.dataset.key !== key || previewKey() !== key) return;  // inputs changed while it was working: drop it
      renderMatchPreview(r);
    } catch (err) { $("#mp-body").innerHTML = `<p class="form-error">Preview failed: ${esc(err.message)}</p>`; }
    finally { btn.disabled = false; btn.classList.remove("busy"); }
  }
  function renderMatchPreview(r) {
    const box = $("#mp-body");
    if (!r.available) { box.innerHTML = `<p class="muted">${esc(r.reason || "No preview for this match setup.")}</p>`; return; }
    const A = r.bat, B = r.chase; const sa = teamStyle(A.code), sb = teamStyle(B.code);
    const v = venue(); const h = r.history || {}; const f = r.first; const c = r.chase_at; const rec = r.record;
    const pct = (x) => (x == null ? "–" : `${Math.round(x)}%`);
    const aPct = Math.round(A.win), bPct = 100 - aPct; const lead = r.favourite.pct;
    const word = lead < 55 ? "Too close to call" : lead < 62 ? `${esc(r.favourite.name)} are slight favourites` : lead < 75 ? `${esc(r.favourite.name)} are favourites` : `${esc(r.favourite.name)} are strong favourites`;
    const short = f && h.short_median != null ? Math.max(0, f.mid - h.short_median) : null;
    const fmtU = (r.format || "t20").toUpperCase();
    const innings = f && c ? `
      <div class="mp-orders">
        <div class="mp-order">
          <div class="mp-order-head">${badgeHTML(A.code)}<b>1st innings · ${esc(A.name)} bat</b></div>
          <div class="mp-inn"><span class="mp-k">Projected total</span>
            <b class="mp-big" style="color:${sa.c1}">${f.mid}</b><small>most likely · 8 in 10 innings land between <b>${f.low}</b> and <b>${f.high}</b> (typical miss ±${Math.round(f.typical_error || 0)} before a ball is bowled)</small></div>
        </div>
        <div class="mp-order">
          <div class="mp-order-head">${badgeHTML(B.code)}<b>2nd innings · ${esc(B.name)} chase</b></div>
          <div class="mp-inn"><span class="mp-k">If ${esc(A.name)} make ${f.mid} (target ${f.mid + 1})</span>
            <b class="mp-big" style="color:${sb.c1}">${pct(c.mid.chase_pct)}</b><small>chance ${esc(B.name)} get there.${short != null ? ` If they fall short they usually finish around <b>${short}</b> (failed chases in ${esc(h.competition)} since ${esc(h.since)} ended a median ${h.short_median} runs short).` : ""}</small></div>
          <div class="mp-sens"><span>If ${esc(A.name)} make only <b>${c.low.total}</b> → ${esc(B.name)} chase it <b>${pct(c.low.chase_pct)}</b></span>
            <span>If they make <b>${c.high.total}</b> → <b>${pct(c.high.chase_pct)}</b></span></div>
        </div>
      </div>
      <p class="muted small">The headline chance weighs every likely ${esc(A.name)} total and both XIs; the chase numbers above are for one exact total each, so they read "if they make…".</p>` : `<p class="muted">No score projection for this match setup.</p>`;
    const turn = [];
    if (rec) turn.push(`<li>Before the first ball the model picked the winner in <b>${pct(rec.pct)}</b> of ${rec.matches} unseen ${esc(rec.competition)} matches (${esc(rec.test_period || "2025–26")}): the favourite lost about <b>${Math.round(100 - rec.pct)} in 100</b>.</li>`);
    if (h.comeback?.n) turn.push(`<li>Chasing sides needing <b>${h.comeback.rate}+ an over</b> after ${h.halfway_overs} overs won <b>${h.comeback.won} of ${h.comeback.n}</b> since ${esc(h.since)}.</li>`);
    if (h.collapse?.n) turn.push(`<li>Chasing sides cruising (≤ ${h.collapse.rate} an over needed, ≤ 2 down after ${h.halfway_overs} overs) still lost <b>${h.collapse.lost} of ${h.collapse.n}</b>.</li>`);
    if (h.matches) turn.push(`<li>Since ${esc(h.since)} (${h.matches} ${esc(h.competition)} matches) the median first innings was <b>${h.first_median}</b> (half between ${h.first_q25} and ${h.first_q75}), and chasing sides won <b>${pct(h.chase_win_pct)}</b>.</li>`);
    box.innerHTML = `
      <p class="mp-sub muted"><b>${esc(A.name)}</b> bat first, <b>${esc(B.name)}</b> chase · ${esc(v.name)} · ${fmtU} · the XIs ticked above, their form and the ground's par.</p>
      <div class="mp-head">
        <div class="mp-team" style="--c1:${sa.c1}">${badgeHTML(A.code, "lg")}<b>${esc(A.name)}</b><span class="mp-pct">${aPct}%</span></div>
        <div class="mp-bar"><i style="width:${aPct}%;background:${sa.c1}"></i><i style="width:${bPct}%;background:${sb.c1}"></i></div>
        <div class="mp-team right" style="--c1:${sb.c1}"><span class="mp-pct">${bPct}%</span><b>${esc(B.name)}</b>${badgeHTML(B.code, "lg")}</div>
      </div>
      <p class="mp-verdict"><b>${word}</b>${lead >= 55 ? ` · ${pct(lead)} chance to win` : ""}. Before the first ball this is a lean: it gets much sharper once the match starts.</p>
      ${innings}
      <div class="mp-turn"><h3>Could it turn on its head?</h3><ul>${turn.join("")}</ul>
        <p class="muted small">From the model's results on matches it never saw, and straight from the match data.</p></div>`;
  }

  function renderChase(r) {
    // an answer that arrives late (you switched to First innings, or picked other teams meanwhile) is out of date: drop it
    if (state.stage !== "chase" || r.batting_code !== state.batting || r.chasing_code !== state.chasing) return;
    state.lastChase = r;
    queueMicrotask(() => { renderPhaseTracker("chase"); renderWhy("chase", !!r.equation); renderBowlLog("chase"); scheduleResources("chase"); schedulePar("chase", PG.chase ? 50 : 400); });
    $("#result-empty").hidden = true; $("#result").hidden = true; $("#chase-result").hidden = false;
    const e = r.equation; const bs = teamStyle(r.batting_code); const cs = teamStyle(r.chasing_code);
    $("#c-verdict").textContent = r.status === "live" ? r.verdict : "Result";
    paintTrust("#c-trust", r.status === "live" ? r.trust : null);
    const winnerCode = r.winner === r.chasing_team ? r.chasing_code : r.winner === r.batting_team ? r.batting_code : null;
    if (winnerCode) paintBadge($("#c-badge"), winnerCode); $("#c-badge").hidden = !winnerCode;
    setHero("chase", winnerCode, r.status === "live" ? (winnerCode === r.chasing_code ? r.chase_pct : 100 - r.chase_pct) : null);
    $("#c-winner").textContent = r.status === "live" ? r.winner : r.verdict;    $("#c-equation").innerHTML = r.status === "live"
      ? `${esc(r.chasing_team)} <b>${e.runs}/${e.wickets}</b> (${e.overs_text}) · need <b>${e.runs_needed}</b> off <b>${e.balls_left}</b> balls · RRR <b>${e.required_rate ?? "–"}</b> · CRR <b>${e.current_rate ?? "–"}</b> · <b>${e.wickets_in_hand}</b> wickets left`
      : r.status === "won" ? `${esc(r.chasing_team)} reached <b>${e.runs}/${e.wickets}</b> with <b>${e.balls_left}</b> balls and <b>${e.wickets_in_hand}</b> wickets to spare.`
      : r.status === "tied" ? `Scores level on <b>${e.runs}</b>. Super over!`
      : `${esc(r.chasing_team)} finished on <b>${e.runs}/${e.wickets}</b>, <b>${e.runs_needed - 1}</b> runs short.`;
    $("#c-bat-name").textContent = r.batting_team; $("#c-chase-name").textContent = r.chasing_team;
    const bb = $("#c-bat-bar"), cb = $("#c-chase-bar"); const batPct = 100 - r.chase_pct;
    bb.style.setProperty("--c1", bs.c1); bb.style.setProperty("--c2", bs.c2); cb.style.setProperty("--c1", cs.c1); cb.style.setProperty("--c2", cs.c2);
    bb.style.width = `${batPct}%`; cb.style.width = `${r.chase_pct}%`;
    const label = (v) => `${r.status === "live" ? Math.min(99, Math.max(1, Math.round(v))) : Math.round(v)}%`;  // live: never "100%"
    $("#c-bat-pct").textContent = batPct >= 12 ? label(batPct) : "";
    $("#c-chase-pct").textContent = r.chase_pct >= 12 ? label(r.chase_pct) : "";
    // swing since the previous update
    const tl = chase.timeline; const prev = tl.length > 1 ? tl[tl.length - 2] : null;
    const swing = prev ? r.chase_pct - prev.pct : 0;
    $("#c-swing").textContent = prev && Math.abs(swing) >= 0.5 ? `${swing > 0 ? "▲" : "▼"} ${Math.abs(swing).toFixed(1)} pts for ${r.chasing_team} since last update` : "";
    renderWorm(r);
    if (r.status === "live") {
      const toward = (pts) => {
        if (pts == null || Math.abs(pts) < 0.5) return `<span class="pill neutral">neutral</span>`;
        const s = pts > 0 ? cs : bs;
        return `<span class="pill" style="background:linear-gradient(135deg, ${s.c1}, ${s.c2})">+${Math.abs(pts).toFixed(1)} ${esc(s.code)}</span>`;
      };
      const pf = r.players_found || {};
      $("#c-factors").innerHTML = [
        [ICONS.score, "The equation", `Runs, balls and wickets alone give ${r.chasing_team} ${r.simple_pct}%`, null, `<span class="pill neutral">${r.simple_pct.toFixed(0)}%</span>`],
        [ICONS.rating, "Team ratings", `Elo ${r.bat_elo ?? "–"} (${r.batting_team}) vs ${r.chase_elo ?? "–"} (${r.chasing_team})`, r.factors.team_ratings],
        [ICONS.xi, "Playing XI records", `${pf.batting?.[0] ?? "?"}/${pf.batting?.[1] ?? "?"} and ${pf.chasing?.[0] ?? "?"}/${pf.chasing?.[1] ?? "?"} players found`, r.factors.playing_xi],
        ...(state.par ? [[ICONS.score, "Your own par (your input)", `Par ${modelPar()} → ${state.par}; the target is judged against it`, null,
          `<span class="pill neutral">par ${state.par - modelPar() >= 0 ? "+" : ""}${state.par - modelPar()}</span>`]] : []),
        ...(r.conditions?.dew ? [[ICONS.rating, `${r.conditions.dew.label} (your input)`, "Fades as the chase goes on", r.conditions.dew.chase_pts]] : []),
      ].map(([icon, title, sub, pts, pill]) => `<li><span class="factor-icon">${icon}</span><span class="factor-text"><strong>${title}</strong><span>${esc(sub)}</span></span>${pill || toward(pts)}</li>`).join("");
      $("#c-model").innerHTML = `Live chase model (<b>${esc(r.model_label)}</b>)${r.test_accuracy ? `, right <b>${(r.test_accuracy * 100).toFixed(1)}%</b> of the time across unseen 2025–26 chases` : ""}. <a href="#accuracy">See chase accuracy →</a>`;
    } else {
      $("#c-factors").innerHTML = ""; $("#c-model").innerHTML = `Press <b>New chase</b> to start another one.`;
    }
  }

  function renderWorm(r) {
    drawWorm($("#c-worm"), chase.timeline, r.chasing_code, r.chasing_team, "chase",
      "Add balls with the buttons (or update the score) and the chase's win-chance line is drawn here.");
  }

  // one chart for both innings: win chance (0–100%) of `teamCode` across the balls of the innings
  function drawWorm(el, tl, teamCode, teamName, id, emptyText) {
    // draw at the box's real pixel size so labels and wicket dots aren't stretched
    const W = Math.max(280, Math.round(el.clientWidth || 600)); const H = 170, pad = 34; const mb = maxBalls();
    if (tl.length < 2) {
      el.innerHTML = `<div class="empty-note">${emptyText}</div>`;
      if (el.nextElementSibling?.classList?.contains("moments")) el.nextElementSibling.innerHTML = "";
      return;
    }
    const x = (b) => pad + (b / mb) * (W - pad * 2); const y = (p) => 8 + (1 - p / 100) * (H - 30);
    const cs = teamStyle(teamCode);
    const pts = tl.map((p) => `${x(p.balls).toFixed(1)},${y(p.pct).toFixed(1)}`).join(" ");
    const area = `${x(tl[0].balls)},${y(0)} ${pts} ${x(tl[tl.length - 1].balls)},${y(0)}`;
    const step = state.format === "odi" ? 10 : 5;
    const ticks = Array.from({ length: Math.floor(mb / 6 / step) + 1 }, (_, i) => i * step);
    const wickets = tl.filter((p, i) => i > 0 && p.wickets > tl[i - 1].wickets);
    const last = tl[tl.length - 1];
    const momentMarks = renderMoments(el, tl, teamName, x, y);
    const glow = brightOf(cs);
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(teamName)} win chance through the innings">
      <defs><linearGradient id="wormfill-${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${glow}" stop-opacity=".32"/><stop offset="1" stop-color="${glow}" stop-opacity="0"/></linearGradient></defs>
      ${[25, 50, 75].map((g) => `<line x1="${pad}" x2="${W - pad}" y1="${y(g)}" y2="${y(g)}" stroke="rgba(255,255,255,${g === 50 ? 0.22 : 0.08})" stroke-dasharray="${g === 50 ? "5 5" : "2 4"}"/><text x="4" y="${y(g) + 3}" fill="rgba(255,255,255,.72)" font-size="10">${g}%</text>`).join("")}
      ${ticks.map((o) => `<text x="${x(o * 6)}" y="${H - 6}" fill="rgba(255,255,255,.72)" font-size="10" text-anchor="middle">${o}</text>`).join("")}
      <polygon points="${area}" fill="url(#wormfill-${id})"/>
      <polyline points="${pts}" fill="none" stroke="${glow}" stroke-width="7" stroke-linejoin="round" opacity=".28" style="filter:blur(4px)"/>
      <polyline points="${pts}" fill="none" stroke="${glow}" stroke-width="2.6" stroke-linejoin="round" vector-effect="non-scaling-stroke" style="filter:drop-shadow(0 0 4px ${glow})"/>
      ${wickets.map((p) => `<circle cx="${x(p.balls)}" cy="${y(p.pct)}" r="4.5" fill="#e5483a" stroke="#fff" stroke-width="1"><title>Wicket at ${oversText(p.balls)}: ${p.pct}%</title></circle>`).join("")}
      ${momentMarks}
      <circle cx="${x(last.balls)}" cy="${y(last.pct)}" r="11" fill="${glow}" opacity=".25" class="worm-pulse"/>
      <circle cx="${x(last.balls)}" cy="${y(last.pct)}" r="5.5" fill="#fff" stroke="${glow}" stroke-width="2" style="filter:drop-shadow(0 0 6px ${glow})"/>
    </svg>`;
  }

  function setStage(stage) {
    state.stage = stage; store.set("stage", stage);
    $$(".stage-toggle [data-stage]").forEach((b) => b.classList.toggle("active", b.dataset.stage === stage));
    $("#chase-step").hidden = stage !== "chase"; $("#first-step").hidden = stage === "chase";
    $("#predict-btn span").textContent = stage === "chase" ? "Update chase & save" : "Predict winner";
    markTabs();
    $("#predict-title").textContent = stage === "chase" ? "Will they chase it down?" : "Who's going to win?";
    $("#predict-lede").innerHTML = stage === "chase"
      ? "Set the target, then tap a button for every ball (<b>1</b>, <b>4</b>, <b>6</b>, <b>W</b>…). The win chance and the chart update instantly."
      : "Pick the teams, enter the first-innings score and press <b>Predict</b>. The model learned from thousands of real matches.";
    if (stage === "chase") {
      restoreChase(); syncChase();
      $("#result").hidden = true;
      if (state.config) predictChase(false);
    } else {
      $("#chase-result").hidden = true;
      $("#result").hidden = !state.hasResult; $("#result-empty").hidden = state.hasResult;
    }
    renderFlow();
  }

  // ------------------------------------------------------------------ match-day flow
  // One path through a match: preview -> first innings -> chase. The bars say where the match is and offer the next
  // step; starting the chase carries the target over (teams, ground and XIs are shared already).
  function flowFacts() {
    const A = team(state.batting).name, B = team(state.chasing).name;
    const firstDone = state.balls >= maxBalls() || state.wickets >= 10;
    const chaseOver = chase.runs >= chase.target || chase.wickets >= 10 || chase.balls >= maxBalls();
    return { A, B, firstDone, target: state.runs + 1, chaseOver, chaseWon: chase.runs >= chase.target,
      notStarted: state.balls === 0 && state.runs === 0 && state.wickets === 0 };
  }
  function renderFlow() {
    const steps = $("#flow-steps"), ff = $("#flow-first"), fc = $("#flow-chase");
    if (!steps || !ff || !fc || !state.config) return;
    const f = flowFacts(); const onChase = state.stage === "chase";
    const step = (key, n, label, cls) => `<button type="button" class="flow-step ${cls}" data-flow="${key}"><i>${cls.includes("done") ? "✓" : n}</i><span>${label}</span></button>`;
    steps.innerHTML = step("preview", 1, "Preview", !f.notStarted || onChase ? "done" : "now")
      + step("first", 2, "First innings", onChase || f.firstDone ? (onChase ? "done" : "done now") : f.notStarted ? "" : "now")
      + step("chase", 3, "The chase", onChase ? (f.chaseOver ? "done now" : "now") : "");
    // first innings
    if (f.notStarted) ff.innerHTML = `<span>Before the first ball. Preview the match, or tap a ball to start the innings.</span><button type="button" class="chip-btn" data-flow="preview">Preview the match</button>`;
    else if (f.firstDone) {
      const going = chase.target === f.target && chase.balls > 0;
      ff.innerHTML = `<span><b>${esc(f.A)} finished on ${state.runs}/${state.wickets}.</b> ${esc(f.B)} need ${f.target} to win.</span>
        <button type="button" class="flow-go" data-flow="start-chase">${going ? "Continue the chase" : `Start the chase: target ${f.target}`} →</button>`;
    } else ff.innerHTML = `<span>${esc(f.A)} ${state.runs}/${state.wickets} after ${oversText(state.balls)} overs. When the innings ends, the chase starts from here with the target filled in.</span>`;
    ff.classList.toggle("ready", f.firstDone);
    // the chase
    const left = maxBalls() - chase.balls; const need = chase.target - chase.runs;
    if (f.chaseOver) {
      const tie = !f.chaseWon && chase.runs === chase.target - 1 && chase.wickets < 10;
      fc.innerHTML = `<span><b>${tie ? "Scores level: a tie" : `${esc(f.chaseWon ? f.B : f.A)} won`}.</b> ${f.chaseWon ? `${esc(f.B)} chased ${chase.target} with ${left} ball${left === 1 ? "" : "s"} left` : tie ? "" : `${esc(f.B)} finished ${chase.target - 1 - chase.runs} run${chase.target - 1 - chase.runs === 1 ? "" : "s"} short`}</span>
        <button type="button" class="flow-go" data-flow="new-match">New match →</button>`;
    } else if (chase.balls === 0) {
      fc.innerHTML = `<span>${esc(f.B)} need <b>${chase.target}</b>. Tap a button for every ball.</span>${f.firstDone && chase.target !== f.target
        ? `<button type="button" class="chip-btn" data-flow="use-target">Use ${esc(f.A)}'s ${state.runs}: target ${f.target}</button>` : ""}`;
    } else fc.innerHTML = `<span>${esc(f.B)} need <b>${need}</b> off ${left} ball${left === 1 ? "" : "s"} with ${10 - chase.wickets} wicket${chase.wickets === 9 ? "" : "s"} in hand.</span>`;
    fc.classList.toggle("ready", f.chaseOver);
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest?.("[data-flow]"); if (!b) return;
    const f = flowFacts(); const go = b.dataset.flow;
    if (go === "preview") { if (state.stage !== "first") setStage("first"); matchPreview(); return; }
    if (go === "first") { setStage("first"); return; }
    if (go === "chase") { setStage("chase"); return; }
    if (go === "use-target") { chase.target = f.target; restoreChase(); syncChase(); scheduleChase(0); toast(`Target set to ${chase.target}`); return; }
    if (go === "start-chase") {
      chase.target = f.target;
      const saved = store.get(chaseKey(), null);
      if (!PUBLIC && f.firstDone && !(saved?.balls || saved?.runs || saved?.wickets) && state.batting !== state.chasing && !xiProblem()) {
        fetch("/api/predict", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload(false), track_innings_break: true, _no_warm: true }),
        }).catch(() => {});
      }
      if (!(saved && saved.balls > 0)) { Object.assign(chase, { runs: 0, wickets: 0, balls: 0, undo: [], timeline: [] }); saveChase(); }  // a chase already under way for this target is kept
      setStage("chase"); syncChase(); scheduleChase(0);
      $("#chase-step").scrollIntoView({ behavior: NO_MOTION ? "auto" : "smooth", block: "start" });
      toast(`The chase: ${f.B} need ${f.target}`);
      return;
    }
    if (go === "new-match") {
      Object.assign(chase, { runs: 0, wickets: 0, balls: 0, undo: [], timeline: [] }); saveChase();
      setStage("first");
      $("#first-live-start").click();  // first innings back to 0/0, ball by ball
      $("#first-step").scrollIntoView({ behavior: NO_MOTION ? "auto" : "smooth", block: "start" });
    }
  });

  function bindChase() {
    $$(".stage-toggle [data-stage]").forEach((b) => b.addEventListener("click", () => setStage(b.dataset.stage)));
    $$(".ball-pad [data-ball]").forEach((b) => b.addEventListener("click", () => addBall(b.dataset.ball)));
  $("#preview-btn")?.addEventListener("click", matchPreview);
    $$("[data-cstep]").forEach((b) => b.addEventListener("click", () => {
      snapshot(); chase[b.dataset.cstep] += Number(b.dataset.delta); syncChase(); scheduleChase();
    }));
    $("#c-runs-input").addEventListener("change", (e) => { snapshot(); chase.runs = parseInt(e.target.value, 10) || 0; syncChase(); scheduleChase(0); });
    $("#c-wickets-input").addEventListener("change", (e) => { snapshot(); chase.wickets = parseInt(e.target.value, 10) || 0; syncChase(); scheduleChase(0); });
    $("#c-overs-input").addEventListener("change", (e) => {
      snapshot(); const [o, b = "0"] = String(e.target.value).split("."); chase.balls = (parseInt(o, 10) || 0) * 6 + Math.min(5, parseInt(b[0] || "0", 10) || 0);
      syncChase(); scheduleChase(0);
    });
    $("#target-input").addEventListener("change", (e) => { chase.target = parseInt(e.target.value, 10) || 1; restoreChase(); syncChase(); scheduleChase(0); });
    $("#target-from-first").addEventListener("click", () => { chase.target = state.runs + 1; restoreChase(); syncChase(); scheduleChase(0); toast(`Target set to ${chase.target}`); });
    $("#chase-reset").addEventListener("click", () => {
      Object.assign(chase, { runs: 0, wickets: 0, balls: 0, undo: [], timeline: [] }); saveChase(); syncChase(); scheduleChase(0);
    });
    $$("#c-worm, .chase-step .sb-value").forEach((i) => i.addEventListener?.("focus", () => i.select?.()));
  }

  // ------------------------------------------------------------------ matchups & form
  const ins = { tab: "preview", dir: "bat_v_chase", side: "bat", data: null, timer: null, seq: 0 };
  const sideTeam = (side) => team(side === "bat" ? state.batting : state.chasing);
  const other = (side) => (side === "bat" ? "chase" : "bat");
  const fmtLabel = () => (state.format === "odi" ? "ODI" : "T20");

  function scheduleInsights() {
    if (!state.config) return;
    clearTimeout(ins.timer); ins.timer = setTimeout(loadInsights, 600);  // wait for a pause in ticking before asking the server
  }
  // panels that don't depend on the XIs (teams, fielding, dropped catches) only reload when what they do depend on changes
  const lastAsked = {};
  const askedAlready = (name, req) => { const k = JSON.stringify(req); if (lastAsked[name] === k) return true; lastAsked[name] = k; return false; };
  const forgetAsked = (name) => { delete lastAsked[name]; };
  async function loadInsights() {
    const seq = ++ins.seq;
    fillH2HPickers();
    try {
      const data = await api("/api/insights", {
        mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing,
        ...xiPayload(),
      });
      if (seq !== ins.seq) return;  // a newer request is on its way
      ins.data = data; renderBattles(); renderForm(); loadH2H(); loadVenue(); loadTeams(); loadPhases(); loadFielding(); loadToss(); renderPreview();
      if (ins.tab === "compare") loadCompare();
    } catch (err) { $("#battle-body").innerHTML = `<tr><td colspan="7">${esc(err.message)}</td></tr>`; }
  }

  // --- head-to-head
  function playerOptions(side, wantBowlers) {
    const t = sideTeam(side); const xi = new Set(state.xi[side]);
    const byRole = (p) => (wantBowlers ? (p.role === "bowler" ? 0 : p.role === "all_rounder" ? 1 : 2) : (p.role === "bowler" ? 1 : 0));
    const inXI = t.squad.filter((p) => xi.has(p.name)).sort((a, b) => byRole(a) - byRole(b));
    const rest = t.squad.filter((p) => !xi.has(p.name));
    const opt = (p) => `<option value="${side}|${esc(p.name)}">${esc(p.name)} · ${esc(p.role_label)}</option>`;
    return `<optgroup label="${esc(t.name)} · playing XI">${inXI.map(opt).join("")}</optgroup>`
      + (rest.length ? `<optgroup label="${esc(t.name)} · rest of squad">${rest.map(opt).join("")}</optgroup>` : "");
  }
  function fillH2HPickers() {
    const bSel = $("#h2h-batter"); const wSel = $("#h2h-bowler");
    const keepBat = bSel.value; const keepBowl = wSel.value;
    bSel.innerHTML = playerOptions("bat", false) + playerOptions("chase", false);
    bSel.value = [...bSel.options].some((o) => o.value === keepBat) ? keepBat : (bSel.options[0]?.value || "");
    fillBowlers(keepBowl);
  }
  function fillBowlers(keep) {
    const batSide = ($("#h2h-batter").value || "bat|").split("|")[0];
    const wSel = $("#h2h-bowler");
    wSel.innerHTML = playerOptions(other(batSide), true);
    wSel.value = [...wSel.options].some((o) => o.value === keep) ? keep : (wSel.options[0]?.value || "");
  }
  async function loadH2H() {
    const [batSide, batter] = ($("#h2h-batter").value || "").split("|");
    const [bowlSide, bowler] = ($("#h2h-bowler").value || "").split("|");
    if (!batter || !bowler) { $("#h2h-result").innerHTML = ""; return; }
    const code = (side) => (side === "bat" ? state.batting : state.chasing);
    try {
      const h = await api("/api/h2h", { mode: state.mode, batter, batter_team: code(batSide), bowler, bowler_team: code(bowlSide) });
      renderH2H(h);
    } catch (err) { $("#h2h-result").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  const edgeLabel = (e, h) => (e === "batter" ? `${esc(h.batter)} on top` : e === "bowler" ? `${esc(h.bowler)} on top` : "Even contest");
  function renderH2H(h) {
    if (!h.available) { $("#h2h-result").innerHTML = `<p class="muted">Matchup data isn't built yet. Go to <a href="#data">Data</a> → Retrain model.</p>`; return; }
    if (!h.batter_found || !h.bowler_found) {
      const who = !h.batter_found ? h.batter : h.bowler;
      $("#h2h-result").innerHTML = `<div class="h2h-card none">${esc(who)} has no matches in the data yet, so there's no head-to-head record.</div>`;
      return;
    }
    const main = h[state.format] || h.all;
    const card = (title, s, fam) => s ? `
      <div class="h2h-card"><h4>${title}</h4>
        <div class="kv"><span>Runs (balls)</span><b>${s.runs} (${s.balls})</b></div>
        <div class="kv"><span>Dismissed by ${esc(h.bowler)}</span><b>${s.outs}×</b></div>
        <div class="kv"><span>Strike rate</span><b>${s.strike_rate ?? "–"}</b></div>
        <div class="kv"><span>Average</span><b>${s.average ?? "no dismissal"}</b></div>
        <div class="kv"><span>4s / 6s</span><b>${s.fours} / ${s.sixes}</b></div>
        <div class="kv"><span>Dot balls</span><b>${s.dot_pct}%</b></div>
        <div class="kv"><span>Matches · last met</span><b>${s.matches} · ${esc(s.last)}</b></div>
        ${fam && s.edge ? `<div style="margin-top:6px"><span class="edge ${s.edge}">${edgeLabel(s.edge, h)}</span></div>` : ""}
      </div>` : `<div class="h2h-card none"><h4>${title}</h4>Never faced each other${fam ? ` in ${title}s` : ""} in the data.</div>`;
    $("#h2h-result").innerHTML = (main ? `
      <div class="h2h-headline">
        <span class="big">${main.runs}<small>runs off ${main.balls} balls</small></span>
        <span class="big">${main.outs}<small>dismissal${main.outs === 1 ? "" : "s"}</small></span>
        <span class="muted">${esc(h.batter)} v ${esc(h.bowler)} · ${h[state.format] ? fmtLabel() : "all formats"}</span>
        ${main.edge ? `<span class="edge ${main.edge} verdict">${edgeLabel(main.edge, h)}</span>` : ""}
      </div>` : `<div class="h2h-headline"><span class="muted">${esc(h.batter)} and ${esc(h.bowler)} haven't faced each other in the data.</span></div>`)
      + `<div class="h2h-formats">${card("T20", h.t20, true)}${card("ODI", h.odi, true)}${card("All formats", h.all, false)}</div>`;
  }

  // --- key battles
  function renderBattles() {
    const d = ins.data; if (!d) return;
    const dirs = [["bat_v_chase", `${d.batting_team} batters v ${d.chasing_team} bowlers`], ["chase_v_bat", `${d.chasing_team} batters v ${d.batting_team} bowlers`]];
    $("#battle-dir").innerHTML = dirs.map(([k, l]) => `<button type="button" data-dir="${k}" class="${k === ins.dir ? "active" : ""}">${esc(l)} <small>(${d.battles[k].length})</small></button>`).join("");
    const rows = d.battles[ins.dir];
    $("#battle-body").innerHTML = rows.length ? rows.map((r) => `
      <tr data-bat="${esc(r.batter)}" data-bowl="${esc(r.bowler)}">
        <td>${esc(r.batter)}</td><td>${esc(r.bowler)}</td><td>${r.runs} (${r.balls})</td><td>${r.outs}</td>
        <td>${r.strike_rate ?? "–"}</td><td>${r.dot_pct}%</td>
        <td><span class="edge ${r.edge}">${r.edge === "batter" ? "Batter" : r.edge === "bowler" ? "Bowler" : "Even"}</span></td>
      </tr>`).join("") : `<tr><td colspan="7" class="muted">These players haven't faced each other much in ${fmtLabel()}s (6+ balls) in the data.</td></tr>`;
  }

  // --- form
  function renderForm() {
    const d = ins.data; if (!d) return;
    const fam = d.format;
    $("#form-team").innerHTML = [["bat", d.batting_team], ["chase", d.chasing_team]].map(([k, l]) => `<button type="button" data-form-side="${k}" class="${k === ins.side ? "active" : ""}">${esc(l)}</button>`).join("");
    const roles = Object.fromEntries(sideTeam(ins.side).squad.map((p) => [p.name, p.role_label]));
    $("#form-grid").innerHTML = d.form[ins.side].map((p) => {
      const f = p.found ? p[fam] : null;
      if (!f || (!f.bat_summary && !f.bowl_summary)) {
        return `<article class="form-card"><header><strong>${esc(p.name)}</strong><small>${esc(roles[p.name] || "")}</small></header><p class="form-line">No ${fmtLabel()} matches in the data${p.found ? "" : " yet"}.</p></article>`;
      }
      const bat = [...f.batting].reverse();  // oldest -> newest
      const maxRuns = Math.max(30, ...bat.map((b) => b.runs));
      const spark = bat.length ? `<div class="spark">${bat.map((b) => `<i class="${b.out ? "" : "notout"} ${b.runs >= 50 ? "fifty" : ""}" style="height:${Math.max(4, (b.runs / maxRuns) * 100)}%" title="${b.runs}${b.out ? "" : "*"} (${b.balls}) v ${esc(b.opponent)} · ${esc(fd(b.date))}"></i>`).join("")}</div>` : "";
      const bs = f.bat_summary; const ws = f.bowl_summary;
      return `<article class="form-card">
        <header><strong>${esc(p.name)}</strong><small>${esc(roles[p.name] || "")}</small></header>
        ${bs ? `<p class="form-line">Last ${bs.innings} inns: <b>${bs.runs}</b> runs · avg <b>${bs.average ?? "–"}</b> · SR <b>${bs.strike_rate ?? "–"}</b>${bs.fifties ? ` · <b>${bs.fifties}</b>×50+` : ""}</p>${spark}
          <p class="form-line">Latest: ${f.batting.slice(0, 4).map((b) => `<b>${b.runs}${b.out ? "" : "*"}</b> (${b.balls}) v ${esc(b.opponent)}`).join(", ")}</p>` : ""}
        ${ws ? `<p class="form-line">Last ${ws.spells} spells: <b>${ws.wickets}</b> wkts · econ <b>${ws.economy ?? "–"}</b>${ws.average ? ` · avg <b>${ws.average}</b>` : ""}</p>
          <div class="spells">${f.bowling.slice(0, 8).map((w) => `<span class="${w.wickets ? "wk" : ""}" title="v ${esc(w.opponent)} · ${esc(fd(w.date))}">${w.wickets}/${w.runs}</span>`).join("")}</div>` : ""}
      </article>`;
    }).join("");
  }

  // --- venue page: the selected ground's record, scoring by phase, toss, results and the XIs' records there
  let venueSide = "bat"; let venueData = null;
  async function loadVenue() {
    try {
      venueData = await api("/api/venue", {
        mode: state.mode, format: state.format, venue: state.venue, batting: state.batting, chasing: state.chasing,
        ...xiPayload(),
      });
      renderVenue(); renderPreview();
    } catch (err) { $("#venue-body").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  function renderVenue() {
    const v = venueData; if (!v) return;
    const head = `<div class="venue-head"><div><p class="eyebrow">${esc(v.competition || "")} · ${esc((v.format || "").toUpperCase())}</p>
      <h3>${esc(v.name)}</h3><p class="muted small">${esc([v.city, v.country].filter(Boolean).join(", "))}</p></div></div>`;
    if (!v.available) { $("#venue-body").innerHTML = `${head}<div class="h2h-card none">${esc(v.reason || "No data for this ground yet.")}</div>`; return; }
    const tile = (big, label, sub = "") => `<div class="v-tile"><span class="v-big">${big ?? "–"}</span><span class="v-label">${label}</span>${sub ? `<span class="v-sub">${sub}</span>` : ""}</div>`;
    const maxRuns = Math.max(...v.phases.map((p) => p.runs));
    const phaseBar = v.phases.map((p, i) => `<div class="phase" style="--w:${(p.runs / maxRuns) * 100}%; --i:${i}">
        <div class="phase-top"><b>${esc(p.label)}</b><span>${p.runs} runs · ${p.wickets} wkts</span></div>
        <div class="phase-track"><i></i></div></div>`).join("");
    const recent = v.recent.map((r) => {
      const other = r.batted_first === r.team1 ? r.team2 : r.team1;
      return `<li><span class="r-date">${esc(fd(r.date))}</span>
        <span class="r-teams">${badgeHTML(r.batted_first)} <b>${r.first_total}</b> <span class="muted">v</span> ${badgeHTML(other)}</span>
        <span class="r-win">${r.winner ? `${esc(r.winner)} won${r.margin ? ` by ${esc(r.margin)}` : ""}` : esc(r.margin || "No result")}</span></li>`;
    }).join("");
    const rows = (v.players[venueSide] || []);
    const played = rows.filter((p) => p.played).sort((a, b) => (b.runs + b.wickets * 20) - (a.runs + a.wickets * 20));
    const notPlayed = rows.filter((p) => !p.played);
    const teamName = v.teams[venueSide];
    $("#venue-body").innerHTML = `${head}
      <div class="v-grid">
        ${tile(v.matches, "matches here")}
        ${tile(v.bat_first_win_pct != null ? `${v.bat_first_win_pct}%` : null, "won by side batting first", v.chase_win_pct != null ? `chasing side won ${v.chase_win_pct}%` : "")}
        ${tile(v.par, "par score now", `all-time average ${v.avg_first}`)}
        ${tile(v.highest, "highest 1st-innings total")}
        ${tile(v.lowest_defended, "lowest total defended")}
        ${tile(v.highest_chased, "highest target chased")}
        ${tile(v.toss.winner_won_pct != null ? `${v.toss.winner_won_pct}%` : null, "toss winners who won", v.toss.chose_bowl_pct != null ? `${v.toss.chose_bowl_pct}% chose to bowl` : "")}
      </div>
      <div class="two-col v-cols">
        <div><h4 class="v-h">Average first innings, by phase</h4>${phaseBar}</div>
        <div><h4 class="v-h">Last ${v.recent.length} results here</h4><ul class="v-recent">${recent}</ul></div>
      </div>
      <h4 class="v-h">Players' records at this ground</h4>
      <div class="seg-tabs" id="venue-side">${[["bat", v.teams.bat], ["chase", v.teams.chase]].map(([k, l]) => `<button type="button" data-vside="${k}" class="${k === venueSide ? "active" : ""}">${esc(l)}</button>`).join("")}</div>
      ${played.length ? `<div class="table-wrap"><table class="acc"><thead><tr><th>Player</th><th>Inns</th><th>Runs</th><th>Avg</th><th>SR</th><th>Best</th><th>50s</th><th>Wkts</th><th>Econ</th></tr></thead><tbody>
        ${played.map((p) => { const bat = p.innings > 0; const d = "–"; return `<tr><td>${esc(p.name)}</td><td>${bat ? p.innings : d}</td><td>${bat ? p.runs : d}</td><td>${p.average ?? d}</td><td>${bat && p.strike_rate != null ? p.strike_rate : d}</td><td>${bat ? p.best : d}</td><td>${bat ? p.fifties : d}</td><td>${p.bowl_spells ? p.wickets : d}</td><td>${p.economy ?? d}</td></tr>`; }).join("")}
      </tbody></table></div>` : `<p class="muted">None of ${esc(teamName)}'s ticked players have played a ${esc(v.format.toUpperCase())} here in the data.</p>`}
      ${notPlayed.length ? `<p class="muted small">First time here (no ${esc(v.format.toUpperCase())} at this ground in the data): ${notPlayed.map((p) => esc(p.name)).join(", ")}.</p>` : ""}`;
  }

  // --- phases: powerplay / middle / death numbers for the ticked XIs, with "best at…" callouts
  let phaseData = null; let phaseSide = "bat";
  async function loadPhases() {
    try {
      phaseData = await api("/api/phases", { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing,
        ...xiPayload() });
      renderPhases(); renderPreview();
    } catch (err) { $("#phases-body").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  function renderPhases() {
    const d = phaseData; if (!d) return;
    const t = d.teams[phaseSide]; const c = t.callouts; const [L0, L1, L2] = d.labels; const phs = ["pp", "mid", "death"];
    const callout = (icon, title, who, stat) => `<div class="pc">${icon}<div><span>${title}</span><b>${who ? esc(who) : "–"}</b><small>${stat || "not enough balls yet"}</small></div></div>`;
    // colour each cell against the format's normal range: green = good for that player's side
    const srColor = (sr) => sr == null ? "" : `background:hsl(${Math.max(0, Math.min(120, (sr - (d.format === "t20" ? 100 : 60)) * (d.format === "t20" ? 1.4 : 1.6)))},60%,92%)`;
    const ecColor = (ec) => ec == null ? "" : `background:hsl(${Math.max(0, Math.min(120, ((d.format === "t20" ? 11 : 7) - ec) * (d.format === "t20" ? 30 : 40)))},60%,92%)`;
    const batRows = t.rows.filter((r) => r.bats).map((r) => `<tr><td>${esc(r.name)}</td>${phs.map((p) => {
      const x = r.bat[p];
      return x.balls ? `<td class="${x.small ? "small-n" : ""}" style="${x.small ? "" : srColor(x.sr)}"><b>${x.sr}</b><small>${x.runs} off ${x.balls}${x.avg != null ? ` · avg ${x.avg}` : ""}</small></td>` : `<td class="none">–</td>`;
    }).join("")}</tr>`).join("");
    const bowlRows = t.rows.filter((r) => r.bowls).map((r) => `<tr><td>${esc(r.name)}</td>${phs.map((p) => {
      const x = r.bowl[p];
      return x.balls ? `<td class="${x.small ? "small-n" : ""}" style="${x.small ? "" : ecColor(x.econ)}"><b>${x.econ}</b><small>${x.wickets} wkts · ${Math.floor(x.balls / 6)} ov</small></td>` : `<td class="none">–</td>`;
    }).join("")}</tr>`).join("");
    const bat = cq("bat");
    const ball = cq("ball");
    $("#phases-body").innerHTML = `
      <div class="seg-tabs" id="phase-side">${[["bat", d.teams.bat.name], ["chase", d.teams.chase.name]].map(([k, l]) => `<button type="button" data-pside="${k}" class="${k === phaseSide ? "active" : ""}">${esc(l)}</button>`).join("")}</div>
      <div class="pc-grid">
        ${callout(bat, "Fastest in the powerplay", c.pp_hitter?.name, c.pp_hitter && `strike rate ${c.pp_hitter.sr} · ${c.pp_hitter.balls} balls`)}
        ${callout(bat, "Fastest at the death", c.death_hitter?.name, c.death_hitter && `strike rate ${c.death_hitter.sr} · ${c.death_hitter.balls} balls`)}
        ${callout(ball, "Tightest in the powerplay", c.pp_bowler?.name, c.pp_bowler && `economy ${c.pp_bowler.econ} · ${c.pp_bowler.wickets} wkts`)}
        ${callout(ball, "Tightest at the death", c.death_bowler?.name, c.death_bowler && `economy ${c.death_bowler.econ} · ${c.death_bowler.wickets} wkts`)}
      </div>
      <h4 class="v-h">Batting · strike rate by phase</h4>
      ${batRows ? `<div class="table-wrap"><table class="acc phase-t"><thead><tr><th>Batter</th><th>${L0}</th><th>${L1}</th><th>${L2}</th></tr></thead><tbody>${batRows}</tbody></table></div>` : `<p class="muted">No batting data for these players.</p>`}
      <h4 class="v-h" style="margin-top:18px">Bowling · economy by phase</h4>
      ${bowlRows ? `<div class="table-wrap"><table class="acc phase-t"><thead><tr><th>Bowler</th><th>${L0}</th><th>${L1}</th><th>${L2}</th></tr></thead><tbody>${bowlRows}</tbody></table></div>` : `<p class="muted">No bowling data for these players.</p>`}
      <p class="muted small">Career figures in ${esc(d.format.toUpperCase())}s${d.format === "t20" ? " (T20 internationals, the IPL and other T20 leagues)" : ""}. Greyed numbers come from fewer than ${d.min_bat_balls} balls faced / ${d.min_bowl_balls} balls bowled, so treat them with care.</p>`;
  }

  // --- teams: all-time head-to-head in this format, last 10 meetings, record at the ground, and current form
  async function loadTeams() {
    const req = { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, venue: state.venue };
    if (teamsData && askedAlready("teams", req)) return;
    try {
      const d = await api("/api/teams", req);
      teamsData = d; renderTeams(d); renderPreview();
    } catch (err) { forgetAsked("teams"); $("#teams-body").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  function renderTeams(d) {
    const h = d.h2h; const [a, b] = h.teams; const fmt = d.format.toUpperCase();
    const sa = teamStyle(a), sb = teamStyle(b);
    if (!h.played) {
      $("#teams-body").innerHTML = `<div class="h2h-card none">${esc(a)} and ${esc(b)} haven't played each other in a ${fmt} in the data.</div>${formBlock(d)}`;
      return;
    }
    const wa = h.wins[a], wb = h.wins[b]; const tot = Math.max(1, wa + wb);
    const tile = (big, label, sub = "") => `<div class="v-tile"><span class="v-big">${big}</span><span class="v-label">${label}</span>${sub ? `<span class="v-sub">${sub}</span>` : ""}</div>`;
    const meet = h.meetings.map((m) => {
      const won = m.winner ? teamStyle(m.winner) : null;
      return `<li>
        <span class="r-date">${esc(fd(m.date))}</span>
        <span class="m-scores">${m.innings.map((i) => `<span class="m-inn ${i.team === m.winner ? "won" : ""}">${badgeHTML(i.team)} <b>${esc(i.text)}</b></span>`).join("")}</span>
        <span class="r-win">${m.winner ? `<b style="color:${won.c1}">${esc(m.winner)}</b> won by ${esc(m.margin)}${m.rain_rule ? " (rain rule)" : ""}` : esc(m.margin || "No result")} · ${esc(m.venue)}</span></li>`;
    }).join("");
    $("#teams-body").innerHTML = `
      <div class="h2h-score">
        <div class="hs-team">${badgeHTML(a, "lg")}<span>${esc(a)}</span></div>
        <div class="hs-num"><b>${wa}</b><span>–</span><b>${wb}</b><small>${h.played} ${fmt}s since ${esc(h.first_met.slice(0, 4))}${h.no_result ? ` · ${h.no_result} no result` : ""}</small></div>
        <div class="hs-team right"><span>${esc(b)}</span>${badgeHTML(b, "lg")}</div>
      </div>
      <div class="hs-bar"><i style="width:${(wa / tot) * 100}%;background:linear-gradient(90deg,${sa.c1},${sa.c2})"></i><i style="width:${(wb / tot) * 100}%;background:linear-gradient(90deg,${sb.c2},${sb.c1})"></i></div>
      <div class="v-grid" style="margin-top:16px">
        ${tile(`${h.last_n[a]}–${h.last_n[b]}`, `last ${h.last_n.n} meetings`, `${esc(a)} first`)}
        ${tile(h.at_ground.played ? `${h.at_ground[a]}–${h.at_ground[b]}` : "–", `at ${esc(d.venue || "this ground")}`, h.at_ground.played ? `${h.at_ground.played} played there` : "never met here")}
        ${tile(`${Math.round(h.bat_first_won * 100 / Math.max(1, h.decided))}%`, "won by side batting first", `${h.bat_first_won} of ${h.decided} in these meetings`)}
      </div>
      <div class="two-col v-cols">
        <div><h4 class="v-h">Last ${h.meetings.length} meetings</h4><ul class="v-recent meets">${meet}</ul></div>
        <div>${formBlock(d)}</div>
      </div>`;
  }
  function formBlock(d) {
    return `<h4 class="v-h">Current form · last 10 ${esc(d.format.toUpperCase())}s</h4>` + ["bat", "chase"].map((k) => {
      const f = d.form[k];
      return `<div class="form-row"><div class="fr-head">${badgeHTML(f.team)}<b>${esc(f.team)}</b><span class="muted small">${f.win_pct != null ? `${f.win_pct}% won` : ""}</span></div>
        <div class="chips">${f.games.map((g) => `<span class="res ${g.result.toLowerCase()}" title="${esc(fd(g.date))} v ${esc(g.opponent)}: ${g.result === "W" ? "won" : g.result === "L" ? "lost" : "no result"}${g.margin ? ` (${esc(g.margin)})` : ""} · ${esc(g.venue)}">${g.result === "NR" ? "–" : g.result}</span>`).join("")}</div>
        <p class="muted small fr-last">${f.games[0] ? `Latest: ${f.games[0].result === "W" ? "beat" : f.games[0].result === "L" ? "lost to" : "no result v"} ${esc(f.games[0].opponent)}${f.games[0].margin && f.games[0].result !== "NR" ? ` by ${esc(f.games[0].margin)}` : ""} (${esc(fd(f.games[0].date))})` : "No matches in the data."}</p></div>`;
    }).join("");
  }

  // --- compare two players side by side
  function fillCompare() {
    const opts = ["bat", "chase"].map((side) => {
      const t = sideTeam(side); const xi = new Set(state.xi[side]);
      const people = [...t.squad.filter((p) => xi.has(p.name)), ...t.squad.filter((p) => !xi.has(p.name))];
      return `<optgroup label="${esc(t.name)}">${people.map((p) => `<option value="${side}|${esc(p.name)}">${esc(p.name)}${p.role_label ? ` · ${esc(p.role_label)}` : ""}</option>`).join("")}</optgroup>`;
    }).join("");
    for (const [id, side, pick] of [["#cmp-a", "bat", (p) => p.role !== "bowler"], ["#cmp-b", "chase", (p) => p.role === "bowler"]]) {
      const el = $(id); const keep = el.value; el.innerHTML = opts;
      if (keep && [...el.options].some((o) => o.value === keep)) { el.value = keep; continue; }
      const t = sideTeam(side); const first = t.squad.find((p) => state.xi[side].includes(p.name) && pick(p)) || t.squad[0];
      if (first) el.value = `${side}|${first.name}`;
    }
  }
  async function loadCompare() {
    fillCompare();
    const [sa, na] = ($("#cmp-a").value || "|").split("|"); const [sb, nb] = ($("#cmp-b").value || "|").split("|");
    if (!na || !nb) return;
    const code = (s) => (s === "bat" ? state.batting : state.chasing);
    try {
      const d = await api("/api/compare", { mode: state.mode, format: state.format, venue: state.venue,
        a: { name: na, team: code(sa) }, b: { name: nb, team: code(sb) } });
      renderCompare(d);
    } catch (err) { $("#compare-body").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  function renderCompare(d) {
    const A = d.a, B = d.b; const fmt = d.format.toUpperCase();
    const v = (x) => (x == null || x === "" ? "–" : x);
    // better = "high" or "low"; the better value is highlighted only when both have a fair sample (fair = [okA, okB])
    const row = (label, a, b, better, fair = [true, true]) => {
      const na = typeof a === "number" ? a : null, nb = typeof b === "number" ? b : null;
      const win = fair[0] && fair[1] && na != null && nb != null && na !== nb ? ((better === "high") === (na > nb) ? "a" : "b") : "";
      const cell = (val, ok, w) => `<td class="${w ? "best" : ""}${ok ? "" : " thin"}" ${ok ? "" : 'title="Small sample"'}>${v(val)}</td>`;
      return `<tr>${cell(a, fair[0], win === "a")}<th>${label}</th>${cell(b, fair[1], win === "b")}</tr>`;
    };
    const ca = A.career || {}, cb = B.career || {};
    const batOK = [(ca.balls || 0) >= 120, (cb.balls || 0) >= 120];      // ~20 innings' worth of balls faced
    const bowlOK = [(ca.overs || 0) >= 20, (cb.overs || 0) >= 20];       // 20 overs bowled
    const fa = A.form || {}, fb = B.form || {};
    const fba = fa.bat_summary || {}, fbb = fb.bat_summary || {}, fwa = fa.bowl_summary || {}, fwb = fb.bowl_summary || {};
    const phase = (p, kind, key) => (p.phases?.[kind]?.[key] || {});
    const phaseRows = ["pp", "mid", "death"].map((k, i) => {
      const lab = d.phase_labels[i];
      return row(`${lab} strike rate`, phase(A, "bat", k).sr ?? null, phase(B, "bat", k).sr ?? null, "high", [!phase(A, "bat", k).small, !phase(B, "bat", k).small])
        + row(`${lab} economy`, phase(A, "bowl", k).econ ?? null, phase(B, "bowl", k).econ ?? null, "low", [!phase(A, "bowl", k).small, !phase(B, "bowl", k).small]);
    }).join("");
    const va = A.venue || {}, vb = B.venue || {};
    const vsLine = (h, bat, bowl) => h && h.balls ? `<p><b>${esc(bat)}</b> v <b>${esc(bowl)}</b>: ${h.runs} off ${h.balls} balls, out ${h.outs}× · SR ${h.strike_rate ?? "–"} · ${h.matches} matches${h.edge ? ` · edge: <b>${esc(h.edge)}</b>` : ""}</p>` : "";
    const vsHtml = vsLine(d.vs.a_bats, A.name, B.name) + vsLine(d.vs.b_bats, B.name, A.name);
    const head = (p) => `<div class="cmp-head">${p.team_code ? badgeHTML(p.team_code, "") : ""}<div><b>${esc(p.name)}</b><small>${esc(p.team)}${p.career?.usual_position ? ` · usually bats at ${p.career.usual_position}` : ""}</small></div></div>`;
    $("#compare-body").innerHTML = `
      <div class="cmp-heads">${head(A)}<span></span>${head(B)}</div>
      <div class="table-wrap"><table class="cmp-table">
        <tbody>
          <tr class="grp"><td></td><th>${fmt} career</th><td></td></tr>
          ${row("Matches", ca.matches ?? null, cb.matches ?? null, "high")}
          ${row("Runs", ca.runs ?? null, cb.runs ?? null, "high")}
          ${row("Batting average", ca.average ?? null, cb.average ?? null, "high", batOK)}
          ${row("Strike rate", ca.strike_rate ?? null, cb.strike_rate ?? null, "high", batOK)}
          ${row("Wickets", ca.wickets ?? null, cb.wickets ?? null, "high")}
          ${row("Economy", ca.economy ?? null, cb.economy ?? null, "low", bowlOK)}
          <tr class="grp"><td></td><th>Last 10 innings / spells</th><td></td></tr>
          ${row("Runs", fba.runs ?? null, fbb.runs ?? null, "high")}
          ${row("Strike rate", fba.strike_rate ?? null, fbb.strike_rate ?? null, "high", [(fba.innings || 0) >= 5, (fbb.innings || 0) >= 5])}
          ${row("Fifties", fba.fifties ?? null, fbb.fifties ?? null, "high")}
          ${row("Wickets", fwa.wickets ?? null, fwb.wickets ?? null, "high")}
          ${row("Economy", fwa.economy ?? null, fwb.economy ?? null, "low", [(fwa.spells || 0) >= 5, (fwb.spells || 0) >= 5])}
          <tr class="grp"><td></td><th>By phase (career)</th><td></td></tr>
          ${phaseRows}
          ${d.venue ? `<tr class="grp"><td></td><th>At ${esc(d.venue)}</th><td></td></tr>
            ${row("Innings", va.innings ?? null, vb.innings ?? null, "high")}
            ${row("Runs", va.runs ?? null, vb.runs ?? null, "high")}
            ${row("Best", va.best ?? null, vb.best ?? null, "high")}
            ${row("Wickets", va.wickets ?? null, vb.wickets ?? null, "high")}` : ""}
        </tbody></table></div>
      <div class="cmp-vs-box"><h3 class="sub">Head to head</h3>${vsHtml || `<p class="muted">They haven't faced each other in ${fmt}s in the data.</p>`}</div>
      <p class="muted small">Highlighted = the better of the two, when both have a fair sample; faded numbers come from very few balls or overs. Career numbers are ${fmt} only (internationals, IPL and other T20 leagues).</p>`;
  }


  // ---- dropped catches (the Drop button in live scoring): first innings → the chasing side is fielding;
  // live chase → the side that batted first is fielding
  const dropSides = (kind) => (kind === "chase" ? { fielding: state.batting, batting: state.chasing } : { fielding: state.chasing, batting: state.batting });
  async function refreshDrops() {
    for (const kind of ["first", "chase"]) {
      const btn = $(`[data-drop="${kind}"]`); if (!btn || !state.config) continue;
      const req = { mode: state.mode, format: state.format, ...dropSides(kind), delta: 0 };
      if (askedAlready(`drops.${kind}`, req)) continue;  // same teams: the count only changes when you log a drop
      try {
        const r = await api("/api/drops", req);
        paintDrop(kind, r.drops);
      } catch { forgetAsked(`drops.${kind}`); /* server down: the banner explains */ }
    }
  }
  function paintDrop(kind, n) {
    const btn = $(`[data-drop="${kind}"]`); const undo = $(`[data-drop-undo="${kind}"]`);
    btn.querySelector(".drop-n").textContent = n ? `drop · ${n}` : "drop";
    btn.classList.toggle("has", n > 0); undo.hidden = !n;
  }
  function bindDrops() {
    document.addEventListener("click", async (e) => {
      const b = e.target.closest?.("[data-drop], [data-drop-undo]"); if (!b) return;
      const kind = b.dataset.drop || b.dataset.dropUndo; const delta = b.dataset.drop ? 1 : -1;
      const sides = dropSides(kind);
      try {
        const r = await api("/api/drops", { mode: state.mode, format: state.format, ...sides, delta });
        paintDrop(kind, r.drops);
        if (delta > 0) { b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop"); }
        toast(delta > 0 ? `Dropped catch logged for ${team(sides.fielding).name} (${r.drops} this match)` : `Last drop taken back (${r.drops} this match)`);
        if (ins.tab === "fielding") loadFielding(true);
      } catch (err) { toast(`Couldn't log it (${err.message})`); }
    });
  }

  // --- team fielding card (catches taken, run-outs, stumpings; drops aren't in the data)
  const fieldWin = { ipl: 2, international: 20 };
  async function loadFielding(force = false) {
    const req = { mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing, window: fieldWin[state.mode] };
    if (!force && askedAlready("fielding", req)) return;
    if (force) lastAsked.fielding = JSON.stringify(req);
    try {
      const d = await api("/api/fielding", req);
      renderFielding(d);
    } catch (err) { forgetAsked("fielding"); $("#fielding-body").innerHTML = `<p class="form-error">${esc(err.message)}</p>`; }
  }
  function renderFielding(d) {
    const body = $("#fielding-body");
    if (!d.available) { body.innerHTML = `<p class="muted">Fielding data appears after the next data rebuild (Data tab → Retrain).</p>`; return; }
    const b = d.benchmark || {};
    const ord = (n) => `${n}${(n % 100 > 10 && n % 100 < 14) ? "th" : (["th", "st", "nd", "rd"][n % 10] || "th")}`;
    const cmp = (v, avg, better = "high", digits = 2) => {
      if (v == null || avg == null) return "";
      const diff = v - avg; const good = better === "high" ? diff > 0 : diff < 0;
      if (Math.abs(diff) < (digits === 1 ? 0.5 : 0.05)) return `<em class="fd-cmp">≈ average</em>`;
      return `<em class="fd-cmp ${good ? "good" : "bad"}">${diff > 0 ? "+" : ""}${diff.toFixed(digits)} v avg</em>`;
    };
    const dropBlock = (t) => {
      const m = t.drops || {}; const est = t.drop_estimate;
      if (m.pct != null) {
        return `<div class="fd-drop measured"><b>${m.pct}%</b><span><strong>Drop chance</strong> · measured: ${m.drops} dropped of ${m.drops + m.catches} chances
          in ${m.matches} logged match${m.matches === 1 ? "" : "es"}${m.waiting ? ` (+${m.waiting} waiting for data)` : ""}</span></div>`;
      }
      const need = Math.max(0, (m.min_matches || 2) - (m.matches || 0));
      return `<div class="fd-drop estimate"><b>${est ? `≈${est.pct}%` : "–"}${est ? `<i class="grade g-${est.grade}" title="A = fewest drops expected … E = most">${est.grade}</i>` : ""}</b>
        <span><strong>Drop chance</strong> · estimate from catches per match (no drop data yet).
        Tap <kbd class="key">✋ drop</kbd> in live scoring when a catch goes down: ${need} more logged match${need === 1 ? "" : "es"} with real data to measure it${m.waiting ? ` · ${m.waiting} logged, waiting for the next data update` : ""}.</span></div>`;
    };
    const card = (side) => {
      const t = d.teams[side]; const code = side === "bat" ? state.batting : state.chasing;
      if (!t || !t.matches) return `<div class="fd-card"><div class="fd-head">${badgeHTML(code, "")}<b>${esc(t?.name || "")}</b></div><p class="muted small">No matches in this window.</p></div>`;
      return `<div class="fd-card">
        <div class="fd-head">${badgeHTML(code, "")}<div><b>${esc(t.name)}</b><small>${t.matches} matches · ${fmtDate(t.first)} – ${fmtDate(t.last)}</small></div>
          ${t.rank ? `<span class="fd-rank" title="Rank by catches per match">${ord(t.rank)} of ${t.of}</span>` : ""}</div>
        <div class="fd-big"><b>${t.catches_pm}</b><span>catches per match ${cmp(t.catches_pm, b.catches_pm)}</span></div>
        <div class="fd-grid">
          <div><b>${t.catch_share ?? "–"}%</b><span>of wickets were catches ${cmp(t.catch_share, b.catch_share, "high", 1)}</span></div>
          <div><b>${t.run_outs_pm}</b><span>run-outs per match ${cmp(t.run_outs_pm, b.run_outs_pm)}</span></div>
          <div><b>${t.stumpings_pm}</b><span>stumpings per match ${cmp(t.stumpings_pm, b.stumpings_pm)}</span></div>
          <div><b>${t.wickets_pm}</b><span>wickets taken per match ${cmp(t.wickets_pm, b.wickets_pm)}</span></div>
        </div>${dropBlock(t)}</div>`;
    };
    const unit = d.mode === "ipl" ? (n) => `${n} season${n > 1 ? "s" : ""}` : (n) => `${n} matches`;
    const table = d.table ? `<div class="table-wrap"><table class="fd-table"><thead><tr><th>#</th><th>Team</th><th>Catches / match</th><th>Catch %</th><th>Run-outs / match</th><th>Stumpings / match</th><th title="Estimate from catches per match">Drop % (est.)</th><th>Matches</th></tr></thead><tbody>
      ${d.table.map((r) => `<tr class="${[state.batting, state.chasing].includes(r.code) ? "mine" : ""}"><td>${r.rank}</td><td><span class="fd-team">${badgeHTML(r.code)}${esc(r.team)}</span></td>
        <td><b>${r.catches_pm}</b></td><td>${r.catch_share ?? "–"}%</td><td>${r.run_outs_pm}</td><td>${r.stumpings_pm}</td><td class="muted">${r.drop_estimate ? `≈${r.drop_estimate.pct}% <i class="grade g-${r.drop_estimate.grade}">${r.drop_estimate.grade}</i>` : "–"}</td><td>${r.matches}</td></tr>`).join("")}
      </tbody></table></div>` : "";
    body.innerHTML = `
      <div class="row-between fd-top">
        <p class="muted small">${esc(d.window_label || "")} · ${esc(d.benchmark_label)}: <b>${b.catches_pm ?? "–"}</b> catches, <b>${b.run_outs_pm ?? "–"}</b> run-outs per match</p>
        <div class="segmented small" role="group" aria-label="Window">${d.windows.map((w) => `<button type="button" data-fwin="${w}" class="${w === d.window ? "active" : ""}">${unit(w)}</button>`).join("")}</div>
      </div>
      <div class="fd-cards">${card("bat")}${card("chase")}</div>
      ${table}
      <p class="muted small fd-note">${esc(d.note)}</p>`;
  }
  function bindInsights() {
    $("#cmp-a").addEventListener("change", loadCompare);
    $("#cmp-b").addEventListener("change", loadCompare);
    $("#fielding-body").addEventListener("click", (e) => {
      const b = e.target.closest("[data-fwin]"); if (!b) return;
      fieldWin[state.mode] = Number(b.dataset.fwin); loadFielding();
    });
    $("#phases-body").addEventListener("click", (e) => { const b = e.target.closest("[data-pside]"); if (b) { phaseSide = b.dataset.pside; renderPhases(); } });
    $("#venue-body").addEventListener("click", (e) => { const b = e.target.closest("[data-vside]"); if (b) { venueSide = b.dataset.vside; renderVenue(); } });
    $("#ins-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-ins]"); if (!b) return;
      ins.tab = b.dataset.ins;
      $$("#ins-tabs [data-ins]").forEach((x) => x.classList.toggle("active", x === b));
      ["preview", "h2h", "battles", "form", "venue", "teams", "phases", "fielding", "compare"].forEach((t) => { $(`#ins-${t}`).hidden = t !== ins.tab; });
      if (ins.tab === "preview") renderPreview();
      if (ins.tab === "compare") loadCompare();
    });
    $("#h2h-batter").addEventListener("change", () => { fillBowlers($("#h2h-bowler").value); loadH2H(); });
    $("#h2h-bowler").addEventListener("change", loadH2H);
    $("#battle-dir").addEventListener("click", (e) => { const b = e.target.closest("[data-dir]"); if (b) { ins.dir = b.dataset.dir; renderBattles(); } });
    $("#form-team").addEventListener("click", (e) => { const b = e.target.closest("[data-form-side]"); if (b) { ins.side = b.dataset.formSide; renderForm(); } });
    $("#battle-body").addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-bat]"); if (!tr) return;
      const batSide = ins.dir === "bat_v_chase" ? "bat" : "chase";
      $("#h2h-batter").value = `${batSide}|${tr.dataset.bat}`; fillBowlers(`${other(batSide)}|${tr.dataset.bowl}`);
      $("#ins-tabs [data-ins=h2h]").click(); loadH2H();
      $("#insights").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // ------------------------------------------------------------------ accuracy
  async function loadInningsTrial() {
    const panel = $("#innings-trial");
    if (PUBLIC || !panel) return;
    panel.hidden = false;
    const body = $("#innings-trial-body");
    let trial;
    try { trial = await api("/api/innings-break-trial"); }
    catch (err) {
      body.textContent = `Could not load the trial. ${err.message}`;
      return;
    }
    if (!trial.recorded) {
      body.textContent = "No forecasts recorded yet. Save a live innings-break prediction or press Start the chase.";
      return;
    }
    const group = trial.groups["All matches"];
    const result = (m, n) => n ? `<b>${m.right}/${n}</b><br><small>${m.log_loss.toFixed(4)} log loss</small>` : "–";
    const rows = Object.entries(trial.groups).map(([name, g]) => `<tr><td>${esc(name)}</td>
      <td>${result(g.first_innings, g.matches)}</td><td>${result(g.chase_start, g.matches)}</td>
      <td>${result(g.blend, g.matches)}</td></tr>`).join("");
    body.innerHTML = `<p class="muted small">${group.matches} verified matches · ${trial.waiting} waiting for a match record · ${trial.excluded} excluded</p>
      ${group.matches ? `<div class="table-wrap"><table class="acc">
        <thead><tr><th>Competition</th><th>First innings</th><th>Chase start</th><th>50/50 average</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
        <p class="muted small">Each cell shows correct picks and log loss. Lower log loss means better probabilities.</p>` : ""}`;
  }
  let accCache = null; let accStage = "innings_break";
  async function loadAccuracy() {
    loadInningsTrial();
    try { accCache = await api("/api/accuracy"); } catch (err) { $("#acc-body").innerHTML = `<div class="empty">Could not load the report: ${esc(err.message)}</div>`; return; }
    renderAccuracy(); loadHonesty();
  }
  // ---- "How honest are the percentages?": for each band of what the model said, how often that side really won
  async function loadHonesty() {
    const box = $("#acc-honesty"); if (!box) return;
    let h;
    try { h = await api("/api/honesty"); } catch { box.hidden = true; return; }
    const BAND_ORDER = ["50-60%", "60-70%", "70-80%", "80-90%", "90-100%"];
    const cell = (r) => {
      if (!r) return `<td class="hn-none">–</td>`;
      const gap = r.won - r.said;
      const cls = r.matches < 15 ? "few" : gap < -5 ? "sure" : gap > 5 ? "shy" : "ok";
      return `<td class="hn-${cls}" title="Said ${r.said}% on average; that side won ${r.won}% of ${r.matches} matches">
        <b>${Math.round(r.won)}%</b><small>said ${Math.round(r.said)} · ${r.matches}</small></td>`;
    };
    const table = (st) => {
      const kinds = st.kinds.filter((k) => k.matches);
      if (!kinds.length) return "";
      const rows = BAND_ORDER.filter((b) => kinds.some((k) => k.rows.some((r) => r.band === b)));
      return `<h3 class="sub">${esc(st.title)}</h3>
        <div class="table-wrap"><table class="fd-table hn-table"><thead><tr><th>Model said</th>${kinds.map((k) => `<th>${esc(k.name)}<small>${k.matches} matches</small></th>`).join("")}</tr></thead>
        <tbody>${rows.map((b) => `<tr><th>${esc(b)}</th>${kinds.map((k) => cell(k.rows.find((r) => r.band === b))).join("")}</tr>`).join("")}</tbody></table></div>`;
    };
    box.innerHTML = `<p class="eyebrow">Honesty check</p><h2>How honest are the percentages?</h2>
      <p class="muted small">When the model said a side had, say, a 70–80% chance, how often did that side really win? Each cell: <b>how often it won</b>, what the model said on average, and how many matches.
        <span class="hn-key hn-sure">too sure</span> means it won more than 5 points less often than the model said;
        <span class="hn-key hn-shy">too cautious</span> more than 5 points more often; faded cells have under 15 matches.</p>
      ${table(h.stages.pre_match)}${table(h.stages.innings_break)}
      <p class="muted small">${esc(h.source)}.</p>`;
    box.hidden = false;
  }
  function renderAccuracy() {
    const rep = accCache.report;
    if (!rep) { $("#acc-body").innerHTML = `<div class="empty">No report yet. Go to <a href="#data">Data</a> and press <b>Retrain model</b>.</div>`; return; }
    const models = rep.shown_models; const names = rep.model_names; const chosen = rep.chosen;
    const all = rep.by_competition["All matches"];
    $("#acc-lede").innerHTML = `Tested on <b>${rep.split.test.matches.toLocaleString()} matches</b> (${esc(rep.test_period.split(" to ").map(fd).join(" → "))}) that no model saw while learning. Trained ${esc(fd(rep.trained_at))}.`;
    const bestOverall = models.reduce((a, m) => (rep.overall[m].accuracy > rep.overall[a].accuracy ? m : a), models[0]);

    const cards = models.map((m) => {
      const o = rep.overall[m].accuracy;
      return `<article class="panel model-card ${m === chosen ? "chosen" : ""} ${MODEL_CLASS[m]}">
        ${m === chosen ? `<span class="tag">Used in app</span>` : m === "original_formula" ? `<span class="tag base">Baseline</span>` : ""}
        <h3>${esc(names[m])}</h3>
        <p>${esc(rep.model_blurbs[m] || "")}</p>
        <div class="big-num">${(o * 100).toFixed(1)}<small>% correct${m === bestOverall ? " · best" : ""}</small></div>
        <div class="meter"><i style="width:${o * 100}%"></i></div>
        <div class="kv"><span>Before the match</span><b>${pct(all.pre_match[m].accuracy)}</b></div>
        <div class="kv"><span>During 1st innings</span><b>${pct(all.mid_innings[m].accuracy)}</b></div>
        <div class="kv"><span>At innings break</span><b>${pct(all.innings_break[m].accuracy)}</b></div>
      </article>`;
    }).join("");

    const legend = `<div class="legend">${models.map((m) => `<span class="${MODEL_CLASS[m]}"><i></i>${esc(names[m])}</span>`).join("")}</div>`;
    const stageGroups = Object.entries(rep.stages).map(([key, label]) => `
      <div class="stage-group"><h4>${esc(label)}</h4>
        ${models.map((m) => { const a = all[key][m].accuracy; return `<div class="bar-h ${MODEL_CLASS[m]}"><div class="track"><i style="width:${a * 100}%"></i></div><b>${pct(a)}</b></div>`; }).join("")}
      </div>`).join("");

    const compRows = (stage) => Object.entries(rep.by_competition).map(([comp, stages]) => {
      const row = stages[stage]; const best = Math.max(...models.map((m) => row[m].accuracy));
      return `<tr><td>${esc(comp)} <span class="n">· ${row[models[0]].matches} matches</span></td>${models.map((m) => `<td class="${row[m].accuracy === best ? "best" : ""}">${pct(row[m].accuracy)}</td>`).join("")}</tr>`;
    }).join("");

    const prog = Object.entries(rep.t20_progress).map(([label, row]) => `
      <div class="stage-group"><h4>${esc(label)}</h4>
        ${["original_formula", chosen].map((m) => `<div class="bar-h ${MODEL_CLASS[m]}"><div class="track"><i style="width:${row[m].accuracy * 100}%"></i></div><b>${pct(row[m].accuracy)}</b></div>`).join("")}
      </div>`).join("");

    const cal = rep.calibration;
    const calCols = Array.from({ length: 10 }, (_, i) => cal.find((c) => c.bucket.startsWith(`${i * 10}`)) || null);
    const calChart = `<div class="cal-chart">${calCols.map((c) => c ? `<div class="cal-col" title="${esc(c.bucket)}: said ${c.predicted}% · actually ${c.actual}% (${c.matches} matches)"><i class="pred" style="height:${c.predicted}%"></i><i class="act" style="height:${c.actual}%"></i></div>` : `<div class="cal-col"></div>`).join("")}</div>
      <div class="cal-labels">${calCols.map((_, i) => `<span>${i * 10}–${i * 10 + 10}%</span>`).join("")}</div>`;
    const worst = cal.reduce((a, c) => (Math.abs(c.predicted - c.actual) > Math.abs(a.predicted - a.actual) ? c : a), cal[0]);

    const versions = [...accCache.versions].reverse();
    const versionRows = versions.map((v, i) => `<tr class="${i === 0 ? "app" : ""}">
      <td>${esc(fd(v.trained_at))}<br><span class="n">${esc(v.label)}</span></td>
      <td>${esc(v.model)}</td><td>${esc(fd(v.data_through))}<br><span class="n">${v.test_matches} test matches</span></td>
      <td>${pct(v.accuracy_all_states)}</td><td>${pct(v.accuracy_innings_break)}</td><td>${pct(v.accuracy_ipl_innings_break)}</td>
      <td>${pct(v.formula_accuracy_all_states)}</td></tr>`).join("");

    const imp = Object.entries(rep.feature_importance).filter(([, v]) => v >= 0.5);
    const maxImp = Math.max(...imp.map(([, v]) => v));
    const impBars = imp.map(([k, v]) => `<div class="bar-h m3 imp"><span class="small">${esc(FEATURE_NAMES[k] || k)}</span><div class="track"><i style="width:${v / maxImp * 100}%"></i></div><b>${v.toFixed(0)}%</b></div>`).join("");

    const fit = Object.entries(rep.fit_check).map(([split, row]) => `<tr><td>${esc(split)}</td>${["logistic_regression", "lightgbm", "ensemble_lr_lgbm"].map((m) => `<td>${pct(row[m])}</td>`).join("")}</tr>`).join("");

    $("#acc-body").innerHTML = `
      <div class="cards-4">${cards}</div>
      <p class="muted small" style="margin-top:12px">“% correct” = how often the team the model favoured actually won, averaged over every point of the first innings.</p>

      <section class="panel section">
        <h2>Accuracy at each stage of the match</h2>
        <p class="muted">Predictions get easier as more of the first innings is known.</p>
        ${legend}<div class="stage-groups">${stageGroups}</div>
      </section>

      <section class="panel section">
        <h2>By competition</h2>
        <p class="muted">★ marks the best model on each row. Associate matches (e.g. Nepal v Oman) are easier because one side is usually much stronger.</p>
        <div class="seg-tabs" id="acc-stage-tabs">${Object.entries(rep.stages).map(([k, l]) => `<button type="button" data-stage="${k}" class="${k === accStage ? "active" : ""}">${esc(l)}</button>`).join("")}</div>
        <div class="table-wrap"><table class="acc"><thead><tr><th>Competition</th>${models.map((m) => `<th>${esc(names[m])}</th>`).join("")}</tr></thead><tbody id="comp-body">${compRows(accStage)}</tbody></table></div>
      </section>

      <div class="two-col">
        <section class="panel section">
          <h2>Gets sharper as the innings goes on</h2>
          <p class="muted">T20 matches: the app's model vs the old formula.</p>
          <div class="legend"><span class="m0"><i></i>Old formula</span><span class="m3"><i></i>${esc(names[chosen])}</span></div>
          ${prog}
        </section>
        <section class="panel section">
          <h2>Can you trust the percentages?</h2>
          <p class="muted">At the innings break: what the model said (grey) vs how often that team really won (colour).</p>
          ${calChart}
          <div class="callout" style="margin-top:14px">When the model says <b>80–90%</b>, the team won <b>${esc(cal.find((c) => c.bucket.startsWith("80"))?.actual ?? "–")}%</b> of the time. The biggest gap is in the ${esc(worst.bucket)} group (${worst.predicted}% said vs ${worst.actual}% actual, ${worst.matches} matches).</div>
        </section>
      </div>

      ${tossSection(rep)}

      ${chaseAccuracySection()}

      ${scoreAccuracySection()}

      <section class="panel section">
        <h2>Model versions over time</h2>
        <p class="muted">Every retrain is recorded here. Newest first. Earlier versions were tested on fewer matches, so compare with care.</p>
        <div class="table-wrap"><table class="acc"><thead><tr><th>When</th><th>Model</th><th>Data up to</th><th>Overall</th><th>Innings break</th><th>IPL innings break</th><th>Old formula</th></tr></thead><tbody>${versionRows}</tbody></table></div>
      </section>

      <div class="two-col">
        <section class="panel section">
          <h2>What the model pays attention to</h2>
          <p class="muted">Share of LightGBM's decisions driven by each input.</p>
          ${impBars}
        </section>
        <section class="panel section">
          <h2>Is it just memorising?</h2>
          <p class="muted">If a model only memorised its training matches, accuracy would drop on new matches. It doesn't.</p>
          <div class="table-wrap"><table class="acc"><thead><tr><th>Matches</th><th>Logistic reg.</th><th>LightGBM</th><th>Ensemble</th></tr></thead><tbody>${fit}</tbody></table></div>
        </section>
      </div>

      <section class="panel section">
        <h2>Plain-English glossary</h2>
        <div class="glossary" style="margin-top:14px">
          <div><b>Accuracy</b>How often the team given more than 50% actually won.</div>
          <div><b>Unseen test matches</b>Matches from ${esc(rep.split.test.label)}. The models learned only from matches ${esc(rep.split.train.label)}, so this is a fair exam.</div>
          <div><b>Ensemble</b>Two models whose answers are averaged. It's steadier than either one alone.</div>
          <div><b>Elo rating</b>A team strength score that goes up when a team wins and down when it loses.</div>
          <div><b>Par score</b>The average first-innings score at that venue in its recent games.</div>
          <div><b>Baseline</b>The original hand-written formula, kept to show how much the ML models improve.</div>
        </div>
      </section>`;

    $("#acc-stage-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      accStage = b.dataset.stage;
      $$("#acc-stage-tabs button").forEach((x) => x.classList.toggle("active", x === b));
      $("#comp-body").innerHTML = compRows(accStage);
    });
  }

  // "Does the toss matter?": real toss outcomes from the data, plus why it isn't in the model
  function tossSection(rep) {
    const t = rep.toss || {};
    const rows = Object.entries(t);
    if (!rows.length) return "";
    const all = t["All matches · all years"] || rows[0][1];
    const ipl = t["IPL · since 2023"] || t["IPL · all years"];
    const bar = (v, cls) => `<div class="bar-h ${cls}"><div class="track"><i style="width:${v}%"></i></div><b>${v}%</b></div>`;
    return `
      <section class="panel section toss">
        <h2>Does the toss matter?</h2>
        <p class="muted">Barely. The toss winner wins <b>${all.toss_winner_won}%</b> of ${all.matches.toLocaleString()} matches, almost a coin flip.
          We tested adding the toss to the model and it made no difference, so the predictions don't use it.</p>
        <div class="toss-grid">
          <div class="toss-stat"><span class="toss-big">${all.toss_winner_won}%</span><span>toss winners who won the match</span></div>
          <div class="toss-stat"><span class="toss-big">${all.won_when_chose_bowl}%</span><span>won after choosing to bowl first</span></div>
          <div class="toss-stat"><span class="toss-big">${all.won_when_chose_bat}%</span><span>won after choosing to bat first</span></div>
          ${ipl ? `<div class="toss-stat"><span class="toss-big">${ipl.chose_to_bowl}%</span><span>of IPL captains now choose to bowl (since 2023)</span></div>` : ""}
        </div>
        <div class="table-wrap"><table class="acc"><thead><tr><th>Competition</th><th>Matches</th><th>Toss winner won</th><th>Chose to bowl</th><th>Won after batting</th><th>Won after bowling</th></tr></thead>
          <tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.matches.toLocaleString()}</td><td>${v.toss_winner_won}%</td><td>${v.chose_to_bowl}%</td><td>${v.won_when_chose_bat ?? "–"}%</td><td>${v.won_when_chose_bowl ?? "–"}%</td></tr>`).join("")}</tbody></table></div>
      </section>`;
  }

  // projected-score model report (accuracy page)
  function scoreAccuracySection() {
    const s = accCache?.score;
    if (!s) return "";
    const rows = Object.entries(s.slices).map(([k, r]) => {
      const best = Math.min(r.model.mae, r.current_rate.mae, r.venue_par.mae);
      const cell = (v) => `<td class="${v === best ? "best" : ""}">±${v}</td>`;
      return `<tr><td>${esc(k)} <span class="n">· ${r.model.states.toLocaleString()} states</span></td>${cell(r.model.mae)}${cell(r.current_rate.mae)}${cell(r.venue_par.mae)}<td>${r.model.within_10}%</td><td>${r.model.coverage_80}%</td><td>±${Math.round(r.model.avg_width / 2)}</td></tr>`;
    }).join("");
    const t20 = s.slices["All T20 states"]; const odi = s.slices["All ODI states"];
    return `
      <div class="hero" style="padding-top:36px">
        <p class="eyebrow">First innings</p>
        <h1 style="font-size:clamp(1.5rem,3vw,2.2rem)">Projected score</h1>
        <p class="lede">How close the projected total gets to the real final score, on <b>${s.test_innings.toLocaleString()} first innings</b> (${esc(s.test_period.replace(" to ", " → "))}) it never saw.</p>
      </div>
      <div class="toss-grid">
        <div class="toss-stat"><span class="toss-big">±${t20.model.mae}</span><span>typical miss in T20s (current-rate method: ±${t20.current_rate.mae})</span></div>
        <div class="toss-stat"><span class="toss-big">±${odi.model.mae}</span><span>typical miss in ODIs (current-rate method: ±${odi.current_rate.mae})</span></div>
        <div class="toss-stat"><span class="toss-big">${t20.model.coverage_80}%</span><span>of T20 finals landed inside the "likely" range (aim: 80%)</span></div>
      </div>
      <section class="panel section">
        <h2>Typical miss at each stage</h2>
        <p class="muted">Average gap between the projection and the real final total. ★ marks the closest method. "Current rate" is the usual "at this rate they'll make…" number.</p>
        <div class="table-wrap"><table class="acc"><thead><tr><th>Stage</th><th>This model</th><th>Current rate</th><th>Venue par</th><th>Within 10 runs</th><th>In likely range</th><th>Range ±</th></tr></thead><tbody>${rows}</tbody></table></div>
      </section>`;
  }

  // live chase model report (shown inside the accuracy page)
  const CHASE_CLASS = { simple_chase: "m0", logistic_regression: "m1", lightgbm: "m2", ensemble_lr_lgbm: "m3" };
  function chaseAccuracySection() {
    const c = accCache?.chase;
    if (!c) return `<section class="panel section"><h2>Live chase model</h2><p class="muted">Not trained yet. Go to <a href="#data">Data</a> and press Retrain model.</p></section>`;
    const models = c.shown_models; const names = c.model_names; const all = c.by_competition["All chases"];
    const best = models.reduce((a, m) => (c.overall[m].accuracy > c.overall[a].accuracy ? m : a), models[0]);
    const cards = models.map((m) => `
      <article class="panel model-card ${m === c.chosen ? "chosen" : ""} ${CHASE_CLASS[m]}">
        ${m === c.chosen ? `<span class="tag">Used in app</span>` : m === "simple_chase" ? `<span class="tag base">Baseline</span>` : ""}
        <h3>${esc(names[m])}</h3><p>${esc(c.model_blurbs[m] || "")}</p>
        <div class="big-num">${(c.overall[m].accuracy * 100).toFixed(1)}<small>% correct${m === best ? " · best" : ""}</small></div>
        <div class="meter"><i style="width:${c.overall[m].accuracy * 100}%"></i></div>
        ${Object.entries(c.phases).map(([k, l]) => `<div class="kv"><span>${esc(l)}</span><b>${pct(all[k][m].accuracy)}</b></div>`).join("")}
      </article>`).join("");
    const rows = (phase) => Object.entries(c.by_competition).map(([comp, ph]) => {
      const row = ph[phase]; const top = Math.max(...models.map((m) => row[m].accuracy));
      return `<tr><td>${esc(comp)} <span class="n">· ${row[models[0]].matches} chases</span></td>${models.map((m) => `<td class="${row[m].accuracy === top ? "best" : ""}">${pct(row[m].accuracy)}</td>`).join("")}</tr>`;
    }).join("");
    const overs = (obj) => Object.entries(obj).map(([label, row]) => `<div class="stage-group"><h4>${esc(label)}</h4>
      ${["simple_chase", c.chosen].map((m) => `<div class="bar-h ${CHASE_CLASS[m]}"><div class="track"><i style="width:${row[m].accuracy * 100}%"></i></div><b>${pct(row[m].accuracy)}</b></div>`).join("")}</div>`).join("");
    const versions = [...(c.versions || [])].reverse().map((v) => `<tr><td>${esc(fd(v.trained_at))}<br><span class="n">${esc(v.label)}</span></td><td>${esc(v.model)}</td><td>${esc(fd(v.data_through))}<br><span class="n">${v.test_chases} test chases</span></td><td>${pct(v.accuracy)}</td><td>${pct(v.simple_accuracy)}</td></tr>`).join("");
    setTimeout(() => {
      const tabs = $("#chase-phase-tabs"); if (!tabs) return;
      tabs.addEventListener("click", (e) => {
        const b = e.target.closest("button"); if (!b) return;
        $$("#chase-phase-tabs button").forEach((x) => x.classList.toggle("active", x === b));
        $("#chase-comp-body").innerHTML = rows(b.dataset.phase);
      });
    });
    return `
      <div class="hero" style="padding-top:36px">
        <p class="eyebrow">Second innings</p>
        <h1 style="font-size:clamp(1.5rem,3vw,2.2rem)">Live chase model</h1>
        <p class="lede">Predicts whether the chasing side gets there, from the target, runs, wickets and balls left. Tested on <b>${c.split.test.toLocaleString()} chases</b> (${esc(c.test_period.replace(" to ", " → "))}) it never saw.</p>
      </div>
      <div class="cards-4">${cards}</div>
      <p class="muted small" style="margin-top:12px">“% correct” is averaged over every over of each chase. The baseline knows only runs needed, balls left and wickets in hand.</p>
      <section class="panel section">
        <h2>Chase accuracy by competition</h2>
        <p class="muted">★ marks the best model on each row.</p>
        <div class="seg-tabs" id="chase-phase-tabs">${Object.entries(c.phases).map(([k, l]) => `<button type="button" data-phase="${k}" class="${k === "late" ? "active" : ""}">${esc(l)}</button>`).join("")}</div>
        <div class="table-wrap"><table class="acc"><thead><tr><th>Competition</th>${models.map((m) => `<th>${esc(names[m])}</th>`).join("")}</tr></thead><tbody id="chase-comp-body">${rows("late")}</tbody></table></div>
      </section>
      <div class="two-col">
        <section class="panel section"><h2>T20 chases, over by over</h2><p class="muted">Baseline (grey) vs the app's model.</p>${overs(c.t20_overs)}</section>
        <section class="panel section"><h2>ODI chases, over by over</h2><p class="muted">Baseline (grey) vs the app's model.</p>${overs(c.odi_overs)}</section>
      </div>
      <section class="panel section">
        <h2>Chase model versions</h2>
        <div class="table-wrap"><table class="acc"><thead><tr><th>When</th><th>Model</th><th>Data up to</th><th>Accuracy</th><th>Baseline</th></tr></thead><tbody>${versions}</tbody></table></div>
      </section>`;
  }

  // ------------------------------------------------------------------ history
  // ---- history: every saved prediction, checked against the real result
  let histData = null; let histFilter = "all";
  // History's Yours / Model checks / Both switch: remembered on this device, sent with every History request
  let histSource = (() => { try { return ["yours", "model"].includes(localStorage.getItem("cwp.histSource")) ? localStorage.getItem("cwp.histSource") : "both"; } catch { return "both"; } })();
  const SOURCES = [["both", "Both"], ["yours", "Your predictions"], ["model", "Model checks"]];
  const sourceTabs = () => `<div class="seg-tabs hist-source" id="hist-source" role="group" aria-label="Show which predictions">${SOURCES
    .map(([k, l]) => `<button type="button" data-hsrc="${k}" class="${k === histSource ? "active" : ""}">${l}</button>`).join("")}</div>`;
  const OUTCOME = {
    right: ["✓", "Right", "right"], wrong: ["✗", "Wrong", "wrong"], waiting: ["⏳", "Waiting for result", "waiting"],
    unmatched: ["–", "No real match found", "none"], no_result: ["–", "No result / tie", "none"],
  };
  // Open a saved prediction on the Predict page with everything as it was: mode, teams, ground, format, conditions,
  // par, XIs and the score. A first-innings prediction opens on the first innings (then "Start the chase" carries
  // on); a chase opens on the chase at the saved score. Older predictions without a stored setup are matched by
  // team and ground names, with each team's latest XI.
  async function openFromHistory(h) {
    const s = h.setup || {};
    const mode = s.mode || h.mode || state.mode;
    location.hash = "#predict";
    if (mode !== state.mode || !state.config) { $$(".mode-switch button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode)); await setMode(mode); }
    if (!state.config) return;
    const byName = (name) => state.config.teams.find((t) => t.name === name)?.code;
    const bat = s.batting && team(s.batting).squad.length ? s.batting : byName(h.batting_first_team);
    const chs = s.chasing && team(s.chasing).squad.length ? s.chasing : byName(h.chasing_team);
    if (!bat || !chs) { toast("Those teams aren't in this season's team list any more."); return; }
    state.format = String(s.format || h.format || "t20").toLowerCase() === "odi" ? "odi" : "t20";
    $$(".segmented [data-format]").forEach((x) => x.classList.toggle("active", x.dataset.format === state.format));
    state.batting = bat; state.chasing = chs; resetXI();
    const squadHas = (side, names) => names.every((n) => team(side === "bat" ? bat : chs).squad.some((p) => p.name === n));
    if (Array.isArray(s.batting_xi) && s.batting_xi.length && squadHas("bat", s.batting_xi)) state.xi.bat = [...s.batting_xi];
    if (Array.isArray(s.chasing_xi) && s.chasing_xi.length && squadHas("chase", s.chasing_xi)) state.xi.chase = [...s.chasing_xi];
    // the batting order you dragged comes back too (only when that saved XI was restored)
    state.order.bat = !!s.batting_order_set && state.xi.bat.join() === (s.batting_xi || []).join();
    state.order.chase = !!s.chasing_order_set && state.xi.chase.join() === (s.chasing_xi || []).join();
    if (s.batting_impact) state.impact.bat = s.batting_impact;
    if (s.chasing_impact) state.impact.chase = s.chasing_impact;
    const v = (s.venue && state.config.venues.find((x) => x.code === s.venue)) || state.config.venues.find((x) => x.name === h.venue);
    if (v) { state.venue = v.code; state.country = "all"; }
    state.pitch = s.pitch || h.pitch || "balanced"; state.dew = s.dew || h.dew || "none";
    state.par = s.par || null;
    fillSelects(); renderCountries(); syncConditions(); syncPar(); renderXI();
    const toBalls = (ov) => parseOvers(String(ov ?? ""));
    if (h.type === "chase") {
      const target = Number(s.target || h.target) || (Number(h.first_innings_score) + 1);
      state.runs = target - 1; state.wickets = Number(s.first_wickets ?? 10) || 10; state.balls = maxBalls();
      syncScore();
      chase.target = target;
      const m = String(h.chase_score || "").match(/(\d+)\/(\d+)\s*\(([\d.]+)\)/);
      const runs = s.runs ?? (m ? +m[1] : 0), wk = s.wickets ?? (m ? +m[2] : 0), ov = s.overs ?? (m ? m[3] : 0);
      setStage("chase");
      Object.assign(chase, { runs: Number(runs) || 0, wickets: Number(wk) || 0, balls: toBalls(ov), undo: [], timeline: [] });
      saveChase(); syncChase(); predictChase(false);
      toast(`Opened: ${team(chs).name} chasing ${target}. Update the score as the chase goes on.`);
    } else {
      state.runs = Number(s.runs ?? h.first_innings_score) || 0;
      state.wickets = Number(s.wickets ?? h.wickets ?? 0) || 0;
      state.balls = (s.overs ?? h.overs) != null ? toBalls(s.overs ?? h.overs) : maxBalls();
      setStage("first"); syncScore(); predict(false);
      toast(`Opened: ${team(bat).name} v ${team(chs).name}. ${state.balls >= maxBalls() || state.wickets >= 10 ? "Press Start the chase to carry on." : "Carry on ball by ball."}`);
    }
    $("#predict-form").scrollIntoView({ behavior: NO_MOTION ? "auto" : "smooth", block: "start" });
  }
  let histBackups = [];
  async function loadHistory() {
    try { histData = await api("/api/history", PUBLIC ? {} : undefined); } catch (err) { $("#history-body").innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
    if (!PUBLIC) { try { histBackups = (await api("/api/history/backups")).backups || []; } catch { histBackups = []; } }
    renderHistory();
  }
  // backups of the saved predictions (a copy a day, and one before every Clear all): list + Restore
  function backupsHTML() {
    if (PUBLIC || !histBackups.length) return "";
    return `<details class="panel hist-backups"><summary><b>Backups</b> <span class="muted small">· ${histBackups.length} saved cop${histBackups.length === 1 ? "y" : "ies"} of your predictions</span></summary>
      <p class="muted small">The app keeps a copy once a day, and another just before a <b>Clear all</b>. Restoring one replaces the list above (the current list is backed up first).</p>
      <ul class="bk-list">${histBackups.map((b) => `<li><span><b>${esc(b.when)}</b> · ${esc(b.why)}</span><span class="muted small">${b.count} prediction${b.count === 1 ? "" : "s"}</span>
        <button type="button" class="chip-btn" data-restore-backup="${esc(b.name)}" data-count="${b.count}">Restore</button></li>`).join("")}</ul></details>`;
  }
  function renderHistory() {
    const { items, summary: s } = histData;
    $("#clear-history").hidden = !items.length;
    if (!items.length) {
      const msg = histSource === "model" ? "No model checks yet. Use Fetch older matches on the Replay page, or Last 5, to add some."
        : `No predictions yet. <a href="#predict">Make your first one →</a>`;
      $("#history-body").innerHTML = `${histSource === "both" ? "" : sourceTabs()}<div class="panel empty">${msg}</div>${backupsHTML()}`; return;
    }
    const tile = (label, sc, sub) => `<div class="score-tile">
        <span class="score-big">${sc.pct == null ? "–" : `${sc.pct}%`}</span>
        <span class="score-label">${label}</span>
        <span class="score-sub">${sc.checked ? `${sc.right} right of ${sc.checked} checked` : sub}</span></div>`;
    // one card per match: saves of the same match (same teams, format and day) together, newest first
    const groups = [];
    const byKey = new Map();
    items.forEach((h) => {
      const k = h.match_key || h.timestamp;
      if (!byKey.has(k)) { const g = []; byKey.set(k, g); groups.push(g); }
      byKey.get(k).push(h);
    });
    const shownGroups = groups.filter((g) => histFilter === "all" || (histFilter === "checked" ? ["right", "wrong"].includes(g[0].outcome.status) : g[0].outcome.status === "waiting"));
    const nChecked = groups.filter((g) => ["right", "wrong"].includes(g[0].outcome.status)).length;
    const nWaiting = groups.filter((g) => g[0].outcome.status === "waiting").length;
    // pie of how every saved prediction went
    const tally = { right: 0, wrong: 0, waiting: 0, other: 0 };
    const counted = items.filter((h) => h.counted !== false);
    counted.forEach((h) => { const st = h.outcome.status; tally[st in tally ? st : "other"] += 1; });
    const PIE = [["right", "Right", "var(--good)"], ["wrong", "Wrong", "var(--bad)"], ["waiting", "Waiting for result", "#f2b631"], ["other", "No result / not matched", "var(--faint)"]];
    const R = 54, C = 2 * Math.PI * R; let acc = 0;
    const arcs = PIE.filter(([k]) => tally[k]).map(([k, label, col]) => {
      const len = (tally[k] / counted.length) * C; const off = -acc; acc += len;
      return `<circle cx="70" cy="70" r="${R}" class="pie-arc" style="stroke:${col};stroke-dasharray:${len.toFixed(2)} ${(C - len).toFixed(2)};stroke-dashoffset:${off.toFixed(2)}"><title>${label}: ${tally[k]} of ${counted.length}</title></circle>`;
    }).join("");
    const checked = tally.right + tally.wrong;
    const pieHTML = `<div class="hist-pie" role="img" aria-label="${tally.right} right, ${tally.wrong} wrong, ${tally.waiting} waiting, ${tally.other} with no result, of ${counted.length} predictions">
        <svg viewBox="0 0 140 140" aria-hidden="true"><circle cx="70" cy="70" r="${R}" class="pie-track"/><g transform="rotate(-90 70 70)">${arcs}</g>
          <text x="70" y="${checked ? 68 : 74}" text-anchor="middle" class="pie-big">${checked ? `${Math.round(tally.right / checked * 100)}%` : "–"}</text>
          ${checked ? `<text x="70" y="86" text-anchor="middle" class="pie-sub">right</text>` : ""}</svg>
        <ul class="pie-legend">${PIE.map(([k, label, col]) => `<li class="${tally[k] ? "" : "zero"}"><i style="background:${col}"></i><span>${label}</span><b>${tally[k]}</b></li>`).join("")}
          <li class="pie-total" title="One per match: a match saved several times counts once, by your latest save"><span>Matches counted</span><b>${counted.length}</b></li></ul>
      </div>`;
    $("#history-body").innerHTML = `
      ${sourceTabs()}
      <section class="panel score-card">
        <div class="score-head"><div>${(() => {
            // with the model's own checks in the record, say so: it is no longer only your predictions
            const mc = counted.filter((h) => h.auto).length, yours = counted.length - mc;
            return mc
              ? `<p class="eyebrow">Your record + model checks</p><h2>How often were the predictions right?</h2>
                 <p class="muted small"><b>${yours}</b> of your predictions and <b>${mc}</b> model check${mc === 1 ? "" : "s"} (the model's own call at the innings break on matches you didn't predict), one per match.</p>`
              : `<p class="eyebrow">Your record</p><h2>How often were your predictions right?</h2>`;
          })()}
          <p class="muted small">Checked automatically against real results in the match data (up to ${esc(s.data_through ? fd(s.data_through) : "–")}), or against results you set yourself.</p></div>${pieHTML}</div>
        <div class="score-grid">
          ${tile("All predictions", s.all, "Nothing checked yet")}
          ${tile("First innings", s.first_innings, "Nothing checked yet")}
          ${tile("Live chase", s.live_chase, "Nothing checked yet")}
          <div class="score-tile muted-tile"><span class="score-big">${s.waiting}</span><span class="score-label">Waiting for a result</span>
            <span class="score-sub">${s.waiting ? `<a href="#data">Download the latest data</a> to check them` : "All caught up"}</span></div>
        </div>
      </section>
      ${formatPiesHTML(counted)}
      ${trackerHTML(s.tracker, s.all)}
      ${pitchCallsHTML(s.pitch)}
      <div class="seg-tabs" id="hist-filter">${[["all", `All matches (${groups.length})`], ["checked", `Checked (${nChecked})`], ["waiting", `Waiting (${nWaiting})`]]
        .map(([k, l]) => `<button type="button" data-hf="${k}" class="${k === histFilter ? "active" : ""}">${l}</button>`).join("")}</div>
      <div class="hist-list">${shownGroups.length ? datedListHTML(shownGroups) : `<div class="panel empty">Nothing here.</div>`}</div>
      ${backupsHTML()}`;
  }
  // ---- prediction tracker: your own hit rate by stage, confidence, competition and team, and over time
  function trackerHTML(t, all) {
    if (!t) return "";
    const n = all.checked;
    const pct = (v) => (v == null ? "–" : `${v}%`);
    const bar = (v, model) => `<span class="tk-bar"><i style="width:${v ?? 0}%"></i>${model != null ? `<b style="left:${model}%" title="Model on unseen matches: ${model}%"></b>` : ""}</span>`;
    // running hit-rate chart
    const tl = t.timeline || [];
    let chart = `<p class="muted small">The chart appears once two predictions have been checked.</p>`;
    if (tl.length >= 2) {
      const W = 1180, H = 230, padL = 40, padR = 12, padT = 14, padB = 26;
      const x = (i) => padL + (i / (tl.length - 1)) * (W - padL - padR);
      const y = (v) => padT + (1 - v / 100) * (H - padT - padB);
      const line = tl.map((p, i) => `${x(i).toFixed(1)},${y(p.pct).toFixed(1)}`).join(" ");
      const ref = t.model_pct?.innings_break;
      chart = `<svg class="tk-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Your running hit rate">
        ${[0, 50, 100].map((v) => `<line x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${padL - 6}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join("")}
        ${ref ? `<line x1="${padL}" x2="${W - padR}" y1="${y(ref)}" y2="${y(ref)}" class="ref"/><text x="${W - padR}" y="${y(ref) - 5}" text-anchor="end" class="ref-t">model at the innings break ${ref}%</text>` : ""}
        <polyline points="${line}" class="run"/>
        ${tl.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.pct).toFixed(1)}" r="4" class="${p.right ? "ok" : "no"}"><title>${esc(fd(p.date))}: ${p.right ? "right" : "wrong"} · running ${p.pct}%</title></circle>`).join("")}
        <text x="${padL}" y="${H - 6}">1st</text><text x="${W - padR}" y="${H - 6}" text-anchor="end">${tl.length}th checked</text>
      </svg>`;
    }
    const stageRows = t.by_stage.map((r) => `<div class="tk-row"><span>${esc(r.label)}</span>${bar(r.pct, t.model_pct?.[r.key])}
      <b>${pct(r.pct)}</b><small>${r.checked ? `${r.right}/${r.checked}` : "none yet"}${t.model_pct?.[r.key] != null ? ` · model ${t.model_pct[r.key]}%` : ""}</small></div>`).join("");
    const confRows = t.by_confidence.map((r) => `<div class="tk-row"><span>Said ${esc(r.label)}</span>${bar(r.pct, r.expected)}
      <b>${pct(r.pct)}</b><small>${r.checked ? `${r.right}/${r.checked} right` : "none yet"}</small></div>`).join("");
    const modeRows = t.by_mode.map((r) => `<div class="tk-row"><span>${esc(r.label)}</span>${bar(r.pct)}<b>${pct(r.pct)}</b><small>${r.checked ? `${r.right}/${r.checked}` : "none yet"}</small></div>`).join("");
    const teamRows = t.by_team.length ? t.by_team.map((r) => `<tr><td><span class="fd-team">${badgeHTML(r.team)}${esc(r.team)}</span></td><td>${r.right}/${r.checked}</td><td><b>${pct(r.pct)}</b></td></tr>`).join("")
      : `<tr><td colspan="3" class="muted">No checked matches yet.</td></tr>`;
    return `<section class="panel section tracker">
      <div class="row-between"><div><p class="eyebrow">Tracker</p><h2>How your predictions are doing</h2></div>
        ${t.streak >= 2 ? `<span class="tk-streak">🔥 ${t.streak} right in a row</span>` : ""}</div>
      ${n < 10 ? `<p class="tk-note">Early days: ${n} checked prediction${n === 1 ? "" : "s"} so far. With fewer than 10 these numbers swing a lot; save predictions on real matches (before the match, at the innings break, during chases) and they'll settle.</p>` : ""}
      ${chart}
      <div class="tk-grid">
        <div><h3 class="sub">By stage <small class="muted">· line = model on unseen matches</small></h3>${stageRows}</div>
        <div><h3 class="sub">By confidence <small class="muted">· line = what it said on average</small></h3>${confRows}
          <p class="muted small">If the model is honest, the "70–80%" row should be right about 75% of the time.</p></div>
        <div><h3 class="sub">By competition</h3>${modeRows}</div>
        <div><h3 class="sub">By team <small class="muted">· matches involving them</small></h3>
          <div class="table-wrap"><table class="fd-table"><tbody>${teamRows}</tbody></table></div></div>
      </div>
    </section>`;
  }
  // ---- your pitch calls (Flat / Green / Dry / Slow) against what the first innings actually made
  function pitchCallsHTML(p) {
    if (!p || !Object.keys(p.by_call || {}).length) return "";
    const rows = Object.entries(p.by_call).map(([k, r]) => {
      const n = r.right + r.wrong;
      return `<div class="tk-row"><span>${esc(r.label)}</span><span class="tk-bar"><i style="width:${n ? Math.round(r.right / n * 100) : 0}%"></i></span>
        <b>${n ? `${Math.round(r.right / n * 100)}%` : "–"}</b><small>${r.right}/${n} right${r.par ? ` · ${r.par} about par` : ""}</small></div>`;
    }).join("");
    const n = p.right + p.wrong;
    return `<section class="panel section tracker pitch-calls">
      <div><p class="eyebrow">Pitch calls</p><h2>Were the pitch calls right?</h2>
      <p class="muted small">A flat call is right when the first innings beat the ground's usual par by more than 5 runs; a green, dry or slow call is right when it fell more than 5 short. Within 5 runs counts as about par and isn't counted. Only matches where the full first-innings total was saved are checked.</p></div>
      ${n < 15 ? `<p class="tk-note">${n} checked call${n === 1 ? "" : "s"} so far. Once there are 30 or more, these show whether the pitch adjustments (Data tab → Tuning) need changing.</p>` : ""}
      ${rows}
    </section>`;
  }
  // a match card: the latest save, with every earlier save of the same match listed inside
  function saveWhen(h) {
    if (h.type === "chase") return `Chase ${h.chase_score || ""}`.trim();
    const st = h.stage || "";
    if (st === "pre_match") return "Before the match";
    if (st === "innings_break") return `Innings break · ${h.first_innings_score}${h.wickets != null ? `/${h.wickets}` : ""}`;
    if (st === "mid_innings") return `1st innings · ${h.first_innings_score}/${h.wickets ?? "?"} after ${h.overs ?? "?"} overs`;
    return `${h.first_innings_score ?? ""}`;
  }
  // ---- one pie per kind of match (T20 internationals, IPL, ODIs): how the predictions and model checks went
  const KIND_OF = (h) => (h.mode === "ipl" ? "ipl" : String(h.format || "").toUpperCase() === "ODI" ? "odi" : "t20i");
  function formatPiesHTML(counted) {
    const KINDS = [["t20i", "T20 internationals"], ["ipl", "IPL"], ["odi", "ODIs"]];
    const COLS = [["right", "Right", "var(--good)"], ["wrong", "Wrong", "var(--bad)"], ["waiting", "Waiting", "#f2b631"], ["other", "No result", "var(--faint)"]];
    const R = 44, C = 2 * Math.PI * R;
    const pie = ([kind, label]) => {
      const list = counted.filter((h) => KIND_OF(h) === kind);
      const tally = { right: 0, wrong: 0, waiting: 0, other: 0 };
      list.forEach((h) => { const st = h.outcome.status; tally[st in tally ? st : "other"] += 1; });
      const checked = tally.right + tally.wrong; let acc = 0;
      const arcs = list.length ? COLS.filter(([k]) => tally[k]).map(([k, l, col]) => {
        const len = (tally[k] / list.length) * C; const off = -acc; acc += len;
        return `<circle cx="56" cy="56" r="${R}" class="pie-arc" style="stroke:${col};stroke-dasharray:${len.toFixed(2)} ${(C - len).toFixed(2)};stroke-dashoffset:${off.toFixed(2)}"><title>${l}: ${tally[k]} of ${list.length}</title></circle>`;
      }).join("") : "";
      return `<div class="fmt-pie" role="img" aria-label="${esc(label)}: ${tally.right} right, ${tally.wrong} wrong, ${tally.waiting} waiting, ${tally.other} no result">
        <svg viewBox="0 0 112 112" aria-hidden="true"><circle cx="56" cy="56" r="${R}" class="pie-track"/><g transform="rotate(-90 56 56)">${arcs}</g>
          <text x="56" y="${checked ? 56 : 61}" text-anchor="middle" class="pie-big">${checked ? `${Math.round(tally.right / checked * 100)}%` : "–"}</text>
          ${checked ? `<text x="56" y="72" text-anchor="middle" class="pie-sub">right</text>` : ""}</svg>
        <div><b>${esc(label)}</b><small class="muted">${list.length ? `${tally.right} right · ${tally.wrong} wrong${tally.waiting ? ` · ${tally.waiting} waiting` : ""}${tally.other ? ` · ${tally.other} no result` : ""}` : "No matches yet"}</small>
          <small class="muted">${list.length} match${list.length === 1 ? "" : "es"}</small></div></div>`;
    };
    return `<section class="panel section fmt-pies"><p class="eyebrow">By kind of match</p>
      <div class="fmt-pie-row">${KINDS.map(pie).join("")}</div></section>`;
  }
  // ---- History list: matches by the day they were played, newest first, under date headings (Today, Yesterday, …).
  // Matches between the same two teams in one format, each within 3 weeks of the next, are labelled 1st / 2nd / 3rd
  // so a series doesn't look like the same match several times.
  const matchDay = (g) => g.reduce((d, h) => ((h.match_date || String(h.timestamp).slice(0, 10)) > d ? (h.match_date || String(h.timestamp).slice(0, 10)) : d), "");
  const latestSave = (g) => g.reduce((t, h) => (String(h.timestamp) > t ? String(h.timestamp) : t), "");
  const ordinal = (n) => `${n}${n % 10 === 1 && n % 100 !== 11 ? "st" : n % 10 === 2 && n % 100 !== 12 ? "nd" : n % 10 === 3 && n % 100 !== 13 ? "rd" : "th"}`;
  const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  function seriesLabels(groups) {  // group -> "2nd of 3 ODIs between these teams (12 Nov to 18 Nov)"
    const labels = new Map(); const open = new Map(); const runs = [];
    const asc = [...groups].sort((a, b) => (matchDay(a) < matchDay(b) ? -1 : 1));
    for (const g of asc) {
      const h = g[0];
      const k = `${[h.batting_first_team, h.chasing_team].sort().join("|")}#${String(h.format || "").toUpperCase()}`;
      const d = new Date(matchDay(g));
      const run = open.get(k);
      if (run && (d - run.last) / 864e5 <= 21) { run.groups.push(g); run.last = d; }
      else { const r = { groups: [g], last: d, fmt: String(h.format || "").toUpperCase() }; open.set(k, r); runs.push(r); }
    }
    for (const r of runs) {
      if (r.groups.length < 2) continue;
      const n = r.groups.length; const kind = r.fmt === "ODI" ? "ODIs" : r.fmt === "T20" ? "T20s" : "matches";
      const span = `${fd(matchDay(r.groups[0]))} to ${fd(matchDay(r.groups[n - 1]))}`;
      r.groups.forEach((g, i) => labels.set(g, `${ordinal(i + 1)} of ${n} ${kind} between these teams (${span})`));
    }
    return labels;
  }
  function datedListHTML(all) {
    const practice = all.filter((g) => g.some((h) => h.is_practice));
    const groups = all.filter((g) => !g.some((h) => h.is_practice));
    const sorted = [...groups].sort((a, b) => (matchDay(b) + latestSave(b)).localeCompare(matchDay(a) + latestSave(a)));
    const labels = seriesLabels(sorted);
    const today = isoDay(new Date()); const yest = isoDay(new Date(Date.now() - 864e5));
    let last = ""; let html = "";
    for (const g of sorted) {
      const day = matchDay(g);
      if (day !== last) {
        last = day;
        const when = day === today ? "Today · " : day === yest ? "Yesterday · " : "";
        html += `<h3 class="hist-day">${when}${esc(fd(day))}</h3>`;
      }
      const tag = labels.get(g);
      html += `${tag ? `<div class="hist-nth">${esc(tag)}</div>` : ""}${historyCard(g)}`;
    }
    if (practice.length) {
      const ps = [...practice].sort((a, b) => latestSave(b).localeCompare(latestSave(a)));
      html += `<h3 class="hist-day hist-practice-head">Practice runs · not counted in your record</h3>
        <p class="muted small hist-practice-note">Saves that match no real match (${esc(ps[0].find((h) => h.is_practice)?.practice_reason || "no real match found")}). If one was a real match the data doesn't have, press <b>Count as a real match</b>.</p>`
        + ps.map((g) => historyCard(g)).join("");
    }
    return html;
  }
  function historyCard(g) {
    let card = historyItem(g[0]);
    if (g[0].auto) {  // the model's own check of a match (from CricketData): not a save of yours, so nothing to open, edit or delete
      card = card.replace(/(<span>)[^<]*?( · [A-Z0-9]+ · )/, `$1${esc(fd(String(g[0].timestamp).slice(0, 10)))}$2`)
        .replace(/<div class="hist-actions">[\s\S]*?<\/details><\/div>/,
          `<div class="hist-actions"><span class="hist-auto">Model check · the model's own call at the innings break, ${String(g[0].match_id || "").startsWith("cs:") ? "from your downloaded match data" : "result from CricketData"}</span></div>`);
    }
    if (g.length < 2) return card;
    const pct = (h) => Math.round(h.predicted_winner === h.batting_first_team ? h.batting_first_win_probability : h.chasing_win_probability);
    const rows = g.map((h, i) => `<li class="${i === 0 ? "now" : ""}"><span class="hu-time">${esc(String(h.timestamp).slice(11, 16))}</span>
        <span class="hu-when">${esc(saveWhen(h))}</span><span class="hu-pick">${esc(h.predicted_winner)} <b>${pct(h)}%</b></span>
        <span class="hu-btns">${i === 0 ? `<i>latest</i>` : `<button type="button" class="hu-open" data-open="${esc(h.timestamp)}">Open</button>
        <button type="button" class="hu-del" data-del="${esc(h.timestamp)}" aria-label="Delete this save">&times;</button>`}</span></li>`).join("");
    const more = `<details class="hist-updates"><summary>${g.length} saves of this match <small>· how the prediction changed</small></summary><ol>${rows}</ol></details>`;
    return card.replace(/<\/article>\s*$/, `${more}</article>`);
  }
  function historyItem(h) {
    const winnerIsBat = h.predicted_winner === h.batting_first_team;
    const p = winnerIsBat ? h.batting_first_win_probability : h.chasing_win_probability;
    const [icon, label, cls] = OUTCOME[h.outcome.status] || OUTCOME.waiting;
    return `<article class="panel hist-item ${cls}">
      <div class="hist-teams">${badgeHTML(h.batting_first_team)}<span class="vs">v</span>${badgeHTML(h.chasing_team)}</div>
      <div class="hist-main"><strong>${h.type === "chase"
        ? `${esc(h.chasing_team)} ${esc(h.chase_score)} chasing ${esc(h.target)} v ${esc(h.batting_first_team)}`
        : `${esc(h.batting_first_team)} ${esc(h.first_innings_score)} v ${esc(h.chasing_team)}`}</strong>
        <span>${esc(fd(String(h.timestamp).slice(0, 16)))} · ${esc(h.format)} · ${h.type === "chase" ? "live chase · " : ""}${esc((h.model || "formula").replace(/^ML (chase )?\((.*)\)$/, "$2"))}</span>
        <span class="outcome ${cls}"><b>${icon} ${label}</b> · ${esc(h.outcome.detail || "")}${h.outcome.source === "you" ? "" : ""}</span>
        ${h.pitch_check ? `<span class="pitch-check pc-${esc(h.pitch_check.status)}"><b>Pitch call</b> · ${esc(h.pitch_check.detail)}</span>` : ""}
        <div class="hist-actions">
        ${h.type === "chase" && ["right", "wrong", "no_result"].includes(h.outcome.status) ? "" /* chase over: nothing to continue */ : `<button type="button" class="hist-open" data-open="${esc(h.timestamp)}" title="Open this prediction on the Predict page, with the same teams, ground, conditions and XIs">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>${h.type === "chase" ? "Continue chase" : "Open"}</button>`}
        <button type="button" class="hist-del" data-del="${esc(h.timestamp)}" title="Delete this prediction" aria-label="Delete this prediction">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 12.5h9l1-12.5M10 11v6M14 11v6"/></svg>Delete</button>
        ${h.auto ? "" : `<button type="button" class="chip-btn hist-practice-btn" data-practice="${h.is_practice ? 0 : 1}" data-ts="${esc(h.timestamp)}"
          title="${h.is_practice ? "It was a real match: list it by its date and count it in your record" : "Not a real match: move it to Practice runs and leave it out of your record"}">${h.is_practice ? "Count as a real match" : "Practice run"}</button>`}
        <details class="set-result"><summary>${h.outcome.source === "you" ? "Change result" : "Set result"}</summary>
          <div class="set-result-row">
            <button type="button" class="chip-btn" data-result="${esc(h.batting_first_team)}" data-ts="${esc(h.timestamp)}">${esc(h.batting_first_team)} won</button>
            <button type="button" class="chip-btn" data-result="${esc(h.chasing_team)}" data-ts="${esc(h.timestamp)}">${esc(h.chasing_team)} won</button>
            <button type="button" class="chip-btn" data-result="No result" data-ts="${esc(h.timestamp)}">No result</button>
            ${h.outcome.source === "you" ? `<button type="button" class="chip-btn danger" data-result="" data-ts="${esc(h.timestamp)}">Clear (use data)</button>` : ""}
          </div></details></div></div>
      <div class="hist-pct">${Number(p).toFixed(0)}%<small>${esc(h.predicted_winner)}</small></div>
    </article>`;
  }
  $("#history-body").addEventListener("click", async (e) => {
    const src = e.target.closest("[data-hsrc]");
    if (src) {
      histSource = src.dataset.hsrc;
      try { localStorage.setItem("cwp.histSource", histSource); } catch { /* storage unavailable */ }
      document.querySelectorAll("#hist-source button").forEach((b) => b.classList.toggle("active", b === src));
      loadHistory(); return;
    }
    const f = e.target.closest("[data-hf]");
    if (f) { histFilter = f.dataset.hf; renderHistory(); return; }
    const op = e.target.closest("[data-open]");
    if (op) { const h = (histData?.items || []).find((x) => x.timestamp === op.dataset.open); if (h) openFromHistory(h); return; }
    const bk = e.target.closest("[data-restore-backup]");
    if (bk) {
      if (!confirm(`Restore this backup (${bk.dataset.count} predictions)? Your current list is backed up first.`)) return;
      bk.disabled = true;
      try {
        const res = await api("/api/history/restore-backup", { name: bk.dataset.restoreBackup });
        histData = res; histBackups = res.backups || histBackups; renderHistory(); toast(`${res.restored} predictions restored`);
      } catch (err) { bk.disabled = false; toast(err.message); }
      return;
    }
    const del = e.target.closest("[data-del]");
    if (del) {
      del.disabled = true;
      const row = del.closest(".hist-item"); row?.classList.add("removing");
      try {
        const [res] = await Promise.all([api("/api/history/delete", { timestamp: del.dataset.del }), new Promise((r) => setTimeout(r, 220))]);
        histData = res; renderHistory();
        toastUndo("Prediction deleted", () => undoDelete(res.removed));
      } catch (err) { row?.classList.remove("removing"); del.disabled = false; toast(err.message); }
      return;
    }
    const pr = e.target.closest("[data-practice]");
    if (pr) {
      try {
        histData = await api("/api/history/practice", { timestamp: pr.dataset.ts, practice: pr.dataset.practice === "1" });
        renderHistory(); toast(pr.dataset.practice === "1" ? "Moved to Practice runs (not counted)" : "Counted as a real match");
      } catch (err) { toast(err.message); }
      return;
    }
    const b = e.target.closest("[data-result]"); if (!b) return;
    try {
      histData = await api("/api/history/result", { timestamp: b.dataset.ts, winner: b.dataset.result || null });
      renderHistory(); toast(b.dataset.result ? "Result saved" : "Using the match data again");
    } catch (err) { toast(err.message); }
  });

  async function undoDelete(removed) {
    try {
      histData = await api("/api/history/restore", { removed });
      renderHistory(); toast(removed.length === 1 ? "Prediction restored" : `${removed.length} predictions restored`);
    } catch (err) { toast(err.message); }
  }

  // ------------------------------------------------------------------ match time machine (replay a past match)
  // /api/replay/search lists past matches; /api/replay?id= gives one match over by over with the model's win chance
  // at each point. The chart draws itself as the match goes: the future is hidden until it happens.
  const rp = { sort: "", comp: null, q: "", data: null, t: 0, playing: false, speed: 1, raf: 0, last: 0, seq: 0, started: false };
  const RP_L = 50, RP_R = 16, RP_T = 34, RP_B = 46;
  function openReplay() {
    if (rp.comp === null) {
      rp.comp = state.mode === "ipl" ? "ipl" : "";
      $$("#rp-comp [data-rc]").forEach((b) => b.classList.toggle("active", b.dataset.rc === rp.comp));
    }
    if (!rp.started) { rp.started = true; searchReplay(); }
  }
  function pauseReplay() { rp.playing = false; cancelAnimationFrame(rp.raf); rp.raf = 0; paintReplayControls(); }
  async function searchReplay() {
    const seq = ++rp.seq; const list = $("#rp-list");
    if (!list.children.length) list.innerHTML = `<div class="rp-wait"><span class="spinner" aria-hidden="true"></span>Opening the archive of past matches… this can take up to a minute the first time after new data.</div>`;
    let res;
    try { res = await api(`/api/replay/search?q=${encodeURIComponent(rp.q)}&competition=${encodeURIComponent(rp.comp || "")}&sort=${encodeURIComponent(rp.sort)}`); }
    catch (err) { if (seq === rp.seq) list.innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
    if (seq !== rp.seq) return;
    if (!res.ready) { list.innerHTML = `<div class="empty">Past matches aren't available right now (the data is being rebuilt). Try again in a few minutes.</div>`; $("#rp-count").textContent = ""; return; }
    const sorts = Object.entries(res.sorts || {});
    $("#rp-sort").innerHTML = sorts.length ? [["", "Latest"], ...sorts].map(([k, l]) => `<button type="button" class="chip-btn ${k === (res.sort || "") ? "on" : ""}" data-rp-sort="${k}">${esc(l)}</button>`).join("") : "";
    $("#rp-count").textContent = res.total ? `${res.total.toLocaleString()} match${res.total === 1 ? "" : "es"}${res.total > res.matches.length ? ` · showing the ${res.sort ? "top" : "latest"} ${res.matches.length}` : ""}` : "";
    // how fresh the data is: the newest match, and when Cricsheet (the data source) was last checked
    if (res.newest) {
      $("#rp-count").insertAdjacentHTML("beforeend", `<span class="data-fresh">Matches up to <b>${esc(fmtDate(res.newest))}</b></span>`);
      (window.__cqStatus ||= api("/api/status")).then((s) => {
        const c = s.cricsheet || {};
        const el = $("#rp-count .data-fresh");
        if (el && c.checked_at) el.insertAdjacentHTML("beforeend", ` · checked with Cricsheet ${esc(fmtDate(c.checked_at.slice(0, 10)))}. New matches appear once Cricsheet publishes them.`);
      }).catch(() => {});
    }
    // newer matches from CricketData: result only (no ball-by-ball yet), shown first until Cricsheet publishes them
    rp.recent = res.recent || [];
    const wl = (m, team) => (m.winner === team ? "won" : m.winner ? "lost" : "");
    const recentHTML = rp.recent.map((m, i) => `
      <button type="button" class="rp-item rp-recent" data-rp-recent="${i}" title="Result only: the full replay comes once Cricsheet publishes this match">
        <span class="rp-item-top"><small>${esc(fmtDate(m.date))} · ${esc(res.competitions[m.competition] || "")}</small><i class="rp-tag new">new · result only</i></span>
        <span class="rp-item-teams">${badgeHTML(m.team1)}<b>${esc(m.team1)}</b> <em class="${wl(m, m.team1)}">${wl(m, m.team1)}</em></span>
        <span class="rp-item-teams">${badgeHTML(m.team2)}<b>${esc(m.team2)}</b> <em class="${wl(m, m.team2)}">${wl(m, m.team2)}</em></span>
        <span class="rp-item-res">${esc(m.result)}${m.venue ? ` · ${esc(m.venue)}` : ""}</span>
      </button>`).join("");
    list.innerHTML = recentHTML + (res.matches.length ? res.matches.map((m) => `
      <button type="button" class="rp-item ${rp.data && rp.data.id === m.id ? "on" : ""}" data-rp-id="${m.id}">
        <span class="rp-item-top"><small>${esc(fmtDate(m.date))} · ${esc(res.competitions[m.competition] || "")}</small>${m.unseen ? `<i class="rp-tag unseen" title="From 2025 on: the model never trained on this match">unseen</i>` : ""}</span>
        <span class="rp-item-teams">${badgeHTML(m.bat)}<b>${esc(m.bat)}</b> <em>${m.total}</em></span>
        <span class="rp-item-teams">${badgeHTML(m.chase)}<b>${esc(m.chase)}</b> <em class="${m.bat_won ? "lost" : "won"}">${m.bat_won ? "lost" : "won"}</em></span>
        ${m.note ? `<span class="rp-item-note">${esc(m.note)}</span>` : ""}
        <span class="rp-item-res">${esc(m.result)}${m.venue ? ` · ${esc(m.venue)}` : ""}</span>
      </button>`).join("") : recentHTML ? "" : `<div class="empty">No match found. Try a team name or a year.</div>`);
  }
  function showRecentResult(i) {  // a CricketData result: there's nothing to replay yet, so say what we know
    const m = (rp.recent || [])[i]; if (!m) return;
    pauseReplay(); rp.data = null;
    $$("#rp-list .rp-item").forEach((x) => x.classList.toggle("on", x.dataset.rpRecent === String(i)));
    $("#rp-stage").innerHTML = `
      <div class="rp-head">
        <div class="rp-teams"><span class="rp-team">${badgeHTML(m.team1)}<b>${esc(m.team1)}</b></span><span class="vs">v</span><span class="rp-team">${badgeHTML(m.team2)}<b>${esc(m.team2)}</b></span></div>
        <p class="muted small">${esc(fmtDate(m.date))}${m.venue ? ` · ${esc(m.venue)}` : ""}</p>
      </div>
      <div class="rp-recent-card">
        <small>Result</small><b>${esc(m.result || "Result not known")}</b>
        <p class="muted small">${esc(m.name)}</p>
        <p class="rp-recent-note">This match is newer than the ball-by-ball data. The result comes from CricketData, which doesn't
          have the balls of this match, so it can't be replayed over by over yet. The full replay, with the model's win chance at
          every point, appears here once Cricsheet publishes it (usually within 1–2 weeks).</p>
      </div>
      <div class="rp-sc" id="rp-sc"></div>`;
    loadRecentCheck(m);
  }
  // model check at the innings break for a CricketData match: first-innings total, both XIs and the ground go into the
  // model, and its pick is compared with the real result. Needs the match's data (about 10 calls once, then saved).
  async function loadRecentCheck(m, fetchNow = false) {
    const box = $("#rp-sc"); if (!box || !m.id) return;
    box.innerHTML = `<div class="rp-wait"><span class="spinner" aria-hidden="true"></span>${fetchNow ? "Getting the match from CricketData…" : "Checking the model…"}</div>`;
    let r;
    try { r = fetchNow ? await api("/api/live-check", { id: m.id }) : await api(`/api/live-check?id=${encodeURIComponent(m.id)}`); }
    catch (err) { box.innerHTML = `<p class="form-error">${esc(err.message)}</p>`; return; }
    const c = r.check || {};
    if (c.available) { m.has_check = true; box.innerHTML = checkHTML(c); if (fetchNow) toast("Model check ready"); return; }
    if (c.reason === "shortened") {  // rain cut the overs: the model is built for full-length matches, so no check (and no calls)
      box.innerHTML = `<p class="muted small"><b>Shortened by rain</b> (overs cut, DLS-style target), so the model isn't checked on this match: it's built for full-length matches. Its result still counts for your own predictions.</p>`;
      return;
    }
    const left = r.budget - r.hits_today;
    box.innerHTML = `${r.error ? `<p class="form-error">${esc(r.error)}</p>` : ""}
      <div class="rp-sc-get"><button type="button" class="chip-btn" id="rp-sc-get" ${left >= r.cost ? "" : "disabled"}>Check the model on this match</button>
        <small class="muted">${left >= r.cost ? `Gets the first-innings score and both XIs from CricketData: about ${r.cost} of your daily calls (${r.hits_today} used today, this app stops at ${r.budget}). Saved after that.` : `<b class="budget-out">Not enough CricketData calls left today.</b> ${Math.max(0, left)} left of this app's ${r.budget}, and a check needs about ${r.cost}. Calls reset at midnight, so this button works again tomorrow.`}</small></div>`;
    $("#rp-sc-get")?.addEventListener("click", () => loadRecentCheck(m, true));
  }
  function checkHTML(c) {
    const ok = c.right === true, bad = c.right === false;
    const filled = [...(c.filled.bat || []).map((n) => `${n} (${c.batting})`), ...(c.filled.chase || []).map((n) => `${n} (${c.chasing})`)];
    const xi = (team, list) => `<p class="rp-ck-xi"><b>${esc(team)}:</b> ${list.map(esc).join(", ")}</p>`;
    return `<div class="rp-ck">
        <div class="rp-verdict-head ${ok ? "ok" : bad ? "bad" : "mix"}">
          <span class="rp-verdict-mark" aria-hidden="true">${ok ? "✓" : bad ? "✗" : "?"}</span>
          <div><b>${ok ? "The model was right" : bad ? "The model was wrong" : "No result to check against"}</b>
            <small>At the innings break: ${esc(c.batting)} ${esc(c.score)} (${esc(c.overs)} ov). The model gave <b>${esc(c.pick)} ${c.pick_pct}%</b>.</small></div>
          <div class="rp-final"><small>Final result</small><b>${esc(c.winner ? `${c.winner} won` : "–")}</b><small>${esc(c.result)}</small></div>
        </div>
        <p class="muted small">Same model and inputs as the Predict page: the first-innings total, both playing XIs and the ground${c.venue_found ? "" : " (ground not in the app's list, so its usual par was used)"}. This match came after the model was trained, so it's a fair test.</p>
        ${filled.length ? `<p class="muted small">Not in the app's squad lists, so filled in from the team's latest XI: ${filled.map(esc).join(", ")}.</p>` : ""}
        <details class="rp-ck-more"><summary>Playing XIs used</summary>${xi(c.batting, c.xi.bat)}${xi(c.chasing, c.xi.chase)}</details>
      </div>`;
  }
  // "How did the model do lately?": its innings-break call on the last 5 matches of a kind, shown in the Replay panel.
  // Matches in the ball-by-ball data cost nothing; newer ones come from CricketData (about 10 calls each, once).
  async function showLast5(kind, fetchNow = false) {
    pauseReplay(); rp.data = null;
    $$("[data-last5]").forEach((b) => b.classList.toggle("on", b.dataset.last5 === kind));
    $$("#rp-list .rp-item").forEach((b) => b.classList.remove("on"));
    const stage = $("#rp-stage");
    stage.innerHTML = `<div class="rp-wait"><span class="spinner" aria-hidden="true"></span>${fetchNow ? "Looking for new matches on CricketData and checking them…" : "Checking the model on the last 5 matches…"}</div>`;
    stage.scrollIntoView({ block: "nearest", behavior: "smooth" });
    let r;
    try { r = fetchNow ? await api("/api/last5", { kind }) : await api(`/api/last5?kind=${encodeURIComponent(kind)}`); }
    catch (err) { stage.innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
    if (!r.ready) { stage.innerHTML = `<div class="empty">The match archive isn't ready yet. Try again in a minute.</div>`; return; }
    const pct = r.checked ? Math.round((r.right / r.checked) * 100) : null;
    const left = r.budget - r.hits_today;
    const row = (m) => {
      const mark = m.right === true ? "ok" : m.right === false ? "bad" : "wait";
      const verdict = m.right === true ? "✓" : m.right === false ? "✗" : "?";
      const call = m.pick ? `${esc(m.bat)} ${esc(m.score)} → model: <b>${esc(m.pick)} ${m.pct}%</b>` : `<span class="muted">Not checked yet</span>`;
      const open = m.replay_id ? `<button type="button" class="chip-btn" data-rp-open="${m.replay_id}">Full replay</button>`
        : `<span class="rp-tag new">new · from CricketData</span>`;
      return `<li class="l5-row ${mark}"><span class="l5-mark" aria-hidden="true">${verdict}</span>
        <div class="l5-main"><small>${esc(fmtDate(m.date))}</small><b>${esc(m.team1)} v ${esc(m.team2)}</b>
          <span class="l5-call">At the innings break: ${call}</span><span class="l5-res">${esc(m.result)}</span></div>
        <div class="l5-side">${open}</div></li>`;
    };
    stage.innerHTML = `
      <div class="l5">
        <div class="l5-head">
          <div><p class="eyebrow">Last 5 ${esc(r.label)}</p>
            <h2>${r.checked ? `${r.right} of ${r.checked} right` : "Not checked yet"}${pct != null ? ` <span>${pct}%</span>` : ""}</h2>
            <p class="muted small">The model's pick at the innings break (first innings done, total known), with the XIs and ground of each match, against the real result. Five matches is a tiny sample: the model's tested rate at the innings break is about 78%.</p></div>
        </div>
        <ol class="l5-list">${r.rows.map(row).join("") || `<li class="muted">No finished matches found.</li>`}</ol>
        ${r.enabled ? `<div class="l5-more">
            <button type="button" class="chip-btn" id="l5-fetch" ${left >= 1 ? "" : "disabled"}>Look for newer ${esc(r.label)} on CricketData</button>
            <small class="muted">Finds matches played after your ball-by-ball data (${esc(fmtDate(r.newest))}) and checks up to 5 of them: a few calls to look, then about ${r.cost} per new match, saved after that. ${r.hits_today} of ${r.budget} calls used today.${left < r.cost && r.unchecked ? ` <b class="budget-out">Not enough calls left today to check more matches; they reset at midnight.</b>` : ""}${r.unchecked ? ` ${r.unchecked} match${r.unchecked === 1 ? "" : "es"} above still to check.` : ""}</small>
          </div>` : ""}
        ${r.note ? `<p class="muted small">${esc(r.note)}</p>` : ""}
        <div class="l5-back">
          <div><b>Fetch older ${esc(r.label)} into History</b>
            <small class="muted">Each press adds the next older matches to History as model checks, newest first, skipping any already there. Matches in your downloaded data are free (up to 20 a press, matches from 2025 on, which the model never trained on); matches newer than that data use today's CricketData calls (about ${r.cost} each).</small></div>
          <button type="button" class="chip-btn" id="l5-back">Fetch older matches</button>
          <button type="button" class="chip-btn danger" id="l5-back-clear" title="Take the matches fetched for this kind back out of History">Remove fetched</button>
          <p class="small l5-back-note" id="l5-back-note" aria-live="polite"></p>
        </div>
      </div>`;
    $("#l5-fetch")?.addEventListener("click", () => showLast5(kind, true));
    $("#l5-back-clear")?.addEventListener("click", async () => {
      const out = $("#l5-back-note");
      if (!confirm(`Take every ${r.label} match added with Fetch older matches back out of History? Your own predictions stay, and you can fetch them again any time.`)) return;
      try {
        const g = await api("/api/go-back/clear", { kind });
        out.textContent = g.removed ? `Removed ${g.removed} fetched match${g.removed === 1 ? "" : "es"} from History.` : "Nothing fetched for this kind yet.";
        histData = null;
      } catch (err) { out.textContent = err.message; }
    });
    $("#l5-back")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget; const out = $("#l5-back-note");
      btn.disabled = true; out.textContent = "Fetching…";
      try {
        const g = await api("/api/go-back", { kind });
        if (!g.ready) { out.textContent = "The match archive isn't ready yet. Try again in a minute."; return; }
        const bits = [];
        if (g.paid) bits.push(`${g.paid} newer match${g.paid === 1 ? "" : "es"} from CricketData (${g.calls} calls)`);
        if (g.free) bits.push(`${g.free} from your match data, ${fmtDate(g.from)} back to ${fmtDate(g.to)} (model right in ${g.free_right})`);
        out.innerHTML = `${bits.length ? `Added to History: ${esc(bits.join("; "))}.` : "Nothing new to add."}
          ${g.left ? `${g.left} older ${esc(g.label)} still to go: press again to continue.` : `All ${esc(g.label)} from 2025 on are in History now.`}
          ${g.note ? ` <span class="muted">${esc(g.note)}</span>` : ""} <a href="#history">Open History</a>`;
        histData = null;  // History reloads with the new checks next time it opens
      } catch (err) { out.textContent = err.message; }
      finally { btn.disabled = false; }
    });
    if (fetchNow) toast(r.note || "Done");
  }
  async function loadReplayMatch(id) {
    pauseReplay();
    const stage = $("#rp-stage");
    stage.innerHTML = `<div class="rp-wait"><span class="spinner" aria-hidden="true"></span>Loading the match…</div>`;
    let d;
    try { d = await api(`/api/replay?id=${encodeURIComponent(id)}`); }
    catch (err) { stage.innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
    rp.data = d; rp.t = 0;
    $$("#rp-list .rp-item").forEach((b) => b.classList.toggle("on", Number(b.dataset.rpId) === d.id));
    const A = teamStyle(d.bat), B = teamStyle(d.chase);
    const cb = B.c1.toLowerCase() === A.c1.toLowerCase() ? B.c2 : B.c1;  // two teams, two colours
    rp.colA = A.c1; rp.colB = cb;
    stage.innerHTML = `
      <div class="rp-head">
        <div class="rp-teams">
          <span class="rp-team">${badgeHTML(d.bat)}<b>${esc(d.bat)}</b></span><span class="vs">v</span><span class="rp-team">${badgeHTML(d.chase)}<b>${esc(d.chase)}</b></span>
        </div>
        <p class="muted small">${esc(fmtDate(d.date))} · ${esc(d.competition)} · ${esc(d.venue || "")}</p>
        <p class="rp-seen ${d.unseen ? "unseen" : ""}">${d.unseen
          ? "<b>Unseen match.</b> From 2025 on: the model never trained on this one, so this is a fair test."
          : "<b>In the training data.</b> The model learned from matches before 2025, including this one, so it had an easier job here."}</p>
      </div>
      <div class="rp-verdict">
        <div class="rp-verdict-head ${d.calls_right === d.calls.length ? "ok" : d.calls_right === 0 ? "bad" : "mix"}">
          <span class="rp-verdict-mark" aria-hidden="true">${d.calls_right === d.calls.length ? "✓" : d.calls_right === 0 ? "✗" : "±"}</span>
          <div><b>${d.calls_right === d.calls.length ? "The model was right" : d.calls_right === 0 ? "The model was wrong" : "The model was right some of the time"}</b>
            <small>It picked the real winner at ${d.calls_right} of ${d.calls.length} checkpoint${d.calls.length === 1 ? "" : "s"}.</small></div>
          <div class="rp-final"><small>Final result</small><b>${esc(d.winner)} won</b><small>${esc(d.result)}</small></div>
        </div>
        <div class="rp-calls">${d.calls.map((c) => `<button type="button" class="rp-call ${c.right ? "ok" : "bad"}" data-rp-turn="${c.index}" title="Jump to this point">
          <small>${esc(c.stage)}</small>
          <span>Model picked <b>${esc(c.team)}</b> <em>${c.pct.toFixed(0)}%</em>${c.close ? ` <i>too close to call</i>` : ""}</span>
          <strong>${c.right ? "✓ Right" : "✗ Wrong"}</strong></button>`).join("")}</div>
      </div>
      <div class="rp-now" id="rp-now"></div>
      <div class="rp-chart" id="rp-chart" style="--ca:${rp.colA};--cb:${rp.colB}"></div>
      <div class="rp-controls">
        <button type="button" class="rp-play" id="rp-play" aria-label="Play"></button>
        <button type="button" class="chip-btn" id="rp-restart" title="Back to the first ball">Restart</button>
        <input type="range" id="rp-scrub" min="0" max="${d.points.length - 1}" step="0.01" value="0" aria-label="Move through the match">
        <div class="seg-tabs small" id="rp-speed" role="group" aria-label="Speed">${[1, 2, 4].map((s) => `<button type="button" data-rs="${s}" class="${s === rp.speed ? "active" : ""}">${s}×</button>`).join("")}</div>
        <button type="button" class="chip-btn" id="rp-end" title="Jump to the result">Skip to end</button>
      </div>
      <div class="rp-turns" id="rp-turns"></div>
      <div class="rp-story" id="rp-story" hidden></div>`;
    $("#rp-turns").innerHTML = d.turning.length ? `<h3 class="sub">Turning points <small class="muted">· tap one to jump there</small></h3>
      <div class="rp-turn-list">${d.turning.map((t, k) => `<button type="button" class="rp-turn" data-rp-turn="${t.index}" data-k="${k}">
        <span class="rp-turn-swing" style="color:${t.swing > 0 ? rp.colA : rp.colB}">${t.swing > 0 ? "+" : "−"}${Math.abs(t.swing).toFixed(0)}%</span>
        <span><b>${esc(t.to)}</b> gain · ${t.inn === 1 ? "1st innings" : "chase"}, over ${esc(t.over)}<small>${esc(t.text)}</small></span></button>`).join("")}</div>` : "";
    drawReplay();
    if (NO_MOTION) { rp.t = d.points.length - 1; drawReplay(); } else playReplay();
    if (window.matchMedia("(max-width: 1020px)").matches) stage.scrollIntoView({ behavior: NO_MOTION ? "auto" : "smooth", block: "start" });
  }
  function playReplay() {
    const d = rp.data; if (!d) return;
    if (rp.t >= d.points.length - 1) rp.t = 0;
    rp.playing = true; rp.last = 0; paintReplayControls();
    const tick = (now) => {
      if (!rp.playing) return;
      if (!rp.last) rp.last = now;
      const dt = Math.min(100, now - rp.last); rp.last = now;
      rp.t = Math.min(d.points.length - 1, rp.t + (dt / 520) * rp.speed);  // about half a second an over at 1x
      drawReplay();
      if (rp.t >= d.points.length - 1) { rp.playing = false; paintReplayControls(); return; }
      rp.raf = requestAnimationFrame(tick);
    };
    rp.raf = requestAnimationFrame(tick);
  }
  function paintReplayControls() {
    const b = $("#rp-play"); if (!b) return;
    const ended = rp.data && rp.t >= rp.data.points.length - 1;
    b.innerHTML = rp.playing ? `<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14" /></svg>` : `<svg viewBox="0 0 24 24"><path d="M7 4.5v15l12-7.5z" /></svg>`;
    b.setAttribute("aria-label", rp.playing ? "Pause" : ended ? "Play again" : "Play");
    b.classList.toggle("playing", rp.playing);
  }
  function drawReplay() {
    const d = rp.data; if (!d) return;
    // drawn at the chart's real size, so labels stay readable in a narrow panel or on a phone
    const RP_W = Math.max(300, Math.round($("#rp-chart").clientWidth || 800)); const RP_H = Math.round(Math.max(240, Math.min(400, RP_W * 0.44)));
    const small = RP_W < 520;
    const P = d.points; const n = P.length - 1; const t = Math.max(0, Math.min(n, rp.t));
    const i = Math.floor(t), f = t - i; const cur = P[Math.min(n, Math.round(t))];
    const x = (k) => RP_L + (RP_W - RP_L - RP_R) * (k / n);
    const y = (p) => RP_T + (RP_H - RP_T - RP_B) * (1 - p / 100);
    const pNow = i >= n ? P[n].p : P[i].p + (P[i + 1].p - P[i].p) * f;
    const pts = P.slice(0, i + 1).map((p, k) => [x(k), y(p.p)]); if (f > 0) pts.push([x(t), y(pNow)]);
    const line = pts.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
    const area = `${RP_L},${y(50)} ${line} ${pts[pts.length - 1][0].toFixed(1)},${y(50)}`;
    const brk = P.findIndex((p) => p.inn === 2);
    let s = `<defs><clipPath id="rp-top"><rect x="0" y="0" width="${RP_W}" height="${y(50)}"/></clipPath><clipPath id="rp-bot"><rect x="0" y="${y(50)}" width="${RP_W}" height="${RP_H}"/></clipPath></defs>`;
    for (const v of [0, 25, 50, 75, 100]) s += `<line x1="${RP_L}" x2="${RP_W - RP_R}" y1="${y(v)}" y2="${y(v)}" class="rp-grid-l${v === 50 ? " mid" : ""}"/><text x="${RP_L - 8}" y="${y(v) + 4}" text-anchor="end" class="rp-ax">${v === 50 ? "50%" : v > 50 ? `${v}%` : `${100 - v}%`}</text>`;
    s += `<text x="${RP_L + 6}" y="${RP_T - 12}" class="rp-side" style="fill:${rp.colA}">▲ ${esc(d.bat)}</text><text x="${RP_L + 6}" y="${RP_H - RP_B + 18}" class="rp-side" style="fill:${rp.colB}">▼ ${esc(d.chase)}</text>`;
    if (brk > 0) {
      s += `<line x1="${x(brk)}" x2="${x(brk)}" y1="${RP_T}" y2="${RP_H - RP_B}" class="rp-brk"/>`;
      s += `<text x="${(x(0) + x(brk)) / 2}" y="${RP_H - 8}" text-anchor="middle" class="rp-ax">1st innings${small ? "" : ` · ${esc(d.bat)} bat`}</text><text x="${(x(brk) + x(n)) / 2}" y="${RP_H - 8}" text-anchor="middle" class="rp-ax">the chase${small ? "" : ` · ${esc(d.chase)} bat`}</text>`;
    }
    s += `<polygon points="${area}" clip-path="url(#rp-top)" style="fill:${rp.colA}" class="rp-area"/><polygon points="${area}" clip-path="url(#rp-bot)" style="fill:${rp.colB}" class="rp-area"/>`;
    s += `<polyline points="${line}" class="rp-line"/>`;
    for (let k = 1; k <= i; k++) if (P[k].d_wkts > 0) s += `<circle cx="${x(k)}" cy="${y(P[k].p)}" r="${3 + Math.min(3, P[k].d_wkts)}" class="rp-wkt"><title>${P[k].d_wkts} wicket${P[k].d_wkts > 1 ? "s" : ""}: ${P[k].runs}/${P[k].wickets} after ${P[k].over}</title></circle>`;
    for (const tp of d.turning) if (tp.index <= i) s += `<circle cx="${x(tp.index)}" cy="${y(P[tp.index].p)}" r="11" class="rp-tp" style="stroke:${tp.swing > 0 ? rp.colA : rp.colB}"/>`;
    const [cx, cy] = pts[pts.length - 1]; const lead = pNow >= 50 ? rp.colA : rp.colB;
    s += `<line x1="${cx}" x2="${cx}" y1="${RP_T}" y2="${RP_H - RP_B}" class="rp-cursor"/><circle cx="${cx}" cy="${cy}" r="15" style="fill:${lead}" class="rp-halo"/><circle cx="${cx}" cy="${cy}" r="7" style="fill:${lead}" class="rp-dot"/>`;
    $("#rp-chart").innerHTML = `<svg viewBox="0 0 ${RP_W} ${RP_H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Win chance through the match">${s}</svg>`;

    // the scoreboard line for this moment
    const pa = Math.round(pNow), pb = 100 - pa; const ended = t >= n;
    let where;
    if (ended) where = `<b>${esc(d.winner)} won.</b> ${esc(d.result)}${d.winner === d.bat ? "" : ` (${esc(d.bat)} made ${d.total})`}.`;
    else if (cur.inn === 1) where = cur.balls === 0 ? `Before the first ball` : `<b>${esc(d.bat)} ${cur.runs}/${cur.wickets}</b> after ${esc(cur.over)} overs`;
    else where = cur.balls === 0 ? `<b>${esc(d.chase)} need ${d.target}</b> to win` : `<b>${esc(d.chase)} ${cur.runs}/${cur.wickets}</b> after ${esc(cur.over)} overs · need ${cur.need} off ${cur.balls_left} balls`;
    const tp = !ended && d.turning.find((q) => q.index === Math.round(t));
    $("#rp-now").innerHTML = `
      <div class="rp-bar" style="--ca:${rp.colA};--cb:${rp.colB}"><span style="width:${pa}%"><b>${pa}%</b></span><span style="width:${pb}%"><b>${pb}%</b></span></div>
      <div class="rp-where"><span>${where}</span>${tp ? `<i class="rp-flash" style="background:${tp.swing > 0 ? rp.colA : rp.colB}">Turning point: ${tp.swing > 0 ? "+" : "−"}${Math.abs(tp.swing).toFixed(0)}% to ${esc(tp.to)}</i>` : ""}</div>`;
    const scrub = $("#rp-scrub"); if (scrub && document.activeElement !== scrub) scrub.value = String(t);
    $$("#rp-turns .rp-turn").forEach((b) => b.classList.toggle("seen", Number(b.dataset.rpTurn) <= i));
    const story = $("#rp-story");
    if (story) {
      story.hidden = !ended;
      if (ended && !story.dataset.for) {
        const st = d.story; const bits = [];
        bits.push(`Before the first ball the model made <b>${esc(st.favourite)}</b> ${st.favourite_pct.toFixed(0)}% favourites.`);
        if (st.upset) bits.push(`<b>${esc(d.winner)}</b> won anyway: an upset. At their lowest they were given just ${st.winner_lowest.toFixed(0)}%.`);
        else if (st.winner_lowest < 40) bits.push(`${esc(d.winner)} won, but it was a fight: at one point they were down to ${st.winner_lowest.toFixed(0)}%.`);
        else bits.push(`${esc(d.winner)} won and were never below ${st.winner_lowest.toFixed(0)}%.`);
        const atBreak = d.calls.find((c) => c.stage === "At the innings break");
        if (atBreak) bits.push(`At the innings break it picked ${esc(atBreak.team)} (${atBreak.pct.toFixed(0)}%): ${atBreak.right ? "the right call" : "the wrong call"}.`);
        story.innerHTML = `<h3 class="sub">The story of the match</h3><p>${bits.join(" ")}</p>`;
        story.dataset.for = String(d.id);
      }
      if (!ended) delete story.dataset.for;
    }
  }
  (function bindReplay() {
    const view = $("#view-replay"); if (!view) return;
    let typing = 0;
    $("#rp-q").addEventListener("input", (e) => { rp.q = e.target.value.trim(); clearTimeout(typing); typing = setTimeout(searchReplay, 250); });
    view.addEventListener("click", (e) => {
      const c = e.target.closest("[data-rc]");
      if (c) { rp.comp = c.dataset.rc; $$("#rp-comp [data-rc]").forEach((b) => b.classList.toggle("active", b === c)); searchReplay(); return; }
      const so = e.target.closest("[data-rp-sort]");
      if (so) { rp.sort = so.dataset.rpSort; $("#rp-list").innerHTML = ""; searchReplay(); return; }
      const m = e.target.closest("[data-rp-id]"); if (m) { loadReplayMatch(m.dataset.rpId); return; }
      const nr = e.target.closest("[data-rp-recent]"); if (nr) { showRecentResult(Number(nr.dataset.rpRecent)); return; }
      const l5 = e.target.closest("[data-last5]"); if (l5) { showLast5(l5.dataset.last5); return; }
      const ro = e.target.closest("[data-rp-open]"); if (ro) { loadReplayMatch(ro.dataset.rpOpen); return; }
      if (!rp.data) return;
      const n = rp.data.points.length - 1;
      if (e.target.closest("#rp-play")) { if (rp.playing) pauseReplay(); else playReplay(); return; }
      if (e.target.closest("#rp-restart")) { pauseReplay(); rp.t = 0; drawReplay(); playReplay(); return; }
      if (e.target.closest("#rp-end")) { pauseReplay(); rp.t = n; drawReplay(); paintReplayControls(); return; }
      const s = e.target.closest("[data-rs]");
      if (s) { rp.speed = Number(s.dataset.rs); $$("#rp-speed [data-rs]").forEach((b) => b.classList.toggle("active", b === s)); return; }
      const tp = e.target.closest("[data-rp-turn]");
      if (tp) { pauseReplay(); rp.t = Number(tp.dataset.rpTurn); drawReplay(); paintReplayControls(); }
    });
    window.addEventListener("resize", () => { if (rp.data && !rp.playing && !view.hidden) drawReplay(); });
    view.addEventListener("input", (e) => {
      if (e.target.id !== "rp-scrub" || !rp.data) return;
      pauseReplay(); rp.t = Number(e.target.value); drawReplay(); paintReplayControls();
    });
  })();

  // ------------------------------------------------------------------ data
  let pollTimer = null;
  function stopPolling() { clearTimeout(pollTimer); pollTimer = null; }
  function autoBlock(a) {
    if (!a.supported) return `<p class="muted small">Automatic updates use Windows Task Scheduler, which isn't available here.</p>`;
    const last = a.last;
    return `
      <div class="auto-row">
        <div><b>${a.enabled ? "On" : "Off"}</b><small>${a.enabled ? `every ${a.every_days} days at ${esc(a.time)}${a.next_run ? ` · next: ${esc(a.next_run)}` : ""}` : "Turn on to keep the model current without pressing anything."}</small></div>
        <button type="button" class="switch ${a.enabled ? "on" : ""}" id="auto-toggle" data-on="${a.enabled ? 1 : 0}" role="switch" aria-checked="${a.enabled}" aria-label="Automatic updates"><i></i></button>
      </div>
      ${last ? `<p class="small ${last.ok ? "" : "form-error"}" style="margin:10px 0 0">Last run ${esc(last.last_run)}: ${esc(last.message)}${last.new_matches ? ` · <b>${last.new_matches}</b> new matches` : ""}</p>` : `<p class="muted small" style="margin:10px 0 0">Hasn't run yet.</p>`}
      <p class="muted small">Downloads new matches and retrains, like <b>Update now</b>. If the app is open the new models load straight away; otherwise next time you start it. Your PC needs to be on at that time (a missed run happens on the next date).</p>`;
  }

  // ------------------------------------------------------------------ Tuning (Data tab)
  // Look & motion: saved on this device and applied straight away.
  // Prediction settings: saved in the app (data/settings.json), used by every prediction.
  const LOOK_DEFAULTS = { blur: 100, tint: 100, glow: 100, sat: 100, bri: 100, motion: "full" };
  let LOOK = { ...LOOK_DEFAULTS, ...(store.get("look", {}) || {}) };
  function applyLook() {
    const r = document.documentElement.style;
    r.setProperty("--blur-k", (LOOK.blur / 100).toFixed(2));
    r.setProperty("--tint-k", (LOOK.tint / 100).toFixed(2));
    r.setProperty("--glow-k", (LOOK.glow / 100).toFixed(2));
    r.setProperty("--photo-sat", (LOOK.sat / 100).toFixed(2));
    r.setProperty("--photo-bri", (LOOK.bri / 100).toFixed(2));
    const cl = document.documentElement.classList;
    cl.toggle("photo-adjust", LOOK.sat !== 100 || LOOK.bri !== 100);
    cl.toggle("motion-calm", LOOK.motion === "calm");
    cl.toggle("motion-off", LOOK.motion === "off");
  }
  let SETTINGS = null;
  async function loadSettings() {
    try { SETTINGS = await api("/api/settings"); } catch { return; }
    for (const k of ["flat", "green", "dry", "slow"]) PITCH[k][1] = 1 + SETTINGS.pitch[k] / 100;
    for (const k of ["light", "heavy", "slowing"]) DEW[k][1] = SETTINGS.dew[k];
    if (typeof syncConditions === "function") { syncConditions(); }
    if (state.config) syncPar();
  }
  const sliderRow = (id, label, value, min, max, step, unit, note) => `
    <label class="tune-row"><span>${label}</span>
      <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${value}">
      <output id="${id}-out">${value}${unit}</output>${note ? `<small>${note}</small>` : ""}</label>`;
  function renderTuning() {
    const box = $("#tuning"); if (!box || !SETTINGS) return;
    const S = SETTINGS, signed = (v) => (v > 0 ? `+${v}` : `${v}`);
    box.innerHTML = `
      <div class="row-between"><div><p class="eyebrow">Tuning</p><h2 id="tuning-title">Adjust the look and the predictions</h2></div></div>
      <div class="tuning-grid">
        <div>
          <h3 class="sub">Look &amp; motion <button type="button" class="chip-btn" data-tune-reset="look">Reset</button></h3>
          ${sliderRow("lk-blur", "Glass blur", LOOK.blur, 0, 200, 5, "%", "How much the glass panels blur what's behind them")}
          ${sliderRow("lk-tint", "Glass tint", LOOK.tint, 30, 170, 5, "%", "Lower = clearer glass (more photo shows through)")}
          ${sliderRow("lk-glow", "Background glow", LOOK.glow, 0, 200, 5, "%", "The drifting olive and clay glow behind the page")}
          ${sliderRow("lk-sat", "Photo colour", LOOK.sat, 50, 160, 5, "%", "Saturation of every photo")}
          ${sliderRow("lk-bri", "Photo brightness", LOOK.bri, 70, 130, 5, "%")}
          <div class="tune-row"><span>Motion</span><span class="tune-seg" id="lk-motion">
            ${[["full", "Full"], ["calm", "Calm"], ["off", "Off"]].map(([k, l]) => `<button type="button" data-motion="${k}" class="${LOOK.motion === k ? "active" : ""}">${l}</button>`).join("")}</span><span></span>
            <small>Calm: no spotlight, shine, colour wash or tilt. Off: nothing moves.</small></div>
        </div>
        <div>
          <h3 class="sub">Pitch (change to par) <button type="button" class="chip-btn" data-tune-reset="pitch">Reset</button></h3>
          ${sliderRow("st-pitch-flat", "Flat / batting", S.pitch.flat, -25, 25, 1, "%")}
          ${sliderRow("st-pitch-green", "Green / grassy", S.pitch.green, -25, 25, 1, "%")}
          ${sliderRow("st-pitch-dry", "Dry / turning", S.pitch.dry, -25, 25, 1, "%")}
          ${sliderRow("st-pitch-slow", "Slow / low", S.pitch.slow, -25, 25, 1, "%")}
          <h3 class="sub">2nd innings (points for the chasers at 50/50) <button type="button" class="chip-btn" data-tune-reset="dew">Reset</button></h3>
          ${sliderRow("st-dew-light", "Light dew", S.dew.light, -15, 15, 0.5, " pts")}
          ${sliderRow("st-dew-heavy", "Heavy dew", S.dew.heavy, -15, 15, 0.5, " pts")}
          ${sliderRow("st-dew-slowing", "Pitch slows / no dew", S.dew.slowing, -15, 15, 0.5, " pts", "Negative = points for the side batting first")}
          <h3 class="sub">Suggested XI <button type="button" class="chip-btn" data-tune-reset="suggest">Reset</button></h3>
          ${sliderRow("st-suggest-form_weight", "Recent form", S.suggest.form_weight, 0, 100, 5, "%", "0% = career only, 100% = last 10 innings/spells only")}
          ${sliderRow("st-suggest-matchup_weight", "Matchups", S.suggest.matchup_weight, 0, 100, 5, "%", "The most a record against this opponent can move a rating")}
        </div>
      </div>
      <p class="muted small">Look settings are saved on this device. Prediction settings are saved in the app and used for every prediction from now on;
        the History tracker shows how your pitch and dew calls are doing, so you can tune them from real results.</p>`;
    // look: live while dragging
    for (const [id, key] of [["lk-blur", "blur"], ["lk-tint", "tint"], ["lk-glow", "glow"], ["lk-sat", "sat"], ["lk-bri", "bri"]]) {
      $(`#${id}`).addEventListener("input", (e) => { LOOK[key] = Number(e.target.value); $(`#${id}-out`).textContent = `${LOOK[key]}%`; applyLook(); store.set("look", LOOK); });
    }
    $("#lk-motion").addEventListener("click", (e) => {
      const b = e.target.closest("[data-motion]"); if (!b) return;
      LOOK.motion = b.dataset.motion; store.set("look", LOOK); applyLook();
      $$("#lk-motion button").forEach((x) => x.classList.toggle("active", x === b));
    });
    // predictions: saved when you let go of a slider
    const units = { pitch: "%", dew: " pts", suggest: "%" };
    $$('#tuning input[id^="st-"]').forEach((inp) => {
      const [, group, key] = inp.id.split("-");
      inp.addEventListener("input", () => { $(`#${inp.id}-out`).textContent = `${inp.value}${units[group]}`; });
      inp.addEventListener("change", async () => {
        try { SETTINGS = await api("/api/settings", { [group]: { [key]: Number(inp.value) } }); await loadSettings(); toast("Saved: used for every prediction from now on"); }
        catch (err) { toast(`Couldn't save (${err.message})`); }
      });
    });
    $$("[data-tune-reset]").forEach((b) => b.addEventListener("click", async () => {
      const what = b.dataset.tuneReset;
      if (what === "look") { LOOK = { ...LOOK_DEFAULTS }; store.set("look", LOOK); applyLook(); }
      else { try { SETTINGS = await api("/api/settings", { reset: what }); await loadSettings(); } catch (err) { toast(err.message); return; } }
      renderTuning(); toast("Back to the defaults");
    }));
  }

  // recent results from CricketData.org (needs your key in data/cricketdata_key.txt): settles History before Cricsheet
  function liveResultsHTML(L) {
    if (!L) return "";
    if (!L.enabled) return `<section class="panel section live-card">
        <h2><span class="step-num">◉</span>Recent results (CricketData)</h2>
        <p class="muted small">Off. Put a free CricketData.org API key in <code>data/cricketdata_key.txt</code> and restart the app to check your predictions within hours instead of waiting for Cricsheet.</p></section>`;
    const used = `${L.hits_today} of ${L.hits_limit} calls used today (this app stops at ${L.budget})`;
    const rows = (L.men || []).map((m) => `<li><span class="lr-date">${esc(fd(m.date))}</span>
        <span class="lr-name">${esc(m.team1)} v ${esc(m.team2)} <small>${esc(m.format.toUpperCase())}</small></span>
        <span class="lr-res">${esc(m.winner ? `${m.winner} won by ${m.margin}` : m.status)}</span></li>`).join("");
    return `<section class="panel section live-card">
        <div class="row-between"><h2><span class="step-num">◉</span>Recent results (CricketData)</h2>
          <button type="button" class="chip-btn" id="live-check">Check now</button></div>
        <p class="muted small">Checks every 3 hours while the app runs, so your History predictions are marked right or wrong before Cricsheet publishes the match. The models still learn only from Cricsheet.</p>
        <p class="data-fresh">${L.fetched_at ? `Last checked <b>${esc(fd(L.fetched_at))}</b> · ` : "Not checked yet · "}${used} · ${L.count} recent results kept</p>
        ${L.last_error ? `<p class="form-error">Last check failed: ${esc(L.last_error)}</p>` : ""}
        ${rows ? `<ul class="lr-list">${rows}</ul>` : `<p class="muted small">No men's results fetched yet.</p>`}
      </section>`;
  }
  async function loadData() {
    let s;
    try { s = await api("/api/status"); } catch (err) { $("#data-body").innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
    const up = s.update || {}; const rt = s.retrain || {};
    const updating = up.state === "running"; const retraining = rt.state === "running";
    let hc = null;
    try { hc = await api("/api/health"); } catch { hc = null; }
    const healthHTML = !hc ? "" : `<section class="panel section health ${hc.ok ? "ok" : hc.needs_repair ? "bad" : "warn"}">
        <div class="row-between"><div><p class="eyebrow">Health check</p>
          <h2>${hc.ok ? "Everything is in order" : hc.needs_repair ? `${hc.problems} problem${hc.problems === 1 ? "" : "s"} found` : "One small thing to tidy"}</h2></div>
          <span class="health-mark" aria-hidden="true">${hc.ok ? "✓" : "!"}</span></div>
        <ul class="health-list">${hc.items.map((i) => `<li class="${i.ok ? "ok" : "bad"}"><i aria-hidden="true">${i.ok ? "✓" : "✗"}</i><span>${esc(i.label)}</span><small>${esc(i.detail)}</small></li>`).join("")}</ul>
        ${hc.ok ? `<p class="muted small">Checked ${esc(hc.checked_at)}. The app's files are complete and the models load.</p>`
          : `<p class="small">${hc.needs_repair ? "<b>Repair</b> rebuilds the match history from the downloaded files and retrains every model. It takes a few minutes; keep the app open until it finishes." : "A leftover file from an interrupted update. Repair clears it by rebuilding."}</p>
             <button class="action-btn" id="repair-btn" ${updating || retraining ? "disabled" : ""}>${retraining ? "Repairing…" : "Repair now"}</button>`}
      </section>`;
    const banner = retraining ? "" : s.needs_retrain
      ? `<div class="banner warn">⚡ <span>New match data arrived after the model was trained. Press <b>Retrain model</b> so predictions use it.</span></div>`
      : `<div class="banner ok">✓ <span>The model is trained on the newest data you have.</span></div>`;
    $("#data-body").innerHTML = `${banner}${healthHTML}
      <div class="data-grid">
        <article class="panel data-card">
          <h2><span class="step-num">1</span>Download latest matches</h2>
          <div class="stat-row">
            <div class="stat"><small>Latest match</small><b>${esc(s.store.latest_match || "–")}</b></div>
            <div class="stat"><small>Matches</small><b>${s.store.matches ? Number(s.store.matches).toLocaleString() : "–"}</b></div>
            <div class="stat"><small>Source</small><b>Cricsheet</b></div>
          </div>
          ${s.cricsheet && s.cricsheet.checked_at ? `<p class="data-fresh">Last checked with Cricsheet <b>${esc(s.cricsheet.checked_at)}</b>${s.cricsheet.published ? ` · Cricsheet last published new files <b>${esc(s.cricsheet.published.slice(0, 10))}</b>` : ""}. Cricsheet publishes matches in batches, often a week or two after they're played, so the latest match can be behind today.</p>` : ""}
          <ul class="files">${s.archives.map((a) => `<li><span>${esc(a.name)}</span><span>${a.size_mb} MB · ${esc(a.modified)}</span></li>`).join("")}</ul>
          ${retraining && rt.mode === "update" ? `<div class="progress indeterminate"><i></i></div><p class="muted small">${esc(rt.step)}</p>`
            : rt.mode === "update" && rt.state === "done" ? `<p class="small" style="color:var(--good)">✓ ${esc(rt.step)}</p>`
            : rt.mode === "update" && rt.state === "error" ? `<p class="form-error">${esc(rt.step)}</p>` : ""}
          <button class="action-btn" id="update-btn" ${updating || retraining ? "disabled" : ""}>${retraining && rt.mode === "update" ? "Updating…" : "Update now"}</button>
          <p class="muted small">Downloads the newest IPL, T20 international and ODI files from Cricsheet (only if they changed), then rebuilds and retrains every model and loads them. If nothing is new it stops after the download.</p>
        </article>
        <article class="panel data-card auto-card">
          <h2><span class="step-num">⟳</span>Automatic updates</h2>
          ${autoBlock(s.auto || {})}
        </article>
        <article class="panel data-card">
          <h2><span class="step-num">2</span>Retrain the model</h2>
          <div class="stat-row">
            <div class="stat"><small>Model</small><b style="font-size:1rem">${esc(s.model.label || "–")}</b></div>
            <div class="stat"><small>Trained</small><b>${esc(s.model.trained_at || "–")}</b></div>
            <div class="stat"><small>Data up to</small><b>${esc(s.model.data_through || "–")}</b></div>
          </div>
          ${retraining ? `<div class="progress indeterminate"><i></i></div><p class="muted small">${esc(rt.step)}</p>`
            : rt.state === "done" ? `<p class="small" style="color:var(--good)">✓ ${esc(rt.step)}. <a href="#accuracy">See the new accuracy →</a></p>`
            : rt.state === "error" ? `<p class="form-error">${esc(rt.step)}</p>` : ""}
          ${rt.log && rt.log.length ? `<pre class="log">${esc(rt.log.join("\n"))}</pre>` : ""}
          <button class="action-btn" id="retrain-btn" ${updating || retraining ? "disabled" : ""}>${retraining ? "Retraining…" : "Retrain model"}</button>
          <p class="muted small">Rebuilds the training data, retrains every model, re-tests them on unseen matches and updates the <a href="#accuracy">accuracy page</a>. Takes about a minute.</p>
        </article>
      </div>
      ${liveResultsHTML(s.live)}
      <section class="panel section">
        <h2>How it works</h2>
        <ol class="how" style="margin-top:14px">
          <li>Cricsheet publishes every ball of every recorded match. The app downloads the IPL, T20 international and ODI files.</li>
          <li>The training step replays each match in date order and records the situation after every over, using only what was known at that moment.</li>
          <li>Several models learn from matches before 2024, are tuned on 2024, then sit an exam on everything since. The best-balanced one powers the Predict tab.</li>
          <li>Venue par scores, team ratings and player records shown in the app come from the same data, so they refresh with every retrain.</li>
        </ol>
      </section>`;
    $("#update-btn").addEventListener("click", async () => { await api("/api/update-all", {}).catch((e) => toast(e.message)); toast("Update started"); loadData(); });
    $("#live-check")?.addEventListener("click", async (e) => {
      e.currentTarget.disabled = true; e.currentTarget.textContent = "Checking…";
      const r = await api("/api/live-results", {}).catch((err) => ({ note: err.message }));
      toast(r.note || "Checked"); loadData();
    });
    $("#auto-toggle")?.addEventListener("click", async (e) => {
      const on = e.currentTarget.dataset.on !== "1"; e.currentTarget.disabled = true;
      const r = await api("/api/auto-update", { enable: on }).catch((err) => ({ error: err.message }));
      toast(r.error ? `Couldn't change it: ${r.error}` : on ? `Automatic updates on: every ${r.every_days} days at ${r.time}` : "Automatic updates off");
      loadData();
    });
    $("#retrain-btn").addEventListener("click", async () => { await api("/api/retrain", {}).catch((e) => toast(e.message)); toast("Retraining started"); loadData(); });
    $("#repair-btn")?.addEventListener("click", async () => {
      if (!confirm("Rebuild the match history and retrain every model now? Keep the app open until it finishes (a few minutes).")) return;
      await api("/api/retrain", { label: "Repaired from the Data page" }).catch((e) => toast(e.message)); toast("Repair started"); loadData();
    });
    stopPolling();
    if (!$("#tuning").childElementCount) { if (!SETTINGS) await loadSettings(); renderTuning(); }
    if (updating || retraining) pollTimer = setTimeout(loadData, 1500);
    if (rt.state === "done" && loadData.lastRetrain === "running") { accCache = null; toast("Model retrained ✓"); setMode(state.mode); }
    loadData.lastRetrain = rt.state;
  }

  // ------------------------------------------------------------------ boot
  $$(".mode-switch button").forEach((b) => b.addEventListener("click", () => { if (b.dataset.mode !== state.mode) setMode(b.dataset.mode); }));
  // ---- online copy: your saved predictions live only in this browser, so you can save them to a file and load them
  // back (after clearing browsing data, or on a new phone). Nothing is sent anywhere: the file stays on your device.
  if (PUBLIC) {
    const clearBtn = $("#clear-history");
    const tools = document.createElement("div"); tools.className = "hist-tools";
    tools.innerHTML = `<button type="button" class="ghost-btn" id="hist-save">Save my history</button>
      <label class="ghost-btn" id="hist-load-label">Load my history<input type="file" id="hist-load" accept=".json,application/json" hidden></label>`;
    clearBtn.before(tools); tools.append(clearBtn);
    const keyOf = (e) => [e.timestamp, e.batting_first_team, e.chasing_team, e.stage].join("|");
    $("#hist-save").addEventListener("click", () => {
      const items = store.get("pub.history", []);
      if (!items.length) { toast("Nothing saved yet"); return; }
      const day = new Date().toISOString().slice(0, 10);
      const blob = new Blob([JSON.stringify({ app: "crease-iq", saved: new Date().toISOString(), items }, null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `crease-iq-history-${day}.json`;
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      toast(`Saved ${items.length} prediction${items.length === 1 ? "" : "s"} to a file`);
    });
    $("#hist-load").addEventListener("change", async (e) => {
      const file = e.target.files[0]; e.target.value = ""; if (!file) return;
      let data;
      try { data = JSON.parse(await file.text()); } catch { toast("That file isn't a Crease IQ history file"); return; }
      const incoming = (Array.isArray(data) ? data : data?.items || [])
        .filter((x) => x && typeof x === "object" && typeof x.timestamp === "string" && x.batting_first_team && x.chasing_team);
      if (!incoming.length) { toast("No saved predictions in that file"); return; }
      const have = store.get("pub.history", []); const seen = new Set(have.map(keyOf));
      const fresh = incoming.filter((x) => !seen.has(keyOf(x)));
      const merged = [...have, ...fresh].sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp))).slice(0, 500);
      store.set("pub.history", merged);
      await loadHistory();
      toast(fresh.length ? `Loaded ${fresh.length} prediction${fresh.length === 1 ? "" : "s"}` : "Those predictions are already here");
    });
  }
  $("#clear-history").addEventListener("click", async () => {
    if (!confirm("Delete all saved predictions? (You can undo this for a few seconds.)")) return;
    const res = await api("/api/history/clear", {}); await loadHistory();
    if (res.removed?.length) toastUndo(`${res.removed.length} predictions deleted`, () => undoDelete(res.removed));
    else toast("History cleared");
  });
  window.addEventListener("hashchange", route);
  keepDatesTidy($("#view-data")); keepDatesTidy($("#view-history"));
  // "still here": the app closes itself (and its terminal window) a few minutes after the last open page goes away
  if (!PUBLIC) {
    const tabId = Math.random().toString(36).slice(2, 10);  // the app closes 30 s after its last tab says goodbye
    const ping = () => fetch(`/api/ping?tab=${tabId}`, { cache: "no-store" }).catch(() => {});
    ping(); setInterval(ping, 20000);
    window.addEventListener("pagehide", () => {  // goodbye: sendBeacon still gets through while the tab is closing
      const bye = `/api/ping?tab=${tabId}&bye=1`;
      if (!(navigator.sendBeacon && navigator.sendBeacon(bye))) fetch(bye, { cache: "no-store", keepalive: true }).catch(() => {});
    });
    window.addEventListener("pageshow", (e) => { if (e.persisted) ping(); });  // back from the browser's page cache
    document.addEventListener("visibilitychange", () => { if (!document.hidden) ping(); });
  }
  bindPredict();
  bindInsights();
  bindChase();
  bindFirstLive();
  // hero banner: the two pill buttons jump to a mode, the floating card shows real accuracy
  $$("[data-go-stage]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault();
    const stage = b.dataset.goStage;
    goPredict(() => { setStage(stage); $("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" }); });
  }));
  bindHome();
  bindImpact();
  bindCrease();
  bindDrops();
  bindWhy();
  bindResources();
  bindPar();
  bindScorecard();
  initHeroCards();
  initResultTabs();
  initLiquid();
  loadPhasePar().then(() => { if (state.lastFirst) renderPhaseTracker("first"); if (state.lastChase) renderPhaseTracker("chase"); });
  $("#server-retry").addEventListener("click", () => location.reload());
  if (PUBLIC) {
    const bar = $("#server-down");
    bar.querySelector("b").textContent = "Crease IQ is waking up or busy.";
    bar.querySelector("span").textContent = "The free server sleeps when nobody has used it for a while. Give it a minute, then try again.";
  }
  applyLook(); loadSettings();
  // conditions box
  function syncConditions() {
    $$("[data-pitch]").forEach((b) => b.classList.toggle("active", b.dataset.pitch === state.pitch));
    $$("[data-dew]").forEach((b) => b.classList.toggle("active", b.dataset.dew === state.dew));
    const bits = [];
    if (state.pitch !== "balanced") bits.push(state.par ? `${PITCH[state.pitch][0]} pitch (your own par is used instead)` : `${PITCH[state.pitch][0]} pitch: par ${autoPar()} → ${currentPar()}`);
    const pts = (v) => `${v > 0 ? "+" : ""}${v}`;
    if (state.dew === "heavy") bits.push(`Heavy dew: chasing side ${pts(DEW.heavy[1])} points at 50/50 (fading through the chase)`);
    if (state.dew === "light") bits.push(`Light dew: chasing side ${pts(DEW.light[1])} points at 50/50`);
    if (state.dew === "slowing") bits.push(`Pitch slows / no dew: chasing side ${pts(DEW.slowing[1])} points at 50/50`);
    $("#cond-note").textContent = bits.length ? bits.join(" · ") : "Balanced: no adjustment.";
    $("#conditions").classList.toggle("on", bits.length > 0);
  }
  $("#conditions").addEventListener("click", (e) => {
    const p = e.target.closest("[data-pitch]"); const d = e.target.closest("[data-dew]");
    if (!p && !d) return;
    if (p) state.pitch = p.dataset.pitch;
    if (d) state.dew = d.dataset.dew;
    syncConditions(); syncPar();
    if (state.stage === "chase") predictChase(false); else livePredict();
  });
  syncConditions();
  // ---- pictures in the online copy: the server has no Windows text recognition, so the phone / browser reads the
  // picture itself with Tesseract.js (free, open source; loaded only when a picture is chosen; the picture never
  // leaves the device). Like the Windows reader, a wide gap between two words on a line (side-by-side columns, e.g.
  // two teams on a TV graphic) is written as " | ", so the pitch and team-sheet readers get the same kind of text.
  const OCR_LIB = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
  let ocrWorker = null;
  async function browserOcr(canvas, onStatus) {
    if (!window.Tesseract) {
      onStatus?.("Getting the picture reader ready… (first time only)");
      await new Promise((ok, fail) => {
        const s = document.createElement("script"); s.src = OCR_LIB; s.onload = ok;
        s.onerror = () => fail(new Error("Couldn't load the picture reader. Check the internet connection."));
        document.head.appendChild(s);
      });
    }
    if (!ocrWorker) ocrWorker = window.Tesseract.createWorker("eng");
    const worker = await ocrWorker;
    onStatus?.("Reading the picture… (a few seconds)");
    const { data } = await worker.recognize(canvas);
    const lines = [];
    for (const line of data.lines || []) {
      const words = (line.words || []).filter((w) => w.text.trim());
      if (!words.length) continue;
      let text = words[0].text;
      for (let i = 1; i < words.length; i++) {
        const a = words[i - 1].bbox, b = words[i].bbox;
        const tall = Math.max(a.y1 - a.y0, b.y1 - b.y0);
        text += (b.x0 - a.x1 > 1.6 * tall ? " | " : " ") + words[i].text;
      }
      lines.push(text);
    }
    return lines.join("\n").trim();
  }
  // a picture file -> a white-backed canvas, shrunk if huge and enlarged if small (clearer for text recognition)
  function pictureCanvas(file) {
    return new Promise((ok, fail) => {
      if (!file || !file.type.startsWith("image/")) { fail(new Error("That isn't a picture.")); return; }
      const url = URL.createObjectURL(file); const img = new Image();
      img.onload = () => {
        const scale = Math.min(2400 / Math.max(img.width, img.height), img.width < 900 ? 2 : 1);
        const c = document.createElement("canvas"); c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
        const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url); ok(c);
      };
      img.onerror = () => { URL.revokeObjectURL(url); fail(new Error("That picture couldn't be opened. Try a PNG or JPG.")); };
      img.src = url;
    });
  }

  // ---- read a pitch report (text, a picture, or a pasted screenshot): sets the pitch and dew buttons, with Undo
  (() => {
    const box = $("#pitch-read"); if (!box) return;
    const status = (t) => { $("#pr-status").textContent = t; };
    const show = (r, before) => {
      const pick = r.pitch !== state.pitch || r.dew !== state.dew;
      state.pitchReport = (r.text || "").slice(0, 600);
      state.pitch = r.pitch; state.dew = r.dew;
      syncConditions(); syncPar();
      if (pick) { if (state.stage === "chase") predictChase(false); else livePredict(); }
      const chip = (w) => `<span class="pr-word pw-${esc(w.means)}${w.ignored ? " ignored" : ""}" title="${w.ignored ? "Ignored: it says the opposite (no / not / hardly …)" : esc(w.means)}">${esc(w.text)}</span>`;
      const words = r.words.length ? r.words.map(chip).join("") : `<span class="muted">no pitch words found</span>`;
      const dews = r.dew_words.length ? r.dew_words.map(chip).join("") : `<span class="muted">nothing about dew</span>`;
      $("#pr-out").innerHTML = `<p><b>${esc(r.pitch_label)}</b> pitch · <b>${esc(r.dew_label)}</b> in the 2nd innings${r.from_picture ? ` <small class="muted">· read from the picture</small>` : ""}</p>
        <p class="muted small">${esc(r.why)} Change the buttons above if you see it differently.</p>
        <div class="pr-words"><span class="pr-lab">Pitch words</span>${words}</div>
        <div class="pr-words"><span class="pr-lab">Dew / later</span>${dews}</div>
        ${before && pick ? `<button type="button" class="chip-btn" id="pr-undo">Undo (back to ${esc(PITCH[before.pitch][0])}, ${esc(DEW[before.dew][0])})</button>` : ""}`;
      $("#pr-out").hidden = false;
      $("#pr-undo")?.addEventListener("click", () => {
        state.pitch = before.pitch; state.dew = before.dew; syncConditions(); syncPar();
        if (state.stage === "chase") predictChase(false); else livePredict();
        $("#pr-undo").remove(); status("Put back.");
      });
    };
    const ask = async (url, body, what) => {
      const before = { pitch: state.pitch, dew: state.dew };
      status(what);
      try {
        const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const r = await res.json();
        if (!res.ok || r.error) { status(r.error || "Couldn't read that."); return; }
        if (body.picture) r.from_picture = true;  // read on this device (online copy)
        if (r.from_picture && r.text) $("#pr-text").value = r.text;  // so you can see (and fix) what was read
        status(""); show(r, before);
      } catch { status("Couldn't reach the app. Is it still running?"); }
    };
    $("#pr-read").addEventListener("click", () => {
      const text = $("#pr-text").value.trim();
      if (!text) { status("Paste or type a pitch report first."); return; }
      ask("/api/pitch-read", { text }, "Reading…");
    });
    // pictures: on your PC Windows reads them (sent as PNG); online this device reads them and sends only the text
    const readPicture = async (file) => {
      try {
        const c = await pictureCanvas(file);
        if (!PUBLIC) { ask("/api/pitch-read-image", { image: c.toDataURL("image/png") }, "Reading the picture… (a few seconds)"); return; }
        const text = await browserOcr(c, status);
        if (!text) { status("No text found in that picture. Try a clearer one, or type the report."); return; }
        $("#pr-text").value = text;
        ask("/api/pitch-read", { text, picture: true }, "Reading…");
      } catch (err) { status(err.message || "Couldn't read that picture."); }
    };
    $("#pr-pic").addEventListener("change", (e) => { readPicture(e.target.files[0]); e.target.value = ""; });
    $("#pr-text").addEventListener("paste", (e) => {
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
      if (!item) return;
      e.preventDefault(); readPicture(item.getAsFile());
    });
  })();
  // ---- playing XIs from a team sheet (a picture, a pasted screenshot or a pasted list): fills the XI in the order
  // shown (= batting order), one or both teams; unclear names get a drop-down, with Undo
  (() => {
    if (!$("[data-xi-read]")) return;
    const box = (s) => $(`#xi-read-${s}`);
    const status = (s, t) => { const el = $(`[data-xr-status="${s}"]`); if (el) el.textContent = t; };
    const SIDE = { bat: "Batting first", chase: "Chasing" };
    const BADGE = { squad: ["ok", "in squad"], data: ["info", "from match data"], check: ["warn", "check"], new: ["new", "new player"] };
    let last = null;  // { from, picks: {side: [name|null per row]}, before }
    const apply = () => {
      for (const [s, picks] of Object.entries(last.picks)) {
        state.xi[s] = [...new Set(picks.filter(Boolean))].slice(0, 11);
        state.order[s] = true;  // the sheet's order is the batting order
      }
      renderXI(); livePredict();
    };
    const render = () => {
      const r = last.result; const out = $(`[data-xr-out="${last.from}"]`);
      const sides = Object.keys(r.sides);
      out.innerHTML = sides.map((s) => {
        const got = r.sides[s]; const picks = last.picks[s];
        const n = picks.filter(Boolean).length; const c = got.counts;
        const sum = [`<span class="xr-chip ok">${c.squad + c.data} of ${got.players.length} matched</span>`,
          c.check ? `<span class="xr-chip warn">${c.check} to check</span>` : "",
          c.new ? `<span class="xr-chip new">${c.new} new player${c.new === 1 ? "" : "s"}</span>` : "",
          n !== 11 ? `<span class="xr-chip warn">${n} in the XI, not 11</span>` : `<span class="xr-chip ok">batting order set</span>`].join("");
        const rows = got.players.map((p, i) => {
          const [cls, label] = BADGE[p.status] || BADGE.new;
          const name = p.status === "check"
            ? `<select data-xr-pick="${s}" data-i="${i}" aria-label="Who is '${esc(p.read)}'?">
                ${p.options.map((o) => `<option value="${esc(o)}" ${picks[i] === o ? "selected" : ""}>${esc(o)}</option>`).join("")}
                <option value="__new" ${picks[i] === p.as_read ? "selected" : ""}>Keep as new player: ${esc(p.as_read)}</option>
                <option value="" ${picks[i] === null ? "selected" : ""}>Leave out</option></select>`
            : `<span class="xr-name">${esc(p.name)}</span>`;
          return `<li class="${picks[i] ? "" : "out"}"><span class="xr-n">${i + 1}</span>${name}
            <span class="xr-tag ${cls}" title="${p.status === "new" ? "Not in the squad or the match data: the model counts him as an average player with no experience" : p.status === "data" ? "Not in this squad, but in the match data: his record is used" : ""}">${label}</span>
            <span class="xr-read" title="What was read">“${esc(p.read)}”</span></li>`;
        }).join("");
        const subs = got.subs.length ? `<div class="xr-subs"><span class="muted small">${state.mode === "ipl" ? "Substitutes:" : "Also listed (not in the XI):"}</span>
          ${got.subs.map((p) => state.mode === "ipl" && p.status === "squad" && !state.xi[s].includes(p.name)
            ? `<button type="button" class="chip-btn" data-xr-impact="${s}" value="${esc(p.name)}" title="Use as the Impact Player">${esc(p.name)} ⚡</button>`
            : `<span class="xr-chip">${p.status === "check" ? `${esc(p.as_read)} <small>(maybe ${esc(p.name)})</small>` : esc(p.name)}</span>`).join("")}</div>` : "";
        const squadBox = got.squad_like ? `<div class="xr-squad"><b>This looks like a full squad (${got.sheet.length} players), so your XI wasn't changed.</b>
            <div class="pr-row">${r.can_save_squad ? `<button type="button" class="chip-btn" data-xr-squad="${s}">Save as the ${esc(r.teams[s])} squad</button>` : ""}
              <button type="button" class="chip-btn" data-xr-first11="${s}">Use the first 11 as the XI</button></div>
            ${r.can_save_squad ? `<small class="muted">Saving replaces the club's squad list in the app with these ${got.sheet.length} players (you can go back to the official list any time).</small>` : ""}</div>` : "";
        // players on the sheet who aren't in the app's squad (new, or only in the match data): one tap adds them all,
        // so the announced XI / squad is recognised next time (PC only: online copies don't keep squads)
        const outsiders = sheetOutsiders(s);
        const addBox = PUBLIC || r.can_save_squad || !outsiders.length ? ""
          : last.added?.[s] ? `<div class="pr-row xr-addsq"><span class="xr-chip ok">Added to the ${esc(r.teams[s])} squad ✓</span></div>`
          : `<div class="pr-row xr-addsq"><button type="button" class="chip-btn" data-xr-addsquad="${s}" title="${esc(outsiders.join(", "))}">Add ${outsiders.length} new player${outsiders.length === 1 ? "" : "s"} to the ${esc(r.teams[s])} squad</button>
              <small class="muted">${esc(outsiders.join(", "))}</small></div>`;
        return `<div class="xr-side"><p class="xr-title"><b>${esc(r.teams[s])}</b> <small class="muted">· ${SIDE[s]}</small></p>${squadBox}
          <div class="xr-sum">${sum}</div><ol class="xr-list">${rows}</ol>${subs}${addBox}</div>`;
      }).join("") + `<div class="pr-row">${last.before ? `<button type="button" class="chip-btn" data-xr-undo>Undo</button>` : ""}
        <span class="muted small">${r.both ? "The sheet had both teams, so both XIs were filled. " : ""}${r.ignored.length ? `Ignored: ${r.ignored.map(esc).join(", ")}. ` : ""}Drag in the batting order list to change it.</span></div>`;
    };
    // the names on the sheet (XI and substitutes / the rest of a squad) that the team's squad in the app doesn't have
    function sheetOutsiders(s) {
      const g = last.result.sides[s]; const picks = last.picks[s] || [];
      const squad = new Set((team(s === "bat" ? state.batting : state.chasing)?.squad || []).map((p) => p.name));
      const names = [];
      g.players.forEach((p, i) => {
        if (p.status === "new" || p.status === "data") names.push(p.name);
        else if (p.status === "check" && picks[i] === p.as_read) names.push(p.as_read);  // you chose "Keep as new player"
      });
      g.subs.forEach((p) => { if (p.status === "new" || p.status === "data") names.push(p.name); });
      return [...new Set(names)].filter((n) => n && !squad.has(n));
    }
    document.addEventListener("click", async (e) => {
      const b = e.target.closest?.("[data-xr-addsquad]"); if (!b || !last) return;
      const s = b.dataset.xrAddsquad; const names = sheetOutsiders(s);
      if (!names.length) return;
      b.disabled = true;
      try {
        const r = await api("/api/squad-update", { mode: state.mode, team: s === "bat" ? state.batting : state.chasing, add: names });
        state.config = await api(`/api/config?mode=${state.mode}`);
        (last.added ||= {})[s] = true;
        renderXI(); render(); toast(r.note);
      } catch (err) { b.disabled = false; status(last.from, err.message); }
    });
    const read = async (s, body, what) => {
      status(s, what);
      try {
        const r = await api(body.image ? "/api/xi-read-image" : "/api/xi-read",
          { ...body, side: s, mode: state.mode, format: state.format, batting: state.batting, chasing: state.chasing });
        if (body.picture) r.from_picture = true;  // read on this device (online copy)
        if (r.from_picture && r.text) $(`[data-xr-text="${s}"]`).value = r.text;
        const found = Object.values(r.sides).reduce((a, g) => a + g.players.length, 0);
        if (!found) { status(s, "No player names found. Try a clearer picture, or paste the list."); return; }
        const before = { xi: { bat: [...state.xi.bat], chase: [...state.xi.chase] }, order: { ...state.order },
          impact: { bat: { ...state.impact.bat }, chase: { ...state.impact.chase } } };
        const picks = {};
        for (const [side, g] of Object.entries(r.sides)) picks[side] = g.players.map((p) => p.name);
        last = { from: s, result: r, picks, before };
        const squadLike = Object.values(r.sides).some((g) => g.squad_like);
        status(s, "");
        if (!squadLike) apply();
        render();
        toast(squadLike ? "That's a full squad: your XI wasn't changed" : r.both ? "Both XIs filled from the team sheet" : `${r.teams[s]} XI filled from the team sheet`);
      } catch (err) { status(s, err.message || "Couldn't read that."); }
    };
    // on your PC Windows reads the picture; online this device reads it and sends only the text
    const readPicture = async (s, file) => {
      try {
        const c = await pictureCanvas(file);
        if (!PUBLIC) { read(s, { image: c.toDataURL("image/png") }, "Reading the picture… (a few seconds)"); return; }
        const text = await browserOcr(c, (t) => status(s, t));
        if (!text) { status(s, "No text found in that picture. Try a clearer one, or paste the list."); return; }
        $(`[data-xr-text="${s}"]`).value = text;
        read(s, { text: text.slice(0, 6000), picture: true }, "Matching the names…");
      } catch (err) { status(s, err.message || "Couldn't read that picture."); }
    };
    document.addEventListener("click", (e) => {
      const open = e.target.closest("[data-xi-read]");
      if (open) { const b = box(open.dataset.xiRead); b.hidden = !b.hidden; if (!b.hidden) b.querySelector("textarea").focus(); return; }
      const close = e.target.closest("[data-xr-close]"); if (close) { box(close.dataset.xrClose).hidden = true; return; }
      const go = e.target.closest("[data-xr-read]");
      if (go) {
        const s = go.dataset.xrRead; const text = $(`[data-xr-text="${s}"]`).value.trim();
        if (!text) { status(s, "Paste the playing XI first."); return; }
        read(s, { text }, "Reading…"); return;
      }
      const sq = e.target.closest("[data-xr-squad]");
      if (sq && last) {
        const s = sq.dataset.xrSquad; const team = last.result.codes[s];
        (async () => {
          try {
            const res = await api("/api/squad-save", { team, names: last.result.sides[s].sheet });
            state.config = await api(`/api/config?mode=${state.mode}`);
            renderXI(); toast(res.note);
            sq.outerHTML = `<button type="button" class="chip-btn" data-xr-squad-reset="${esc(team)}">Back to the official squad</button>`;
          } catch (err) { status(last.from, err.message); }
        })();
        return;
      }
      const sr = e.target.closest("[data-xr-squad-reset]");
      if (sr) {
        (async () => {
          try {
            const res = await api("/api/squad-save", { team: sr.dataset.xrSquadReset, reset: true });
            state.config = await api(`/api/config?mode=${state.mode}`);
            renderXI(); toast(res.note); sr.remove();
          } catch (err) { toast(err.message); }
        })();
        return;
      }
      const f11 = e.target.closest("[data-xr-first11]");
      if (f11 && last) { apply(); render(); toast("First 11 of the sheet set as the XI (drag to change the order)"); return; }
      const imp = e.target.closest("[data-xr-impact]");
      if (imp) { state.impact[imp.dataset.xrImpact].in = imp.value; renderImpact(); livePredict(); toast(`Impact player: ${imp.value}`); render(); return; }
      if (e.target.closest("[data-xr-undo]") && last?.before) {
        const b = last.before;
        state.xi.bat = b.xi.bat; state.xi.chase = b.xi.chase; Object.assign(state.order, b.order);
        state.impact.bat = b.impact.bat; state.impact.chase = b.impact.chase;
        renderXI(); livePredict(); $(`[data-xr-out="${last.from}"]`).innerHTML = ""; status(last.from, "Put back."); last = null;
      }
    });
    document.addEventListener("change", (e) => {
      const pick = e.target.closest("[data-xr-pick]");
      if (pick && last) {
        const s = pick.dataset.xrPick; const i = +pick.dataset.i; const p = last.result.sides[s].players[i];
        last.picks[s][i] = pick.value === "__new" ? p.as_read : pick.value || null;
        apply(); render(); return;
      }
      const pic = e.target.closest("[data-xr-pic]");
      if (pic) { readPicture(pic.dataset.xrPic, pic.files[0]); pic.value = ""; }
    });
    document.addEventListener("paste", (e) => {
      const ta = e.target.closest?.("[data-xr-text]"); if (!ta) return;
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
      if (!item) return;
      e.preventDefault(); readPicture(ta.dataset.xrText, item.getAsFile());
    });
  })();
  // ---- Update squad (XI box): new players from the team's latest match on CricketData, or added by name. They are
  // saved, so they stay in the squad; the model treats a player with no record as an average newcomer.
  (() => {
    if (!$("[data-sq-open]")) return;
    if (PUBLIC) { document.querySelectorAll("[data-sq-open]").forEach((b) => { b.hidden = true; }); return; }  // squads are kept on your PC only
    const teamOf = (s) => (s === "bat" ? state.batting : state.chasing);
    const status = (s, t) => { const el = $(`[data-sq-status="${s}"]`); if (el) el.textContent = t; };
    const refresh = async (s, note) => {
      state.config = await api(`/api/config?mode=${state.mode}`);
      renderXI(); showAdded(s); if (note) toast(note);
    };
    const showAdded = (s) => {
      const box = $(`[data-sq-added="${s}"]`); if (!box) return;
      const added = (team(teamOf(s)).squad || []).filter((p) => p.added);
      box.innerHTML = added.length ? `<span class="muted small">You added:</span> ${added.map((p) =>
        `<span class="xr-chip">${esc(p.name)} <button type="button" class="sq-x" data-sq-remove="${s}" value="${esc(p.name)}" aria-label="Take ${esc(p.name)} out of the squad">&times;</button></span>`).join(" ")}` : "";
    };
    const showLatest = (s, r) => {
      const out = $(`[data-sq-out="${s}"]`);
      if (r.needs_fetch) {
        out.innerHTML = `<p class="small">The latest match, <b>${esc(r.match.name)}</b> (${esc(fmtDate(r.match.date))}), isn't saved yet.
          Getting its players uses about <b>${r.cost}</b> of today's CricketData calls (${r.calls_left} left).</p>
          <div class="pr-row">${r.enabled && r.calls_left >= r.cost ? `<button type="button" class="chip-btn" data-sq-fetch="${s}">Get it (${r.cost} calls)</button>` : `<span class="muted small">Not enough calls left today, or no CricketData key.</span>`}
          ${r.older ? `<button type="button" class="chip-btn" data-sq-older="${s}">Use ${esc(r.older.name.split(",")[1] || "the last saved match")} instead (free)</button>` : ""}</div>`;
        return;
      }
      if (!r.found) { out.innerHTML = `<p class="small muted">${esc(r.note || "Nothing found.")}</p>`; return; }
      const fresh = r.players.filter((p) => !p.in_squad);
      out.innerHTML = `<p class="small"><b>${esc(r.match.name)}</b> · ${esc(fmtDate(r.match.date))}${r.match.result ? ` · ${esc(r.match.result)}` : ""}</p>
        <ul class="sq-list">${r.players.map((p) => `<li><label><input type="checkbox" data-sq-pick="${s}" value="${esc(p.in_squad || p.name)}" checked>
          <span>${esc(p.in_squad || p.name)}</span> <span class="xr-tag ${p.in_squad ? "ok" : "new"}">${p.in_squad ? "in squad" : "new"}</span></label></li>`).join("")}</ul>
        <div class="pr-row">${fresh.length ? `<button type="button" class="chip-btn" data-sq-addnew="${s}">Add ${fresh.length} new player${fresh.length === 1 ? "" : "s"} to the squad</button>` : `<span class="muted small">Everyone who played is already in the squad.</span>`}
          <button type="button" class="chip-btn" data-sq-usexi="${s}" title="Set the ticked players as the XI, in this order (batting order)">Use ticked as the XI</button></div>`;
      out.dataset.result = JSON.stringify(r);
    };
    // ---- the official squad: for IPL, one tap loads it from Wikipedia (kept up to date from the announcements) and
    // offers the players the app is missing; for every team, a link to the official site (copy or screenshot it,
    // then use Team sheet)
    const IPL_SLUG = { MI: "mumbai-indians", CSK: "chennai-super-kings", RCB: "royal-challengers-bengaluru", KKR: "kolkata-knight-riders",
      DC: "delhi-capitals", PBKS: "punjab-kings", RR: "rajasthan-royals", SRH: "sunrisers-hyderabad", GT: "gujarat-titans", LSG: "lucknow-super-giants" };
    const BOARD = { IND: "https://www.bcci.tv/", AUS: "https://www.cricket.com.au/", ENG: "https://www.ecb.co.uk/", NZ: "https://www.nzc.nz/",
      SA: "https://cricket.co.za/", PAK: "https://www.pcb.com.pk/", SL: "https://www.srilankacricket.lk/", BAN: "https://www.tigercricket.com.bd/",
      WI: "https://www.windiescricket.com/", AFG: "https://www.cricket.af/" };
    const officialSite = (code) => state.mode === "ipl" && IPL_SLUG[code] ? `https://www.iplt20.com/teams/${IPL_SLUG[code]}`
      : BOARD[code] || "https://www.icc-cricket.com/";
    for (const s of ["bat", "chase"]) {
      const first = $(`#xi-sq-${s} .pr-row`); if (!first) continue;
      const row = document.createElement("div"); row.className = "pr-row sq-official";
      row.innerHTML = `<button type="button" class="chip-btn" data-sq-official="${s}">Official squad</button>
        <a class="chip-btn" data-sq-site="${s}" target="_blank" rel="noopener noreferrer">Official site ↗</a>
        <span class="muted small" data-sq-ostatus="${s}" aria-live="polite"></span>`;
      first.before(row);
    }
    const paintSites = () => ["bat", "chase"].forEach((s) => { const a = $(`[data-sq-site="${s}"]`); if (a) a.href = officialSite(teamOf(s)); });
    const showOfficial = (s, r) => {
      const out = $(`[data-sq-out="${s}"]`);
      if (!r.found) { out.innerHTML = `<p class="small muted">${esc(r.note || "No official squad found.")}</p>`; return; }
      const missing = r.players.filter((p) => !p.in_squad);
      const have = r.players.length - missing.length;
      out.innerHTML = `<p class="small"><b>${esc(r.team)}</b> · official ${r.season} squad, ${r.players.length} players
          <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">(Wikipedia)</a> · ${have} already in the app</p>
        ${missing.length ? `<ul class="sq-list">${missing.map((p) => `<li><label><input type="checkbox" data-sq-opick="${s}" value="${esc(p.name)}" checked>
            <span>${esc(p.name)}</span> <span class="xr-tag ${p.status === "data" ? "info" : "new"}">${p.status === "data" ? "has a record" : "new: no record yet"}</span></label></li>`).join("")}</ul>
          <div class="pr-row"><button type="button" class="chip-btn" data-sq-oadd="${s}">Add ${missing.length} to the squad</button></div>`
          : `<p class="small">Everyone in the official squad is already in the app ✓</p>`}
        ${r.withdrawn.length ? `<p class="muted small">Withdrawn (not added): ${r.withdrawn.map(esc).join(", ")}</p>` : ""}`;
    };
    const loadOfficial = async (s) => {
      const st = $(`[data-sq-ostatus="${s}"]`); st.textContent = "Loading the official squad…";
      try { const r = await api("/api/official-squad", { mode: state.mode, team: teamOf(s) }); st.textContent = ""; showOfficial(s, r); }
      catch (err) { st.textContent = err.message; }
    };
    document.addEventListener("click", async (e) => {
      let b;
      if ((b = e.target.closest?.("[data-sq-official]"))) { loadOfficial(b.dataset.sqOfficial); return; }
      if ((b = e.target.closest?.("[data-sq-oadd]"))) {
        const s = b.dataset.sqOadd;
        const names = [...document.querySelectorAll(`[data-sq-opick="${s}"]:checked`)].map((i) => i.value);
        if (!names.length) { $(`[data-sq-ostatus="${s}"]`).textContent = "Tick the players to add first."; return; }
        if (await add(s, names)) loadOfficial(s);
      }
      if (e.target.closest?.("[data-sq-open]")) paintSites();
    });
    $("#batting-select")?.addEventListener("change", paintSites); $("#chasing-select")?.addEventListener("change", paintSites);
    paintSites();
    const latest = async (s, extra) => {
      status(s, "Looking…");
      try { const r = await api("/api/latest-players", { mode: state.mode, team: teamOf(s), ...extra }); status(s, ""); showLatest(s, r); }
      catch (err) { status(s, err.message); }
    };
    const add = async (s, names) => {
      try { const r = await api("/api/squad-update", { mode: state.mode, team: teamOf(s), add: names }); await refresh(s, r.note); return true; }
      catch (err) { status(s, err.message); return false; }
    };
    document.addEventListener("click", async (e) => {
      const t = (sel) => e.target.closest(sel);
      let b;
      if ((b = t("[data-sq-open]"))) { const p = $(`#xi-sq-${b.dataset.sqOpen}`); p.hidden = !p.hidden; if (!p.hidden) showAdded(b.dataset.sqOpen); return; }
      if ((b = t("[data-sq-close]"))) { $(`#xi-sq-${b.dataset.sqClose}`).hidden = true; return; }
      if ((b = t("[data-sq-latest]"))) { latest(b.dataset.sqLatest, {}); return; }
      if ((b = t("[data-sq-fetch]"))) { latest(b.dataset.sqFetch, { fetch: true }); return; }
      if ((b = t("[data-sq-older]"))) { latest(b.dataset.sqOlder, { older: true }); return; }
      if ((b = t("[data-sq-add]"))) {
        const s = b.dataset.sqAdd; const inp = $(`[data-sq-name="${s}"]`); const n = inp.value.trim();
        if (!n) { status(s, "Type the player's name first."); return; }
        if (await add(s, [n])) inp.value = "";
        return;
      }
      if ((b = t("[data-sq-remove]"))) {
        const s = b.dataset.sqRemove;
        try { const r = await api("/api/squad-update", { mode: state.mode, team: teamOf(s), remove: b.value }); await refresh(s, r.note); }
        catch (err) { toast(err.message); }
        return;
      }
      if ((b = t("[data-sq-addnew]"))) {
        const s = b.dataset.sqAddnew; const r = JSON.parse($(`[data-sq-out="${s}"]`).dataset.result || "{}");
        const ticked = new Set([...document.querySelectorAll(`[data-sq-pick="${s}"]:checked`)].map((i) => i.value));
        const names = (r.players || []).filter((p) => !p.in_squad && ticked.has(p.name)).map((p) => p.name);
        if (!names.length) { status(s, "Tick the new players to add first."); return; }
        if (await add(s, names)) latest(s, r.match && r.match.date ? { older: true } : {});
        return;
      }
      if ((b = t("[data-sq-usexi]"))) {
        const s = b.dataset.sqUsexi;
        const picked = [...document.querySelectorAll(`[data-sq-pick="${s}"]:checked`)].map((i) => i.value);
        const inSquad = new Set((team(teamOf(s)).squad || []).map((p) => p.name));
        const missing = picked.filter((n) => !inSquad.has(n));
        if (!picked.length) { status(s, "Tick the players who are playing first."); return; }
        if (missing.length && !(await add(s, missing))) return;
        state.xi[s] = picked.slice(0, 11); state.order[s] = true; renderXI(); livePredict();
        toast(`XI set from the latest match (${state.xi[s].length} players, in batting order)`);
      }
    });
  })();
  // ---- Check a match from a link: the link's words say which match (the website isn't opened); the scorecard comes
  // from CricketData; the result is the model's innings-break call with the toss, XIs, chase and result
  (() => {
    const go = $("#lc-go"); if (!go) return;
    const stage = () => $("#rp-stage");
    let lastUrl = "";
    const msg = (html) => { stage().innerHTML = `<div class="l5 lc">${html}</div>`; stage().scrollIntoView({ block: "nearest", behavior: "smooth" }); };
    const head = (r) => r.match ? `<p class="eyebrow">From your link</p><h2>${esc(r.match.name || "")}</h2>
      <p class="muted small">${esc(fmtDate(r.match.date || ""))}${r.match.venue ? ` · ${esc(r.match.venue)}` : ""}</p>` : `<p class="eyebrow">From your link</p>`;
    const run = async (extra = {}) => {
      const url = $("#lc-url").value.trim();
      if (!url) { toast("Paste the match link first."); return; }
      lastUrl = url;
      pauseReplay(); rp.data = null;
      msg(`<div class="rp-wait"><span class="spinner" aria-hidden="true"></span>${extra.fetch ? "Getting the scorecard from CricketData…" : extra.look ? "Looking for the match on CricketData…" : "Reading the link…"}</div>`);
      let r;
      try { r = await api("/api/link-check", { url, ...extra }); } catch (err) { msg(`<div class="empty">${esc(err.message)}</div>`); return; }
      if (r.state === "needs_fetch") {
        msg(`${head(r)}<p>Its scorecard isn't saved yet. Getting it uses about <b>${r.cost}</b> of today's CricketData calls (${r.calls_left} left); after that it's saved and also counted in History as a model check.</p>
          ${r.enabled && r.calls_left >= r.cost ? `<button type="button" class="chip-btn" data-lc="fetch">Get the scorecard (${r.cost} calls)</button>` : `<p class="muted small">Not enough calls left today, or no CricketData key: try again after midnight.</p>`}`);
        return;
      }
      if (r.state === "not_found") {
        msg(`${head(r)}<p>${esc(r.note)}</p>${r.can_look && r.enabled ? `<button type="button" class="chip-btn" data-lc="look">Look for it on CricketData (a few calls)</button>` : ""}`);
        return;
      }
      if (r.state !== "ok") { msg(`${head(r)}<p>${esc(r.note || "This match can't be checked.")}</p>`); return; }
      const c = r.check;
      const second = c.second && c.second.runs != null ? `${esc(c.second.title)} ${c.second.runs}/${c.second.wickets} (${esc(c.second.overs)} ov) chasing ${Number(String(c.score).split("/")[0]) + 1}` : "";
      const trust = r.trust ? `<p class="small"><b>${esc(r.trust.label)}</b> · calls like this were right ${Math.round(r.trust.right_pct)}% of the time at the innings break</p>` : "";
      msg(`${head(r)}
        ${c.toss ? `<p class="small"><b>Toss:</b> ${esc(c.toss)}</p>` : ""}
        ${checkHTML(c)}
        ${trust}${r.sure_note ? `<p class="sure-note">${esc(r.sure_note.text)}</p>` : ""}
        ${second ? `<p class="small"><b>The chase:</b> ${second}</p>` : ""}
        <div class="pr-row"><button type="button" class="chip-btn" data-lc="open">Open in Predict</button>
          <span class="muted small">Opens this match on the Predict page with the teams, ground, both XIs and the first-innings score, so you can add a pitch report or try "what if".</span></div>`);
      stage().querySelector('[data-lc="open"]').onclick = () => {
        const runs = Number(String(c.score).split("/")[0]) || 0;
        openFromHistory({
          type: "first", stage: "innings_break", batting_first_team: c.batting, chasing_team: c.chasing,
          first_innings_score: runs, wickets: c.wickets, overs: c.overs, format: c.format, mode: c.codes?.mode,
          setup: { mode: c.codes?.mode, format: c.format, batting: c.codes?.bat, chasing: c.codes?.chase, venue: c.codes?.venue,
                   batting_xi: c.xi.bat, chasing_xi: c.xi.chase, batting_order_set: true, chasing_order_set: true,  // the scorecard's batting order
                   runs, wickets: c.wickets, overs: c.overs },
        });
      };
    };
    go.addEventListener("click", () => run());
    $("#lc-url").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
    document.addEventListener("click", (e) => {
      const b = e.target.closest("[data-lc]"); if (!b || b.dataset.lc === "open") return;
      if (lastUrl) $("#lc-url").value = lastUrl;
      run(b.dataset.lc === "fetch" ? { fetch: true } : { look: true });
    });
  })();
  // installable app (Edge/Chrome: "Install Crease IQ"); the service worker only exists on localhost/https
  if ("serviceWorker" in navigator && (location.protocol === "https:" || ["127.0.0.1", "localhost"].includes(location.hostname))) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  // dark / light mode, remembered on this device
  const applyTheme = (t) => {
    document.documentElement.dataset.theme = t;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "dark" ? "#18180f" : "#4a4a36");
  };
  // until you press the moon / sun button, the app follows your computer's light / dark setting (live)
  const systemDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  applyTheme(store.get("theme", systemDark?.matches ? "dark" : "light"));
  const followSystem = () => { if (systemDark && store.get("theme", null) === null) applyTheme(systemDark.matches ? "dark" : "light"); };
  systemDark?.addEventListener?.("change", followSystem);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) followSystem(); });  // and whenever you come back
  $("#theme-btn").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next); store.set("theme", next);
  });
  api("/api/accuracy").then((a) => {
    const rep = a.report; const ch = a.chase;
    if (rep) {
      const first = pct(rep.by_competition["All matches"].innings_break[rep.chosen].accuracy);
      $("#hero-first").textContent = first; $("#club-first").textContent = first; $("#club-acc").textContent = first;
      const n = rep.test_match_counts?.["All matches"];
      if (n) { $("#proof-tested").textContent = n.toLocaleString(); setStat("tested", n); }
      $("#proof-acc").textContent = `${first} right at the innings break`;
      if (rep.trained_at) $("#club-updated").textContent = `Last retrained ${fmtDate(rep.trained_at.slice(0, 10))}`;
    }
    if (ch) { const c = pct(ch.overall[ch.chosen].accuracy); $("#hero-chase").textContent = c; $("#club-chase").textContent = c; }
    const mae = a.score?.slices?.["All T20 states"]?.model?.mae;
    if (mae) $("#club-mae").textContent = `±${Math.round(mae)}`;
  }).catch(() => {});
  // ================= phone layout (screens up to 760 px wide; desktop is untouched) =================
  // "Scoreboard" style: one job per screen. The page's own parts are reused, not copied: groups of extras are wrapped
  // in .m-fold boxes (display: contents on desktop, so nothing changes there; folded with a button on phones), the
  // Predict steps open one at a time with a progress bar, and teams are picked by tapping their crests.
  (function phoneLayout() {
    const mq = matchMedia("(max-width: 760px)");
    const sync = () => document.documentElement.classList.toggle("m-phone", mq.matches);
    sync(); mq.addEventListener?.("change", sync);
    // wrap a run of neighbouring elements in a fold with a title (they keep their order and ids)
    const fold = (els, title, sub = "") => {
      els = els.filter(Boolean); if (!els.length) return null;
      const box = document.createElement("div"); box.className = "m-fold";
      const btn = document.createElement("button"); btn.type = "button"; btn.className = "m-fold-btn";
      btn.innerHTML = `<span><b>${esc(title)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</span><i aria-hidden="true"></i>`;
      btn.setAttribute("aria-expanded", "false");
      const body = document.createElement("div"); body.className = "m-fold-body";
      els[0].before(box); box.append(btn, body); els.forEach((el) => body.append(el));
      btn.addEventListener("click", () => { const open = box.classList.toggle("open"); btn.setAttribute("aria-expanded", String(open)); });
      return box;
    };
    const run = (first, last) => {  // first .. last, siblings in order
      const out = []; let el = first;
      while (el) { out.push(el); if (el === last) break; el = el.nextElementSibling; }
      return out;
    };
    // ---- Home: the hero (photo, two buttons, scoreboard numbers) stays; everything below folds into one box
    const home = $("#view-home");
    if (home) {
      const firstExtra = $("#home-search"); const lastExtra = home.querySelector(".benefits");
      if (firstExtra && lastExtra) fold(run(firstExtra, lastExtra), "More from Crease IQ", "Accuracy, top teams, how it works");
    }
    // ---- Predict: compact header with the step title and a progress bar; steps open one at a time
    const form = $("#predict-form");
    const steps = form ? $$(".step", form) : [];
    const STEP_TITLE = ["Who's playing?", "Where, and which format?", "What's the score?", "Playing XIs"];
    if (form && steps.length) {
      const head = document.createElement("div"); head.className = "m-phead";
      head.innerHTML = `<small class="m-step-no"></small><h2 class="m-step-title"></h2><div class="m-progress">${STEP_TITLE.map(() => "<i></i>").join("")}</div>`;
      form.querySelector(".stage-toggle")?.after(head);
      const visible = () => steps.filter((s) => !s.hidden && !s.classList.contains("m-off"));
      const summary = (s) => {
        const i = visible().indexOf(s);
        if (i === 0) return `${team(state.batting)?.name || state.batting} v ${team(state.chasing)?.name || state.chasing}`;
        if (i === 1) return `${state.format.toUpperCase()} · ${($("#venue-input")?.value || "any ground").split(",")[0]}`;
        if (i === 2) return state.stage === "chase" ? `${$("#c-runs-input")?.value || 0}/${$("#c-wickets-input")?.value || 0} chasing ${$("#target-input")?.value || ""}`
          : `${$("#runs-input")?.value || 0}/${$("#wickets-input")?.value || 0} (${$("#overs-input")?.value || 0} ov)`;
        return $("#xi-summary")?.textContent || "";
      };
      const openStep = (target, scroll) => {
        const vis = visible(); const idx = Math.max(0, vis.indexOf(target));
        vis.forEach((s, i) => s.classList.toggle("m-closed", i !== idx));
        $$(".m-progress i", head).forEach((b, i) => b.classList.toggle("on", i <= idx));
        $(".m-step-no", head).textContent = `Step ${idx + 1} of ${vis.length}`;
        $(".m-step-title", head).textContent = idx === 2 && state.stage === "chase" ? "The chase" : STEP_TITLE[idx] || "";
        refreshSums();
        if (scroll && mq.matches) head.scrollIntoView({ behavior: "smooth", block: "start" });
      };
      const refreshSums = () => visible().forEach((s) => { const el = $(".m-sum", s); if (el) el.textContent = summary(s); });
      steps.forEach((s, i) => {
        const sh = $(".step-head", s); if (!sh) return;
        const sum = document.createElement("small"); sum.className = "m-sum"; sh.append(sum);
        sh.addEventListener("click", (e) => { if (!mq.matches || e.target.closest("button, a, input, select")) return; openStep(s, true); });
        // "Next" at the end of each step but the last
        const next = document.createElement("button"); next.type = "button"; next.className = "m-next";
        next.innerHTML = `Next <span aria-hidden="true">→</span>`;
        next.addEventListener("click", () => { const vis = visible(); const k = vis.indexOf(s); if (vis[k + 1]) openStep(vis[k + 1], true); });
        s.append(next);
      });
      // extras inside the steps fold away: pitch and conditions, the batters at the crease, the XI helpers
      fold([$("#conditions")], "Pitch and conditions", "From the pitch report · read a report or a picture");
      fold([$(".step-hint", steps[steps.length - 1])], "How to pick the XIs");
      // ---- the first choice decides the form: Before the match (teams only, score left out), Innings break (teams +
      // score) or Live chase (teams + the ball pad). Ground and XIs stay as optional, closed steps.
      const MODES = [["pre", "Before the match", "Pick two teams"], ["inns", "Innings break", "Teams + score"], ["chase", "Live chase", "Ball by ball"]];
      const modes = document.createElement("div"); modes.className = "m-modes"; modes.setAttribute("role", "group"); modes.setAttribute("aria-label", "What to predict");
      modes.innerHTML = MODES.map(([k, l, s]) => `<button type="button" data-m-mode="${k}"><b>${l}</b><small>${s}</small></button>`).join("");
      head.before(modes);
      let mMode = store.get("m.mode", state.stage === "chase" ? "chase" : "inns");
      const firstStep = $("#first-step"), chaseStep = $("#chase-step");
      const paintMode = () => {
        $$("[data-m-mode]", modes).forEach((b) => b.classList.toggle("active", b.dataset.mMode === mMode));
        firstStep?.classList.toggle("m-off", mMode === "pre");
        form.classList.toggle("m-pre", mMode === "pre");
      };
      const setMode = (m, user) => {
        mMode = m; store.set("m.mode", m); paintMode();
        if (!user) return;
        if (m === "chase") { if (state.stage !== "chase") $('.stage-toggle [data-stage="chase"]')?.click(); openStep(chaseStep, true); return; }
        if (state.stage === "chase") $('.stage-toggle [data-stage="first"]')?.click();
        if (m === "pre") { $("#pre-match-btn")?.click(); openStep(steps[0], true); }
        else { if (state.balls === 0) $("#innings-over-btn")?.click(); openStep(firstStep, true); }
      };
      modes.addEventListener("click", (e) => { const b = e.target.closest("[data-m-mode]"); if (b && mq.matches) setMode(b.dataset.mMode, true); });
      // Before the match always predicts from 0/0 (even if a saved innings came back after the page opened)
      $("#predict-btn")?.addEventListener("click", () => {
        if (mq.matches && mMode === "pre" && state.stage !== "chase" && (state.balls || state.runs || state.wickets)) {
          state.balls = 0; state.runs = 0; state.wickets = 0; syncScore();
        }
      }, true);
      paintMode();
      openStep(steps[0], false);
      form.addEventListener("change", refreshSums); form.addEventListener("input", refreshSums); form.addEventListener("click", () => setTimeout(refreshSums, 30));
      // the chase / first-innings switch (also from the Live chase tab) swaps step 3: keep the mode and open step sensible
      new MutationObserver(() => {
        const inChase = state.stage === "chase";
        if (inChase && mMode !== "chase") setMode("chase", false);
        else if (!inChase && mMode === "chase") setMode("inns", false);
        const open = visible().find((s) => !s.classList.contains("m-closed")); openStep(open || visible()[0], false);
      }).observe(form, { subtree: true, attributes: true, attributeFilter: ["hidden"] });
    }
    // ---- team crests: tap the team batting first, then the chasing team (the drop-downs stay for every team)
    const teamsBox = form?.querySelector(".teams");
    if (teamsBox) {
      const wrap = document.createElement("div"); wrap.className = "m-crests";
      wrap.innerHTML = `<p class="m-crest-hint"></p><div class="m-crest-grid" role="group" aria-label="Pick the teams"></div>`;
      teamsBox.before(wrap);
      let next = "bat";
      const hint = () => { $(".m-crest-hint", wrap).innerHTML = next === "bat" ? "Tap the team <b>batting first</b>" : "Now tap the <b>chasing</b> team"; };
      const pick = (code) => {
        const bat = $("#batting-select"), ch = $("#chasing-select");
        if (next === "bat") {
          if (code === state.chasing) { $("#swap-btn")?.click(); }
          else if (code !== state.batting) { bat.value = code; bat.dispatchEvent(new Event("change", { bubbles: true })); }
          next = "chase";
        } else {
          if (code === state.batting) return;
          ch.value = code; ch.dispatchEvent(new Event("change", { bubbles: true })); next = "bat";
        }
        hint(); mark();
      };
      const mark = () => $$("button", wrap).forEach((b) => {
        b.classList.toggle("bat", b.dataset.code === state.batting); b.classList.toggle("chase", b.dataset.code === state.chasing);
      });
      const build = () => {
        const opts = [...$("#batting-select").options].filter((o) => o.value);
        $(".m-crest-grid", wrap).innerHTML = opts.map((o) => `<button type="button" data-code="${esc(o.value)}" title="${esc(o.textContent)}">${badgeHTML(o.value, "md")}<small>${esc(o.value)}</small></button>`).join("");
        hint(); mark();
      };
      wrap.addEventListener("click", (e) => { const b = e.target.closest("button[data-code]"); if (b) pick(b.dataset.code); });
      new MutationObserver(build).observe($("#batting-select"), { childList: true });
      $("#batting-select").addEventListener("change", mark); $("#chasing-select").addEventListener("change", mark);
      $("#swap-btn")?.addEventListener("click", () => setTimeout(mark, 30));
      build();
    }
    // ---- results: the winner, the chance and the bar stay on top; the rest folds
    fold(run($("#first-phases"), $("#r-worm-wrap")), "Charts and projection", "Phase tracker, par by wickets, projected total");
    const rWhy = $("#r-factors")?.previousElementSibling;
    fold(run(rWhy, $("#r-model")), "Why this call", "What moved the needle, what if, ask why");
    fold(run($("#chase-phases"), $("#chase-res")), "Phases, par and who's left");
    const cWorm = $("#c-worm")?.previousElementSibling;
    fold(run(cWorm, $("#c-model")), "Charts and why", "Win chance through the chase, what moved it");
    fold([$("#insights")], "Matchups and form", "Batter v bowler, last 10 innings, venues");

    // ---- Accuracy: three headline numbers on a scoreboard; each model's full report and the honesty table fold.
    // The report is redrawn now and then (IPL / International), so the folds are put back each time.
    const accBody = $("#acc-body");
    if (accBody) {
      const card = document.createElement("div"); card.className = "m-acc-card";
      $("#view-accuracy > .hero")?.after(card);
      const num = (sel) => ($(sel)?.textContent || "").trim() || "–";
      const paintCard = () => {
        card.innerHTML = `<div><b>${esc(num("#hero-first"))}</b><small>right at the innings break</small></div>
          <div><b>${esc(num("#hero-chase"))}</b><small>right in live chases</small></div>
          <div><b>${esc(num("#club-mae"))}</b><small>runs off on projected T20 totals</small></div>`;
      };
      const foldAcc = () => {
        if (accBody.querySelector(":scope > .m-fold") || !accBody.children.length || accBody.querySelector(":scope > .loading")) return;
        const kids = [...accBody.children]; const heads = kids.filter((k) => k.classList.contains("hero"));
        if (heads.length >= 2) {
          const i1 = kids.indexOf(heads[0]), i2 = kids.indexOf(heads[1]);
          fold(kids.slice(0, i1), "Innings-break model", "Every model compared, stage by stage, by competition, the toss");
          fold(kids.slice(i1, i2), "Live chase model", "Over by over, by competition, model versions");
          fold(kids.slice(i2), "Projected score", "Typical miss, versions, what the model looks at, glossary");
        } else fold(kids, "The full report", "Every model, every stage");
        paintCard();
      };
      new MutationObserver(foldAcc).observe(accBody, { childList: true }); foldAcc();
      for (const sel of ["#hero-first", "#hero-chase", "#club-mae"]) { const el = $(sel); if (el) new MutationObserver(paintCard).observe(el, { childList: true, characterData: true, subtree: true }); }
      paintCard();
      fold([$("#acc-honesty")], "How honest are the percentages?", "When it said 70%, did that side win 70% of the time?");
    }
    // ---- History: your record on top; the breakdown and the charts fold; each saved prediction is a short card
    // (teams, right / wrong / waiting, the chance) that opens on a tap to show the details and its buttons.
    const histBody = $("#history-body");
    if (histBody) {
      const foldHist = () => {
        if (histBody.querySelector(".m-fold")) return;
        const grid = histBody.querySelector(".score-card .score-grid");
        const pies = histBody.querySelector(":scope > .fmt-pies"), tracker = histBody.querySelector(":scope > .tracker");
        if (grid) fold([grid], "The breakdown", "First innings, live chase, by format");
        const charts = [pies, tracker].filter(Boolean);
        if (charts.length) fold(charts.length === 2 ? run(pies, tracker) : charts, "Charts and trends", "By kind of match, over time, by level");
      };
      new MutationObserver(foldHist).observe(histBody, { childList: true }); foldHist();
      histBody.addEventListener("click", (e) => {
        if (!mq.matches || e.target.closest("button, a, input, select, label, summary")) return;
        const item = e.target.closest(".hist-item"); if (item) item.classList.toggle("m-open");
      });
    }
  })();

  state.stage = store.get("stage", "first") === "chase" ? "chase" : "first";
  loadPhotos().finally(() => setMode(state.mode).then(() => { setStage(state.stage); route(); }));
})();
