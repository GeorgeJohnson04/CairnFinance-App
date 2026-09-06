"use strict";
(function () {
  // ---------------------------------------------------- flashes
  document.querySelectorAll(".flash").forEach(function (el) {
    var close = el.querySelector(".flash-close");
    if (close) close.addEventListener("click", function () { el.remove(); });
    setTimeout(function () {
      el.style.transition = "opacity .4s ease, transform .4s ease";
      el.style.opacity = "0";
      el.style.transform = "translateX(20px)";
      setTimeout(function () { el.remove(); }, 400);
    }, 6000);
  });

  // ---------------------------------------------------- password toggle
  document.querySelectorAll("[data-toggle-pw]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-toggle-pw"));
      if (!input) return;
      input.type = input.type === "password" ? "text" : "password";
    });
  });

  // ---------------------------------------------------- modals
  function openModal(id) {
    var dlg = document.getElementById(id);
    if (dlg && typeof dlg.showModal === "function") dlg.showModal();
  }
  document.querySelectorAll("[data-open]").forEach(function (btn) {
    btn.addEventListener("click", function () { openModal(btn.getAttribute("data-open")); });
  });
  document.querySelectorAll("dialog.modal").forEach(function (dlg) {
    dlg.querySelectorAll("[data-close]").forEach(function (b) {
      b.addEventListener("click", function () { dlg.close(); });
    });
    // click on backdrop closes
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg) dlg.close();
    });
  });

  // --------------------------------- populate "edit" dialogs from data-*
  function fillEdit(trigger, attr, dialogId, action, fields) {
    var data;
    try { data = JSON.parse(trigger.getAttribute(attr)); } catch (e) { return; }
    var form = document.getElementById(dialogId + "-form");
    if (form && action) form.action = action.replace("__ID__", data.id);
    Object.keys(fields).forEach(function (key) {
      var el = document.getElementById(fields[key]);
      if (!el) return;
      var v = data[key];
      el.value = (v === null || v === undefined) ? "" : v;
    });
    openModal(dialogId);
  }

  document.querySelectorAll("[data-edit-holding]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      fillEdit(btn, "data-edit-holding", "edit-holding",
        "/holdings/__ID__/edit",
        { account_id: "eh-account", asset_type: "eh-type", ticker: "eh-ticker",
          name: "eh-name", industry: "eh-industry", quantity: "eh-quantity",
          avg_cost: "eh-avg", current_price: "eh-price" });
    });
  });
  document.querySelectorAll("[data-edit-goal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      fillEdit(btn, "data-edit-goal", "edit-goal", "/goals/__ID__/edit",
        { name: "eg-name", target_amount: "eg-target",
          saved_amount: "eg-saved", target_date: "eg-date" });
    });
  });
  document.querySelectorAll("[data-edit-account]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      fillEdit(btn, "data-edit-account", "edit-account",
        "/settings/accounts/__ID__/edit", { name: "ea-name", kind: "ea-kind" });
    });
  });

  // ---------------------------------------------------- mobile nav
  var shell = document.getElementById("app-shell");
  if (shell) {
    document.querySelectorAll("[data-open-nav]").forEach(function (b) {
      b.addEventListener("click", function () { shell.classList.add("nav-open"); });
    });
    document.querySelectorAll("[data-close-nav]").forEach(function (b) {
      b.addEventListener("click", function () { shell.classList.remove("nav-open"); });
    });
  }

  // =================================================== STOCK SEARCH
  // Live symbol search + quote lookup, all proxied through our server
  // (the browser never calls Yahoo directly, which keeps CSP strict).
  function money(n) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    return "$" + Number(n).toLocaleString(undefined,
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  document.querySelectorAll("[data-stock-search]").forEach(function (input) {
    var wrap = input.closest(".stock-search");
    var box = wrap.querySelector(".stock-search-results");
    var field = input.closest(".field");
    var preview = field ? field.querySelector(".quote-preview") : null;
    var tTicker = input.getAttribute("data-target-ticker");
    var tName = input.getAttribute("data-target-name");
    var tPrice = input.getAttribute("data-target-price");
    var timer = null, items = [], active = -1, lastQuery = "";

    function close() { box.classList.remove("open"); box.innerHTML = ""; active = -1; }

    function render() {
      if (!items.length) {
        box.innerHTML = '<div class="ss-empty">No matches found</div>';
        box.classList.add("open");
        return;
      }
      box.innerHTML = items.map(function (it, i) {
        return '<div class="ss-item' + (i === active ? " active" : "") +
          '" data-i="' + i + '">' +
          '<span class="ss-sym">' + it.symbol + "</span>" +
          '<span class="ss-name">' + (it.name || "") + "</span>" +
          (it.exchange ? '<span class="ss-exch">' + it.exchange + "</span>" : "") +
          "</div>";
      }).join("");
      box.classList.add("open");
      box.querySelectorAll(".ss-item").forEach(function (row) {
        row.addEventListener("mousedown", function (e) {
          e.preventDefault();
          choose(items[parseInt(row.getAttribute("data-i"), 10)]);
        });
      });
    }

    function setField(sel, val) {
      if (!sel || val === undefined || val === null) return;
      var el = document.querySelector(sel);
      if (el) el.value = val;
    }

    function choose(it) {
      if (!it) return;
      input.value = it.symbol + (it.name ? " - " + it.name : "");
      setField(tTicker, it.symbol);
      if (tName && it.name) setField(tName, it.name);
      close();
      // fetch a fresh quote to fill price + preview
      fetch("/api/quote?symbol=" + encodeURIComponent(it.symbol))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (q) {
          if (!q || q.price == null) return;
          setField(tPrice, q.price);
          if (preview) {
            var cls = q.change >= 0 ? "pos" : "neg";
            var sign = q.change >= 0 ? "+" : "";
            preview.innerHTML = "<span><b>" + q.symbol + "</b> " +
              money(q.price) + "</span>" +
              '<span class="delta ' + cls + '">' + sign +
              money(q.change).replace("$", "$").replace("$-", "-$") +
              " (" + sign + (q.change_pct != null ? q.change_pct.toFixed(2) : "0") +
              "%)</span>";
            preview.classList.add("show");
          }
        })
        .catch(function () {});
    }

    function search(q) {
      fetch("/api/search?q=" + encodeURIComponent(q))
        .then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (data) {
          items = (data.results || []).slice(0, 8);
          active = -1;
          render();
        })
        .catch(function () { items = []; render(); });
    }

    input.addEventListener("input", function () {
      var q = input.value.trim();
      if (preview) preview.classList.remove("show");
      if (q.length < 1) { close(); return; }
      if (q === lastQuery) return;
      lastQuery = q;
      clearTimeout(timer);
      timer = setTimeout(function () { search(q); }, 220);
    });

    input.addEventListener("keydown", function (e) {
      if (!box.classList.contains("open")) return;
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
      else if (e.key === "Enter") { e.preventDefault(); if (active >= 0) choose(items[active]); }
      else if (e.key === "Escape") { close(); }
    });

    input.addEventListener("blur", function () { setTimeout(close, 150); });
  });

  // =================================================== THEME TOGGLE
  var REDUCED = !!(window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function paintToggle() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      var lbl = b.querySelector("[data-theme-label]");
      if (lbl) lbl.textContent = dark ? "Light mode" : "Dark mode";
      var sun = b.querySelector(".ic-sun"), moon = b.querySelector(".ic-moon");
      if (sun) sun.hidden = !dark;
      if (moon) moon.hidden = dark;
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0e0a1c" : "#7c3aed");
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("cairn-theme", next); } catch (e) {}
      paintToggle();
      if (window.cairnRenderCharts) window.cairnRenderCharts();
    });
  });
  paintToggle();

  // =================================================== COUNT-UP NUMBERS
  // Big stat values tick up from zero on load. The final text is restored
  // verbatim so formatting (currency, sign, decimals, %) is never altered.
  function countUp(el) {
    var txt = el.textContent.trim();
    var m = txt.match(/^([+\-]?)(\$?)([\d,]+)(?:\.(\d+))?(%?)$/);
    if (!m) return;
    var sign = m[1], cur = m[2], dec = m[4] || "", pct = m[5];
    var target = parseFloat(m[3].replace(/,/g, "") + (dec ? "." + dec : ""));
    if (!isFinite(target) || target === 0) return;
    var decimals = dec.length, start = null, dur = 900;
    function fmt(v) {
      return sign + cur + v.toLocaleString(undefined,
        { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + pct;
    }
    function step(t) {
      if (start === null) start = t;
      var p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * e);
      if (p < 1) requestAnimationFrame(step); else el.textContent = txt;
    }
    requestAnimationFrame(step);
  }
  if (!REDUCED) document.querySelectorAll(".stat-value, .gs-val").forEach(countUp);

  // =================================================== SORTABLE TABLES
  document.querySelectorAll("table.data.sortable").forEach(function (table) {
    var ths = table.querySelectorAll("th[data-sort]");
    ths.forEach(function (th) {
      th.addEventListener("click", function () {
        var col = Array.prototype.indexOf.call(th.parentNode.children, th);
        var type = th.getAttribute("data-sort");
        var asc = !th.classList.contains("asc");
        ths.forEach(function (o) { o.classList.remove("asc", "desc"); });
        th.classList.add(asc ? "asc" : "desc");
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        function val(r) {
          var c = r.cells[col], t = c ? c.textContent.trim() : "";
          if (type === "num") {
            var n = parseFloat(t.replace(/[^0-9.\-]/g, ""));
            return isNaN(n) ? -Infinity : n;
          }
          return t.toLowerCase();
        }
        rows.sort(function (a, b) {
          var va = val(a), vb = val(b);
          if (va < vb) return asc ? -1 : 1;
          if (va > vb) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  // =================================================== PWA SERVICE WORKER
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }
})();
