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
})();
