# MeaningSearch AI
Chat + Semantic Search (manual cosine similarity on NumPy) + RAG + Action tools (calculator, weather, currency, age) in one workspace.

## Run
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY
python app.py               # http://127.0.0.1:5000
```
Weather uses Open-Meteo and currency uses open.er-api.com, so no extra keys are needed.
After changing GEMINI_EMBED_MODEL, press "Re-generate embeddings" in Knowledge.
