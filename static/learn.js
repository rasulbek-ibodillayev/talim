(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const msg = $('#msg');

  function show(text, type = 'err') {
    if (!msg) return;
    msg.textContent = text;
    msg.className = 'msg ' + type;
    msg.hidden = !text;
    if (text) window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function api(url, data) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(data || {}),
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: "Server bilan aloqa yo'q. Internetni tekshiring." };
    }
  }

  // ---- Chiqish ----
  const logout = $('#logout');
  if (logout) logout.addEventListener('click', async () => {
    await api('/api/logout', {});
    location.href = '/';
  });

  // ---- Tasdiqlash so'raladigan formalar (admin o'chirish) ----
  $$('form[data-confirm]').forEach((f) =>
    f.addEventListener('submit', (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); })
  );

  // ---- Test boshlash tugmalari ----
  $$('[data-start-url]').forEach((btn) =>
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await api(btn.dataset.startUrl, {});
      if (r.ok) location.href = r.redirect;
      else { show(r.error); btn.disabled = false; }
    })
  );

  // ---- Material o'qildi ----
  $$('.read-btn').forEach((btn) =>
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await api(`/api/material/${btn.dataset.id}/read`, {});
      if (!r.ok) { show(r.error); btn.disabled = false; return; }
      btn.textContent = "✓ O'qilgan";
      btn.classList.add('done');
      const cnt = $('#read-count');
      if (cnt) cnt.textContent = r.read;
      if (r.read >= r.total) {
        const hint = $('#read-hint'); if (hint) hint.hidden = true;
        const tb = $('#test-btn'); if (tb) tb.disabled = false;
      }
    })
  );

  // ---- Profil ----
  const pf = $('#profile-form');
  if (pf) pf.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(pf).entries());
    const r = await api('/api/profile', d);
    show(r.ok ? r.message : r.error, r.ok ? 'ok' : 'err');
  });

  const pw = $('#password-form');
  if (pw) pw.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(pw).entries());
    const r = await api('/api/profile/password', d);
    show(r.ok ? r.message : r.error, r.ok ? 'ok' : 'err');
    if (r.ok) pw.reset();
  });

  const pick = $('#avatar-pick');
  const input = $('#avatar-input');
  if (pick && input) {
    pick.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
      const f = input.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) { show('Rasm hajmi 2 MB dan oshmasligi kerak.'); return; }
      const fd = new FormData();
      fd.append('avatar', f);
      fd.append('_csrf', window.CSRF);
      try {
        const res = await fetch('/api/profile/avatar', { method: 'POST', body: fd, credentials: 'same-origin' });
        const r = await res.json();
        if (r.ok) location.reload();
        else show(r.error);
      } catch (e) { show("Server bilan aloqa yo'q."); }
    });
  }
  const del = $('#avatar-delete');
  if (del) del.addEventListener('click', async () => {
    const r = await api('/api/profile/avatar/delete', {});
    if (r.ok) location.reload(); else show(r.error);
  });

  // ---- Test (quiz) ----
  const quiz = $('#quiz');
  if (quiz) initQuiz(quiz);

  async function initQuiz(root) {
    const body = $('#quiz-body', root);
    let data;
    try {
      const res = await fetch(`/api/quiz/${root.dataset.id}`, { credentials: 'same-origin' });
      data = await res.json();
    } catch (e) { data = { ok: false, error: "Server bilan aloqa yo'q." }; }
    if (!data.ok) {
      if (data.redirect) { location.href = data.redirect; return; }
      body.textContent = '';
      show(data.error);
      return;
    }
    const qs = data.questions;
    const answers = new Array(qs.length).fill(null);
    let i = 0;
    const LET = ['A', 'B', 'C', 'D'];

    function el(tag, cls, text) {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    }

    function render() {
      const q = qs[i];
      body.textContent = '';
      const head = el('div', 'q-head');
      head.append(el('span', 'muted', `Savol ${i + 1} / ${qs.length}`), el('span', 'muted', `Javob berilgan: ${answers.filter((x) => x !== null).length}`));
      const bar = el('div', 'bar'); const fill = el('i'); fill.style.width = `${((i + 1) / qs.length) * 100}%`; bar.append(fill);
      body.append(head, bar, el('h2', 'q-text', q.text));

      const list = el('div', 'opt-list');
      q.options.forEach((o, idx) => {
        const b = el('button', 'opt' + (answers[i] === idx ? ' sel' : ''));
        b.type = 'button';
        b.append(el('b', '', LET[idx] + ')'), document.createTextNode(' ' + o));
        b.addEventListener('click', () => { answers[i] = idx; render(); });
        list.append(b);
      });
      body.append(list);

      const nav = el('div', 'actions');
      const prev = el('button', 'ghost', '← Oldingi'); prev.type = 'button'; prev.disabled = i === 0;
      prev.addEventListener('click', () => { i--; render(); });
      nav.append(prev);
      if (i < qs.length - 1) {
        const next = el('button', 'btn inline', 'Keyingi →'); next.type = 'button';
        next.addEventListener('click', () => { i++; render(); });
        nav.append(next);
      } else {
        const fin = el('button', 'btn inline', 'Yakunlash'); fin.type = 'button';
        fin.addEventListener('click', finish);
        nav.append(fin);
      }
      body.append(nav);

      // Savollar raqamlari (tez o'tish)
      const dots = el('div', 'dots');
      qs.forEach((_, n) => {
        const d = el('button', 'dot' + (n === i ? ' cur' : '') + (answers[n] !== null ? ' ans' : ''), String(n + 1));
        d.type = 'button';
        d.addEventListener('click', () => { i = n; render(); });
        dots.append(d);
      });
      body.append(dots);
    }

    async function finish() {
      const left = answers.filter((x) => x === null).length;
      if (left && !confirm(`${left} ta savolga javob bermadingiz. Baribir yakunlaysizmi?`)) return;
      $$('button', body).forEach((b) => (b.disabled = true));
      const r = await api(`/api/quiz/${root.dataset.id}/submit`, { answers });
      if (r.ok) location.href = r.redirect;
      else { show(r.error); render(); }
    }

    render();
  }
})();
