import json, requests

def ollama_generate_json(model: str, prompt: str, temperature: float = 0.0, timeout: int = 120) -> dict:
    r = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature}},
        timeout=timeout,
    )
    r.raise_for_status()
    txt = r.json()["response"]
    start, end = txt.rfind("{"), txt.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Model did not return JSON.\n{txt}")
    return json.loads(txt[start:end+1])

