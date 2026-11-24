(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const msg = $('#msg');

  function show(text, type = 'err') {
    msg.textContent = text;
    msg.className = 'msg ' + type;
    msg.hidden = !text;
  }

  async function api(url, data) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {}),
        credentials: 'same-origin',
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: "Server bilan aloqa yo'q. Internetni tekshiring." };
    }
  }

  async function submit(form, fn) {
    const btn = $('button[type=submit]', form);
    btn.disabled = true;
    try { await fn(); } finally { btn.disabled = false; }
  }

  // ---- Bo'limlar: kirish, ro'yxatdan o'tish, parolni tiklash ----
  function view(name) {
    $$('.tab').forEach((x) => x.classList.toggle('active', x.dataset.tab === name));
    ['login', 'register', 'recover'].forEach((n) => ($('#tab-' + n).hidden = n !== name));
    if (name === 'recover') recoverStep(1);
    show('');
  }
  $$('.tab').forEach((t) => t.addEventListener('click', () => view(t.dataset.tab)));
  $$('[data-view]').forEach((b) => b.addEventListener('click', () => view(b.dataset.view)));

  // ---- Telefon maydoni: faqat raqam, 9 ta ----
  $$('input[type=tel]').forEach((i) =>
    i.addEventListener('input', () => {
      let d = i.value.replace(/\D/g, '');
      if (d.startsWith('998') && d.length > 9) d = d.slice(3);
      d = d.slice(0, 9);
      const parts = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
      i.value = parts.join(' ');
    })
  );
  const phoneOf = (form) => '+998' + form.phone.value.replace(/\D/g, '');

  // ---- Kirish ----
  $('#login-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    submit(f, async () => {
      const r = await api('/api/login', { phone: phoneOf(f), password: f.password.value });
      if (r.ok) location.href = r.redirect;
      else show(r.error);
    });
  });

  // ---- Ro'yxatdan o'tish ----
  const digits = (form) => form.phone.value.replace(/\D/g, '').length;
  $('#register-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    if (digits(f) !== 9) return show("Telefon raqamni to'liq kiriting (masalan: 90 123 45 67).");
    if (f.password.value !== f.password2.value) return show('Parollar bir xil emas.');
    submit(f, async () => {
      const d = Object.fromEntries(new FormData(f).entries());
      const r = await api('/api/register', { ...d, phone: phoneOf(f) });
      if (r.ok) location.href = r.redirect;
      else show(r.error);
    });
  });

  // ---- Parolni tiklash ----
  function recoverStep(n) {
    $('#recover-form').hidden = n !== 1;
    $('#reset-form').hidden = n !== 2;
    if (n === 1) { $('#recover-form').secret.value = ''; $('#reset-form').reset(); }
  }
  $('#recover-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    submit(f, async () => {
      const r = await api('/api/recover/check', { phone: phoneOf(f), secret: f.secret.value });
      if (!r.ok) return show(r.error);
      show('');
      recoverStep(2);
    });
  });
  $('#reset-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.password.value !== f.password2.value) return show('Parollar bir xil emas.');
    submit(f, async () => {
      const r = await api('/api/recover/reset', { password: f.password.value, password2: f.password2.value });
      if (r.ok) {
        $('#login-form').phone.value = $('#recover-form').phone.value;
        view('login');
        show(r.message, 'ok');
      } else {
        if (r.restart) recoverStep(1);
        show(r.error);
      }
    });
  });
})();
