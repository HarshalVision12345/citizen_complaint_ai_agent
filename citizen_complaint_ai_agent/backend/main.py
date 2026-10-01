"""CivicAI – Citizen Complaint AI Agent (FastAPI + SQLite)."""
import json, os, re, sqlite3, time
from collections import Counter
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DB = os.getenv("DB_PATH", str(BASE / "complaints.db"))
PIN = os.getenv("OFFICER_PIN", "iiitnr")
FRONT = BASE.parent / "frontend"
STATUSES = ["Submitted", "Assigned", "In Progress", "Resolved"]
SLA = {"High": "4 hours", "Medium": "24 hours", "Low": "72 hours"}
SLAH = {"High": 4, "Medium": 24, "Low": 72}
STOP = set("the a an is are was not in on at of to for and near since has have been from with it this that very my our there days".split())

CATS = {
 "Street Lighting": ("Electrical Department", ["street light","streetlight","lamp","dark road","electric pole","light not","बिजली","लाइट","खंभा"], "Verify location and assign an electrical team to repair the light."),
 "Garbage & Sanitation": ("Sanitation Department", ["garbage","waste","trash","dustbin","dirty","sewage","cleaning","toilet","smell","कचरा","गंदा","सफाई"], "Assign a sanitation team to inspect and clear the waste."),
 "Water Supply": ("Water Department", ["water","pipeline","tap","leakage","no water","drinking","पानी","नल","पाइप"], "Send to the water department for pipeline/supply inspection."),
 "Drainage & Flooding": ("Drainage / Storm Water Cell", ["drain","flood","waterlogging","manhole","overflow","nala","नाली","जलभराव"], "Dispatch a drainage crew to clear the blockage and inspect."),
 "Road & Infrastructure": ("Public Works Department", ["road","pothole","footpath","bridge","divider","construction","crack","सड़क","गड्ढा","पुल"], "Create a field inspection request for the public works team."),
 "Traffic & Police": ("Traffic / Police Department", ["traffic","signal","parking","accident","theft","crime","harass","illegal","stray","चोरी","ट्रैफिक"], "Forward to traffic/police for verification and action."),
 "Electricity Supply": ("Electricity Board", ["power cut","outage","transformer","voltage","wire","meter","current","power"], "Raise a ticket with the electricity board for fault repair."),
 "Public Health": ("Health Department", ["health","hospital","clinic","mosquito","disease","medical","dengue","fever","स्वास्थ्य","मच्छर"], "Forward to the health department for verification and action."),
 "Pollution & Noise": ("Pollution Control Board", ["pollution","smoke","noise","loud","burning","dust","factory","प्रदूषण","शोर","धुआं"], "Log with pollution control for inspection and enforcement."),
 "Parks & Public Spaces": ("Parks & Horticulture", ["park","garden","tree","playground","bench","encroachment","पार्क","पेड़"], "Assign horticulture/parks team to inspect the site."),
 "Other Civic Issue": ("Civic Administration", [], "Route to civic administration for manual review and assignment."),
}
HIGH = ["emergency","fire","spark","electrocution","open manhole","gas leak","accident","injury","flood","unsafe","danger","ambulance","आग","खतरा"]
MED = ["urgent","broken","not working","leak","blocked","overflow","days","दिन","काम नहीं","stopped","no water","no internet"]

def analyze(text: str) -> dict:
    t = " " + text.lower() + " "
    best, score = "Other Civic Issue", 0
    for k, (_, words, _) in CATS.items():
        n = sum(w in t for w in words)
        if n > score: best, score = k, n
    pr = "High" if any(w in t for w in HIGH) else "Medium" if any(w in t for w in MED) else "Low"
    return {"category": best, "department": CATS[best][0], "priority": pr,
            "action": CATS[best][2], "confidence": min(98, 60 + score * 14 if score else 40), "sla": SLA[pr]}

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS complaints(
            id TEXT PRIMARY KEY, name TEXT, contact TEXT, location TEXT, description TEXT,
            category TEXT, department TEXT, priority TEXT, action TEXT, status TEXT,
            created REAL, log TEXT)""")
        cols = [x[1] for x in c.execute("PRAGMA table_info(complaints)")]
        if "dup_of" not in cols: c.execute("ALTER TABLE complaints ADD COLUMN dup_of TEXT")
        if "reports" not in cols: c.execute("ALTER TABLE complaints ADD COLUMN reports INTEGER DEFAULT 1")

def row(r):
    d = dict(r); d["log"] = json.loads(d["log"]); d["sla"] = SLA[d["priority"]]
    d["escalated"] = d["status"] != "Resolved" and (time.time() * 1000 - d["created"]) > SLAH[d["priority"]] * 3600e3
    return d

def new_id(c):
    p = datetime.now().strftime("%y%m%d")
    n = c.execute("SELECT COUNT(*) FROM complaints WHERE id LIKE ?", (f"CMP{p}-%",)).fetchone()[0] + 1
    return f"CMP{p}-{n:04d}"

def toks(t):
    return {w for w in re.findall(r"[\w\u0900-\u097f]+", t.lower()) if len(w) > 2 and w not in STOP}

def find_dup(c, cat, desc, loc):
    """Duplicate detection: same category + similar wording / same place -> grouped under the original."""
    T, L = toks(desc), toks(loc)
    for r in c.execute("SELECT id,description,location FROM complaints WHERE status!='Resolved' AND category=? AND dup_of IS NULL", (cat,)).fetchall():
        T2, L2 = toks(r["description"]), toks(r["location"])
        sim = len(T & T2) / max(1, len(T | T2)); same = len(L & L2) / max(1, len(L | L2))
        if sim >= 0.5 or (sim >= 0.25 and same >= 0.5): return r["id"]

def insert(c, name, contact, location, desc, created=None, status="Submitted"):
    a = analyze(f"{desc} {location}")
    created = created or time.time() * 1000
    cid = new_id(c)
    dup = find_dup(c, a["category"], desc, location)
    note = "Complaint received and analysed by AI" + (f" · grouped with {dup} (duplicate detection)" if dup else "")
    c.execute("INSERT INTO complaints(id,name,contact,location,description,category,department,priority,action,status,created,log,dup_of,reports) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
              (cid, name, contact, location, desc, a["category"], a["department"], a["priority"], a["action"], status, created,
               json.dumps([{"s": "Submitted", "t": created, "note": note}]), dup))
    if dup: c.execute("UPDATE complaints SET reports=reports+1 WHERE id=?", (dup,))
    return cid

def auth(pin):
    if pin != PIN: raise HTTPException(401, "Invalid officer PIN")

class Complaint(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    contact: str = Field(..., min_length=5, max_length=100)
    location: str = Field(..., min_length=2, max_length=250)
    description: str = Field(..., min_length=5, max_length=2000)
class Preview(BaseModel): text: str = Field(..., min_length=1, max_length=2000)
class StatusIn(BaseModel): status: str

app = FastAPI(title="CivicAI Citizen Complaint API", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init()

@app.get("/api/health")
def health(): return {"status": "ok"}

@app.post("/api/analyze")
def preview(p: Preview): return analyze(p.text)

@app.post("/api/complaints")
def create(c: Complaint):
    with db() as con:
        cid = insert(con, c.name.strip(), c.contact.strip(), c.location.strip(), c.description.strip())
        return {"complaint": row(con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())}

@app.get("/api/complaints/lookup")
def lookup(ids: str = ""):
    keys = [i.strip().upper() for i in ids.split(",") if i.strip()][:50]
    if not keys: return {"complaints": []}
    with db() as con:
        rs = con.execute(f"SELECT * FROM complaints WHERE id IN ({','.join('?'*len(keys))}) ORDER BY created DESC", keys).fetchall()
    return {"complaints": [row(r) for r in rs]}

@app.get("/api/complaints")
def list_all(x_officer_pin: str = Header("")):
    auth(x_officer_pin)
    with db() as con:
        return {"complaints": [row(r) for r in con.execute("SELECT * FROM complaints ORDER BY created DESC")]}

@app.get("/api/complaints/{cid}")
def get_one(cid: str):
    with db() as con:
        r = con.execute("SELECT * FROM complaints WHERE id=?", (cid.strip().upper(),)).fetchone()
    if not r: raise HTTPException(404, "Complaint not found")
    return {"complaint": row(r)}

@app.patch("/api/complaints/{cid}/status")
def set_status(cid: str, s: StatusIn, x_officer_pin: str = Header("")):
    auth(x_officer_pin)
    if s.status not in STATUSES: raise HTTPException(400, "Invalid status")
    with db() as con:
        r = con.execute("SELECT * FROM complaints WHERE id=?", (cid.upper(),)).fetchone()
        if not r: raise HTTPException(404, "Complaint not found")
        now = time.time() * 1000
        kids = con.execute("SELECT id,log FROM complaints WHERE dup_of=?", (r["id"],)).fetchall()
        log = json.loads(r["log"]); log.append({"s": s.status, "t": now, "note": "Updated by officer · citizen notified (SMS/email)"})
        con.execute("UPDATE complaints SET status=?, log=? WHERE id=?", (s.status, json.dumps(log), r["id"]))
        for k in kids:  # linked duplicate reports follow the original
            l = json.loads(k["log"]); l.append({"s": s.status, "t": now, "note": f"Follows linked complaint {r['id']} · citizen notified"})
            con.execute("UPDATE complaints SET status=?, log=? WHERE id=?", (s.status, json.dumps(l), k["id"]))
    return {"ok": True}

@app.post("/api/demo")
def demo(x_officer_pin: str = Header("")):
    auth(x_officer_pin)
    S = [("Street light near main gate not working for four days", "Sector 5"), ("Large pothole on main road, accident risk", "Ring Road"),
         ("Garbage not collected for a week, bad smell", "Ward 12"), ("No water supply since morning, urgent", "Sector 21"),
         ("Open manhole near market, danger to kids", "City Market"), ("Street light not working near main gate for days", "Sector 5")]
    with db() as con:
        for i, (d, l) in enumerate(S):
            cid = insert(con, "Demo Citizen", "demo@example.com", l, d, time.time() * 1000 - i * 8 * 3600e3)
            if i % 4: con.execute("UPDATE complaints SET status=? WHERE id=?", (STATUSES[i % 4], cid))
    return {"ok": True}

@app.get("/api/analytics")
def analytics():
    """Public, anonymised city-wide performance (no personal data)."""
    with db() as con: rs = [row(r) for r in con.execute("SELECT * FROM complaints")]
    res = [r for r in rs if r["status"] == "Resolved"]
    def hrs(r):
        t = [l["t"] for l in r["log"] if l["s"] == "Resolved"]
        return ((max(t) if t else r["created"]) - r["created"]) / 3.6e6
    ok = [r for r in res if hrs(r) <= SLAH[r["priority"]]]
    return {"total": len(rs), "resolved": len(res), "open": len(rs) - len(res),
            "resolution_rate": round(100 * len(res) / len(rs)) if rs else 0,
            "avg_hours": round(sum(hrs(r) for r in res) / len(res), 1) if res else 0,
            "sla_compliance": round(100 * len(ok) / len(res)) if res else 0,
            "escalated": sum(r["escalated"] for r in rs),
            "duplicates_merged": sum(1 for r in rs if r["dup_of"]),
            "by_category": Counter(r["category"] for r in rs).most_common(),
            "hotspots": Counter(r["location"].split(" – ")[0] for r in rs).most_common(5)}

if FRONT.exists():  # serve the website from the same server (single deployment)
    app.mount("/", StaticFiles(directory=FRONT, html=True), name="frontend")
