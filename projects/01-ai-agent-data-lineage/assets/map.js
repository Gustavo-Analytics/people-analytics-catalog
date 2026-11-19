/* Data lineage map engine. The page defines DATA, KIND, T and GROUPS before loading this file. */
(function () {
  const stage = document.getElementById("stage"), svg = document.getElementById("wires"), detail = document.getElementById("detail");
  const NS = "http://www.w3.org/2000/svg";
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const byId = Object.fromEntries(DATA.nodes.map(n => [n.id, n]));
  const up = {}, down = {};
  DATA.edges.forEach(([a, b]) => { (down[a] = down[a] || []).push(b); (up[b] = up[b] || []).push(a); });
  const TAG = { bronze: ["nom", T.nominal], gold: ["ok", T.anon] };
  let pinned = null;

  function chain(id) {
    const seen = new Set([id]);
    const walk = (map, s) => (map[s] || []).forEach(t => { if (!seen.has(t)) { seen.add(t); walk(map, t); } });
    walk(up, id); walk(down, id);
    return seen;
  }

  function build() {
    DATA.cols.forEach((title, i) => {
      const col = document.createElement("div"); col.className = "col";
      col.innerHTML = '<div class="colh"><b>' + (i + 1) + "</b><span>" + title + "</span></div>";
      const stack = document.createElement("div"); stack.className = "stack";
      DATA.nodes.filter(n => n.col === i).forEach(n => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "node k-" + n.kind; b.dataset.id = n.id;
        const tg = TAG[n.kind];
        b.innerHTML = (tg ? '<i class="tag ' + tg[0] + '">' + tg[1] + "</i>" : "") + "<b>" + n.title + "</b><span>" + n.sub + "</span>";
        b.addEventListener("mouseenter", () => { if (!pinned) focus(n.id); });
        b.addEventListener("mouseleave", () => { if (!pinned) clearFocus(); });
        b.addEventListener("focus", () => { if (!pinned) focus(n.id); });
        b.addEventListener("click", e => { e.stopPropagation(); pinned = pinned === n.id ? null : n.id; pinned ? focus(n.id) : clearFocus(); });
        stack.appendChild(b);
      });
      col.appendChild(stack); stage.appendChild(col);
    });
    stage.addEventListener("click", () => { pinned = null; clearFocus(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") { pinned = null; clearFocus(); } });
    wire();
  }

  const el = id => stage.querySelector('[data-id="' + id + '"]');

  function wire() {
    svg.innerHTML = "";
    const sr = stage.getBoundingClientRect();
    svg.setAttribute("width", stage.scrollWidth); svg.setAttribute("height", stage.scrollHeight);
    DATA.edges.forEach(([a, b]) => {
      const A = el(a).getBoundingClientRect(), B = el(b).getBoundingClientRect();
      const x1 = A.right - sr.left, y1 = A.top + A.height / 2 - sr.top, x2 = B.left - sr.left, y2 = B.top + B.height / 2 - sr.top;
      const dx = Math.max(24, (x2 - x1) / 2);
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", "M" + x1 + " " + y1 + " C" + (x1 + dx) + " " + y1 + " " + (x2 - dx) + " " + y2 + " " + x2 + " " + y2);
      p.setAttribute("class", "w"); p.dataset.a = a; p.dataset.b = b; svg.appendChild(p);
      [[x1, y1], [x2, y2]].forEach(([cx, cy]) => {
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", 3);
        c.setAttribute("class", "dot"); c.dataset.a = a; c.dataset.b = b; svg.appendChild(c);
      });
    });
    if (pinned) focus(pinned);
  }

  function focus(id) {
    const s = chain(id);
    stage.querySelectorAll(".node").forEach(n => {
      const on = s.has(n.dataset.id);
      n.classList.toggle("sel", n.dataset.id === id); n.classList.toggle("dim", !on);
    });
    svg.querySelectorAll(".w,.dot").forEach(w => {
      const on = s.has(w.dataset.a) && s.has(w.dataset.b);
      w.classList.toggle("hot", on); w.classList.toggle("dim", !on);
    });
    const n = byId[id], names = l => (l || []).map(x => byId[x].title).join(", ") || T.none;
    detail.innerHTML = '<div class="meta">' + KIND[n.kind] + "</div><h3>" + n.title + "</h3><p>" + n.detail + "</p>" +
      '<div class="chain"><b>' + T.from + "</b> " + names(up[id]) + " &nbsp;·&nbsp; <b>" + T.feeds + "</b> " + names(down[id]) + "</div>";
  }

  function clearFocus() {
    stage.querySelectorAll(".node").forEach(n => n.classList.remove("sel", "dim"));
    svg.querySelectorAll(".w,.dot").forEach(w => w.classList.remove("hot", "dim"));
    detail.innerHTML = '<div class="idle">' + T.select + "</div>";
  }

  /* k-anonymity demo */
  function kdemo() {
    const box = document.getElementById("kdemo");
    box.innerHTML = "<b>" + T.demoTitle + "</b>" +
      GROUPS.map(([g, n], i) => '<div class="r"><span>' + T.group + " " + g + " · " + n + " " + T.people + '</span><span class="chip" id="kc' + i + '"></span></div>').join("") +
      "<label>" + T.minK + ' <input type="range" id="kr" min="1" max="8" value="3"><b id="kv">3</b></label>';
    const upd = () => {
      const k = +document.getElementById("kr").value; document.getElementById("kv").textContent = k;
      GROUPS.forEach(([g, n], i) => { const c = document.getElementById("kc" + i), ok = n >= k; c.textContent = ok ? T.shown : T.hidden + k + ")"; c.className = "chip" + (ok ? "" : " no"); });
    };
    document.getElementById("kr").addEventListener("input", upd); upd();
  }

  /* count-up numbers and reveal on scroll */
  function motion() {
    const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      if (e.target.dataset.to !== undefined) count(e.target);
      io.unobserve(e.target);
    }), { threshold: .15 }) : null;
    document.querySelectorAll(".rv").forEach(x => io ? io.observe(x) : x.classList.add("in"));
    document.querySelectorAll(".num .v").forEach(v => { if (!io || reduce) v.textContent = v.dataset.to; });
    if (io && !reduce) document.querySelectorAll(".num").forEach(n => { const v = n.querySelector(".v"); n.dataset.to = v.dataset.to; v.textContent = "0"; });
  }
  function count(card) {
    const v = card.querySelector(".v"), to = +card.dataset.to, t0 = performance.now();
    const step = t => { const k = Math.min(1, (t - t0) / 900); v.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }

  build(); clearFocus(); kdemo(); motion();
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(wire, 120); });
  window.addEventListener("load", wire); setTimeout(wire, 250);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(wire);
})();
