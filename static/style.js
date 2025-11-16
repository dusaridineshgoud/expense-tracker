/* Expensive Tracker — Fully Fixed Analytics + Dashboard + Stats + SPA + Theme Toggle + Mobile Sidebar */
(function () {
  'use strict';

  const $ = (sel, root = document) => (root || document).querySelector(sel);
  const $$ = (sel, root = document) => Array.from((root || document).querySelectorAll(sel));
  window._ET_CHARTS = window._ET_CHARTS || {};
  window.EXP_ITEMS = window.EXP_ITEMS || [];

  // --- Helpers ---
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replaceAll('&', '&amp;')
                     .replaceAll('<', '&lt;')
                     .replaceAll('>', '&gt;')
                     .replaceAll('"', '&quot;')
                     .replaceAll("'", '&#39;');
  }
  function money(n) { return Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 }); }

  // --- Charts ---
  function destroyChartIfExists(id) {
    try { const inst = window._ET_CHARTS[id]; if (inst && inst.destroy) inst.destroy(); } catch { }
    window._ET_CHARTS[id] = null;
  }

  function buildCharts(summary, targetId) {
    if (!summary || !summary.by_category) return;
    const canvas = $(targetId[0] === '#' ? targetId : '#' + targetId);
    if (!canvas) return;

    destroyChartIfExists(targetId);
    const ctx = canvas.getContext('2d');
    const labels = [], values = [];
    for (const k in summary.by_category) {
      if (k.toLowerCase() !== 'income') {
        labels.push(k || 'General');
        values.push(isNaN(summary.by_category[k]) ? 0 : summary.by_category[k]);
      }
    }
    if (labels.length === 0) { labels.push('No data'); values.push(1); }

    const colors = ['#00cfff', '#3afba5', '#ff5c8a', '#ffc857', '#7b6cff'];
    try {
      const chart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors }] },
        options: { cutout: '65%', plugins: { legend: { position: 'bottom' } }, maintainAspectRatio: false }
      });
      window._ET_CHARTS[targetId] = chart;
    } catch (e) { console.error(e); }
  }

  // --- Recent List + History Table ---
  function renderRecentList(items) {
    const tbl = $('#recentList');
    if (!tbl) return;
    tbl.innerHTML = '';
    items.slice(0, 10).forEach(it => {
      const tr = document.createElement('tr');
      tr.dataset.id = it[0];
      tr.dataset.category = it[3];
      tr.innerHTML = `
        <td title="${escapeHtml(it[4])}">${escapeHtml(it[1])}</td>
        <td><span class="muted-pill">${escapeHtml(it[3])}</span></td>
        <td class="text-end">₹ ${money(it[2])}</td>
        <td class="text-end">
          <button class="btn btn-sm btn-link text-danger p-0 js-delete" data-id="${it[0]}" title="Delete"><i class="bi bi-trash"></i></button>
        </td>
      `;
      tbl.appendChild(tr);
    });
  }

  function renderHistoryTable(items) {
    const tbl = $('#historyTable');
    if (!tbl) return;
    tbl.innerHTML = '';
    if (!items || items.length === 0) {
      tbl.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No transactions yet.</td></tr>';
      return;
    }
    items.forEach(it => {
      const tr = document.createElement('tr');
      tr.dataset.id = it[0];
      tr.innerHTML = `
        <td>${escapeHtml(it[1])}</td>
        <td><span class="muted-pill">${escapeHtml(it[3])}</span></td>
        <td class="text-end">₹ ${money(it[2])}</td>
        <td class="text-end" style="white-space:nowrap">${escapeHtml(it[4])}</td>
        <td class="text-end">
          <button class="btn btn-sm btn-link text-danger p-0 js-delete" data-id="${it[0]}"><i class="bi bi-trash"></i></button>
        </td>
      `;
      tbl.appendChild(tr);
    });
  }

  // --- Analytics Right Panel ---
  function renderCategorySummary(summary) {
    const container = $('#categorySummaryList');
    if (!container || !summary || !summary.by_category) return;
    const rows = Object.entries(summary.by_category)
      .filter(([cat]) => cat.toLowerCase() !== 'income')
      .map(([cat, val], idx) => {
        const colorDot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px;background:${['#00cfff','#3afba5','#ff5c8a','#ffc857','#7b6cff'][idx % 5]}"></span>`;
        return `<tr><td>${colorDot}${escapeHtml(cat)}</td><td class="text-end">₹ ${money(val)}</td></tr>`;
      }).join('');
    container.innerHTML = `<table class="table table-sm mb-0 align-middle"><thead><tr><th>Category</th><th class="text-end">Total</th></tr></thead><tbody>${rows || '<tr><td colspan="2" class="text-center text-muted">No data</td></tr>'}</tbody></table>`;
  }

  // --- Update Dashboard Stats ---
  function updateDashboardStats(items) {
    const totalTx = items.length || 0;
    const totalExpense = items.reduce((sum, tx) => tx[3].toLowerCase() !== 'income' ? sum + (tx[2] || 0) : sum, 0);
    const avgExpense = totalTx > 0 ? (totalExpense / totalTx) : 0;
    const countEl = $('#countTxns');
    const avgEl = $('#avgSpend');
    if (countEl) countEl.textContent = totalTx;
    if (avgEl) avgEl.textContent = '₹' + money(avgExpense);
  }

  // --- Update Dashboard Totals ---
  function updateUIWithSummary(summary) {
    if (!summary) return;
    $('#totalIncome').textContent = money(summary.total_income);
    $('#totalExpense').textContent = money(summary.total_expense);
    $('#remainingBalance').textContent = money(summary.balance);
    $('#topTotal').textContent = '₹ ' + money(summary.balance);
  }

  // --- Quick Add ---
  async function handleQuickAdd(e) {
    e.preventDefault();
    const title = $('#qa_title').value.trim();
    const category = $('#qa_category').value;
    const amount = parseFloat($('#qa_amount').value);
    if (!title || !amount) return alert('Enter valid data');

    const btn = e.submitter;
    btn.disabled = true; btn.textContent = 'Adding...';

    const res = await fetch('/api/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, amount })
    });

    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-plus-circle"></i> Add';

    if (!res.ok) return alert('Add failed');

    const data = await res.json();
    window.EXP_SUMMARY = data.summary;
    window.EXP_ITEMS = data.items;

    updateUIWithSummary(data.summary);
    renderRecentList(data.items);
    renderHistoryTable(data.items);
    renderCategorySummary(data.summary);
    buildCharts(data.summary, 'spendChart');
    buildCharts(data.summary, 'fullAnalyticsChart');
    updateDashboardStats(data.items);

    $('#qa_title').value = '';
    $('#qa_amount').value = '';
  }

  // --- Global Delete ---
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.js-delete');
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    if (!confirm('Delete this transaction?')) return;

    try {
      const res = await fetch(`/api/delete/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      const data = await res.json();

      window.EXP_SUMMARY = data.summary;
      window.EXP_ITEMS = data.items;

      updateUIWithSummary(data.summary);
      renderRecentList(data.items);
      renderHistoryTable(data.items);
      renderCategorySummary(data.summary);
      buildCharts(data.summary, 'spendChart');
      buildCharts(data.summary, 'fullAnalyticsChart');
      updateDashboardStats(data.items);

      const row = document.querySelector(`tr[data-id="${id}"]`);
      if (row) row.remove();
    } catch (err) { alert('Delete failed'); console.error(err); }
  });

  // --- SPA Navigation ---
  function attachNavigation() {
    const sidebar = $('.sidebar');
    if (!sidebar) return;
    const links = $$('.sidebar a.nav-item');
    links.forEach(link => link.addEventListener('click', e => {
      e.preventDefault();
      const target = link.dataset.target || 'dashboard';
      activateSection(target);
      // close mobile sidebar
      if (window.innerWidth < 992) sidebar.classList.remove('open');
    }));
    window.addEventListener('popstate', e => {
      const sec = (e.state && e.state.section) || location.pathname.replace('/', '') || 'dashboard';
      activateSection(sec, false);
    });
    const init = location.pathname.replace('/', '') || 'dashboard';
    activateSection(init, false);
  }

  async function activateSection(name, pushHistory = true) {
    if (!name) name = 'dashboard';
    const sections = $$('.page-section');
    const links = $$('.sidebar a.nav-item');
    const pageTitle = $('#pageTitle');
    const pageSubtitle = $('#pageSubtitle');

    const active = $('.page-section.active');
    if (active) {
      active.classList.remove('active');
      active.style.opacity = 0;
      active.style.transform = 'translateY(12px)';
      await new Promise(r => setTimeout(r, 200));
      active.style.display = 'none';
    }

    const next = $(`.page-section[data-name="${name}"]`);
    if (next) {
      next.style.display = 'block';
      await new Promise(r => setTimeout(r, 50));
      next.style.opacity = 1;
      next.style.transform = 'translateY(0)';
      next.classList.add('active');
    }

    links.forEach(l => l.classList.toggle('active', l.dataset.target === name));

    if (pageTitle) pageTitle.textContent = name.charAt(0).toUpperCase() + name.slice(1);
    if (pageSubtitle) pageSubtitle.textContent = sectionMeta[name]?.subtitle || '';

    if (pushHistory) history.pushState({ section: name }, '', name === 'dashboard' ? '/' : `/${name}`);

    if (name === 'dashboard') buildCharts(window.EXP_SUMMARY, 'spendChart');
    if (name === 'analytics') buildCharts(window.EXP_SUMMARY, 'fullAnalyticsChart');
  }

  // --- Theme Toggle ---
  function attachThemeToggle() {
    const btn = $('#themeToggle');
    const icon = $('#themeIcon');
    if (!btn || !icon) return;

    const saved = localStorage.getItem('theme');
    if (saved) {
      document.body.dataset.theme = saved;
      icon.className = saved === 'light' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    }

    btn.addEventListener('click', () => {
      const cur = document.body.dataset.theme === 'light' ? 'light' : 'dark';
      const next = cur === 'light' ? 'dark' : 'light';
      document.body.dataset.theme = next;
      icon.className = next === 'light' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
      localStorage.setItem('theme', next);
    });
  }

  // --- Mobile Sidebar Toggle ---
  function attachSidebarToggle() {
    const sidebar = $('#sidebar');
    const toggleBtn = $('#sidebarToggle');
    if (!sidebar || !toggleBtn) return;

    toggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));

    document.addEventListener('click', e => {
      if (window.innerWidth >= 992) return;
      if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) sidebar.classList.remove('open');
    });
  }

  // --- Init ---
  function init() {
    attachNavigation();
    attachThemeToggle();
    attachSidebarToggle();

    const form = $('#quickAddForm');
    if (form) form.addEventListener('submit', handleQuickAdd);

    if (window.EXP_SUMMARY) {
      updateUIWithSummary(window.EXP_SUMMARY);
      renderRecentList(window.EXP_ITEMS);
      renderHistoryTable(window.EXP_ITEMS);
      renderCategorySummary(window.EXP_SUMMARY);
      buildCharts(window.EXP_SUMMARY, 'spendChart');
      buildCharts(window.EXP_SUMMARY, 'fullAnalyticsChart');
      updateDashboardStats(window.EXP_ITEMS);
    }
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();

})();
