from __future__ import annotations
import json
from sotu_analytics.prompts import build_topic_label_prompt, build_disambiguate_prompt
from collections import defaultdict
from typing import Dict, Any, List
import numpy as np
import requests
import re


def _strip_code_fences(s: str) -> str:
    # Remove ```json ... ``` or ``` ... ``` wrappers if present
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _parse_first_json_object(text: str) -> dict:
    text = _strip_code_fences(text)

    # Find first likely JSON object/array start
    starts = []
    for ch in ("{", "["):
        i = text.find(ch)
        if i != -1:
            starts.append(i)
    if not starts:
        raise ValueError(f"No JSON start found in response:\n{text[:800]}")

    start = min(starts)
    s = text[start:]

    dec = json.JSONDecoder()
    obj, end = dec.raw_decode(s)  # parses first JSON entity; ignores trailing text
    return obj

def ollama_generate_json(model: str, prompt: str, temperature: float = 0.0, timeout: int = 180, num_predict: int=160) -> dict:
    r = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    txt = r.json()["response"]
    obj = _parse_first_json_object(txt)
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj)}:\n{txt[:800]}")
    return obj



def top_representative_chunks(texts, X, labels, centroids, topic_id, top_n=6, max_chars=450):
    # (your existing, hardened version is fine)
    X = np.nan_to_num(np.asarray(X, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    centroids = np.nan_to_num(np.asarray(centroids, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    idx = np.where(labels == topic_id)[0]
    if len(idx) == 0:
        return []
    C = centroids[topic_id]
    Xi = np.ascontiguousarray(X[idx], dtype=np.float64)
    C  = np.ascontiguousarray(C, dtype=np.float64)
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        sims = Xi @ C
    sims = np.nan_to_num(sims, nan=-1e9, posinf=-1e9, neginf=-1e9)
    top_local = idx[np.argsort(-sims)[:top_n]]
    reps = []
    for i in top_local:
        t = texts[i].strip()
        if len(t) > max_chars:
            t = t[:max_chars].rsplit(" ", 1)[0] + "..."
        reps.append(t)
    return reps

def _norm_label(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def resolve_duplicate_labels(topic_labels: dict, model: str) -> dict:
    groups = defaultdict(list)
    for tid, rec in topic_labels.items():
        groups[_norm_label(rec.get("label", ""))].append(int(tid))

    dupes = {lbl: tids for lbl, tids in groups.items() if lbl and len(tids) > 1}
    if not dupes:
        return topic_labels

    for lbl_norm, tids in dupes.items():
        base_label = topic_labels[tids[0]].get("label", lbl_norm)

        topics_payload = []
        for tid in tids:
            rec = topic_labels[tid]
            topics_payload.append({
                "topic_id": tid,
                "ngram_terms": rec.get("ngram_terms", [])[:12],
                "excerpts": rec.get("excerpts", [])[:6],
            })

        prompt = build_disambiguate_prompt(label=base_label, topics=topics_payload)

        try:
            resp = ollama_generate_json(model, prompt, temperature=0.0, timeout=180, num_predict=140)
        except Exception as e:
            # Fallback: deterministic unique labels using top ngram term
            for tid in tids:
                rec = topic_labels[tid]
                top_term = (rec.get("ngram_terms") or ["subtopic"])[0]
                safe_term = re.sub(r"\s+", " ", str(top_term)).strip()
                rec.setdefault("disambiguation", {})
                rec["disambiguation"].update({
                    "status": "fallback",
                    "original_label": rec.get("label"),
                    "error": str(e),
                })
                rec["label"] = f"{base_label}: {safe_term}"
            continue

        for tid in tids:
            new_label = resp.get(str(tid)) or resp.get(tid)
            if not new_label:
                continue
            topic_labels[tid].setdefault("disambiguation", {})
            topic_labels[tid]["disambiguation"].update({
                "status": "ok",
                "original_label": topic_labels[tid].get("label"),
                "prompt": prompt,
                "response": resp,
            })
            topic_labels[tid]["label"] = str(new_label).strip()

    return topic_labels


def label_topics_with_llm(year, texts, X, labels, km, ngram_terms_by_topic, model, top_n=6):
    raw = np.asarray(km.cluster_centers_, dtype=np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    centroids = raw / norms

    k = int(raw.shape[0])
    topic_labels = {}
    for t in range(k):
        excerpts = top_representative_chunks(texts, X, labels, centroids, t, top_n=top_n)
        prompt = build_topic_label_prompt(year, t, ngram_terms_by_topic.get(t, []), excerpts)
        resp = ollama_generate_json(model, prompt, temperature=0.0, num_predict=200)
        topic_labels[t] = {
            "label": resp.get("label"),
            "confidence": resp.get("confidence"),
            "keywords": resp.get("keywords", []),
            "rationale": resp.get("rationale", ""),
            "excerpts": excerpts,
            "ngram_terms": ngram_terms_by_topic.get(t, []),
            "prompt": prompt,  # optional but great for audit/debug
            "model": model, 
        }
    topic_labels = resolve_duplicate_labels(topic_labels=topic_labels, model=model)
    return topic_labels
