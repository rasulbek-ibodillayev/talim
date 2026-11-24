(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const msg = $('#msg');

  function show(text, type = 'err') {
    if (!msg) return;
    msg.textContent = text;
    msg.className = 'msg ' + type;
    msg.hidden = !text;
    if (text) msg.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ixtiyoriy */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ixtiyoriy */ } },
  };

  // ---- Mobil menyu ----
  const menuBtn = $('#menu-btn');
  if (menuBtn) {
    menuBtn.addEventListener('click', () => document.body.classList.toggle('nav-open'));
    const scrim = $('#scrim');
    if (scrim) scrim.addEventListener('click', () => document.body.classList.remove('nav-open'));
  }

  // ---- Chiqish ----
  const logout = $('#logout');
  if (logout) logout.addEventListener('click', async () => {
    await api('/api/logout', {});
    location.href = '/';
  });

  // ---- Tasdiqlash so'raladigan formalar ----
  $$('form[data-confirm]').forEach((f) =>
    f.addEventListener('submit', (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); })
  );

  // ---- Test boshlash tugmalari ----
  $$('[data-start-url]').forEach((btn) =>
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await api(btn.dataset.startUrl, {});
      if (r.ok) location.href = r.redirect;
      else if (r.redirect) location.href = r.redirect;
      else { show(r.error); btn.disabled = false; }
    })
  );

  // ---- Diagnostikani rad etish ----
  const decline = $('#decline-diag');
  if (decline) decline.addEventListener('click', async () => {
    if (!confirm("Diagnostikasiz boshlaysizmi? Darslar birinchi mavzudan boshlanadi, diagnostikani keyin ishlab bo'lmaydi.")) return;
    decline.disabled = true;
    const r = await api('/api/diagnostic/decline', {});
    if (r.ok) location.href = r.redirect; else { show(r.error); decline.disabled = false; }
  });

  // ---- Jadval qatorini bosib natijani ochish ----
  $$('tr[data-href]').forEach((tr) => tr.addEventListener('click', (e) => {
    if (!e.target.closest('a, button')) location.href = tr.dataset.href;
  }));

  // ---- Admin: test turi o'zgarganda standart ball va vaqt ----
  $$('[data-exam-defaults]').forEach((box) => {
    const defs = JSON.parse(box.dataset.examDefaults);
    const sel = $('[data-exam-kind]', box);
    const form = box.closest('form');
    if (!sel || !form) return;
    sel.addEventListener('change', () => {
      const d = defs[sel.value];
      const isDtm = sel.value === 'dtm';
      const set = (name, v) => { const i = $(`[data-def=${name}]`, form); if (i) i.value = v; };
      set('time', d.time); set('pa', d.pa);
      if (isDtm) set('pb', d.pb);
      $$('[data-dtm-only]', form).forEach((n) => (n.hidden = !isDtm));
      const la = $('[data-label-a]', form);
      if (la) la.textContent = isDtm ? 'Majburiy blok: 1 savol balli' : '1 savol balli';
    });
  });

  // ---- Material o'qildi ----
  $$('.read-btn').forEach((btn) =>
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await api(`/api/material/${btn.dataset.id}/read`, {});
      if (!r.ok) { show(r.error); btn.disabled = false; return; }
      const label = $('span', btn);
      if (label) label.textContent = "O'qilgan";
      btn.classList.add('done');
      const cnt = $('#read-count');
      if (cnt) cnt.textContent = r.read;
      const bar = $('#read-bar i');
      if (bar && r.total) bar.style.width = Math.round((100 * r.read) / r.total) + '%';
      if (r.read >= r.total) {
        const hint = $('#read-hint'); if (hint) hint.hidden = true;
        const tb = $('#test-btn'); if (tb) tb.disabled = false;
      }
    })
  );

  // ---- Natija: xatolar filtri ----
  const tabs = $('#review-tabs');
  if (tabs) {
    const items = $$('.review');
    const empty = $('#review-empty');
    const apply = (f) => {
      let n = 0;
      items.forEach((it) => {
        const s = it.dataset.status;
        const vis = f === 'all' || (f === 'right' ? s === 'right' : s !== 'right');
        it.hidden = !vis;
        n += vis;
      });
      empty.hidden = n > 0;
      $$('.tab', tabs).forEach((t) => t.classList.toggle('active', t.dataset.filter === f));
    };
    $$('.tab', tabs).forEach((t) => t.addEventListener('click', () => apply(t.dataset.filter)));
    const first = $('.tab.active', tabs);
    apply(first ? first.dataset.filter : 'all');
  }

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

  const sf = $('#secret-form');
  if (sf) sf.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(sf).entries());
    const r = await api('/api/profile/secret', d);
    show(r.ok ? r.message : r.error, r.ok ? 'ok' : 'err');
    if (r.ok) { sf.reset(); $$('.flash', sf.parentElement).forEach((n) => n.remove()); }
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
    const main = $('#quiz-main');
    const aid = root.dataset.id;
    let data;
    try {
      const res = await fetch(`/api/quiz/${aid}`, { credentials: 'same-origin' });
      data = await res.json();
    } catch (e) { data = { ok: false, error: "Server bilan aloqa yo'q." }; }
    if (!data.ok) {
      if (data.redirect) { location.href = data.redirect; return; }
      main.textContent = '';
      show(data.error);
      return;
    }

    const IDK = -1;
    const qs = data.questions;
    const KEY = `quiz:${aid}`;
    const local = store.get(KEY);
    const valid = (arr) => Array.isArray(arr) && arr.length === qs.length;
    // Serverdagi saqlangan javoblar asosiy, brauzerdagisi zaxira
    const answers = valid(data.answers) ? data.answers.slice()
      : valid(local) ? local : new Array(qs.length).fill(null);
    let i = answers.findIndex((a) => a === null);
    if (i < 0) i = 0;
    let finished = false;
    const LET = ['A', 'B', 'C', 'D'];
    const palette = $('#palette');
    const saveState = $('#save-state');
    $('#total').textContent = qs.length;

    function el(tag, cls, text) {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    }

    // Javoblarni serverga avtomatik saqlash (kechiktirib)
    let saveTimer = null;
    function scheduleSave() {
      store.set(KEY, answers);
      clearTimeout(saveTimer);
      saveState.textContent = '· saqlanmoqda...';
      saveTimer = setTimeout(async () => {
        const r = await api(`/api/quiz/${aid}/save`, { answers });
        saveState.textContent = r.ok ? '· saqlandi' : '· saqlanmadi';
        if (!r.ok && r.redirect) location.href = r.redirect;
      }, 700);
    }

    function choose(idx) {
      answers[i] = answers[i] === idx ? null : idx;
      scheduleSave();
      render();
      // «Bilmayman» bosilsa keyingi savolga avtomatik o'tiladi
      if (answers[i] === IDK && i < qs.length - 1) {
        const from = i;
        setTimeout(() => { if (i === from) go(from + 1); }, 200);
      }
    }

    function go(n) {
      if (n < 0 || n >= qs.length) return;
      i = n;
      render();
    }

    function render() {
      const q = qs[i];
      main.textContent = '';
      const top = el('div', 'quiz-top');
      top.append(el('span', 'q-count', `${i + 1}-savol / ${qs.length}`));
      const tags = el('div', 'actions');
      if (q.section) tags.append(el('span', 'badge accent q-section', q.section));
      if (q.topic) tags.append(el('span', 'badge q-topic', q.topic));
      top.append(tags);
      const prog = el('div', 'bar thin');
      const fill = el('i'); fill.style.width = `${((i + 1) / qs.length) * 100}%`; prog.append(fill);
      main.append(top, prog, el('h2', 'q-text', q.text));

      const list = el('div', 'opt-list');
      list.setAttribute('role', 'radiogroup');
      q.options.forEach((o, idx) => {
        const b = el('button', 'opt' + (answers[i] === idx ? ' sel' : ''));
        b.type = 'button';
        b.setAttribute('role', 'radio');
        b.setAttribute('aria-checked', answers[i] === idx ? 'true' : 'false');
        b.append(el('span', 'letter', LET[idx]), el('span', '', o));
        b.addEventListener('click', () => choose(idx));
        list.append(b);
      });
      const idk = el('button', 'opt idk-btn' + (answers[i] === IDK ? ' sel' : ''));
      idk.type = 'button';
      idk.setAttribute('role', 'radio');
      idk.setAttribute('aria-checked', answers[i] === IDK ? 'true' : 'false');
      idk.append(el('span', 'letter', '?'), el('span', '', "Bilmayman — keyingi savolga o'tish"));
      idk.addEventListener('click', () => choose(IDK));
      list.append(idk);
      main.append(list);

      const nav = el('div', 'quiz-nav');
      const prev = el('button', 'ghost', '← Oldingi'); prev.type = 'button'; prev.disabled = i === 0;
      prev.addEventListener('click', () => go(i - 1));
      nav.append(prev);
      if (i < qs.length - 1) {
        const next = el('button', 'btn', 'Keyingi →'); next.type = 'button';
        next.addEventListener('click', () => go(i + 1));
        nav.append(next);
      } else {
        const fin = el('button', 'btn accent', 'Yakunlash'); fin.type = 'button';
        fin.addEventListener('click', () => finish(false));
        nav.append(fin);
      }
      main.append(nav);

      palette.textContent = '';
      qs.forEach((_, n) => {
        const a = answers[n];
        const cls = 'pal' + (n === i ? ' cur' : '') + (a === IDK ? ' idk' : a !== null ? ' ans' : '');
        const d = el('button', cls, String(n + 1));
        d.type = 'button';
        d.setAttribute('aria-label', `${n + 1}-savol${a === IDK ? ', bilmayman' : a !== null ? ', javob berilgan' : ''}`);
        d.addEventListener('click', () => go(n));
        palette.append(d);
      });
      const done = answers.filter((x) => x !== null).length;
      $('#answered').textContent = done;
      $('#answered-bar i').style.width = `${(100 * done) / qs.length}%`;
    }

    function lock(on) { $$('button', root).forEach((b) => (b.disabled = on)); }

    async function finish(auto) {
      if (finished) return;
      const left = answers.filter((x) => x === null).length;
      if (!auto && !confirm(left
        ? `${left} ta savolga javob bermadingiz (xato hisoblanadi). Testni yakunlaysizmi?`
        : 'Testni yakunlaysizmi?')) return;
      finished = true;
      clearTimeout(saveTimer);
      lock(true);
      const r = await api(`/api/quiz/${aid}/submit`, { answers });
      if (r.ok) store.del(KEY);
      if (r.redirect) location.href = r.redirect;
      else { finished = false; show(r.error); lock(false); render(); }
    }

    $('#finish').addEventListener('click', () => finish(false));

    // Vaqt chegarasi
    if (typeof data.remaining === 'number') {
      const t = $('#timer');
      const label = $('span', t);
      t.hidden = false;
      const end = Date.now() + data.remaining * 1000;
      let timerId = null;
      const tick = () => {
        const s = Math.max(0, Math.round((end - Date.now()) / 1000));
        const h = Math.floor(s / 3600);
        const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
        const ss = String(s % 60).padStart(2, '0');
        label.textContent = (h ? h + ':' : '') + mm + ':' + ss;
        t.classList.toggle('low', s <= 60);
        if (s === 0) {
          clearInterval(timerId);
          show("Vaqt tugadi. Test avtomatik yakunlanmoqda...", 'info');
          finish(true);
        }
      };
      timerId = setInterval(tick, 1000);
      tick();
    }

    // Klaviatura: A-D javob, 0 yoki ? — bilmayman, strelkalar — savollar
    document.addEventListener('keydown', (e) => {
      if (finished || e.ctrlKey || e.metaKey || e.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      const k = e.key.toUpperCase();
      const map = { A: 0, B: 1, C: 2, D: 3, '1': 0, '2': 1, '3': 2, '4': 3, '0': IDK, '?': IDK };
      if (k in map) { choose(map[k]); e.preventDefault(); }
      else if (e.key === 'ArrowRight') { go(i + 1); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { go(i - 1); e.preventDefault(); }
    });

    render();
  }
})();
