from fastapi import FastAPI
from service.inference import summarize

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/summarize")
def summarize_api(payload: dict):
    text = payload.get("text", "")
    result = summarize(text)
    return result