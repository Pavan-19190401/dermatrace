/* DermaTrace API client — role-aware (Client vs Admin), local-first with server synchronization. */
const API = {
  tok: (() => { try { return localStorage.getItem('dt-tok') || ''; } catch (e) { return ''; } })(),
  role: (() => { try { return localStorage.getItem('dt-role') || 'client'; } catch (e) { return 'client'; } })(),
  email: (() => { try { return localStorage.getItem('dt-email') || ''; } catch (e) { return ''; } })(),

  isAdmin() {
    return this.role === 'admin';
  },

  setAuth(token, role, email) {
    this.tok = token || '';
    this.role = (role || 'client').toLowerCase();
    this.email = email || '';
    try {
      if (this.tok) {
        localStorage.setItem('dt-tok', this.tok);
        localStorage.setItem('dt-role', this.role);
        localStorage.setItem('dt-email', this.email);
      } else {
        localStorage.removeItem('dt-tok');
        localStorage.removeItem('dt-role');
        localStorage.removeItem('dt-email');
      }
    } catch (e) {}
  },

  async req(p, o = {}) {
    const r = await fetch('/api' + p, {
      method: o.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(this.tok ? { Authorization: 'Bearer ' + this.tok } : {})
      },
      body: o.body ? JSON.stringify(o.body) : undefined
    });
    if (r.status === 401 && this.tok) this.out();
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ('HTTP ' + r.status));
    return r.status === 204 ? null : r.json();
  },

  async login(kind, forceRole = null) {
    const email = document.getElementById('em')?.value.trim();
    const password = document.getElementById('pw')?.value;
    const role = forceRole || (document.getElementById('role-select')?.value || 'client');
    if (!email || !password) return toast('Please enter both email and password');
    try {
      const d = await this.req('/auth/' + kind, {
        method: 'POST',
        body: { email, password, role }
      });
      this.setAuth(d.token, d.role, d.email);
      toast(`Signed in as ${d.role === 'admin' ? 'Clinician (Admin)' : 'Patient (Client)'}`);
      await this.push();
      renderNav();
      renderView();
    } catch (e) {
      toast(e.message);
    }
  },

  async quickDemoLogin(role) {
    const email = role === 'admin' ? 'admin@dermatrace.com' : 'patient@example.com';
    const password = role === 'admin' ? 'admin1234' : 'password123';
    try {
      let d;
      try {
        d = await this.req('/auth/login', { method: 'POST', body: { email, password } });
      } catch (err) {
        d = await this.req('/auth/register', { method: 'POST', body: { email, password, role } });
      }
      this.setAuth(d.token, d.role, d.email);
      toast(`Switched to: ${this.isAdmin() ? 'Clinician Admin Mode' : 'Patient Client Mode'}`);
      renderNav();
      renderView();
    } catch (e) {
      toast('Demo switch failed: ' + e.message);
    }
  },

  out() {
    this.setAuth('', 'client', '');
    toast('Signed out');
    renderNav();
    renderView();
  },

  cmp(a, b, c) {
    return this.req('/compare', {
      method: 'POST',
      body: { a: a.img, b: b.img, sens: c.sens, fov: c.fov, mode: c.mode, w: c.w }
    });
  },

  async pushVisit(l, v) {
    if (!this.tok || v.sid) return;
    try {
      if (!l.sid) l.sid = (await this.req('/lesions', { method: 'POST', body: { name: l.name, site: l.site } })).id;
      v.sid = (await this.req(`/lesions/${l.sid}/visits`, {
        method: 'POST',
        body: { image: v.img, taken: v.t / 1000, sens: App.cfg.sens, fov: App.cfg.fov }
      })).id;
    } catch (e) {}
  },

  async push() {
    if (!this.tok) return;
    for (const l of App.lesions) for (const v of l.visits) await this.pushVisit(l, v);
    saveState();
    toast('Synced to cloud server');
  },

  async pull() {
    if (!this.tok) return;
    try {
      const rs = await this.req('/lesions');
      for (const r of rs) {
        if (App.lesions.some(l => l.sid === r.id)) continue;
        const vs = [];
        for (const v of r.visits) {
          const b = await (await fetch(`/api/visits/${v.id}/image`, { headers: { Authorization: 'Bearer ' + this.tok } })).blob();
          const img = await new Promise(ok => {
            const f = new FileReader();
            f.onload = () => ok(f.result);
            f.readAsDataURL(b);
          });
          vs.push({ img, t: v.taken * 1000, m: v.metrics, sid: v.id });
        }
        App.lesions.push({ id: Date.now() + r.id, sid: r.id, name: r.name, site: r.site, visits: vs });
      }
      saveState();
      renderView();
      toast('Pulled records from cloud');
    } catch (e) {
      toast(e.message);
    }
  },

  async pdf(l, i, j) {
    if (!this.tok) return toast('Sign in to export official PDF report');
    try {
      await this.push();
      const A = l.visits[i], B = l.visits[j];
      const r = await fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + this.tok },
        body: JSON.stringify({ a_visit: A.sid, b_visit: B.sid, sens: App.cfg.sens, fov: App.cfg.fov, mode: App.cfg.mode, w: App.cfg.w })
      });
      if (!r.ok) throw new Error('Report generation failed');
      const u = URL.createObjectURL(await r.blob());
      const k = document.createElement('a');
      k.href = u;
      k.download = `dermatrace-${l.name.replace(/\s+/g, '-').toLowerCase()}-report.pdf`;
      k.click();
    } catch (e) {
      toast(e.message);
    }
  },

  async erase() {
    if (!confirm('Permanently delete account and all cloud data?')) return;
    try {
      await this.req('/account', { method: 'DELETE' });
      this.out();
      toast('Account and data deleted');
    } catch (e) {
      toast(e.message);
    }
  },

  async getHealth() {
    try { return await this.req('/health'); } catch (e) { return { ok: false, deep_model: false }; }
  },

  async getEda() {
    try { return await this.req('/pipeline/eda'); } catch (e) { return null; }
  },

  async getMetrics() {
    try { return await this.req('/pipeline/metrics'); } catch (e) { return null; }
  },

  async getAdminPatients() {
    try { return await this.req('/admin/patients'); } catch (e) { return []; }
  },

  authCard() {
    if (this.tok) {
      return `
        <div class="sk-card">
          <div class="row sp" style="margin-bottom:8px">
            <h3 style="margin:0;font-size:15px;font-weight:800">Account Session</h3>
            <span class="chip ${this.isAdmin() ? 'bad' : 'ok'}">${this.isAdmin() ? 'Admin / Clinician' : 'Patient / Client'}</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-muted);margin:0 0 12px">
            Signed in as: <b>${this.email}</b>
          </p>
          <div class="row">
            <button class="sk-btn" style="flex:1" onclick="API.push()">☁ Sync Up</button>
            <button class="sk-btn" style="flex:1" onclick="API.pull()">⬇ Pull</button>
            <button class="sk-btn" style="flex:1" onclick="API.out()">Sign Out</button>
          </div>
          <div style="margin-top:14px;border-top:1px solid var(--border-sub);padding-top:12px">
            <span style="font-size:11px;font-weight:700;color:var(--text-muted)">SWITCH ROLE (DEMO & TESTING):</span>
            <div class="row" style="margin-top:6px">
              <button class="sk-btn ${!this.isAdmin() ? 'pri' : ''}" style="flex:1;font-size:11.5px" onclick="API.quickDemoLogin('client')">Patient View</button>
              <button class="sk-btn ${this.isAdmin() ? 'pri' : ''}" style="flex:1;font-size:11.5px" onclick="API.quickDemoLogin('admin')">Clinician (Admin)</button>
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div class="sk-card">
        <div class="row sp" style="margin-bottom:8px">
          <h3 style="margin:0;font-size:15px;font-weight:800">Sign In / Register</h3>
          <span class="chip wa">Role Access</span>
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px">
          Sign in to unlock personalized tracking or the clinical workstation.
        </p>
        <input id="em" type="email" placeholder="Email address">
        <input id="pw" type="password" placeholder="Password (8+ chars)">
        <select id="role-select" style="margin-bottom:10px">
          <option value="client">Role: Patient / Client (Focused Triage)</option>
          <option value="admin">Role: Clinician / Admin (All ML & Controls Unlocked)</option>
        </select>
        <div class="row" style="margin-bottom:12px">
          <button class="sk-btn pri" style="flex:1" onclick="API.login('login')">Sign In</button>
          <button class="sk-btn" style="flex:1" onclick="API.login('register')">Register</button>
        </div>
        <div style="border-top:1px solid var(--border-sub);padding-top:10px">
          <span style="font-size:11px;font-weight:700;color:var(--text-muted)">1-CLICK ROLE DEMO LOGIN:</span>
          <div class="row" style="margin-top:6px">
            <button class="sk-btn" style="flex:1;font-size:11.5px" onclick="API.quickDemoLogin('client')">👤 Patient (Client)</button>
            <button class="sk-btn pri" style="flex:1;font-size:11.5px" onclick="API.quickDemoLogin('admin')">🩺 Clinician (Admin)</button>
          </div>
        </div>
      </div>
    `;
  }
};
