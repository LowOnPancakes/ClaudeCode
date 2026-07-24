// Chart rendering (plain SVG, no external libraries) + table filters + form wiring.
(function () {
  "use strict";

  const SERIES_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
  const SVG_NS = "http://www.w3.org/2000/svg";

  function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function niceMax(value) {
    if (value <= 0) return 1;
    const exp = Math.floor(Math.log10(value));
    const base = Math.pow(10, exp);
    const steps = [1, 2, 2.5, 5, 10];
    for (const s of steps) {
      if (value <= s * base) return s * base;
    }
    return 10 * base;
  }

  function formatValue(v, fmt) {
    if (fmt === "currency") {
      if (Math.abs(v) >= 1000) return "$" + (v / 1000).toFixed(1) + "k";
      return "$" + Math.round(v);
    }
    if (fmt === "percent") return v.toFixed(1) + "%";
    return String(Math.round(v * 10) / 10);
  }

  // Horizontal grouped bar chart. data = {labels: [...], series: [{name, values}]}
  function renderBarChart(containerId, data, opts) {
    const container = document.getElementById(containerId);
    if (!container) return;
    opts = opts || {};
    const fmt = opts.valueFormat || "count";
    const labels = data.labels;
    const series = data.series;
    if (!labels.length) {
      container.innerHTML = '<p class="hint">No data yet.</p>';
      return;
    }

    const rowH = series.length > 1 ? 15 : 20;
    const rowGap = 10;
    const groupH = rowH * series.length + (series.length > 1 ? 2 * (series.length - 1) : 0);
    const bandH = groupH + rowGap;
    const marginLeft = opts.labelWidth || 150;
    const marginTop = 26;
    const marginRight = 46;
    const width = 560;
    const plotW = width - marginLeft - marginRight;
    const height = marginTop + labels.length * bandH + 10;

    let maxVal = 0;
    series.forEach((s) => s.values.forEach((v) => { if (v > maxVal) maxVal = v; }));
    const scaleMax = niceMax(maxVal || 1);

    container.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "viz-root";
    container.appendChild(wrap);

    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
    wrap.appendChild(svg);

    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    wrap.appendChild(tooltip);

    // Gridlines + axis ticks (4 divisions)
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const x = marginLeft + (plotW * i) / ticks;
      el("line", { x1: x, x2: x, y1: marginTop - 8, y2: height - 8, class: "gridline" }, svg);
      const t = el("text", { x: x, y: marginTop - 12, class: "axis-label", "text-anchor": "middle" }, svg);
      t.textContent = formatValue((scaleMax * i) / ticks, fmt);
    }

    labels.forEach((label, li) => {
      const groupTop = marginTop + li * bandH;
      const labelNode = el("text", {
        x: marginLeft - 10, y: groupTop + groupH / 2 + 4, class: "axis-label", "text-anchor": "end",
      }, svg);
      labelNode.textContent = label.length > 26 ? label.slice(0, 25) + "…" : label;
      const titleNode = el("title", {}, labelNode);
      titleNode.textContent = label;

      series.forEach((s, si) => {
        const val = s.values[li] || 0;
        const barW = Math.max(val > 0 ? 2 : 0, (val / scaleMax) * plotW);
        const y = groupTop + si * (rowH + 2);
        const rect = el("rect", {
          x: marginLeft, y: y, width: barW, height: rowH, rx: 3,
          fill: SERIES_COLORS[si % SERIES_COLORS.length],
          class: "bar-mark",
        }, svg);
        rect.addEventListener("mousemove", (evt) => {
          const rectBounds = wrap.getBoundingClientRect();
          tooltip.style.left = (evt.clientX - rectBounds.left + 12) + "px";
          tooltip.style.top = (evt.clientY - rectBounds.top - 10) + "px";
          tooltip.style.opacity = "1";
          tooltip.textContent = `${label}${s.name ? " – " + s.name : ""}: ${formatValue(val, fmt)}`;
        });
        rect.addEventListener("mouseleave", () => { tooltip.style.opacity = "0"; });

        if (series.length === 1 && val > 0) {
          const valLabel = el("text", {
            x: marginLeft + barW + 6, y: y + rowH / 2 + 4, class: "axis-label",
          }, svg);
          valLabel.textContent = formatValue(val, fmt);
        }
      });
    });

    if (series.length > 1) {
      const legend = document.createElement("div");
      legend.className = "viz-legend";
      series.forEach((s, si) => {
        const item = document.createElement("span");
        item.innerHTML = `<span class="swatch" style="background:${SERIES_COLORS[si % SERIES_COLORS.length]}"></span>${s.name}`;
        legend.appendChild(item);
      });
      container.appendChild(legend);
    }
  }

  function initCharts() {
    const dataNode = document.getElementById("chart-data");
    if (!dataNode) return;
    const d = JSON.parse(dataNode.textContent);

    renderBarChart("chart-dept", { labels: d.dept_budget.labels, series: [{ name: "Recommended raise $", values: d.dept_budget.values }] }, { valueFormat: "currency", labelWidth: 170 });
    renderBarChart("chart-perf", { labels: d.perf_budget.labels, series: [{ name: "Recommended raise $", values: d.perf_budget.values }] }, { valueFormat: "currency", labelWidth: 100 });
    renderBarChart("chart-priority", { labels: d.priority_budget.labels, series: [{ name: "Recommended raise $", values: d.priority_budget.values }] }, { valueFormat: "currency", labelWidth: 210 });
    renderBarChart("chart-immediate-phased", { labels: d.immediate_vs_phased.labels, series: [{ name: "Cost", values: d.immediate_vs_phased.values }] }, { valueFormat: "currency", labelWidth: 170 });
    renderBarChart("chart-compa", { labels: d.compa_dist.labels, series: [{ name: "Before", values: d.compa_dist.before }, { name: "After", values: d.compa_dist.after }] }, { valueFormat: "count", labelWidth: 90 });
    renderBarChart("chart-position", { labels: d.position_dist.labels, series: [{ name: "Before", values: d.position_dist.before }, { name: "After", values: d.position_dist.after }] }, { valueFormat: "count", labelWidth: 160 });
    renderBarChart("chart-flight-risk", { labels: d.flight_risk_counts.labels, series: [{ name: "Employees", values: d.flight_risk_counts.values }] }, { valueFormat: "count", labelWidth: 90 });
  }

  // --- Table filters -------------------------------------------------------
  function initFilters() {
    const search = document.getElementById("search");
    const deptFilter = document.getElementById("filter-department");
    const riskFilter = document.getElementById("filter-risk");
    const priorityFilter = document.getElementById("filter-priority");
    const reviewOnly = document.getElementById("filter-review-only");
    const rows = Array.from(document.querySelectorAll("table.emp-table tbody tr"));
    if (!rows.length) return;

    function apply() {
      const q = (search && search.value || "").trim().toLowerCase();
      const dept = deptFilter && deptFilter.value;
      const risk = riskFilter && riskFilter.value;
      const priority = priorityFilter && priorityFilter.value;
      const needsReview = reviewOnly && reviewOnly.checked;

      rows.forEach((row) => {
        const hay = (row.dataset.search || "").toLowerCase();
        let show = q === "" || hay.includes(q);
        if (show && dept) show = row.dataset.department === dept;
        if (show && risk) show = row.dataset.risk === risk;
        if (show && priority) show = row.dataset.priority === priority;
        if (show && needsReview) show = row.dataset.review === "1";
        row.classList.toggle("hidden-row", !show);
      });
    }

    [search, deptFilter, riskFilter, priorityFilter, reviewOnly].forEach((elx) => {
      if (elx) elx.addEventListener("input", apply);
    });
  }

  // --- Edit / override row wiring ------------------------------------------
  function initRowActions() {
    document.querySelectorAll("[data-edit-employee]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const data = JSON.parse(btn.dataset.editEmployee);
        const form = document.getElementById("employee-form");
        if (!form) return;
        Object.keys(data).forEach((key) => {
          const input = form.elements[key];
          if (!input) return;
          if (input.type === "checkbox") input.checked = data[key] === "Y";
          else input.value = data[key] == null ? "" : data[key];
        });
        document.getElementById("employee-panel").open = true;
        form.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });

    document.querySelectorAll("[data-override-employee]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const data = JSON.parse(btn.dataset.overrideEmployee);
        const form = document.getElementById("override-form");
        if (!form) return;
        form.elements["employee_id"].value = data.employee_id;
        document.getElementById("override-context").textContent =
          `${data.name} — system recommendation: ${data.system_pct}% ($${data.system_amount})`;
        document.getElementById("override-panel").open = true;
        form.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }

  function initRangeDisplays() {
    document.querySelectorAll("input[type=range]").forEach((range) => {
      const out = document.getElementById(range.id + "-value");
      if (!out) return;
      const update = () => { out.textContent = range.value; };
      range.addEventListener("input", update);
      update();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    initFilters();
    initRowActions();
    initRangeDisplays();
  });
})();
