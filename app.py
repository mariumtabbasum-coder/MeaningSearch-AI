import json
from flask import Flask, request, jsonify, Response, render_template, stream_with_context
from flask_cors import CORS
from google.genai import types
import db, services as S
from config import CHAT_MODELS, EMBED_MODEL, GEMINI_API_KEY

app = Flask(__name__, static_folder="public", static_url_path="")  # Vercel serves public/ from its CDN
CORS(app)
db.init()

@app.errorhandler(Exception)
def err(e):
    code = getattr(e, "code", 500)
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg: msg = "Gemini rate limit reached. Please wait a moment and try again."
    return jsonify(error=msg), code if isinstance(code, int) else 500

@app.get("/")
def index(): return render_template("index.html")

# ----- chat -----
@app.post("/api/chat")
def chat():
    d = request.get_json(force=True)
    text, cid = (d.get("message") or "").strip(), d.get("chat_id")
    if not text: return jsonify(error="Message is empty"), 400
    if not cid: cid = db.run("INSERT INTO chats(title) VALUES(?)", (text[:48],))
    db.run("INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)", (cid, "user", text))
    hist = db.q("SELECT role,content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 20", (cid,))[::-1]
    contents = [types.Content(role="user" if m["role"] == "user" else "model",
                parts=[types.Part.from_text(text=m["content"])]) for m in hist]

    def gen():
        full = ""
        yield json.dumps({"type": "chat", "id": cid}) + "\n"
        try:
            for ev in S.run_chat(contents):
                if ev["type"] == "text": full += ev["text"]
                yield json.dumps(ev, default=str) + "\n"
        except Exception as e:
            m = str(e)
            if "429" in m or "RESOURCE_EXHAUSTED" in m: m = "Gemini rate limit reached. Please try again shortly."
            if "503" in m or "UNAVAILABLE" in m: m = "Gemini is busy right now (high demand). Please send your message again in a few seconds."
            if "NOT_FOUND" in m or "404" in m: m = "This Gemini model is not available. Set GEMINI_CHAT_MODEL in .env to a current model (e.g. gemini-3.5-flash-lite) and restart."
            yield json.dumps({"type": "error", "message": m}) + "\n"
        if full: db.run("INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)", (cid, "assistant", full))
    return Response(stream_with_context(gen()), mimetype="application/x-ndjson")

@app.get("/api/chats")
def chats(): return jsonify(db.q("SELECT id,title,created,(SELECT COUNT(*) FROM messages WHERE chat_id=chats.id) n FROM chats ORDER BY id DESC"))

@app.get("/api/chats/<int:cid>")
def chat_get(cid): return jsonify(db.q("SELECT role,content FROM messages WHERE chat_id=? ORDER BY id", (cid,)))

@app.delete("/api/chats/<int:cid>")
def chat_del(cid):
    db.run("DELETE FROM messages WHERE chat_id=?", (cid,)); db.run("DELETE FROM chats WHERE id=?", (cid,))
    return jsonify(ok=True)

# ----- semantic search -----
@app.post("/api/search")
def search():
    d = request.get_json(force=True)
    qy = (d.get("query") or "").strip()
    if not qy: return jsonify(error="Enter a search query"), 400
    return jsonify(results=S.search(qy, int(d.get("k", 5))))

# ----- knowledge base -----
@app.get("/api/docs")
def docs(): return jsonify(db.q("SELECT id,text,category,embedding IS NOT NULL AS embedded FROM documents ORDER BY id DESC"))

@app.post("/api/docs")
def docs_add():
    items = request.get_json(force=True).get("docs", [])
    n = 0
    for it in items:
        t = (it.get("text") or "").strip()
        if t: db.run("INSERT INTO documents(text,category) VALUES(?,?)", (t, (it.get("category") or "General").strip())); n += 1
    S.start_embedding()
    return jsonify(added=n)

@app.delete("/api/docs/<int:i>")
def docs_del(i): db.run("DELETE FROM documents WHERE id=?", (i,)); return jsonify(ok=True)

@app.post("/api/docs/reembed")
def reembed(): return jsonify(started=S.start_embedding(force=True))

@app.post("/api/embed")
def embed_now(): return jsonify(started=S.start_embedding())

@app.get("/api/embed/status")
def embed_status():
    n = db.q("SELECT COUNT(*) n FROM documents WHERE embedding IS NULL", one=True)["n"]
    return jsonify(**S.STATE, pending=n)

@app.post("/api/docs/reset")
def docs_reset():
    db.run("DELETE FROM documents")
    if request.get_json(force=True).get("sample", True):
        db.load_sample(); S.start_embedding()
    return jsonify(ok=True)

# ----- stats / settings -----
@app.get("/api/stats")
def stats():
    one = lambda s: db.q(s, one=True)
    return jsonify(documents=one("SELECT COUNT(*) n FROM documents")["n"], embedded=one("SELECT COUNT(*) n FROM documents WHERE embedding IS NOT NULL")["n"],
        conversations=one("SELECT COUNT(*) n FROM chats")["n"], searches=one("SELECT COUNT(*) n FROM searches")["n"],
        avg_results=round(one("SELECT COALESCE(AVG(results),0) n FROM searches")["n"], 1),
        avg_score=round(one("SELECT COALESCE(AVG(top_score),0) n FROM searches")["n"], 3),
        recent=db.q("SELECT query,top_score,results,created FROM searches ORDER BY id DESC LIMIT 8"),
        categories=db.q("SELECT category,COUNT(*) n FROM documents GROUP BY category ORDER BY n DESC"))

@app.get("/api/settings")
def settings(): return jsonify(chat_model=" > ".join(CHAT_MODELS), embed_model=EMBED_MODEL, api_key=bool(GEMINI_API_KEY))

if __name__ == "__main__":
    if GEMINI_API_KEY: S.start_embedding()
    app.run(debug=True, use_reloader=False, port=5000)
