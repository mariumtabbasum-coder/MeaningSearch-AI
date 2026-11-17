"""Embeddings, cosine search, action tools and the chat/RAG orchestration loop."""
import json, time, ast, operator, datetime, numpy as np, requests
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, CHAT_MODELS, EMBED_MODEL
import db

_client = None
def client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

# ---------- Embeddings + manual cosine similarity ----------
def embed(texts):
    r = client().models.embed_content(model=EMBED_MODEL, contents=texts)
    vecs = [e.values for e in r.embeddings]
    if len(vecs) != len(texts):
        raise RuntimeError(f"Embedding API returned {len(vecs)} vectors for {len(texts)} texts")
    return vecs

def cosine(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / d) if d else 0.0

import threading
STATE = {"running": False, "done": 0, "total": 0, "error": None}
_lock = threading.Lock()

def _embed_one(text):
    for i in range(5):  # back off when the API says "too many requests" / busy
        try: return embed([text])[0]
        except Exception as e:
            if i < 4 and any(k in str(e) for k in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
                time.sleep(min(2 ** (i + 1), 20)); continue
            raise

def _worker():
    try:
        while True:
            rows = db.q("SELECT id,text FROM documents WHERE embedding IS NULL LIMIT 50")
            if not rows: break
            pending = db.q("SELECT COUNT(*) n FROM documents WHERE embedding IS NULL", one=True)["n"]
            STATE["total"] = STATE["done"] + pending
            for r in rows:
                db.run("UPDATE documents SET embedding=? WHERE id=?", (json.dumps(_embed_one(r["text"])), r["id"]))
                STATE["done"] += 1
    except Exception as e:
        STATE["error"] = str(e)[:200]
    finally:
        STATE["running"] = False

def start_embedding(force=False):
    """Embeds only documents that have no vector yet, in a background thread."""
    with _lock:
        if STATE["running"]: return False
        if force: db.run("UPDATE documents SET embedding=NULL")
        STATE.update(running=True, done=0, total=0, error=None)
    threading.Thread(target=_worker, daemon=True).start()
    return True

def search(query, k=5):
    qv = embed([query])[0]
    docs = db.q("SELECT id,text,category,embedding FROM documents WHERE embedding IS NOT NULL")
    res = [{"id": d["id"], "text": d["text"], "category": d["category"],
            "score": round(cosine(qv, json.loads(d["embedding"])), 4)} for d in docs]
    res.sort(key=lambda r: r["score"], reverse=True)
    res = res[:k]
    db.run("INSERT INTO searches(query,top_score,results) VALUES(?,?,?)",
           (query, res[0]["score"] if res else 0, len(res)))
    return res

# ---------- Action tools (Gemini function calling) ----------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.FloorDiv: operator.floordiv}
def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS: return _OPS[type(n.op)](_ev(n.left), _ev(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS: return _OPS[type(n.op)](_ev(n.operand))
    raise ValueError("Unsupported expression")

def calculator(expression: str) -> dict:
    """Evaluate a math expression such as '25 * 8' or '(12+3)/5'. Use * for multiplication."""
    return {"expression": expression, "result": _ev(ast.parse(expression.replace("×", "*").replace("÷", "/"), mode="eval").body)}

def get_weather(city: str) -> dict:
    """Get current live weather for a city."""
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1}, timeout=10).json()
    if not g.get("results"): return {"error": f"City '{city}' not found"}
    p = g["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": p["latitude"], "longitude": p["longitude"],
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m"}, timeout=10).json()["current"]
    return {"city": p["name"], "country": p.get("country"), "temperature_c": w["temperature_2m"],
            "humidity_percent": w["relative_humidity_2m"], "wind_kmh": w["wind_speed_10m"]}

def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert money between currencies using ISO codes, e.g. USD to PKR."""
    f, t = from_currency.upper(), to_currency.upper()
    r = requests.get(f"https://open.er-api.com/v6/latest/{f}", timeout=10).json()
    if r.get("result") != "success" or t not in r["rates"]: return {"error": "Unsupported currency"}
    return {"amount": amount, "from": f, "to": t, "rate": r["rates"][t], "converted": round(amount * r["rates"][t], 2)}

def calculate_age(birth_date: str) -> dict:
    """Calculate age from a birth date in YYYY-MM-DD format."""
    b, t = datetime.date.fromisoformat(birth_date), datetime.date.today()
    y = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    return {"birth_date": birth_date, "age_years": y, "days_lived": (t - b).days}

def search_knowledge(query: str) -> dict:
    """Search the user's knowledge base by meaning. Use for learning, how-to and factual topic questions."""
    return {"results": search(query, 3)}

TOOLS = {f.__name__: f for f in (calculator, get_weather, convert_currency, calculate_age, search_knowledge)}

SYSTEM = ("You are MeaningSearch AI, an assistant inside a knowledge workspace. Reply in the language the user writes in. "
          "For greetings or small talk, answer normally. For knowledge, learning or how-to questions, call search_knowledge "
          "and answer using the retrieved documents, saying when they don't cover the question. For math, weather, currency "
          "or age, call the matching tool. Use earlier messages to resolve follow-up questions. Keep answers clear and concise.")

def _stream(contents, cfg):
    """Try each model in order. Busy (503) -> retry once; unavailable/quota (404/429/403) -> next model."""
    last = None
    for model in CHAT_MODELS:
        for attempt in range(2):
            started = False
            try:
                for ch in client().models.generate_content_stream(model=model, contents=contents, config=cfg):
                    started = True
                    yield ch
                return
            except Exception as e:
                m = str(e); last = e
                if started: raise
                if "503" in m or "UNAVAILABLE" in m:
                    time.sleep(1); continue
                if any(k in m for k in ("404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "403", "PERMISSION_DENIED")):
                    break
                raise
    raise last or RuntimeError("No Gemini model is available")

def run_chat(contents):
    """Yields events: text / tool / sources. Streams text, executes tool calls, loops until final answer."""
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, tools=list(TOOLS.values()),
          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    for _ in range(4):
        calls, parts = [], []
        for ch in _stream(contents, cfg):
            if not ch.candidates or not ch.candidates[0].content or not ch.candidates[0].content.parts: continue
            for p in ch.candidates[0].content.parts:
                parts.append(p)
                if p.function_call: calls.append(p.function_call)
                elif p.text and not getattr(p, "thought", False): yield {"type": "text", "text": p.text}
        if not calls: return
        contents.append(types.Content(role="model", parts=parts))
        out_parts = []
        for fc in calls:
            args = dict(fc.args or {})
            yield {"type": "tool", "name": fc.name, "args": args}
            try: out = TOOLS[fc.name](**args)
            except Exception as e: out = {"error": str(e)}
            if fc.name == "search_knowledge": yield {"type": "sources", "items": out.get("results", [])}
            out_parts.append(types.Part.from_function_response(name=fc.name, response={"result": out}))
        contents.append(types.Content(role="user", parts=out_parts))
