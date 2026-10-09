import base64, os, time, uuid, json
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi import Request
from collections import defaultdict, deque
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import db, auth, engine, report, pipeline

db.init()
app = FastAPI(title="DermaTrace API", version="1.0")
HITS = defaultdict(deque)
@app.middleware("http")
async def guard(req: Request, call_next):
    if req.url.path.startswith("/api"):                      # sliding-window rate limit per IP
        ip = (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "?")).split(",")[0].strip()
        key, lim = (ip + "|auth", 10) if req.url.path.startswith("/api/auth") else (ip, 120); q = HITS[key]; now = time.time()
        while q and q[0] < now - 60: q.popleft()
        if len(q) >= lim: return JSONResponse({"detail": "Too many requests, slow down"}, 429)
        q.append(now)
    r = await call_next(req)
    r.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                      "Permissions-Policy": "camera=(self)", "Strict-Transport-Security": "max-age=31536000"})
    if req.url.path.startswith("/api"): r.headers["Cache-Control"] = "no-store"
    return r
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

def user_info(authorization: str = Header(default="")):
    data = auth.read_token_data(authorization.removeprefix("Bearer ").strip())
    if not data: raise HTTPException(401, "Invalid or expired token")
    return data

def user(data: dict = Depends(user_info)):
    return data["uid"]

def admin_only(data: dict = Depends(user_info)):
    if data.get("role") != "admin":
        raise HTTPException(403, "Admin privileges required")
    return data["uid"]

def seed_admin():
    try:
        with db.conn() as k:
            r = k.execute("SELECT id FROM users WHERE email=?", ("admin@dermatrace.com",)).fetchone()
            if not r:
                k.execute("INSERT INTO users(email,pw,role,created) VALUES(?,?,?,?)",
                          ("admin@dermatrace.com", auth.hash_pw("admin1234"), "admin", time.time()))
    except Exception:
        pass

seed_admin()

class Cred(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Optional[str] = "client"

class LesionIn(BaseModel): name: str = Field(min_length=1, max_length=80); site: str = ""
class VisitIn(BaseModel): image: str; taken: Optional[float] = None; note: str = ""; sens: float = .5; fov: float = 40
class CmpIn(BaseModel):
    a: Optional[str] = None; b: Optional[str] = None; a_visit: Optional[int] = None; b_visit: Optional[int] = None
    sens: float = .5; fov: float = 40; mode: str = "Auto"; w: dict = {}

@app.get("/api/health")
def health():
    from . import model
    return {"ok": True, "deep_model": model.available()}

@app.get("/api/pipeline/eda")
def pipeline_eda():
    return pipeline.get_pipeline_eda()

@app.get("/api/pipeline/metrics")
def pipeline_metrics():
    return pipeline.get_model_metrics()

@app.get("/api/auth/me")
def me(info: dict = Depends(user_info)):
    with db.conn() as k:
        r = k.execute("SELECT id, email, role FROM users WHERE id=?", (info["uid"],)).fetchone()
    if not r: raise HTTPException(404, "User not found")
    return {"id": r["id"], "email": r["email"], "role": r.get("role", "client")}

@app.post("/api/auth/register")
def register(c: Cred):
    role = "admin" if (c.role == "admin" or "admin" in c.email.lower()) else "client"
    try:
        with db.conn() as k:
            uid = k.execute("INSERT INTO users(email,pw,role,created) VALUES(?,?,?,?)",
                            (c.email.lower(), auth.hash_pw(c.password), role, time.time())).lastrowid
    except Exception:
        raise HTTPException(409, "Email already registered")
    return {"token": auth.make_token(uid, role), "role": role, "email": c.email.lower()}

@app.post("/api/auth/login")
def login(c: Cred):
    with db.conn() as k:
        r = k.execute("SELECT * FROM users WHERE email=?", (c.email.lower(),)).fetchone()
    if not r or not auth.check_pw(c.password, r["pw"]):
        raise HTTPException(401, "Wrong email or password")
    role = r.get("role") or ("admin" if "admin" in r["email"].lower() else "client")
    return {"token": auth.make_token(r["id"], role), "role": role, "email": r["email"]}

@app.get("/api/admin/patients")
def admin_patients(admin_id: int = Depends(admin_only)):
    with db.conn() as k:
        rows = k.execute("""
            SELECT l.id, l.name, l.site, l.created, u.email as patient_email,
                   (SELECT COUNT(*) FROM visits WHERE lesion_id=l.id) as visits_count
            FROM lesions l
            JOIN users u ON u.id = l.user_id
            ORDER BY l.id DESC
        """).fetchall()
    return [dict(r) for r in rows]

def own(k, uid, lid):
    r = k.execute("SELECT * FROM lesions WHERE id=? AND user_id=?", (lid, uid)).fetchone()
    if not r: raise HTTPException(404, "Lesion not found")
    return r

@app.get("/api/lesions")
def lesions(uid: int = Depends(user)):
    with db.conn() as k:
        out = []
        for l in k.execute("SELECT * FROM lesions WHERE user_id=? ORDER BY id", (uid,)):
            v = k.execute("SELECT id,taken,metrics,note FROM visits WHERE lesion_id=? ORDER BY taken", (l["id"],)).fetchall()
            out.append({**dict(l), "visits": [{**dict(x), "metrics": json.loads(x["metrics"])} for x in v]})
    return out

@app.post("/api/lesions", status_code=201)
def add_lesion(b: LesionIn, uid: int = Depends(user)):
    with db.conn() as k: lid = k.execute("INSERT INTO lesions(user_id,name,site,created) VALUES(?,?,?,?)", (uid, b.name, b.site, time.time())).lastrowid
    return {"id": lid, **b.model_dump()}

@app.delete("/api/lesions/{lid}", status_code=204)
def del_lesion(lid: int, uid: int = Depends(user)):
    with db.conn() as k:
        own(k, uid, lid)
        for f in k.execute("SELECT file FROM visits WHERE lesion_id=?", (lid,)):
            try: os.remove(os.path.join(db.DATA, "img", f["file"]))
            except OSError: pass
        k.execute("DELETE FROM lesions WHERE id=?", (lid,))

@app.post("/api/lesions/{lid}/visits", status_code=201)
def add_visit(lid: int, b: VisitIn, uid: int = Depends(user)):
    try: img = engine.decode(b.image)
    except Exception: raise HTTPException(422, "Invalid image")
    m = engine.metrics(img, b.sens, b.fov); name = uuid.uuid4().hex + ".jpg"
    img.resize((512, 512)).save(os.path.join(db.DATA, "img", name), quality=85)
    with db.conn() as k:
        own(k, uid, lid)
        vid = k.execute("INSERT INTO visits(lesion_id,file,taken,metrics,note) VALUES(?,?,?,?,?)", (lid, name, b.taken or time.time(), json.dumps(m), b.note)).lastrowid
    return {"id": vid, "metrics": m}

@app.get("/api/visits/{vid}/image")
def visit_image(vid: int, uid: int = Depends(user)):
    with db.conn() as k:
        r = k.execute("SELECT v.file FROM visits v JOIN lesions l ON l.id=v.lesion_id WHERE v.id=? AND l.user_id=?", (vid, uid)).fetchone()
    if not r: raise HTTPException(404)
    return FileResponse(os.path.join(db.DATA, "img", r["file"]), media_type="image/jpeg")

@app.post("/api/compare")
def compare(b: CmpIn, uid: int = Depends(user)):
    def get(data, vid):
        if data:
            try: return engine.decode(data)
            except Exception: raise HTTPException(422, "Invalid image")
        with db.conn() as k:
            r = k.execute("SELECT v.file FROM visits v JOIN lesions l ON l.id=v.lesion_id WHERE v.id=? AND l.user_id=?", (vid, uid)).fetchone()
        if not r: raise HTTPException(404, "Visit not found")
        from PIL import Image
        return Image.open(os.path.join(db.DATA, "img", r["file"])).convert("RGB")
    res = engine.compare(get(b.a, b.a_visit), get(b.b, b.b_visit), b.sens, b.fov, b.mode, b.w)
    if b.a_visit and b.b_visit:
        with db.conn() as k:
            k.execute("INSERT INTO results(visit_a,visit_b,score,verdict,conf,created) VALUES(?,?,?,?,?,?)", (b.a_visit, b.b_visit, res["score"], res["v"], res["conf"], time.time()))
    return res

class RepIn(BaseModel): a_visit: int; b_visit: int; sens: float = .5; fov: float = 40; mode: str = "Auto"; w: dict = {}
@app.post("/api/report")
def make_report(b: RepIn, uid: int = Depends(user)):
    from PIL import Image
    with db.conn() as k:
        rows = [k.execute("SELECT v.file,v.taken,l.name,l.site FROM visits v JOIN lesions l ON l.id=v.lesion_id WHERE v.id=? AND l.user_id=?", (i, uid)).fetchone() for i in (b.a_visit, b.b_visit)]
    if not all(rows): raise HTTPException(404, "Visit not found")
    ims = [Image.open(os.path.join(db.DATA, "img", r["file"])).convert("RGB") for r in rows]
    res = engine.compare(ims[0], ims[1], b.sens, b.fov, b.mode, b.w); fm = lambda t: time.strftime("%d-%m-%Y", time.localtime(t))
    pdf = report.make_pdf(rows[0]["name"], rows[0]["site"], ims[0], ims[1], fm(rows[0]["taken"]), fm(rows[1]["taken"]), res)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="dermatrace-report.pdf"'})

@app.delete("/api/account", status_code=204)
def delete_account(uid: int = Depends(user)):          # right to erasure: removes user, lesions, visits, image files
    with db.conn() as k:
        for f in k.execute("SELECT v.file FROM visits v JOIN lesions l ON l.id=v.lesion_id WHERE l.user_id=?", (uid,)):
            try: os.remove(os.path.join(db.DATA, "img", f["file"]))
            except OSError: pass
        k.execute("DELETE FROM users WHERE id=?", (uid,))

@app.get("/")
def index(): return FileResponse(os.path.join(ROOT, "index.html"))
app.mount("/", StaticFiles(directory=ROOT), name="static")
