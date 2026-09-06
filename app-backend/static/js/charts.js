"use strict";
// Renders accessible SVG charts from JSON embedded by the template macros.
// No external chart library, which keeps the strict CSP intact. Rendering is
// re-runnable (window.cairnRenderCharts) so a theme change can repaint the
// charts with the new colors.
(function () {
  var PALETTE = ["#7c3aed", "#a855f7", "#c026d3", "#a78bfa", "#8b5cf6",
                 "#d946ef", "#c4b5fd", "#9333ea", "#6d28d9", "#e879f9",
                 "#ddd6fe", "#581c87"];
  var NS = "http://www.w3.org/2000/svg";
  var REDUCED = !!(window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var TONE = { violet: "#7c3aed", pos: "#10b981", warn: "#f59e0b",
               neg: "#ef4444", ink: "#8e87a6" };

  // ------------------------------------------------------------ helpers
  function tok(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function E(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function readJSON(sel) {
    var h = document.querySelector(sel);
    if (!h) return null;
    try { return JSON.parse(h.textContent); } catch (e) { return null; }
  }
  function money0(n) {
    return "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  function money(n) {
    var sign = n < 0 ? "-" : "";
    return sign + "$" + Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  function moneyShort(n) {
    var a = Math.abs(n), s = n < 0 ? "-" : "";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k";
    return s + "$" + Math.round(a);
  }
  function raf(fn) {
    if (REDUCED) { fn(); return; }
    requestAnimationFrame(function () { requestAnimationFrame(fn); });
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  // entrance animations
  function drawIn(path, ms) {
    if (REDUCED) return;
    var len = path.getTotalLength();
    path.style.strokeDasharray = len + " " + len;
    path.style.strokeDashoffset = len;
    path.style.transition = "none";
    raf(function () {
      path.style.transition = "stroke-dashoffset " + ms + "ms ease";
      path.style.strokeDashoffset = "0";
    });
  }
  function fadeIn(el, ms, delay) {
    if (REDUCED) return;
    el.style.opacity = "0";
    el.style.transition = "none";
    raf(function () {
      el.style.transition = "opacity " + ms + "ms ease " + (delay || 0) + "ms";
      el.style.opacity = "1";
    });
  }

  // hover tooltip (one per chart host)
  function tipEl(host) {
    var t = host.querySelector(".chart-tip");
    if (!t) { t = document.createElement("div"); t.className = "chart-tip"; host.appendChild(t); }
    return t;
  }
  function showTip(host, pos, label, lines) {
    var t = tipEl(host);
    clear(t);
    var l = document.createElement("span"); l.className = "tip-l"; l.textContent = label;
    t.appendChild(l);
    t.appendChild(document.createTextNode(lines.join("\n")));
    t.style.left = pos[0] + "px"; t.style.top = pos[1] + "px";
    t.classList.add("show");
  }
  function hideTip(host) {
    var t = host.querySelector(".chart-tip");
    if (t) t.classList.remove("show");
  }
  function svgToHost(svg, host, vx, vy) {
    var r = svg.getBoundingClientRect(), h = host.getBoundingClientRect();
    var vb = svg.viewBox.baseVal;
    return [r.left - h.left + vx * (r.width / vb.width),
            r.top - h.top + vy * (r.height / vb.height)];
  }
  function mouseToView(svg, e) {
    var r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
    return [(e.clientX - r.left) * vb.width / r.width,
            (e.clientY - r.top) * vb.height / r.height];
  }

  // ------------------------------------------------- growth line chart
  function renderLine(host) {
    var id = host.getAttribute("data-chart");
    var pts = readJSON('[data-linechart="' + id + '"]');
    if (!pts || pts.length < 2) return;

    var W = 760, H = 260, padL = 56, padR = 16, padT = 16, padB = 34;
    var vals = pts.map(function (p) { return p.value; });
    var lo = Math.min.apply(null, vals.concat([0]));
    var hi = Math.max.apply(null, vals.concat([0]));
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.1;
    lo -= pad; hi += pad;
    var n = pts.length;
    function X(i) { return padL + (i / (n - 1)) * (W - padL - padR); }
    function Y(v) { return padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB); }

    var svg = E("svg", { viewBox: "0 0 " + W + " " + H, class: "linechart-svg",
      preserveAspectRatio: "none" });
    var defs = E("defs", {}, svg);
    defs.innerHTML =
      '<linearGradient id="lc-fill" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#7c3aed" stop-opacity="0.35"/>' +
      '<stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></linearGradient>';

    var grid = tok("--chart-grid", "#f1ecfd"), zero = tok("--chart-zero", "#c4b5fd");
    for (var t = 0; t <= 4; t++) {
      var v = lo + (t / 4) * (hi - lo), y = Y(v);
      E("line", { x1: padL, x2: W - padR, y1: y, y2: y,
        stroke: v === 0 ? zero : grid, "stroke-width": v === 0 ? "1.5" : "1" }, svg);
      var lbl = E("text", { x: padL - 8, y: y + 4, "text-anchor": "end", class: "lc-axis" }, svg);
      lbl.textContent = money(v);
    }

    var d = "", area = "M " + X(0) + " " + Y(0);
    pts.forEach(function (p, i) {
      d += (i === 0 ? "M " : "L ") + X(i) + " " + Y(p.value) + " ";
      area += " L " + X(i) + " " + Y(p.value);
    });
    area += " L " + X(n - 1) + " " + Y(0) + " Z";
    var areaPath = E("path", { d: area, fill: "url(#lc-fill)" }, svg);
    var endVal = pts[n - 1].value;
    var lineColor = endVal >= 0 ? "#7c3aed" : "#ef4444";
    var linePath = E("path", { d: d.trim(), fill: "none", stroke: lineColor,
      "stroke-width": "2.5", "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);

    [0, Math.floor((n - 1) / 2), n - 1].forEach(function (i) {
      var tx = E("text", { x: X(i), y: H - 10, class: "lc-axis",
        "text-anchor": i === 0 ? "start" : (i === n - 1 ? "end" : "middle") }, svg);
      tx.textContent = pts[i].label;
    });
    var dot = E("circle", { cx: X(n - 1), cy: Y(endVal), r: "4", fill: lineColor }, svg);

    // hover: guide line + point + tooltip with the breakdown
    var guide = E("line", { class: "chart-guide", x1: 0, x2: 0, y1: padT, y2: H - padB, opacity: 0 }, svg);
    var hover = E("circle", { r: 5, fill: lineColor, stroke: tok("--surface", "#fff"),
      "stroke-width": 2, opacity: 0 }, svg);
    svg.addEventListener("mousemove", function (e) {
      var vx = mouseToView(svg, e)[0];
      var i = Math.round((vx - padL) / (W - padL - padR) * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      var x = X(i), y = Y(pts[i].value);
      guide.setAttribute("x1", x); guide.setAttribute("x2", x); guide.setAttribute("opacity", 1);
      hover.setAttribute("cx", x); hover.setAttribute("cy", y); hover.setAttribute("opacity", 1);
      var lines = ["Total " + money(pts[i].value)];
      if (pts[i].realized !== undefined) lines.push("Realized " + money(pts[i].realized));
      if (pts[i].income !== undefined) lines.push("Income " + money(pts[i].income));
      showTip(host, svgToHost(svg, host, x, y), pts[i].label, lines);
    });
    svg.addEventListener("mouseleave", function () {
      guide.setAttribute("opacity", 0); hover.setAttribute("opacity", 0); hideTip(host);
    });

    host.appendChild(svg);
    drawIn(linePath, 1100);
    fadeIn(areaPath, 700, 400);
    fadeIn(dot, 300, 1000);
  }

  // ------------------------------------------------------------- donut
  function renderDonut(svg) {
    var id = svg.getAttribute("data-src");
    var data = readJSON('[data-donut="' + id + '"]');
    var legend = document.querySelector('[data-legend="' + id + '"]');
    if (!data || !data.length) return;
    var total = data.reduce(function (s, d) { return s + (d.value || 0); }, 0);
    if (total <= 0) return;

    E("circle", { cx: 21, cy: 21, r: 15.9155, fill: "none",
      stroke: tok("--chart-track", "#f1ecfd"), "stroke-width": 5 }, svg);

    var offset = 25, segs = [];
    data.forEach(function (d, i) {
      var pct = (d.value / total) * 100;
      var color = PALETTE[i % PALETTE.length];
      var seg = E("circle", { cx: 21, cy: 21, r: 15.9155, fill: "none", stroke: color,
        "stroke-width": 5, "stroke-dashoffset": offset.toFixed(2),
        "stroke-dasharray": REDUCED ? pct.toFixed(2) + " " + (100 - pct).toFixed(2) : "0 100",
        "stroke-linecap": pct > 4 ? "round" : "butt" }, svg);
      segs.push([seg, pct]);
      offset = (offset - pct + 100) % 100;
      d._color = color;
    });
    raf(function () {
      segs.forEach(function (s) {
        s[0].setAttribute("stroke-dasharray", s[1].toFixed(2) + " " + (100 - s[1]).toFixed(2));
      });
    });

    if (legend) {
      legend.innerHTML = data.map(function (d) {
        var pct = (d.value / total) * 100;
        return '<li><span class="lg-dot" style="background:' + d._color + '"></span>' +
          "<span>" + d.label + "</span>" +
          '<span class="lg-val">' + money0(d.value) + "</span>" +
          '<span class="lg-pct">' + pct.toFixed(1) + "%</span></li>";
      }).join("");
    }
  }

  // ------------------------------------------------------------- gauge
  function polar(cx, cy, r, deg) {
    var a = deg * Math.PI / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  }
  function arcPath(cx, cy, r, fromDeg, toDeg) {
    var s = polar(cx, cy, r, fromDeg), e = polar(cx, cy, r, toDeg);
    var large = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
    return "M " + s[0].toFixed(2) + " " + s[1].toFixed(2) + " A " + r + " " +
      r + " 0 " + large + " 1 " + e[0].toFixed(2) + " " + e[1].toFixed(2);
  }
  function renderGauge(host) {
    var id = host.getAttribute("data-gauge");
    var d = readJSON('[data-gauge-src="' + id + '"]');
    if (!d) return;
    var f = Math.max(0, Math.min(1, d.value || 0));
    var color = TONE[d.tone] || TONE.violet;
    var cx = 100, cy = 100, r = 78, sw = 15;
    var svg = E("svg", { viewBox: "0 0 200 130", class: "gauge-svg", role: "img" });
    var defs = E("defs", {}, svg);
    defs.innerHTML = '<linearGradient id="g-' + id + '" x1="0" y1="0" x2="1" y2="0">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.6"/>' +
      '<stop offset="1" stop-color="' + color + '"/></linearGradient>';
    E("path", { d: arcPath(cx, cy, r, 180, 360), fill: "none",
      stroke: tok("--chart-track", "#efeafb"), "stroke-width": sw, "stroke-linecap": "round" }, svg);
    if (f > 0.004) {
      var arc = E("path", { d: arcPath(cx, cy, r, 180, 180 + f * 180), fill: "none",
        stroke: "url(#g-" + id + ")", "stroke-width": sw, "stroke-linecap": "round",
        class: "gauge-val-arc", pathLength: 100,
        "stroke-dasharray": REDUCED ? "100 100" : "0 100" }, svg);
      var end = polar(cx, cy, r, 180 + f * 180);
      var dot = E("circle", { cx: end[0].toFixed(2), cy: end[1].toFixed(2), r: 4.5,
        fill: tok("--surface", "#fff"), stroke: color, "stroke-width": 3,
        class: "gauge-dot", opacity: REDUCED ? 1 : 0 }, svg);
      raf(function () {
        arc.setAttribute("stroke-dasharray", "100 100");
        dot.setAttribute("opacity", 1);
      });
    }
    var val = E("text", { x: cx, y: cy - 16, "text-anchor": "middle", class: "gauge-val" }, svg);
    val.textContent = (d.center != null) ? d.center : Math.round(f * 100) + "%";
    var lbl = E("text", { x: cx, y: cy + 6, "text-anchor": "middle", class: "gauge-label" }, svg);
    lbl.textContent = d.label || "";
    host.appendChild(svg);
  }

  // -------------------------------------------------------------- bars
  function renderBars(host) {
    var id = host.getAttribute("data-barchart");
    var d = readJSON('[data-barchart-src="' + id + '"]');
    if (!d || !d.points || !d.points.length) return;
    var pts = d.points;
    var W = 760, H = 240, padL = 50, padR = 14, padT = 24, padB = 36;
    var iw = W - padL - padR, ih = H - padT - padB;
    var max = Math.max.apply(null, pts.map(function (p) { return p.value; }).concat([0]));
    if (max <= 0) max = 1;
    var fmt = d.unit === "plain" ? function (n) { return Math.round(n); } : moneyShort;
    var svg = E("svg", { viewBox: "0 0 " + W + " " + H, class: "barchart-svg" });
    var defs = E("defs", {}, svg);
    defs.innerHTML = '<linearGradient id="bc-' + id + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#a855f7"/><stop offset="1" stop-color="#7c3aed"/></linearGradient>';
    var grid = tok("--chart-grid", "#f1ecfd");
    for (var t = 0; t <= 3; t++) {
      var gv = (t / 3) * max, gy = padT + (1 - t / 3) * ih;
      E("line", { x1: padL, x2: W - padR, y1: gy, y2: gy, stroke: grid, "stroke-width": 1 }, svg);
      var yl = E("text", { x: padL - 8, y: gy + 4, "text-anchor": "end", class: "ch-axis" }, svg);
      yl.textContent = fmt(gv);
    }
    var step = iw / pts.length, bw = Math.min(46, step * 0.6), bars = [];
    pts.forEach(function (p, i) {
      var x = padL + i * step + (step - bw) / 2;
      var h = Math.max(0, (p.value / max) * ih);
      var y = padT + ih - h;
      var rect = E("rect", { x: x.toFixed(2), y: y.toFixed(2), width: bw.toFixed(2),
        height: h.toFixed(2), rx: Math.min(5, bw / 2), class: "bar",
        fill: p.value > 0 ? "url(#bc-" + id + ")" : tok("--chart-empty", "#ece8f7") }, svg);
      if (!REDUCED) { rect.style.transform = "scaleY(0)"; bars.push(rect); }
      var xl = E("text", { x: (x + bw / 2).toFixed(2), y: H - 14, "text-anchor": "middle",
        class: "ch-axis" }, svg);
      xl.textContent = p.label;
      if (p.value > 0 && pts.length <= 12) {
        var vt = E("text", { x: (x + bw / 2).toFixed(2), y: (y - 6).toFixed(2),
          "text-anchor": "middle", class: "ch-barval" }, svg);
        vt.textContent = fmt(p.value);
      }
      (function (px, py, label, value) {
        rect.addEventListener("mouseenter", function () {
          var full = d.unit === "plain" ? String(Math.round(value)) : money(value);
          showTip(host, svgToHost(svg, host, px, py), label, [full]);
        });
        rect.addEventListener("mouseleave", function () { hideTip(host); });
      })(x + bw / 2, y, p.label, p.value);
    });
    E("line", { x1: padL, x2: W - padR, y1: padT + ih, y2: padT + ih,
      stroke: tok("--chart-zero", "#c4b5fd"), "stroke-width": 1 }, svg);
    host.appendChild(svg);
    raf(function () { bars.forEach(function (b, i) {
      b.style.transitionDelay = (i * 40) + "ms"; b.style.transform = "";
    }); });
  }

  // -------------------------------------------------------------- flow
  function renderFlow(host) {
    var id = host.getAttribute("data-flowbar");
    var d = readJSON('[data-flowbar-src="' + id + '"]');
    if (!d || !d.segments || !d.segments.length) return;
    var total = d.total || d.segments.reduce(function (s, x) { return s + (x.value || 0); }, 0);
    if (total <= 0) return;
    var W = 760, H = 60, rx = 16;
    var svg = E("svg", { viewBox: "0 0 " + W + " " + H, class: "flowbar-svg" });
    var defs = E("defs", {}, svg);
    defs.innerHTML = '<clipPath id="fb-' + id + '"><rect x="0" y="0" width="' +
      W + '" height="' + H + '" rx="' + rx + '"/></clipPath>';
    var g = E("g", { "clip-path": "url(#fb-" + id + ")" }, svg);
    E("rect", { x: 0, y: 0, width: W, height: H, fill: tok("--chart-track", "#f1ecfd") }, g);
    var x = 0, legend = [];
    d.segments.forEach(function (s, i) {
      var w = (s.value / total) * W;
      var color = s.accent ? TONE.pos : PALETTE[i % PALETTE.length];
      E("rect", { x: x.toFixed(2), y: 0, width: Math.max(0, w).toFixed(2), height: H, fill: color }, g);
      if (w > 56) {
        var tx = E("text", { x: (x + w / 2).toFixed(2), y: H / 2 + 4, "text-anchor": "middle",
          class: "flow-seg-lbl" }, g);
        tx.textContent = Math.round(s.value / total * 100) + "%";
      }
      legend.push({ label: s.label, value: s.value, pct: s.value / total, color: color });
      x += w;
    });
    host.appendChild(svg);
    fadeIn(g, 600, 0);
    var ul = document.querySelector('[data-flowlegend="' + id + '"]');
    if (ul) ul.innerHTML = legend.map(function (l) {
      return '<li><span class="lg-dot" style="background:' + l.color + '"></span>' +
        '<span class="lg-name">' + l.label + '</span>' +
        '<span class="lg-val">' + money0(l.value) + '</span>' +
        '<span class="lg-pct">' + (l.pct * 100).toFixed(0) + '%</span></li>';
    }).join("");
  }

  // -------------------------------------------------------------- area
  function renderArea(host) {
    var id = host.getAttribute("data-areachart");
    var d = readJSON('[data-areachart-src="' + id + '"]');
    if (!d || !d.series || !d.series.length) return;
    var series = d.series.filter(function (s) { return s.points && s.points.length >= 2; });
    if (!series.length) return;
    var W = 760, H = 280, padL = 58, padR = 18, padT = 18, padB = 34;
    var iw = W - padL - padR, ih = H - padT - padB;
    var labels = series[0].points.map(function (p) { return p.label; });
    var n = labels.length, hi = 0;
    series.forEach(function (s) { s.points.forEach(function (p) { if (p.value > hi) hi = p.value; }); });
    if (hi <= 0) hi = 1;
    hi *= 1.08;
    function X(i) { return padL + (i / (n - 1)) * iw; }
    function Y(v) { return padT + (1 - v / hi) * ih; }
    var svg = E("svg", { viewBox: "0 0 " + W + " " + H, class: "areachart-svg" });
    var defs = E("defs", {}, svg), defsHTML = "";
    var grid = tok("--chart-grid", "#f1ecfd");
    for (var t = 0; t <= 4; t++) {
      var gv = (t / 4) * hi, gy = Y(gv);
      E("line", { x1: padL, x2: W - padR, y1: gy, y2: gy, stroke: grid, "stroke-width": 1 }, svg);
      var yl = E("text", { x: padL - 8, y: gy + 4, "text-anchor": "end", class: "ch-axis" }, svg);
      yl.textContent = moneyShort(gv);
    }
    var lines = [];
    series.forEach(function (s, si) {
      var line = "", area = "";
      s.points.forEach(function (p, i) {
        var px = X(i).toFixed(2), py = Y(p.value).toFixed(2);
        line += (i === 0 ? "M " : "L ") + px + " " + py + " ";
        area += (i === 0 ? "M " : "L ") + px + " " + py + " ";
      });
      if (s.fill) {
        area += "L " + X(n - 1).toFixed(2) + " " + Y(0).toFixed(2) +
          " L " + X(0).toFixed(2) + " " + Y(0).toFixed(2) + " Z";
        var gid = "ac-" + id + "-" + si;
        defsHTML += '<linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0" stop-color="' + s.color + '" stop-opacity="0.32"/>' +
          '<stop offset="1" stop-color="' + s.color + '" stop-opacity="0.02"/></linearGradient>';
        var ap = E("path", { d: area, fill: "url(#" + gid + ")", stroke: "none" }, svg);
        fadeIn(ap, 700, 500);
      }
      var lp = E("path", { d: line.trim(), fill: "none", stroke: s.color, "stroke-width": 2.5,
        "stroke-linejoin": "round", "stroke-linecap": "round",
        "stroke-dasharray": s.fill ? "0" : "5 4" }, svg);
      if (s.fill) drawIn(lp, 1200); else fadeIn(lp, 600, 700);
      lines.push(lp);
    });
    defs.innerHTML = defsHTML;
    [0, Math.floor((n - 1) / 2), n - 1].forEach(function (i) {
      var tx = E("text", { x: X(i).toFixed(2), y: H - 10, class: "ch-axis",
        "text-anchor": i === 0 ? "start" : (i === n - 1 ? "end" : "middle") }, svg);
      tx.textContent = labels[i];
    });
    // hover
    var guide = E("line", { class: "chart-guide", x1: 0, x2: 0, y1: padT, y2: H - padB, opacity: 0 }, svg);
    var dots = series.map(function (s) {
      return E("circle", { r: 5, fill: s.color, stroke: tok("--surface", "#fff"),
        "stroke-width": 2, opacity: 0 }, svg);
    });
    svg.addEventListener("mousemove", function (e) {
      var vx = mouseToView(svg, e)[0];
      var i = Math.round((vx - padL) / iw * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      var x = X(i);
      guide.setAttribute("x1", x); guide.setAttribute("x2", x); guide.setAttribute("opacity", 1);
      var tipLines = [], topY = H;
      series.forEach(function (s, si) {
        var y = Y(s.points[i].value);
        dots[si].setAttribute("cx", x); dots[si].setAttribute("cy", y); dots[si].setAttribute("opacity", 1);
        if (y < topY) topY = y;
        tipLines.push(s.name + ": " + money(s.points[i].value));
      });
      showTip(host, svgToHost(svg, host, x, topY), labels[i], tipLines);
    });
    svg.addEventListener("mouseleave", function () {
      guide.setAttribute("opacity", 0);
      dots.forEach(function (c) { c.setAttribute("opacity", 0); });
      hideTip(host);
    });
    host.appendChild(svg);
    var ul = document.querySelector('[data-arealegend="' + id + '"]');
    if (ul) ul.innerHTML = series.map(function (s) {
      var last = s.points[s.points.length - 1].value;
      return '<li><span class="lg-dot" style="background:' + s.color + '"></span>' +
        '<span class="lg-name">' + s.name + '</span>' +
        '<span class="lg-val">' + money0(last) + '</span></li>';
    }).join("");
  }

  // ---------------------------------------------------------- render all
  function renderAll() {
    document.querySelectorAll(".linechart[data-chart]").forEach(function (h) { clear(h); renderLine(h); });
    document.querySelectorAll("svg.donut[data-src]").forEach(function (s) { clear(s); renderDonut(s); });
    document.querySelectorAll(".gauge[data-gauge]").forEach(function (h) { clear(h); renderGauge(h); });
    document.querySelectorAll(".barchart[data-barchart]").forEach(function (h) { clear(h); renderBars(h); });
    document.querySelectorAll(".flowbar[data-flowbar]").forEach(function (h) { clear(h); renderFlow(h); });
    document.querySelectorAll(".areachart[data-areachart]").forEach(function (h) { clear(h); renderArea(h); });
  }
  window.cairnRenderCharts = renderAll;
  renderAll();
})();
