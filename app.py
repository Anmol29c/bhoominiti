import os, csv, io, json, threading, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
BASE = Path(__file__).parent; DATA = BASE / "data"; STORE = DATA / "store.json"
ADMIN = os.getenv("ADMIN_KEY", ""); MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
lock = threading.Lock(); app = FastAPI(title="BhoomiNiti API")

def load():
    return json.loads((STORE if STORE.exists() else DATA / "seed.json").read_text("utf-8"))
def save(d): STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
def pct(s): return round(100 * s["clr"] / s["vil"], 2) if s["vil"] else 0.0

@app.get("/api/data")
def data(): return load()

class Res(BaseModel):
    title: str; type: str = "Research Paper"; year: int | None = None; description: str = ""; file: str = ""; url: str = ""

def add_res(r: Res):
    if len(r.title.strip()) < 5: raise HTTPException(400, "Title too short")
    item = dict(id="c" + uuid.uuid4().hex[:8], title=r.title.strip(), type=r.type, year=r.year, desc=r.description, url=r.url, file=r.file, status="Pending", rel=70)
    with lock:
        d = load(); d["resources"].append(item); save(d)
    return item

@app.post("/api/resources")
def post_res(r: Res): return add_res(r)

@app.post("/api/resources/{rid}/approve")
def approve(rid: str, x_admin_key: str = Header("")):
    if ADMIN and x_admin_key != ADMIN: raise HTTPException(401, "Admin key missing/wrong")
    with lock:
        d = load(); hit = [r for r in d["resources"] if r["id"] == rid]
        if not hit: raise HTTPException(404, "Not found")
        hit[0]["status"] = "Verified"; save(d)
    return {"ok": True}

@app.post("/api/import")
async def import_csv(file: UploadFile = File(...)):
    rd = csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig")))
    keys = {"state": ("state", "state/ut_name", "state_name", "name"), "ror": ("total_ror", "ror"), "vil": ("total_villages", "villages"), "clr": ("clr_villages", "villages_of_clr_completed", "clr")}
    def num(v): return int(float(str(v).replace(",", "").replace("%", "").strip()))
    upd = add = skip = 0
    with lock:
        d = load(); idx = {s["n"].lower(): s for s in d["states"]}
        for row in rd:
            norm = {(k or "").strip().lower().replace(" ", "_"): v for k, v in row.items()}
            g = lambda f: next((norm[k] for k in keys[f] if norm.get(k) not in (None, "")), None)
            try:
                name = g("state").strip(); vals = {f: num(g(f)) for f in ("ror", "vil", "clr") if g(f) is not None}
            except Exception: skip += 1; continue
            if not vals: skip += 1; continue
            s = idx.get(name.lower())
            if s: s.update(vals); upd += 1
            else:
                s = dict(n=name, ror=0, vil=0, clr=0, lat=None, lon=None); s.update(vals); d["states"].append(s); idx[name.lower()] = s; add += 1
        save(d)
    return dict(updated=upd, added=add, skipped=skip)

def sim(a, b, c):
    return dict(score=min(100, round(45 + a * .22 + b * .18 + c * .15)), mutation_time_pct=-round(10 + a * .18 + b * .22), grievance_backlog_pct=-round(8 + b * .12 + c * .25), evidence_access_pct=round(12 + a * .42))

SYS = ("You are BhoomiAI, policy assistant of the BhoomiNiti land-governance platform. ALWAYS call tools to fetch real platform data before answering; never invent numbers or sources. "
       "Platform data = state-wise Computerisation of Land Records (CLR) from Lok Sabha USQ 749 (25 Jul 2023) plus any CSV imported by users; there is NO district or dispute data unless imported. "
       "The policy simulator is illustrative, not a forecast - say so. When asked to act (map, simulate, save a resource) call the tool and confirm. "
       "Reply in the user's language (Hinglish ok), max 120 words, cite resource titles used.")

def friendly(e):
    m = str(e)
    if any(x in m for x in ("API key", "API_KEY", "UNAUTHENTICATED", "PERMISSION_DENIED")): return "Gemini API key galat/band hai. aistudio.google.com se nayi key banao aur terminal me dobara set karo."
    if "429" in m or "RESOURCE_EXHAUSTED" in m: return "Gemini quota/limit khatam. 1 minute baad try karo."
    if "404" in m or "NOT_FOUND" in m: return "Model available nahi. GEMINI_MODEL=gemini-2.0-flash set karke try karo."
    return "Gemini error: " + m[:300]

class Chat(BaseModel): messages: list[dict]

@app.post("/api/chat")
def chat(c: Chat):
    key = os.getenv("GEMINI_API_KEY")
    if not key: raise HTTPException(503, "GEMINI_API_KEY set nahi hai")
    from google import genai
    from google.genai import types
    used, actions = [], []
    def search_resources(query: str) -> list:
        """Search the evidence repository by keywords; returns up to 5 resources."""
        used.append("search_resources"); t = [w for w in query.lower().split() if len(w) > 2]; out = []
        for r in load()["resources"]:
            m = sum(w in (r["title"] + " " + r["type"] + " " + r.get("desc", "")).lower() for w in t)
            if m: out.append((m, r))
        return [dict(title=r["title"], type=r["type"], year=r["year"], status=r["status"], url=r.get("url", "")) for _, r in sorted(out, key=lambda x: -x[0])[:5]]
    def state_stats(state: str = "") -> dict:
        """Land-record stats for a state/UT (partial name ok). Empty state returns national totals."""
        used.append("state_stats"); S = load()["states"]
        if not state:
            v = sum(s["vil"] for s in S); cl = sum(s["clr"] for s in S)
            return dict(states=len(S), villages=v, clr_villages=cl, clr_pct=round(100 * cl / v, 2), ror_records=sum(s["ror"] for s in S))
        return dict(matches=[dict(state=s["n"], ror_records=s["ror"], villages=s["vil"], clr_villages=s["clr"], clr_pct=pct(s)) for s in S if state.lower() in s["n"].lower()])
    def rank_states(indicator: str = "p", order: str = "asc", n: int = 5) -> list:
        """Rank states by indicator: p (CLR %), vil (villages), ror (RoR records), clr (CLR villages). order asc or desc."""
        used.append("rank_states"); S = load()["states"]
        f = (lambda s: pct(s)) if indicator == "p" else (lambda s: s.get(indicator, 0))
        return [dict(state=s["n"], value=f(s)) for s in sorted(S, key=f, reverse=order == "desc")[:max(1, min(n, 36))]]
    def simulate_policy(investment: int, automation: int, grievance: int) -> dict:
        """Run the illustrative policy simulator; each input 0-100. Also moves the UI sliders."""
        used.append("simulate_policy"); a, b, g = (max(0, min(100, int(x))) for x in (investment, automation, grievance))
        actions.append(dict(type="sim", investment=a, automation=b, grievance=g)); return sim(a, b, g)
    def show_on_map(indicator: str = "p", status: str = "all") -> dict:
        """Open the GIS map. indicator p/vil/ror; status all, lo (<50%), mid (50-90%), hi (>=90%)."""
        used.append("show_on_map"); actions.append(dict(type="map", indicator=indicator, status=status)); return {"shown": True}
    def add_resource(title: str, type: str = "Research Paper", year: int = 2026, description: str = "") -> dict:
        """Save a new resource to the repository as Pending verification."""
        used.append("add_resource"); return add_res(Res(title=title, type=type, year=year, description=description))
    contents = [types.Content(role="user" if m.get("role") == "user" else "model", parts=[types.Part(text=str(m.get("content", "")))]) for m in c.messages[-10:]]
    while contents and contents[0].role != "user": contents.pop(0)
    if not contents: raise HTTPException(400, "No message")
    cfg = types.GenerateContentConfig(system_instruction=SYS, temperature=.3, tools=[search_resources, state_stats, rank_states, simulate_policy, show_on_map, add_resource],
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=6))
    client = genai.Client(api_key=key); err = None
    for m in dict.fromkeys([MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]):
        try:
            used.clear(); actions.clear()
            r = client.models.generate_content(model=m, contents=contents, config=cfg)
            return dict(reply=r.text or "Kaam ho gaya, par text reply nahi aaya - dobara poochho.", tools=used, actions=actions)
        except Exception as e:
            import traceback; traceback.print_exc(); err = e
            if any(x in str(e) for x in ("API key", "API_KEY", "UNAUTHENTICATED", "PERMISSION_DENIED")): break
    raise HTTPException(502, friendly(err))

app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
