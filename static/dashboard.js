// Graphiques du tableau de bord (Chart.js, servi localement).
(function () {
  const raw = document.getElementById("chart-data");
  if (!raw || !window.Chart) return;
  const { charts, domainIds } = JSON.parse(raw.textContent);
  const PAL = ["#12355b", "#1f8a5b", "#c4501b", "#6b7fd7", "#d9a400", "#7a4d9e", "#2b9fb8"];
  const labels = (rows) => rows.map((r) => r[0]);
  const values = (rows) => rows.map((r) => r[1]);
  const fcfa = (v) => new Intl.NumberFormat("fr-FR").format(v) + " FCFA";
  Chart.defaults.font.family = "system-ui, sans-serif";
  const opt = { responsive: true, maintainAspectRatio: false };
  const make = (id, cfg) => new Chart(document.getElementById(id), cfg);

  make("c-domain", {
    type: "bar",
    data: { labels: labels(charts.domain), datasets: [{ label: "Idées", data: values(charts.domain), backgroundColor: PAL[0] }] },
    options: { ...opt, indexAxis: "y", plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } },
        y: { ticks: { callback(v) { const l = this.getLabelForValue(v); return l.length > 26 ? l.slice(0, 25) + "…" : l; } } } },
      onClick(_e, els, chart) {
        if (!els.length) return;
        const id = domainIds[chart.data.labels[els[0].index]];
        if (!id) return;
        const u = new URL(location.href); u.searchParams.set("domain_id", id); location.href = u;
      } },
  });
  const cs = charts.cohorts;
  make("c-cohorts", {
    type: "bar",
    data: { labels: cs.labels, datasets: Object.entries(cs.series).map(([name, data], i) => ({ label: name, data, backgroundColor: PAL[i] })) },
    options: { ...opt, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
  make("c-gender", {
    type: "doughnut",
    data: { labels: labels(charts.gender), datasets: [{ data: values(charts.gender), backgroundColor: [PAL[2], PAL[0]] }] },
    options: { ...opt, plugins: { legend: { position: "bottom" } } },
  });
  make("c-status", {
    type: "bar",
    data: { labels: labels(charts.status), datasets: [{ label: "Projets", data: values(charts.status), backgroundColor: PAL[1] }] },
    options: { ...opt, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
  make("c-monthly", {
    type: "line",
    data: { labels: labels(charts.monthly), datasets: [{ label: "Idées reçues", data: values(charts.monthly), borderColor: PAL[0], tension: 0.25 }] },
    options: { ...opt, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
  make("c-funding", {
    type: "bar",
    data: { labels: labels(charts.funding), datasets: [{ label: "Financements", data: values(charts.funding), backgroundColor: PAL[3] }] },
    options: { ...opt, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fcfa(c.parsed.y) } } },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => v / 1e6 + " M" } } } },
  });

  // Export image : fond blanc, puis téléchargement PNG
  document.querySelectorAll("button.dl").forEach((btn) => {
    btn.addEventListener("click", () => {
      const src = document.getElementById(btn.dataset.chart);
      const c = document.createElement("canvas");
      c.width = src.width; c.height = src.height;
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(src, 0, 0);
      const a = document.createElement("a");
      a.href = c.toDataURL("image/png"); a.download = btn.dataset.chart + ".png"; a.click();
    });
  });
})();
