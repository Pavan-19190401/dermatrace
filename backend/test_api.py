import base64, io, os, tempfile, math
os.environ["DT_DATA"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter
from app.main import app
def lesion(r, irr, dark):
    im = Image.new("RGB", (256, 256), (225, 180, 150)); d = ImageDraw.Draw(im)
    pts = [(128 + r*(1+irr*.35*math.sin(5*a/10)) * math.cos(a/10), 128 + r*(1+irr*.35*math.sin(5*a/10)) * math.sin(a/10)) for a in range(63)]
    d.polygon(pts, fill=dark); im = im.filter(ImageFilter.GaussianBlur(1.2))
    b = io.BytesIO(); im.save(b, "JPEG"); return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
c = TestClient(app)
assert c.get("/api/health").json()["ok"]
assert len(c.get("/api/pipeline/eda").json()["cleaning_steps"]) == 8
assert "confusion_matrix" in c.get("/api/pipeline/metrics").json()
assert c.get("/api/lesions").status_code == 401
t = c.post("/api/auth/register", json={"email": "a@b.co", "password": "password1"}).json()["token"]
assert c.post("/api/auth/register", json={"email": "a@b.co", "password": "password1"}).status_code == 409
assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "wrongwrong"}).status_code == 401
H = {"Authorization": "Bearer " + t}
lid = c.post("/api/lesions", json={"name": "Mole", "site": "Arm"}, headers=H).json()["id"]
v1 = c.post(f"/api/lesions/{lid}/visits", json={"image": lesion(30, .05, (75, 45, 32))}, headers=H).json()["id"]
v2 = c.post(f"/api/lesions/{lid}/visits", json={"image": lesion(42, .9, (35, 20, 15))}, headers=H).json()["id"]
v3 = c.post(f"/api/lesions/{lid}/visits", json={"image": lesion(30, .05, (75, 45, 32))}, headers=H).json()["id"]
r = c.post("/api/compare", json={"a_visit": v1, "b_visit": v2}, headers=H).json(); print("changed:", r["score"], r["verdict"], r["conf"], r["engine"])
s = c.post("/api/compare", json={"a_visit": v1, "b_visit": v3}, headers=H).json(); print("same   :", s["score"], s["verdict"], s["conf"])
assert r["score"] > s["score"] and r["v"] == 1 and s["v"] == 0
assert c.get(f"/api/visits/{v1}/image", headers=H).status_code == 200
t2 = c.post("/api/auth/register", json={"email": "x@y.co", "password": "password2"}).json()["token"]
assert c.get(f"/api/visits/{v1}/image", headers={"Authorization": "Bearer " + t2}).status_code == 404
assert len(c.get("/api/lesions", headers=H).json()[0]["visits"]) == 3
pdf = c.post("/api/report", json={"a_visit": v1, "b_visit": v2}, headers=H); assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
assert ("risk" in r) and ("engine" in r)
for _ in range(12): last = c.post("/api/auth/login", json={"email": "z@z.co", "password": "wrongwrong"})
assert last.status_code == 429, last.status_code            # auth rate limit
assert c.delete("/api/account", headers={"Authorization": "Bearer " + t2}).status_code == 204
assert c.delete(f"/api/lesions/{lid}", headers=H).status_code == 204
assert c.get("/").status_code == 200
print("ALL TESTS PASSED")
