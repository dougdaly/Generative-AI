import argparse
import json
from pathlib import Path
import yaml

from sotu_analytics.models.topic_label_llm import ollama_generate_json  # uses your robust parser
from sotu_analytics.io.save_json import save_json

# -----------------------------
# Macro taxonomy (freeze this)
# -----------------------------
DEFAULT_MACROS = [
    "Economy and Jobs",
    "Taxes, Budget, and Debt", 
    "Healthcare",
    "Education and Workforce",
    "Immigration and Border",
    "Infrastructure and Energy",
    "Industry, Technology, and Trade",
    "Foreign Policy and Alliances",
    "National Security and Military",
    "Rights and Social Issues",
    "Crime and Public Safety",
    "Governance and Institutions",
    "National Identity and Values",
    "Other",
]


def repo_paths():
    here = Path(__file__).resolve()
    repo_root = here.parents[4]        # .../Generative-AI
    project_root = here.parents[1]     # .../src/demos/sotu-speech-analytics
    return repo_root, project_root

def build_macro_prompt(topic_id: int, micro_label: str, terms: list[str], excerpts: list[str], macros: list[str]) -> str:
    macro_lines = "\n".join([f"- {m}" for m in macros])

    # Keep these short; long prompts increase failure rate
    term_block = "\n".join([f"- {t}" for t in (terms or [])[:12]])
    ex_block = "\n".join([f"{i+1}) {e}" for i, e in enumerate((excerpts or [])[:4])])

    return f"""You are mapping discovered micro-topics from State of the Union speeches into a fixed set of macro topics.

Choose exactly ONE macro_topic from this list:
{macro_lines}

Micro-topic:
- topic_id: {topic_id}
- micro_label: {micro_label}

Top terms (distinctive ngrams):
{term_block}

Representative excerpts:
{ex_block}

Rules:
- macro_topic MUST be exactly one of the listed options.
- subtopic: 1-5 words, more specific than the macro.
- Use "Other" only if none of the macro topics fit.

Tie-break guidance:
- Military ceremonies/honors/medals/service members/veterans/sacrifice/combat injuries => "National Security and Military" (even if ceremonial).
- Schools/college/student loans/education affordability/apprenticeships/job training/upskilling/workforce skills => "Education and Workforce".
  If primarily framed as deficit/taxpayer cost/budget impact => "Taxes, Budget, and Debt".
- NATO/allies/diplomacy/foreign aid/international coordination => "Foreign Policy and Alliances".
- Congress functioning/elections/democratic process/government operations => "Governance and Institutions".
- National unity/resilience/optimism/identity/closing-peroration ("who we are", "American spirit") => "National Identity and Values".

Return JSON only. Do not ask questions.

Return JSON:
{{
  "macro_topic": "...",
  "subtopic": "...",
  "confidence": "low|med|high",
  "evidence": {{
    "macro": "short phrase",
    "subtopic": "short phrase"
  }}
}}
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="qwen2.5:14b-instruct-q4_K_M")
    parser.add_argument("--force", action="store_true", help="Overwrite output mapping file.")
    parser.add_argument("--max_topics", type=int, default=None, help="For testing; cap number of topics processed.")
    args = parser.parse_args()

    REPO_ROOT, PROJECT_ROOT = repo_paths()

    cfg_path = PROJECT_ROOT / "configs" / "v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # Allow overriding macro list from config if you later add it there
    macros = cfg.get("macro_topics", DEFAULT_MACROS)
    if "Other" not in macros:
        macros = list(macros) + ["Other"]

    base = REPO_ROOT / "assets" / "sotu-speech-analytics" / "data" / "derived" / "topics_global"
    labels_path = base / "global_topic_labels_llm.json"
    terms_path = base / "global_topic_terms.json"
    out_path = base / "global_topic_macro_map.json"

    if not labels_path.exists():
        raise FileNotFoundError(f"Missing: {labels_path}")
    if not terms_path.exists():
        raise FileNotFoundError(f"Missing: {terms_path}")

    if args.force and out_path.exists():
        out_path.unlink()

    topic_labels = json.loads(labels_path.read_text(encoding="utf-8"))
    topic_terms = json.loads(terms_path.read_text(encoding="utf-8"))

    # Resume behavior if not forcing
    existing = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))

    # Normalize keys to int internally
    def as_int_keys(d):
        out = {}
        for k, v in d.items():
            out[int(k)] = v
        return out

    topic_labels_i = as_int_keys(topic_labels)
    topic_terms_i = as_int_keys(topic_terms)
    existing_i = as_int_keys(existing) if existing else {}

    topic_ids = sorted(topic_labels_i.keys())
    if args.max_topics:
        topic_ids = topic_ids[: args.max_topics]

    out_map = dict(existing_i)

    for idx, tid in enumerate(topic_ids, start=1):
        if (not args.force) and tid in out_map:
            continue

        rec = topic_labels_i[tid]
        micro_label = rec.get("label", f"topic_{tid}")
        excerpts = rec.get("excerpts", [])
        terms = topic_terms_i.get(tid, rec.get("ngram_terms", []))

        prompt = build_macro_prompt(tid, micro_label, terms, excerpts, macros)

        # Keep output short to reduce JSON breakage
        resp = ollama_generate_json(args.model, prompt, temperature=0.0, timeout=180, num_predict=180)

        macro = resp.get("macro_topic")
        if macro not in macros:
            macro = "Other"

        out_map[tid] = {
            "topic_id": tid,
            "micro_label": micro_label,
            "macro_topic": macro,
            "subtopic": resp.get("subtopic"),
            "confidence": resp.get("confidence"),
            "evidence": resp.get("evidence", {}),
            "model": args.model,
        }

        if idx % 5 == 0:
            print(f"Mapped {idx}/{len(topic_ids)} topics...")

    # Save with string keys for JSON readability
    out_map_str = {str(k): v for k, v in sorted(out_map.items(), key=lambda x: x[0])}
    save_json(str(out_path), out_map_str)
    print("Wrote:", out_path)

if __name__ == "__main__":
    main()
