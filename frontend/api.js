/* DermaTrace API client — local-first; syncs and uses the server engine when signed in. */
const API={
 tok:(()=>{try{return localStorage.getItem('dt-tok')||''}catch(e){return ''}})(),
 async req(p,o={}){const r=await fetch('/api'+p,{method:o.method||'GET',headers:{'Content-Type':'application/json',...(this.tok?{Authorization:'Bearer '+this.tok}:{})},body:o.body?JSON.stringify(o.body):undefined});
  if(r.status==401&&this.tok)this.out();
  if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||('HTTP '+r.status));return r.status==204?null:r.json()},
 async login(kind){const email=document.getElementById('em').value.trim(),password=document.getElementById('pw').value;
  try{const d=await this.req('/auth/'+kind,{method:'POST',body:{email,password}});this.tok=d.token;localStorage.setItem('dt-tok',d.token);toast('Signed in');await this.push();render()}catch(e){toast(e.message)}},
 out(){this.tok='';try{localStorage.removeItem('dt-tok')}catch(e){}render()},
 cmp(a,b,c){return this.req('/compare',{method:'POST',body:{a:a.img,b:b.img,sens:c.sens,fov:c.fov,mode:c.mode,w:c.w}})},
 async pushVisit(l,v){if(!this.tok||v.sid)return;try{if(!l.sid)l.sid=(await this.req('/lesions',{method:'POST',body:{name:l.name,site:l.site}})).id;
  v.sid=(await this.req(`/lesions/${l.sid}/visits`,{method:'POST',body:{image:v.img,taken:v.t/1000,sens:S.cfg.sens,fov:S.cfg.fov}})).id}catch(e){}},
 async push(){if(!this.tok)return;for(const l of S.lesions)for(const v of l.visits)await this.pushVisit(l,v);save();toast('Synced to server')},
 async pull(){if(!this.tok)return;try{const rs=await this.req('/lesions');
  for(const r of rs){if(S.lesions.some(l=>l.sid==r.id))continue;const vs=[];
   for(const v of r.visits){const b=await (await fetch(`/api/visits/${v.id}/image`,{headers:{Authorization:'Bearer '+this.tok}})).blob();
    const img=await new Promise(ok=>{const f=new FileReader();f.onload=()=>ok(f.result);f.readAsDataURL(b)});vs.push({img,t:v.taken*1000,m:v.metrics,sid:v.id})}
   S.lesions.push({id:Date.now()+r.id,sid:r.id,name:r.name,site:r.site,visits:vs})}
  save();render();toast('Pulled from server')}catch(e){toast(e.message)}},
 async pdf(l,i,j){if(!this.tok)return toast('Sign in (Console) to export a PDF');try{await this.push();const A=l.visits[i],B=l.visits[j],r=await fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+this.tok},body:JSON.stringify({a_visit:A.sid,b_visit:B.sid,sens:S.cfg.sens,fov:S.cfg.fov,mode:S.cfg.mode,w:S.cfg.w})});if(!r.ok)throw new Error('Report failed');const u=URL.createObjectURL(await r.blob()),k=document.createElement('a');k.href=u;k.download='dermatrace-report.pdf';k.click()}catch(e){toast(e.message)}},
 async erase(){if(!confirm('Permanently delete your account and ALL server data?'))return;try{await this.req('/account',{method:'DELETE'});this.out();toast('Account deleted')}catch(e){toast(e.message)}},
 async getHealth(){try{return await this.req('/health')}catch(e){return{ok:false,deep_model:false}}},
 async getEda(){try{return await this.req('/pipeline/eda')}catch(e){return null}},
 async getMetrics(){try{return await this.req('/pipeline/metrics')}catch(e){return null}},
 card(){return this.tok?`<div class="card sk"><h2>Account</h2><p class="m">Signed in. Comparisons run on the server engine and visits are backed up.</p><div class="row" style="margin-top:10px"><button class="btn" style="flex:1" onclick="API.push()">Sync up</button><button class="btn" style="flex:1" onclick="API.pull()">Pull</button><button class="btn" style="flex:1" onclick="API.out()">Sign out</button></div><button class="btn" style="width:100%;margin-top:10px;color:var(--bad)" onclick="API.erase()">Delete my account &amp; data</button></div>`
  :`<div class="card sk"><h2>Account (Optional Cloud Sync)</h2><p class="m">Sign in to back up visits and use server-side Siamese CNN inference.</p><input id="em" type="email" placeholder="Email"><input id="pw" type="password" placeholder="Password (8+ chars)"><div class="row" style="margin-top:10px"><button class="btn pri" style="flex:1" onclick="API.login('login')">Sign in</button><button class="btn" style="flex:1" onclick="API.login('register')">Register</button></div></div>`}
};
