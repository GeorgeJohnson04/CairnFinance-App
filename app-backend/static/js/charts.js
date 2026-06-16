"use strict";
// Renders accessible SVG donut charts + legends from JSON embedded by the
// `donut()` macro. No external chart library — keeps the strict CSP intact.
(function () {
  var PALETTE = ["#7c3aed", "#a855f7", "#c026d3", "#a78bfa", "#8b5cf6",
                 "#d946ef", "#c4b5fd", "#9333ea", "#6d28d9", "#e879f9",
                 "#ddd6fe", "#581c87"];

  function money0(n) {
    return "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  // ---------------------------------------------------- area/line chart
  function money(n) {
    var sign = n < 0 ? "-" : "";
    return sign + "$" + Math.abs(n).toLocaleString(undefined,
      { maximumFractionDigits: 0 });
  }

  document.querySelectorAll(".linechart[data-chart]").forEach(function (host) {
    var id = host.getAttribute("data-chart");
    var holder = document.querySelector('[data-linechart="' + id + '"]');
    if (!holder) return;
    var pts;
    try { pts = JSON.parse(holder.textContent); } catch (e) { return; }
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

    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("class", "linechart-svg");
    svg.setAttribute("preserveAspectRatio", "none");

    var defs = document.createElementNS(ns, "defs");
    defs.innerHTML =
      '<linearGradient id="lc-fill" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#7c3aed" stop-opacity="0.35"/>' +
      '<stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></linearGradient>';
    svg.appendChild(defs);

    // horizontal gridlines + y labels (4 ticks)
    for (var t = 0; t <= 4; t++) {
      var v = lo + (t / 4) * (hi - lo);
      var y = Y(v);
      var line = document.createElementNS(ns, "line");
      line.setAttribute("x1", padL); line.setAttribute("x2", W - padR);
      line.setAttribute("y1", y); line.setAttribute("y2", y);
      line.setAttribute("stroke", v === 0 ? "#c4b5fd" : "#f1ecfd");
      line.setAttribute("stroke-width", v === 0 ? "1.5" : "1");
      svg.appendChild(line);
      var lbl = document.createElementNS(ns, "text");
      lbl.setAttribute("x", padL - 8); lbl.setAttribute("y", y + 4);
      lbl.setAttribute("text-anchor", "end"); lbl.setAttribute("class", "lc-axis");
      lbl.textContent = money(v);
      svg.appendChild(lbl);
    }

    // build path
    var d = "", area = "M " + X(0) + " " + Y(0);
    pts.forEach(function (p, i) {
      d += (i === 0 ? "M " : "L ") + X(i) + " " + Y(p.value) + " ";
      area += " L " + X(i) + " " + Y(p.value);
    });
    area += " L " + X(n - 1) + " " + Y(0) + " Z";

    var areaPath = document.createElementNS(ns, "path");
    areaPath.setAttribute("d", area); areaPath.setAttribute("fill", "url(#lc-fill)");
    svg.appendChild(areaPath);

    var endVal = pts[n - 1].value;
    var lineColor = endVal >= 0 ? "#7c3aed" : "#ef4444";
    var linePath = document.createElementNS(ns, "path");
    linePath.setAttribute("d", d.trim()); linePath.setAttribute("fill", "none");
    linePath.setAttribute("stroke", lineColor); linePath.setAttribute("stroke-width", "2.5");
    linePath.setAttribute("stroke-linejoin", "round");
    linePath.setAttribute("stroke-linecap", "round");
    svg.appendChild(linePath);

    // x labels (first, middle, last)
    [0, Math.floor((n - 1) / 2), n - 1].forEach(function (i) {
      var tx = document.createElementNS(ns, "text");
      tx.setAttribute("x", X(i)); tx.setAttribute("y", H - 10);
      tx.setAttribute("text-anchor", i === 0 ? "start" : (i === n - 1 ? "end" : "middle"));
      tx.setAttribute("class", "lc-axis");
      tx.textContent = pts[i].label;
      svg.appendChild(tx);
    });

    // end marker
    var dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", X(n - 1)); dot.setAttribute("cy", Y(endVal));
    dot.setAttribute("r", "4"); dot.setAttribute("fill", lineColor);
    svg.appendChild(dot);

    host.appendChild(svg);
  });

  document.querySelectorAll("svg.donut[data-src]").forEach(function (svg) {
    var id = svg.getAttribute("data-src");
    var holder = document.querySelector('[data-donut="' + id + '"]');
    var legend = document.querySelector('[data-legend="' + id + '"]');
    if (!holder) return;
    var data;
    try { data = JSON.parse(holder.textContent); } catch (e) { return; }
    if (!data || !data.length) return;

    var total = data.reduce(function (s, d) { return s + (d.value || 0); }, 0);
    if (total <= 0) return;

    var ns = "http://www.w3.org/2000/svg";
    // track ring
    var track = document.createElementNS(ns, "circle");
    track.setAttribute("cx", "21"); track.setAttribute("cy", "21");
    track.setAttribute("r", "15.9155"); track.setAttribute("fill", "none");
    track.setAttribute("stroke", "#f1ecfd"); track.setAttribute("stroke-width", "5");
    svg.appendChild(track);

    var offset = 25; // start at top
    data.forEach(function (d, i) {
      var pct = (d.value / total) * 100;
      var color = PALETTE[i % PALETTE.length];
      var seg = document.createElementNS(ns, "circle");
      seg.setAttribute("cx", "21"); seg.setAttribute("cy", "21");
      seg.setAttribute("r", "15.9155"); seg.setAttribute("fill", "none");
      seg.setAttribute("stroke", color); seg.setAttribute("stroke-width", "5");
      seg.setAttribute("stroke-dasharray", pct.toFixed(2) + " " + (100 - pct).toFixed(2));
      seg.setAttribute("stroke-dashoffset", offset.toFixed(2));
      seg.setAttribute("stroke-linecap", pct > 4 ? "round" : "butt");
      svg.appendChild(seg);
      offset = (offset - pct + 100) % 100;
      d._color = color;
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
  });

  // ============================================ shared chart helpers
  var NS = "http://www.w3.org/2000/svg";
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
  function moneyShort(n) {
    var a = Math.abs(n), s = n < 0 ? "-" : "";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k";
    return s + "$" + Math.round(a);
  }
  var TONE = { violet: "#7c3aed", pos: "#10b981", warn: "#f59e0b",
               neg: "#ef4444", ink: "#8e87a6" };

  // ------------------------------------------------- semicircle gauges
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
  document.querySelectorAll(".gauge[data-gauge]").forEach(function (host) {
    var id = host.getAttribute("data-gauge");
    var d = readJSON('[data-gauge-src="' + id + '"]');
    if (!d) return;
    var f = Math.max(0, Math.min(1, d.value || 0));
    var color = TONE[d.tone] || TONE.violet;
    var cx = 100, cy = 100, r = 78, sw = 15;
    var svg = E("svg", { viewBox: "0 0 200 130", class: "gauge-svg",
      role: "img" });
    var defs = E("defs", {}, svg);
    defs.innerHTML = '<linearGradient id="g-' + id + '" x1="0" y1="0" x2="1" y2="0">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.6"/>' +
      '<stop offset="1" stop-color="' + color + '"/></linearGradient>';
    E("path", { d: arcPath(cx, cy, r, 180, 360), fill: "none",
      stroke: "#efeafb", "stroke-width": sw, "stroke-linecap": "round" }, svg);
    if (f > 0.004) {
      E("path", { d: arcPath(cx, cy, r, 180, 180 + f * 180), fill: "none",
        stroke: "url(#g-" + id + ")", "stroke-width": sw,
        "stroke-linecap": "round" }, svg);
      var end = polar(cx, cy, r, 180 + f * 180);
      E("circle", { cx: end[0].toFixed(2), cy: end[1].toFixed(2), r: 4.5,
        fill: "#fff", stroke: color, "stroke-width": 3 }, svg);
    }
    var val = E("text", { x: cx, y: cy - 16, "text-anchor": "middle",
      class: "gauge-val" }, svg);
    val.textContent = (d.center != null) ? d.center : Math.round(f * 100) + "%";
    var lbl = E("text", { x: cx, y: cy + 6, "text-anchor": "middle",
      class: "gauge-label" }, svg);
    lbl.textContent = d.label || "";
    host.appendChild(svg);
  });

  // ------------------------------------------------- vertical bar charts
  document.querySelectorAll(".barchart[data-barchart]").forEach(function (host) {
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
    for (var t = 0; t <= 3; t++) {
      var gv = (t / 3) * max, gy = padT + (1 - t / 3) * ih;
      E("line", { x1: padL, x2: W - padR, y1: gy, y2: gy, stroke: "#f1ecfd",
        "stroke-width": 1 }, svg);
      var yl = E("text", { x: padL - 8, y: gy + 4, "text-anchor": "end",
        class: "ch-axis" }, svg);
      yl.textContent = fmt(gv);
    }
    var step = iw / pts.length;
    var bw = Math.min(46, step * 0.6);
    pts.forEach(function (p, i) {
      var x = padL + i * step + (step - bw) / 2;
      var h = Math.max(0, (p.value / max) * ih);
      var y = padT + ih - h;
      E("rect", { x: x.toFixed(2), y: y.toFixed(2), width: bw.toFixed(2),
        height: h.toFixed(2), rx: Math.min(5, bw / 2),
        fill: p.value > 0 ? "url(#bc-" + id + ")" : "#ece8f7" }, svg);
      var xl = E("text", { x: (x + bw / 2).toFixed(2), y: H - 14,
        "text-anchor": "middle", class: "ch-axis" }, svg);
      xl.textContent = p.label;
      if (p.value > 0 && pts.length <= 12) {
        var vt = E("text", { x: (x + bw / 2).toFixed(2), y: (y - 6).toFixed(2),
          "text-anchor": "middle", class: "ch-barval" }, svg);
        vt.textContent = fmt(p.value);
      }
    });
    E("line", { x1: padL, x2: W - padR, y1: padT + ih, y2: padT + ih,
      stroke: "#c4b5fd", "stroke-width": 1 }, svg);
    host.appendChild(svg);
  });

  // ------------------------------------------------- horizontal flow bar
  document.querySelectorAll(".flowbar[data-flowbar]").forEach(function (host) {
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
    E("rect", { x: 0, y: 0, width: W, height: H, fill: "#f1ecfd" }, g);
    var x = 0, legend = [];
    d.segments.forEach(function (s, i) {
      var w = (s.value / total) * W;
      var color = s.accent ? TONE.pos : PALETTE[i % PALETTE.length];
      E("rect", { x: x.toFixed(2), y: 0, width: Math.max(0, w).toFixed(2),
        height: H, fill: color }, g);
      if (w > 56) {
        var tx = E("text", { x: (x + w / 2).toFixed(2), y: H / 2 + 4,
          "text-anchor": "middle", class: "flow-seg-lbl" }, g);
        tx.textContent = Math.round(s.value / total * 100) + "%";
      }
      legend.push({ label: s.label, value: s.value, pct: s.value / total,
        color: color });
      x += w;
    });
    host.appendChild(svg);
    var ul = document.querySelector('[data-flowlegend="' + id + '"]');
    if (ul) ul.innerHTML = legend.map(function (l) {
      return '<li><span class="lg-dot" style="background:' + l.color + '"></span>' +
        '<span class="lg-name">' + l.label + '</span>' +
        '<span class="lg-val">' + money0(l.value) + '</span>' +
        '<span class="lg-pct">' + (l.pct * 100).toFixed(0) + '%</span></li>';
    }).join("");
  });

  // ------------------------------------------------- multi-series area chart
  document.querySelectorAll(".areachart[data-areachart]").forEach(function (host) {
    var id = host.getAttribute("data-areachart");
    var d = readJSON('[data-areachart-src="' + id + '"]');
    if (!d || !d.series || !d.series.length) return;
    var series = d.series.filter(function (s) { return s.points && s.points.length >= 2; });
    if (!series.length) return;
    var W = 760, H = 280, padL = 58, padR = 18, padT = 18, padB = 34;
    var iw = W - padL - padR, ih = H - padT - padB;
    var labels = series[0].points.map(function (p) { return p.label; });
    var n = labels.length;
    var hi = 0;
    series.forEach(function (s) {
      s.points.forEach(function (p) { if (p.value > hi) hi = p.value; });
    });
    if (hi <= 0) hi = 1;
    hi *= 1.08;
    function X(i) { return padL + (i / (n - 1)) * iw; }
    function Y(v) { return padT + (1 - v / hi) * ih; }
    var svg = E("svg", { viewBox: "0 0 " + W + " " + H, class: "areachart-svg" });
    var defs = E("defs", {}, svg), defsHTML = "";
    for (var t = 0; t <= 4; t++) {
      var gv = (t / 4) * hi, gy = Y(gv);
      E("line", { x1: padL, x2: W - padR, y1: gy, y2: gy, stroke: "#f1ecfd",
        "stroke-width": 1 }, svg);
      var yl = E("text", { x: padL - 8, y: gy + 4, "text-anchor": "end",
        class: "ch-axis" }, svg);
      yl.textContent = moneyShort(gv);
    }
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
        E("path", { d: area, fill: "url(#" + gid + ")", stroke: "none" }, svg);
      }
      E("path", { d: line.trim(), fill: "none", stroke: s.color,
        "stroke-width": 2.5, "stroke-linejoin": "round",
        "stroke-linecap": "round",
        "stroke-dasharray": s.fill ? "0" : "5 4" }, svg);
    });
    defs.innerHTML = defsHTML;
    [0, Math.floor((n - 1) / 2), n - 1].forEach(function (i) {
      var tx = E("text", { x: X(i).toFixed(2), y: H - 10,
        "text-anchor": i === 0 ? "start" : (i === n - 1 ? "end" : "middle"),
        class: "ch-axis" }, svg);
      tx.textContent = labels[i];
    });
    host.appendChild(svg);
    var ul = document.querySelector('[data-arealegend="' + id + '"]');
    if (ul) ul.innerHTML = series.map(function (s) {
      var last = s.points[s.points.length - 1].value;
      return '<li><span class="lg-dot" style="background:' + s.color + '"></span>' +
        '<span class="lg-name">' + s.name + '</span>' +
        '<span class="lg-val">' + money0(last) + '</span></li>';
    }).join("");
  });
})();
