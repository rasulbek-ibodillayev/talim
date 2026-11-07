(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const msg = $('#msg');
  let timerId = null;

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

  // ---- Tablar ----
  $$('.tab').forEach((t) =>
    t.addEventListener('click', () => {
      $$('.tab').forEach((x) => x.classList.toggle('active', x === t));
      $('#tab-login').hidden = t.dataset.tab !== 'login';
      $('#tab-register').hidden = t.dataset.tab !== 'register';
      show('');
    })
  );

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

  // ---- Ro'yxatdan o'tish bosqichlari ----
  function setStep(n) {
    $$('#steps li').forEach((li, i) => li.classList.toggle('on', i <= n - 1));
    $('#step1').hidden = n !== 1;
    $('#step2').hidden = n !== 2;
    $('#step3').hidden = n !== 3;
    if (n !== 2) stopTimer();
  }

  function startTimer(seconds) {
    stopTimer();
    const end = Date.now() + seconds * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      $('#timer').textContent = String(Math.floor(left / 60)).padStart(2, '0') + ':' + String(left % 60).padStart(2, '0');
      if (left === 0) {
        stopTimer();
        show("Kod muddati tugadi. Iltimos, boshidan boshlang.");
      }
    };
    tick();
    timerId = setInterval(tick, 1000);
  }
  function stopTimer() { if (timerId) clearInterval(timerId); timerId = null; }

  function restart(text) {
    setStep(1);
    $('#step1').phone.value = '';
    $('#step2form').code.value = '';
    $('#step3').reset();
    show(text || '', text ? 'err' : 'ok');
  }

  $('#step1').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    submit(f, async () => {
      const r = await api('/api/register/start', { phone: phoneOf(f) });
      if (!r.ok) return show(r.error);
      show('');
      $('#codeA').textContent = r.code;
      $('#codeA').dataset.raw = r.raw_code;
      $('#botName').textContent = r.bot_username;
      $('#botLink').href = r.bot_url;
      setStep(2);
      startTimer(r.expires_in);
    });
  });

  $('#copyBtn').addEventListener('click', async () => {
    const raw = $('#codeA').textContent;
    try { await navigator.clipboard.writeText(raw); $('#copyBtn').textContent = 'Nusxalandi ✓'; }
    catch { $('#copyBtn').textContent = 'Qo\'lda nusxalang'; }
    setTimeout(() => ($('#copyBtn').textContent = 'Nusxalash'), 1800);
  });

  $('#step2form').code.addEventListener('input', (e) => {
    let v = e.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 8);
    e.target.value = v.length > 4 ? v.slice(0, 4) + '-' + v.slice(4) : v;
  });

  $('#step2form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    submit(f, async () => {
      const r = await api('/api/register/verify', { code: f.code.value });
      if (r.ok) { show(''); setStep(3); }
      else if (r.restart) restart(r.error);
      else show(r.error);
    });
  });

  $('#restart').addEventListener('click', () => restart(''));

  $('#step3').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.password.value !== f.password2.value) return show('Parollar bir xil emas.');
    submit(f, async () => {
      const r = await api('/api/register/complete', {
        first_name: f.first_name.value,
        last_name: f.last_name.value,
        region: f.region.value,
        password: f.password.value,
        password2: f.password2.value,
      });
      if (r.ok) location.href = r.redirect;
      else if (r.restart) restart(r.error);
      else show(r.error);
    });
  });
})();
