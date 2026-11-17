"""Run: python check_models.py  -> shows which Gemini models actually work with YOUR key."""
import time
from google import genai
from config import GEMINI_API_KEY
c = genai.Client(api_key=GEMINI_API_KEY)
cands = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
         "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
try:
    avail = {m.name.replace("models/", "") for m in c.models.list()}
    print("Models visible to your key:", len(avail))
    cands += sorted(m for m in avail if "flash" in m and m not in cands and "image" not in m and "tts" not in m and "live" not in m)[:8]
except Exception as e:
    print("Could not list models:", str(e)[:150])
ok = []
for m in dict.fromkeys(cands):
    t = time.time()
    try:
        c.models.generate_content(model=m, contents="Reply with the single word OK")
        print(f"OK    {m}  ({time.time() - t:.1f}s)"); ok.append(m)
    except Exception as e:
        print(f"FAIL  {m}  -> {str(e)[:110]}")
print("\\nPut this in .env:" if ok else "\\nNo model worked. Check your API key / quota in Google AI Studio.")
if ok: print("GEMINI_CHAT_MODEL=" + ",".join(ok[:4]))
