import re
from dataclasses import dataclass

@dataclass
class PolicyMatch:
    proc_code: str
    indicated_dx: str | None = None
    requires_modifier: tuple[str,str] | None = None  # (code, condition)
    rule_text: str | None = None

PROC_PATTERNS = [
    (re.compile(r"\barthrocentesis\b|PROC-123", re.I),
     PolicyMatch(proc_code="PROC-123", indicated_dx="M75.0x",
                 requires_modifier=("50", "if bilateral"))),
    (re.compile(r"\bnerve conduction\b|PROC-456", re.I),
     PolicyMatch(proc_code="PROC-456",
                 rule_text="NCS requires prior auth unless E11.40 documented")),
]

def parse_policies(text: str) -> list[PolicyMatch]:
    return [spec for pat, spec in PROC_PATTERNS if pat.search(text)]

def extract_policy_id(text: str) -> str | None:
    m = re.search(r"Policy ID:\s*([^\s]+)", text)
    return m.group(1) if m else None
