import re

CPT5 = re.compile(r"^\d{5}$")
PROC_CANON = {"PROC-123": "20610"}  # collapse demo alias → real CPT (add more if you have them)
ICD_RE = re.compile(r'\b[A-TV-Z]\d[\dA-Z](?:\.?\d[\dA-Z]*)?\b')   # e.g. M75.41, M75.0x, E11.40
CPT_RE = re.compile(r'\b\d{5}\b')                                 # 5-digit CPT like 20610


# remove non alphanumeric -- move lowercase to upper
def norm_code(code: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', (code or '').upper())
