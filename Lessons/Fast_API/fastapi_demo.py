from fastapi import FastAPI
from pydantic import BaseModel

# Run by: uvicorn fastapi_demo:app --reload --port 8000
# http://localhost:8000/health
# http://localhost:8000/docs (Swagger UI)

app = FastAPI(title="Demo API")

class EchoRequest(BaseModel):
    text: str

class EchoResponse(BaseModel):
    length: int
    upper: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/echo", response_model=EchoResponse)
async def echo(req: EchoRequest):
    return EchoResponse(
        length=len(req.text),
        upper=req.text.upper(),
    )
