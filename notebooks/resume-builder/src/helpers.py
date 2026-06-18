from docx import Document
import json
from pathlib import Path
import re
from typing import Any
import yaml

def extract_docx_text(path: Path):
    '''Reads text cleanly from a docx file.'''
    doc = Document(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)

def parse_json_response(response):
    '''Cleans the JSON response from an LLM.'''
    text = response.output_text.strip()

    # Defensive fallback if the model returned ```json fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return json.loads(text)

# Simple JSON file handling
def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save_json(obj: Any, path: str | Path) -> None:
    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


# Text file handling
def load_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")

def save_text(text: str, path: str | Path) -> None:
    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# YAML file loading
def load_yaml(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
