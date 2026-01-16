from __future__ import annotations

from pathlib import Path
from datetime import datetime as dt, timezone, UTC
import traceback
import json 
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
import numpy as np
from PIL import Image
import pytesseract
import shutil
from typing import List, Callable, Dict, Any, Optional
from archival_restore.types import PageArtifact
import preprocess_utils as pp
from dataclasses import asdict, is_dataclass
import re
import string
from collections import Counter
import hashlib
from typing import Literal
from functools import partial

PreprocessMethod = Literal["basic", "normalize", "denoise", "binarize"]

PUNCT = ".,;:!?\"'()-"
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
DEFAULT_OCR_CONFIG = "--oem 1 --psm 3 --dpi 300 -c preserve_interword_spaces=1"
DEFAULT_OCR_UPSCALE = 1.0
DEFAULT_SWEEP_CONFIGS = [
    "--oem 1 --psm 6 --dpi 300 -c preserve_interword_spaces=1",
    "--oem 1 --psm 4 --dpi 300 -c preserve_interword_spaces=1",
    "--oem 1 --psm 3 --dpi 300 -c preserve_interword_spaces=1",
    "--oem 1 --psm 6 --dpi 400 -c preserve_interword_spaces=1",
    "--oem 1 --psm 4 --dpi 400 -c preserve_interword_spaces=1",
    "--oem 1 --psm 3 --dpi 400 -c preserve_interword_spaces=1",
]
DEFAULT_SWEEP_UPSCALES = [1.0, 2.0]
DEFAULT_POLICY = {
    "ok_mean_conf": 0.88,
    "ok_low_conf_rate": 0.20,
    "attention_mean_conf": 0.82,   # below this -> needs_attention True
    "human_mean_conf": 0.82,       # below this -> needs_human_review True
    "min_improvement": 0.01,        # only escalate if we’re meaningfully below ok
    "variants_full": [
        ("PreprocessBasic", pp.preprocess_basic),
        ("PreprocessNormalize", pp.preprocess_normalize),
        ("PreprocessDenoise", pp.preprocess_denoise),
        ("PreprocessBinarizeForOCR", pp.preprocess_binarize_for_ocr),
    ],
}
DEFAULT_ESCALATION_POLICY = {
        "pass_mean_conf": 0.90,          # if >=, we accept without OCR sweep
        "pass_low_conf_rate": 0.06,      # also require low_conf_rate <= this when available
        "force_sweep": False,            # debug knob
        "default_ocr_config": DEFAULT_OCR_CONFIG,
        "default_ocr_upscale": DEFAULT_OCR_UPSCALE,
        "sweep_configs": DEFAULT_SWEEP_CONFIGS,
        "sweep_upscales": DEFAULT_SWEEP_UPSCALES,
    }

_PREPROCESS_STEP_FNS = {
    "basic": lambda image_path, out_path, upscale: pp.preprocess_basic(image_path, out_path, upscale),
    "normalize": lambda image_path, out_path, upscale: pp.preprocess_normalize(image_path, out_path, upscale),
    "denoise": lambda image_path, out_path, upscale: pp.preprocess_denoise(image_path, out_path, upscale),
    "binarize": lambda image_path, out_path, upscale: pp.preprocess_binarize_for_ocr(image_path, out_path),
}

_PREPROCESS_MAP = {
    "basic": pp.preprocess_basic,
    "normalize": pp.preprocess_normalize,
    "denoise": pp.preprocess_denoise,
    "binarize": pp.preprocess_binarize_for_ocr,
}

def ok_result(
    tool: str,
    outputs: Dict[str, Any],
    *,
    inputs: Optional[Dict[str, Any]] = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    debug: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    version: str = "v1",
) -> Dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "version": version,
        "run_id": run_id,
        "inputs": inputs or {},
        "outputs": outputs,
        "artifacts": artifacts or [],
        "metrics": metrics or {},
        "warnings": warnings or [],
        **({"debug": debug} if debug is not None else {}),
    }

def err_result(
    tool: str,
    message: str,
    *,
    code: str = "ERROR",
    inputs: Optional[Dict[str, Any]] = None,
    debug: Optional[Dict[str, Any]] = None,
    version: str = "v1",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "version": version,
        "error": {"code": code, "message": message},
        "inputs": inputs or {},
        **({"debug": debug} if debug is not None else {}),
    }


def _passes(policy: dict, score: dict) -> bool:
    return (
        float(score.get("mean_conf", 0.0)) >= float(policy["pass_mean_conf"])
        and float(score.get("low_conf_rate", 1.0)) <= float(policy["pass_low_conf_rate"])
    )

def _delta(a: dict, b: dict) -> dict:
    # mean_conf: higher is better (b - a)
    # low_conf_rate: lower is better (a - b)
    return {
        "mean_conf": float(b.get("mean_conf", 0.0)) - float(a.get("mean_conf", 0.0)),
        "low_conf_rate": float(a.get("low_conf_rate", 0.0)) - float(b.get("low_conf_rate", 0.0)),
    }

def _page_id_from_path(p: Path) -> str:
    """
    Produce a stable id for filenames.
    Examples:
      page_14_raw.png -> page_14
      001.png         -> page_001
      anything.png    -> anything
    """
    stem = p.stem
    m = re.search(r"(page[_-]?\d+)", stem, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower().replace("-", "_")
    # fallback: preserve stem
    return stem


def _list_images(in_dir: Path, recursive: bool = False) -> List[Path]:
    if recursive:
        paths = [p for p in in_dir.rglob("*") if p.is_file() and p.suffix.lower() in _IMG_EXTS]
    else:
        paths = [p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in _IMG_EXTS]
    return sorted(paths, key=lambda p: p.name)

def process_page_tool(
    image_path: str,
    out_dir: str,
    lang: str = "eng",
    policy: Optional[Dict[str, Any]] = None,
    fast: bool = False,
    enable_preprocess_rescue: bool = True,
    enable_ocr_sweep: bool = True,
    preprocess_rescue_topk: Optional[int] = None,
) -> dict:
    """
    ProcessPage = unified orchestrator.

    Steps:
      1) preprocess selection (run_preprocess_experiment)
      2) baseline OCR score on chosen clean image (default ocr spec)
      3) if baseline fails and enable_preprocess_rescue: rescore topK preprocess candidates and pick best
      4) if still fails and enable_ocr_sweep: OCR sweep on final clean image
      5) write record
      6) return ok_result with stable outputs + artifacts
    """
    run_id = dt.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tool = "ProcessPage"
    inputs = {
        "image_path": str(image_path),
        "out_dir": str(out_dir),
        "lang": lang,
        "fast": bool(fast),
        "enable_preprocess_rescue": bool(enable_preprocess_rescue),
        "enable_ocr_sweep": bool(enable_ocr_sweep),
        "preprocess_rescue_topk": preprocess_rescue_topk,
    }

    try:
        policy = policy or DEFAULT_ESCALATION_POLICY  # one policy to rule them all
        img_p = Path(_strip_quotes(image_path))
        out_p = Path(_strip_quotes(out_dir))
        out_p.mkdir(parents=True, exist_ok=True)

        # (A) Orientation (informational)
        rot, rot_conf, _ = pp.detect_orientation(img_p)
        orientation = {"rotate_deg": int(rot), "conf": float(rot_conf)}

        # (B) Preprocess selection (canonical)
        prep_dir = out_p / "preprocess"
        prep_dir.mkdir(parents=True, exist_ok=True)

        prep_result = run_preprocess_experiment(
            image_path=img_p,
            out_dir=prep_dir,
            lang=lang,
            upscale=float(policy["default_ocr_upscale"]),
            fast=fast,
        )

        prep_lb: List[dict] = (prep_result.get("leaderboard") or [])
        chosen_pre = prep_result.get("chosen") or (prep_lb[0] if prep_lb else None)
        if not chosen_pre or not chosen_pre.get("clean_image"):
            raise ValueError("run_preprocess_experiment did not return a chosen clean_image")

        clean_initial = Path(chosen_pre["clean_image"])
        clean_current = clean_initial

        # (C) Baseline OCR on initial chosen clean image
        default_cfg = _norm_cfg(policy["default_ocr_config"])
        default_up = float(policy["default_ocr_upscale"])

        baseline_score = score_ocr(
            clean_current,
            lang=lang,
            tess_config=default_cfg,
            upscale=default_up,
            fast=fast,
        )
        baseline_passes = _passes(policy, baseline_score)

        # (D) Preprocess rescue: rescore topK preprocess variants with baseline OCR spec
        rescue = {
            "ran": False,
            "chosen_variant": None,
            "passes": baseline_passes,
            "top3": [],
        }
        score_after_rescue = baseline_score
        passes_after_rescue = baseline_passes

        if enable_preprocess_rescue and (not baseline_passes) and prep_lb:
            rescue["ran"] = True

            topk = int(preprocess_rescue_topk or policy.get("preprocess_rescue_topk", 6))
            cands = [r for r in prep_lb if r.get("clean_image")][:topk]

            rescored = []
            for r in cands:
                p = Path(r["clean_image"])
                s = score_ocr(
                    p,
                    lang=lang,
                    tess_config=default_cfg,
                    upscale=default_up,
                    fast=fast,
                )
                rescored.append({"name": r.get("name"), "clean_image": str(p), "score": s})

            # deterministic ties: earlier preprocess variants win
            variant_rank = {r["name"]: i for i, r in enumerate(rescored) if r.get("name")}
            rescored_sorted = sorted(rescored, key=lambda x: _score_key(x, fast=fast, rank_map=variant_rank), reverse=True)

            rescue["top3"] = [
                {**x, "passes": _passes(policy, x["score"])} for x in rescored_sorted[:3]
            ]

            best = rescored_sorted[0] if rescored_sorted else None
            if best:
                clean_current = Path(best["clean_image"])
                score_after_rescue = best["score"]
                passes_after_rescue = _passes(policy, score_after_rescue)
                rescue["chosen_variant"] = best.get("name")
                rescue["passes"] = passes_after_rescue

        # (E) OCR sweep if still failing
        sweep_ran = False
        sweep_used = False
        sweep_record_path = None

        final_cfg = default_cfg
        final_cfg_id = _cfg_id(final_cfg)
        final_up = default_up
        final_score = score_after_rescue

        if enable_ocr_sweep and (policy.get("force_sweep", False) or (not passes_after_rescue)):
            sweep_ran = True

            sweep_dir = out_p / "ocr_sweep"
            sweep_dir.mkdir(parents=True, exist_ok=True)

            # If you want a stable preference order for configs in ties:
            cfg_rank = { _cfg_id(_norm_cfg(c)): i for i, c in enumerate(policy["sweep_configs"]) }

            sweep_result = run_ocr_sweep(
                image_paths=[clean_current],
                out_dir=sweep_dir,
                lang=lang,
                configs=[_norm_cfg(c) for c in policy["sweep_configs"]],
                upscales=[float(u) for u in policy["sweep_upscales"]],
                fast=fast,
                preprocessed=True,
            )
            sweep_record_path = sweep_result.get("record_path")

            per_page = (sweep_result.get("per_page_best") or [])
            chosen = (per_page[0].get("chosen") if per_page else None) or None

            if chosen:
                # normalize key names; your sweep output uses upscale
                chosen_cfg = _norm_cfg(chosen.get("tess_config") or final_cfg)
                chosen_cfg_id = chosen.get("tess_config_id") or _cfg_id(chosen_cfg)
                chosen_up = float(chosen.get("upscale", final_up))
                chosen_score = chosen.get("score") or final_score

                # Only accept if it wins by your scoring rule
                # (Your run_ocr_sweep should already have chosen best, but this guards regressions.)
                baseline_row = {"tess_config_id": _cfg_id(default_cfg), "score": score_after_rescue}
                chosen_row = {"tess_config_id": chosen_cfg_id, "score": chosen_score}

                if _score_key(chosen_row, fast=fast, rank_map=cfg_rank) >= _score_key(baseline_row, fast=fast, rank_map=cfg_rank):
                    final_cfg, final_cfg_id, final_up, final_score = chosen_cfg, chosen_cfg_id, chosen_up, chosen_score

                sweep_used = (final_cfg_id != _cfg_id(default_cfg)) or (final_up != float(default_up))

        # (F) Deltas
        delta_vs_baseline = _delta(baseline_score, final_score)
        delta_vs_current = _delta(score_after_rescue, final_score)

        # (G) Build outputs (compact + stable)
        outputs = {
            "raw_image": str(img_p),
            "orientation": orientation,

            "clean_image_initial": str(clean_initial),
            "clean_image": str(clean_current),

            "baseline_ocr": {
                "tess_config": default_cfg,
                "tess_config_id": _cfg_id(default_cfg),
                "upscale": default_up,
                "score": baseline_score,
                "passes": baseline_passes,
            },

            "preprocess_rescue": rescue,

            "final_ocr": {
                "tess_config": final_cfg,
                "tess_config_id": final_cfg_id,
                "upscale": final_up,
                "score": final_score,
                "delta_vs_baseline": delta_vs_baseline,
                "delta_vs_current": delta_vs_current,
                "passes": _passes(policy, final_score),
            },

            "sweep_ran": sweep_ran,
            "sweep_used": sweep_used,
            "sweep_record_path": sweep_record_path,

            # optional pointer to preprocess record (if your preprocess step writes one)
            "preprocess_record_path": (prep_result.get("record", {}) or {}).get("record_path") or prep_result.get("record_path"),
        }
        # (G.5) Emit OCR text artifact for the final chosen image/config
        ocr_text_dir = out_p / "ocr_text"
        ocr_text_dir.mkdir(parents=True, exist_ok=True)

        ocr_text_path = ocr_text_dir / f"{img_p.stem}_ocr.txt"

        ocr_out = ocr_page(
            image_path=clean_current,
            lang=lang,
            tess_config=final_cfg,
            upscale=final_up,
        )

        text = ocr_out.get("text", "")
        ocr_text_path.write_text(text, encoding="utf-8")

        outputs["ocr_text"] = {
            "path": str(ocr_text_path),
            "tokens": len(ocr_out.get("tokens", [])),
            "mean_conf": float(ocr_out.get("mean_conf", 0.0)),
        }

        # (H) Record (keep it useful, not enormous)
        payload = {
            "pipeline": tool,
            "ts_utc": run_id,
            "inputs": inputs,
            "outputs": {
                "raw_image": outputs["raw_image"],
                "orientation": outputs["orientation"],
                "clean_image_initial": outputs["clean_image_initial"],
                "clean_image": outputs["clean_image"],
                "baseline_ocr": outputs["baseline_ocr"],
                "preprocess_rescue": outputs["preprocess_rescue"],
                "final_ocr": outputs["final_ocr"],
                "sweep_ran": outputs["sweep_ran"],
                "sweep_used": outputs["sweep_used"],
                "sweep_record_path": outputs["sweep_record_path"],
                "preprocess_record_path": outputs.get("preprocess_record_path"),
            },
            "policy_effective": {
                "pass_mean_conf": policy["pass_mean_conf"],
                "pass_low_conf_rate": policy["pass_low_conf_rate"],
                "default_ocr_config": default_cfg,
                "default_ocr_upscale": default_up,
                "force_sweep": policy.get("force_sweep", False),
                "sweep_configs": [_norm_cfg(c) for c in policy["sweep_configs"]],
                "sweep_upscales": [float(u) for u in policy["sweep_upscales"]],
                "preprocess_rescue_topk": int(preprocess_rescue_topk or policy.get("preprocess_rescue_topk", 6)),
            },
        }

        record_meta = write_artifact_record_tool(payload=payload, out_dir=str(out_p))
        record_path = record_meta.get("record_path")

        artifacts = []
        stable_dir = out_p / "page_artifacts"
        stable_dir.mkdir(parents=True, exist_ok=True)
        stable_record = stable_dir / f"{img_p.stem}_artifact.json"
        if record_path:
            shutil.copy2(record_path, stable_record)
            artifacts.append({"kind": "page_artifact", "path": str(stable_record)})
            outputs["page_artifact_path"] = str(stable_record)
            artifacts.append({"kind": "record", "path": str(record_path), **{k: v for k, v in record_meta.items() if k != "record_path"}})
        if sweep_record_path:
            artifacts.append({"kind": "sweep_record", "path": str(sweep_record_path)})
        artifacts.append({"kind": "ocr_text", "path": str(ocr_text_path)})

        metrics = {
            "baseline_mean_conf": float(baseline_score.get("mean_conf", 0.0)),
            "final_mean_conf": float(final_score.get("mean_conf", 0.0)),
            "baseline_low_conf_rate": float(baseline_score.get("low_conf_rate", 0.0)),
            "final_low_conf_rate": float(final_score.get("low_conf_rate", 0.0)),
        }

        return ok_result(run_id=run_id, tool=tool, inputs=inputs, outputs=outputs, artifacts=artifacts, metrics=metrics)

    except Exception as e:
        return err_result(
            tool=tool,
            code="exception",
            message=str(e),
            inputs=inputs,
            debug={"traceback": traceback.format_exc()},
        )


def preprocess_tool(image_path: str, out_path: str, method: str = "basic") -> dict:
    fn = _PREPROCESS_MAP.get(method.lower())
    if fn is None:
        raise ValueError(f"Unknown preprocess method: {method}. Expected one of {sorted(_PREPROCESS_MAP)}")

    # only basic returns meta in your current setup; keep that detail here
    if method.lower() == "basic":
        p, meta = fn(Path(image_path), Path(out_path), return_meta=True)
        return {"clean_image": str(p), "method": method, "meta": meta}

    p = fn(Path(image_path), Path(out_path))
    return {"clean_image": str(p), "method": method}

def _as_path(s: str) -> Path:
    return Path(_strip_quotes(s))

def _norm_step(s: str) -> str:
    return (s or "").strip().lower().replace("-", "_").replace(" ", "_")


def _norm_cfg(s: str) -> str:
    return " ".join((s or "").split())
def _cfg_id(s: str) -> str:
    return hashlib.sha1(_norm_cfg(s).encode("utf-8")).hexdigest()[:10]

def _strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s

def _jsonify(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj):
        return _jsonify(asdict(obj))
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def _passes(policy: Dict[str, Any], score: Dict[str, Any]) -> bool:
    mean_conf = float(score.get("mean_conf", 0.0) or 0.0)
    low_rate = score.get("low_conf_rate", None)
    if low_rate is None:
        # if fast score lacks it, fall back to mean_conf only
        return mean_conf >= float(policy["pass_mean_conf"])
    return (mean_conf >= float(policy["pass_mean_conf"])) and (float(low_rate) <= float(policy["pass_low_conf_rate"]))

def load_for_ocr(path: Path, upscale: float = DEFAULT_OCR_UPSCALE) -> Image.Image:
    img = Image.open(path).convert("RGB")
    if upscale and upscale != 1.0:
        w, h = img.size
        img = img.resize((int(w * upscale), int(h * upscale)), resample=Image.Resampling.LANCZOS)
    return img



def compute_text_stats(text: str, ref_stats: dict | None = None) -> dict:
    text = text or ""
    n = max(len(text), 1)

    # basic counts
    punct_counts = Counter(ch for ch in text if ch in PUNCT)
    punct_total = sum(punct_counts.values())

    # "weird" chars (not printable) – should be near 0
    printable = set(string.printable)
    non_printable = sum((ch not in printable) for ch in text)

    # tokenization (simple)
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    tok_n = max(len(tokens), 1)

    stats = {
        "chars": len(text),
        "tokens": tok_n,
        "punct_total": punct_total,
        "punct_per_100_chars": 100.0 * punct_total / n,
        "apostrophes_per_100_tokens": 100.0 * punct_counts.get("'", 0) / tok_n,
        "periods_per_100_tokens": 100.0 * punct_counts.get(".", 0) / tok_n,
        "non_printable_rate": non_printable / n,
        "punct_hist": {k: punct_counts.get(k, 0) / n for k in PUNCT},  # normalized
    }

    # Optional: match punctuation distribution to reference pages
    if ref_stats and "punct_hist" in ref_stats:
        # L1 distance; lower is better
        dist = 0.0
        for k in PUNCT:
            dist += abs(stats["punct_hist"].get(k, 0.0) - ref_stats["punct_hist"].get(k, 0.0))
        stats["punct_dist_to_ref"] = dist
    else:
        stats["punct_dist_to_ref"] = None

    return stats


def score_ocr(
    image_path: Path,
    lang: str = "eng",
    tess_config: str = DEFAULT_OCR_CONFIG,
    upscale: float = DEFAULT_OCR_UPSCALE,
    fast: bool=False
) -> Dict[str, Any]:
    img = load_for_ocr(image_path, upscale=upscale)

    data = pytesseract.image_to_data(
        img, lang=lang, config=tess_config, output_type=pytesseract.Output.DICT
    )

    confs, low, toks = [], 0, 0
    for c_raw, t_raw in zip(data.get("conf", []), data.get("text", [])):
        t = (t_raw or "").strip()
        if not t:
            continue
        if not any(ch.isalnum() for ch in t):
            continue

        toks += 1
        try:
            c = float(c_raw)
        except Exception:
            c = -1.0

        if c >= 0:
            confs.append(c)
            if c < 50:
                low += 1

    mean_conf = (sum(confs) / len(confs)) / 100.0 if confs else 0.0
    low_rate = (low / toks) if toks else 0.0
    if fast:
        return {
            "mean_conf": mean_conf,
            "low_conf_rate": low_rate,
            "tokens": toks,
        }

    text = pytesseract.image_to_string(img, lang=lang, config=tess_config)
    total_chars = max(len(text), 1)
    alpha_ratio = sum(ch.isalpha() for ch in text) / total_chars
    printable = set(string.printable)
    printable_ratio = sum((ch in printable) for ch in text) / total_chars

    return {
        "mean_conf": float(mean_conf),
        "low_conf_rate": float(low_rate),
        "alpha_ratio": float(alpha_ratio),
        "printable_ratio": float(printable_ratio),
        "chars": int(len(text)),
        "tokens": int(toks),
        "text_preview": text[:400],
    }

def choose_best_preprocess_variant_for_ocr(
    *,
    candidates: list[dict],
    lang: str,
    tess_config: str,
    upscale: float,
    pass_mean: float,
    pass_low: float,
    fast: bool,
    topk: int = 6,
) -> dict:
    # Filter + cap
    cand = [c for c in (candidates or []) if c.get("clean_image")]
    cand = cand[:topk]

    rows = []
    for c in cand:
        p = Path(c["clean_image"])
        sc = score_ocr(p, lang=lang, tess_config=tess_config, upscale=upscale, fast=fast)
        rows.append({
            **c,
            "score": sc,
            "passes": (sc.get("mean_conf", 0.0) >= pass_mean) and (sc.get("low_conf_rate", 1.0) <= pass_low),
        })

    # Prefer passing results first, then your standardized score key
    rows_sorted = sorted(
        rows,
        key=lambda r: (1 if r.get("passes") else 0, *_score_key(r, fast=fast)),
        reverse=True
    )

    chosen = rows_sorted[0] if rows_sorted else None
    return {
        "leaderboard": rows_sorted,
        "chosen": chosen,
    }


def ocr_page(image_path: Path, lang: str = "eng", tess_config: str=DEFAULT_OCR_CONFIG, upscale: float=DEFAULT_OCR_UPSCALE) -> Dict[str, Any]:
    img = load_for_ocr(image_path, upscale)

    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT, config=tess_config)

    tokens = []
    confs = []
    n = len(data.get("text", []))
    for i in range(n):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        c_raw = data["conf"][i]
        try:
            c = float(c_raw)
        except Exception:
            c = -1.0
        if c >= 0:
            confs.append(c)
        tokens.append({
            "t": t,
            "c": (max(c, 0.0) / 100.0),
            "bbox": [int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])]
        })

    mean_conf = (sum(confs) / len(confs)) / 100.0 if confs else 0.0
    text = pytesseract.image_to_string(img, lang=lang, config=tess_config)
    return {"text": text, "tokens": tokens, "mean_conf": mean_conf}


def _score_key(row: dict, *, fast: bool = True, rank_map: dict | None = None) -> tuple:
    """
    Generic scorer for both:
      - preprocess rows: {name, clean_image, score}
      - OCR sweep rows: {tess_config_id, ... score}
    rank_map can be keyed by name OR tess_config_id.
    """
    s = row.get("score", {}) or {}

    rank = 10_000
    if rank_map is not None:
        k = row.get("tess_config_id") or row.get("name") or ""
        rank = rank_map.get(k, 10_000)

    # Prefer higher mean_conf, lower low_conf_rate, earlier rank, then more tokens.
    return (
        float(s.get("mean_conf", 0.0)),
        -float(s.get("low_conf_rate", 1.0)),
        -int(rank),
        int(s.get("tokens", 0)),
    )


def run_preprocess_experiment(image_path: Path, out_dir: Path, lang: str = "eng", upscale: float=DEFAULT_OCR_UPSCALE, fast:bool=False) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: orientation (signal for debugging / routing)
    rot, conf, osd = pp.detect_orientation(image_path)
    orientation = {"rotate_deg": int(rot), "conf": float(conf)}

    # Define your tool-bank variants (internal funcs)
    variants = [
        ("PreprocessBasic", pp.preprocess_basic),
        ("PreprocessNormalize", pp.preprocess_normalize),
        ("PreprocessDenoise", pp.preprocess_denoise),
        ("PreprocessBinarizeForOCR", pp.preprocess_binarize_for_ocr),
    ]

    results = []
    for name, fn in variants:
        clean_path = out_dir / f"{image_path.stem}__{name}.png"
        fn(image_path, clean_path)
        score = score_ocr(clean_path, lang=lang, upscale=upscale, fast=fast)
        results.append({
            "name": name,
            "clean_image": str(clean_path),
            "score": score,
        })

    best = sorted(results, key=_score_key, reverse=True)[0]

    payload = {
        "raw_image": str(image_path),
        "orientation": orientation,
        "candidates": results,
        "chosen_preprocess": best["name"],
        "final": {"clean_image": best["clean_image"], "score": best["score"]},
    }

    record = write_artifact_record_tool(payload=payload, out_dir=str(out_dir))

    return {
        "raw_image": str(image_path),
        "orientation": orientation,
        "leaderboard": sorted(results, key=_score_key, reverse=True),
        "chosen": best,
        "record": record,
    }

# Build a test harness
def _is_significant_improvement(best: dict, baseline: dict,
                                min_delta_mean: float = 0.01,
                                min_delta_low: float = 0.01) -> bool:
    '''Use the scoring rules to determine if the improvement is significant'''
    b = baseline["score"]
    w = best["score"]
    d_mean = w.get("mean_conf", 0.0) - b.get("mean_conf", 0.0)
    d_low  = b.get("low_conf_rate", 1.0) - w.get("low_conf_rate", 1.0)
    return (d_mean >= min_delta_mean) or (d_low >= min_delta_low)


def ocr_baseline_then_sweep_if_needed(
    clean_path: Path,
    lang: str,
    baseline_cfg: str,
    baseline_upscale: float,
    fail_min_mean: float = 0.90,
    fail_max_low: float = 0.04,
    sweep_cfgs: list[str] | None = None,
    sweep_upscales: list[float] | None = None,
    fast: bool = True,
) -> dict:
    """Baseline OCR; if it fails thresholds, sweep configs/upscales."""
    baseline_cfg = _norm_cfg(baseline_cfg)
    baseline = {
        "tess_config": baseline_cfg,
        "tess_config_id": _cfg_id(baseline_cfg),
        "upscale": float(baseline_upscale),
        "score": score_ocr(
            clean_path, lang=lang, tess_config=baseline_cfg,
            upscale=float(baseline_upscale), fast=fast
        ),
    }

    bscore = baseline["score"]
    baseline_passes = (bscore.get("mean_conf", 0.0) >= fail_min_mean) and (bscore.get("low_conf_rate", 1.0) <= fail_max_low)
    dbg_base = {
        "baseline_passes": baseline_passes,
        "fail_min_mean": fail_min_mean,
        "fail_max_low": fail_max_low,
        "baseline_cfg_id": baseline["tess_config_id"],
        "baseline_score": baseline["score"],
    }
    if baseline_passes:
        return {
            "baseline": baseline,
            "passes": True,
            "sweep_ran": False,
            "leaderboard": [],
            "chosen": baseline,
            "delta": {"mean_conf": 0.0, "low_conf_rate": 0.0},
            "debug": dbg_base,
        }

    # Ensure baseline is included in sweep candidates for honest comparison
    sweep_cfgs = sweep_cfgs or []
    sweep_cfgs = [baseline_cfg] + [ _norm_cfg(c) for c in sweep_cfgs if _norm_cfg(c) != baseline_cfg ]

    sweep_upscales = sweep_upscales or []
    sweep_upscales = [float(baseline_upscale)] + [ float(u) for u in sweep_upscales if float(u) != float(baseline_upscale) ]

    rows = []
    for cfg in sweep_cfgs:
        for u in sweep_upscales:
            sc = score_ocr(clean_path, lang=lang, tess_config=cfg, upscale=float(u), fast=fast)
            rows.append({
                "tess_config": cfg,
                "tess_config_id": _cfg_id(cfg),
                "upscale": float(u),
                "score": sc,
            })

    rows_sorted = sorted(rows, key=_score_key, reverse=True)
    best = rows_sorted[0] if rows_sorted else baseline

    wscore = best["score"]
    best_passes = (wscore.get("mean_conf", 0.0) >= fail_min_mean) and (wscore.get("low_conf_rate", 1.0) <= fail_max_low)

    # Use the significance guard only when the sweep *didn't* achieve a pass.
    # If sweep achieves a pass, take it regardless.
    if best_passes:
        chosen = best
    else:
        chosen = best if _is_significant_improvement(best, baseline) else baseline

    cscore = chosen["score"]
    chosen_passes = (cscore.get("mean_conf", 0.0) >= fail_min_mean) and (cscore.get("low_conf_rate", 1.0) <= fail_max_low)
    dbg_sweep = {
        **dbg_base,
        "n_candidates": len(rows_sorted),
        "cfg_ids": sorted({r["tess_config_id"] for r in rows_sorted}),
        "top": [
            {
                "cfg": r["tess_config"],
                "u": r["upscale"],
                "mean": r["score"].get("mean_conf"),
                "low": r["score"].get("low_conf_rate"),
            }
            for r in rows_sorted
        ],
    }
    return {
        "baseline": baseline,
        "passes": chosen_passes,
        "sweep_ran": True,
        "leaderboard": rows_sorted[:10],
        "chosen": chosen,
        "delta": {
            "mean_conf": cscore.get("mean_conf", 0.0) - bscore.get("mean_conf", 0.0),
            "low_conf_rate": bscore.get("low_conf_rate", 1.0) - cscore.get("low_conf_rate", 1.0),
        },
        "switched": chosen is not baseline,
        "best_passes": best_passes,
        "significant": _is_significant_improvement(best, baseline),
    }

def run_ocr_sweep(
    image_paths: List[Path],
    out_dir: Path,
    lang: str,
    configs: List[str],
    upscales: List[float],
    preprocessed: bool=False, # check whether the images are already preprocessed (don't want to redo preprocessing)
    preprocess_fn: Callable[[Path, Path], Path]=pp.preprocess_basic,
    fast: bool=True #for a sweep, default to 'fast' so it does fewer tesseract calls
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_dir = out_dir / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    # Preprocess once per page, then sweep OCR knobs on the clean result
    per_page = []
    for p in image_paths:
        clean_path = clean_dir / f"{p.stem}__clean.png"
        if preprocessed:
            if "raw_pages" in str(p): # make sure we think it's preprocessed, but we're reading from a raw page
                raise ValueError("preprocessed=True but path looks like a raw page")
            # p is already a "clean" image; just copy it into sweep_dir for provenance
            shutil.copy2(p, clean_path)
        else:
            preprocess_fn(p, clean_path)

        decision = ocr_baseline_then_sweep_if_needed(
            clean_path=clean_path,
            lang=lang,
            baseline_cfg=DEFAULT_OCR_CONFIG,
            baseline_upscale=1.0,
            sweep_cfgs=configs,          # your existing list
            sweep_upscales=upscales,     # your existing list
            fail_min_mean=0.90,
            fail_max_low=0.04,
            fast=fast,
        )
        lb = decision.get("leaderboard")
        if not lb:
            # No sweep leaderboard; treat baseline as the only candidate
            lb = [decision["baseline"]]

        per_page.append({
            "raw_image": str(p),
            "clean_image": str(clean_path),
            "chosen": decision["chosen"],
            "debug": decision.get("debug"),
            "ocr_policy": {
                "passes": decision["passes"],
                "sweep_ran": decision["sweep_ran"],
                "baseline": decision["baseline"],
                "chosen": decision["chosen"],
                "delta": decision["delta"],
            },
            "leaderboard": lb, 
        })    # Aggregate key: average mean_conf, then avg low_conf_rate
    agg: Dict[tuple, Dict[str, Any]] = {}
    for page in per_page:
        r = page["chosen"]
        k = (r["tess_config_id"], r["upscale"])
        a = agg.setdefault(k, {
            "tess_config": r["tess_config"],
            "tess_config_id": r["tess_config_id"],
            "upscale": r["upscale"],
            "mean_conf_sum": 0.0,
            "low_conf_sum": 0.0,
            "alpha_sum": 0.0,
            "n": 0,
        })
        s = r["score"]
        a["mean_conf_sum"] += s.get("mean_conf", 0.0)
        a["low_conf_sum"] += s.get("low_conf_rate", 1.0)
        a["alpha_sum"] += s.get("alpha_ratio", 0.0)
        a["n"] += 1

    agg_rows = []
    for _, a in agg.items():
        n = max(a["n"], 1)
        agg_rows.append({
            "tess_config": a["tess_config"],
            "tess_config_id": a["tess_config_id"],
            "upscale": a["upscale"],
            "avg_mean_conf": a["mean_conf_sum"] / n,
            "avg_low_conf_rate": a["low_conf_sum"] / n,
            "avg_alpha_ratio": a["alpha_sum"] / n,
            "n_pages": a["n"],
        })
    if fast:
        agg_rows = [{k:v for k,v in d.items() if k!='avg_alpha_ratio'} for d in agg_rows ]
    def agg_key(r):
        if fast:
            return (r["avg_mean_conf"], -r["avg_low_conf_rate"])
        else:
            return (r["avg_mean_conf"], -r["avg_low_conf_rate"], r["avg_alpha_ratio"])
    
    agg_rows = sorted(agg_rows, key=agg_key, reverse=True)
    best_overall = agg_rows[0] if agg_rows else None

    run_id = dt.now().strftime("%Y%m%dT%H%M%SZ")
    record = {
        "run_id": run_id,
        "lang": lang,
        "pages": [str(p) for p in image_paths],
        "configs": [{"id": _cfg_id(c), "config": c} for c in configs],
        "upscales": upscales,
        "best_overall": best_overall,
        "per_page": per_page,
        "aggregate": agg_rows[:20],
    }

    record_path = out_dir / f"ocr_sweep_{run_id}.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Return compact summary for MCP
    return {
        "run_id": run_id,
        "record_path": str(record_path),
        "best_overall": best_overall,
        "per_page_best": [
            {
                "raw_image": p["raw_image"],
                "chosen": {
                    "tess_config": p["chosen"].get("tess_config"),
                    "tess_config_id": p["chosen"]["tess_config_id"],
                    "upscale": p["chosen"]["upscale"],
                    "score": p["chosen"]["score"],
                },
                "passes": p["ocr_policy"]["passes"],
                "sweep_ran": p["ocr_policy"]["sweep_ran"],
                "baseline": p["ocr_policy"]["baseline"],
                "delta": p["ocr_policy"]["delta"],
                "debug": p.get("debug"),      
            }
            for p in per_page
        ],
    }




# -------------------------
# MCP-friendly wrappers
# -------------------------

def write_artifact_record_tool(payload: Dict[str, Any], out_dir: str) -> dict:
    """
    Writes a run record JSON. Payload is JSON-friendly.
    Good for: experiment results, chaining traces, "best preprocessor" decisions.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # stable-ish filename
    page_index = payload.get("page_index")
    stamp = dt.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if page_index is None:
        fname = f"run_{stamp}_artifact_record.json"
    else:
        fname = f"page_{int(page_index):02d}_{stamp}_artifact_record.json"

    record_path = out_dir / fname

    record = {
        "written_utc": stamp,
        "payload": _jsonify(payload),
    }

    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {"record_path": str(record_path), "written_utc": stamp}

def preprocess_hough_tool(image_path: str, out_path: str) -> dict:
    image_path = Path(image_path)
    out_path = Path(out_path)

    arr = pp._load_bgr(image_path)

    rot, rot_conf, _ = pp.detect_orientation(image_path)
    arr = pp._rotate_upright(arr, rot)

    arr, deskew_deg = pp.deskew_hough(arr)

    pp._save_bgr(arr, out_path)

    return {
        "clean_image": str(out_path),
        "orientation": {"rotate_deg": int(rot), "conf": float(rot_conf)},
        "deskew": {"angle_deg": float(deskew_deg)},
    }

def preprocess_tool(image_path: str, out_path: str, method: str = "basic") -> dict:
    fn = _PREPROCESS_MAP.get(method.lower())
    if fn is None:
        raise ValueError(f"Unknown preprocess method: {method}. Expected one of {sorted(_PREPROCESS_MAP)}")

    # only basic returns meta in your current setup; keep that detail here
    if method.lower() == "basic":
        p, meta = fn(Path(image_path), Path(out_path), return_meta=True)
        return {"clean_image": str(p), "method": method, "meta": meta}

    p = fn(Path(image_path), Path(out_path))
    return {"clean_image": str(p), "method": method}


def score_ocr_tool(image_path: str, lang: str = "eng", tess_config = DEFAULT_OCR_CONFIG, upscale=DEFAULT_OCR_UPSCALE, fast=False) -> dict:
    return score_ocr(Path(image_path), lang=lang, config=tess_config, upscale=upscale, fast=fast)


def preprocess_page_tool(image_path: str, out_dir: str, lang: str = "eng", upscale: float = 1.0, fast: bool = True) -> dict:
    # Equivalent-ish to old behavior: preprocess selection only, no OCR sweep.
    run_id = dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    policy = dict(DEFAULT_ESCALATION_POLICY)
    policy["default_ocr_upscale"] = float(upscale)
    return process_page_tool(
        image_path=image_path,
        out_dir=out_dir,
        lang=lang,
        policy=policy,
        fast=fast,
        enable_preprocess_rescue=False,  # old PreprocessPage didn’t do rescue-after-selection
        enable_ocr_sweep=False,
    )

def preprocess_with_ocr_escalation_tool(image_path: str, out_dir: str, lang: str="eng", fast: bool=False) -> dict:
    return process_page_tool(
        image_path=image_path,
        out_dir=out_dir,
        lang=lang,
        policy=DEFAULT_ESCALATION_POLICY,
        fast=fast,
        enable_preprocess_rescue=True,
        enable_ocr_sweep=True,
    )

def run_ocr_sweep_tool(
    image_paths: List[str],
    out_dir: str,
    lang: str = "eng",
    preprocess: str = "basic",
    configs: List[str] = None,
    upscales: List[float] = None,
    preprocessed: bool = False,
    fast: bool = True
) -> dict:
    configs = configs or DEFAULT_SWEEP_CONFIGS
    upscales = upscales or DEFAULT_SWEEP_UPSCALES

    preprocess_fn = _PREPROCESS_MAP.get(preprocess.lower(), pp.preprocess_basic)

    return run_ocr_sweep(
        image_paths=[Path(p) for p in image_paths],
        out_dir=Path(out_dir),
        preprocess_fn=preprocess_fn,
        lang=lang,
        configs=configs,
        upscales=upscales,
        preprocessed=preprocessed,
        fast=fast
    )

async def process_directory_tool(
    in_dir: str,
    out_dir: str,
    *,
    lang: str = "eng",
    fast: bool = True,
    recursive: bool = False,
    enable_preprocess_rescue: bool = True,
    enable_ocr_sweep: bool = True,
    stop_on_error: bool = False,
    max_pages: Optional[int] = None,
    ctx:Context
) -> dict:
    tool = "ProcessDirectory"
    run_id = dt.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    inputs = {
        "in_dir": str(in_dir),
        "out_dir": str(out_dir),
        "lang": lang,
        "fast": bool(fast),
        "recursive": bool(recursive),
        "enable_preprocess_rescue": bool(enable_preprocess_rescue),
        "enable_ocr_sweep": bool(enable_ocr_sweep),
        "stop_on_error": bool(stop_on_error),
        "max_pages": max_pages,
    }

    try:
        in_p = Path(_strip_quotes(in_dir)).expanduser()
        out_p = Path(_strip_quotes(out_dir)).expanduser()
        out_p.mkdir(parents=True, exist_ok=True)

        # Stable output folders
        clean_dir = out_p / "clean"
        ocr_dir = out_p / "ocr"
        art_dir = out_p / "page_artifacts"
        clean_dir.mkdir(parents=True, exist_ok=True)
        ocr_dir.mkdir(parents=True, exist_ok=True)
        art_dir.mkdir(parents=True, exist_ok=True)

        images = _list_images(in_p, recursive=recursive)
        if max_pages is not None:
            images = images[: int(max_pages)]

        per_page: List[dict] = []
        failures: List[dict] = []

        N = 1
        total=len(images)
        for i, img in enumerate(images):
            page_id = _page_id_from_path(img)

            try:
                # 1) Run your page pipeline (preprocess selection + rescue + OCR sweep)
                await ctx.report_progress(progress=i + 0.001, total=total, message=f"Starting {page_id} ({i+1}/{total})")
                r = process_page_tool(
                    image_path=str(img),
                    out_dir=str(out_p),
                    lang=lang,
                    fast=fast,
                    enable_preprocess_rescue=enable_preprocess_rescue,
                    enable_ocr_sweep=enable_ocr_sweep,
                    preprocess_rescue_topk=None,
                )

                if not r.get("ok", False):
                    failures.append({"page_id": page_id, "image": str(img), "error": r.get("error"),"debug": r.get("debug"),})
                    if stop_on_error:
                        break
                    continue

                outputs = r["outputs"]

                # 2) Stable clean image
                chosen_clean = Path(outputs["clean_image"])
                stable_clean = clean_dir / f"{page_id}.png"
                if chosen_clean.exists():
                    shutil.copy2(chosen_clean, stable_clean)

                # 3) Stable page artifact JSON:
                #    copy the timestamped record created by ProcessPage into a stable filename
                record_art = next((a for a in (r.get("artifacts") or []) if a.get("kind") == "record"), None)
                stable_artifact = art_dir / f"{page_id}_artifact.json"
                if record_art and record_art.get("path"):
                    shutil.copy2(record_art["path"], stable_artifact)
                else:
                    # fallback: write a minimal artifact if record missing
                    with stable_artifact.open("w", encoding="utf-8") as f:
                        json.dump({"run_id": run_id, "page_id": page_id, "outputs": outputs}, f, indent=2)

                # 4) OCR text: prefer text produced by ProcessPage (no re-OCR)
                final = outputs["final_ocr"]
                stable_txt = ocr_dir / f"{page_id}_ocr.txt"

                if isinstance(final, dict) and final.get("text") is not None:
                    stable_txt.write_text(final["text"], encoding="utf-8")
                elif isinstance(final, dict) and final.get("txt_path"):
                    shutil.copy2(final["txt_path"], stable_txt)
                else:
                    # fallback only if ProcessPage didn't return text
                    text_r = ocr_page(
                        stable_clean,
                        lang=lang,
                        tess_config=final["tess_config"],
                        upscale=float(final["upscale"]),
                    )
                    stable_txt.write_text(text_r.get("text", ""), encoding="utf-8")

                # 5) Collect summary row (keep it compact)
                per_page.append({
                    "page_id": page_id,
                    "raw_image": outputs["raw_image"],
                    "clean_image": str(stable_clean),
                    "artifact": str(stable_artifact),
                    "ocr_txt": str(stable_txt),
                    "passes": bool(final.get("passes", False)),
                    "final_mean_conf": float(final["score"].get("mean_conf", 0.0)),
                    "final_low_conf_rate": float(final["score"].get("low_conf_rate", 1.0)),
                    "chosen_preprocess": outputs.get("preprocess_rescue", {}).get("chosen_variant"),
                    "sweep_used": bool(outputs.get("sweep_used", False)),
                })

            except Exception as e:
                failures.append({
                    "page_id": page_id,
                    "image": str(img),
                    "error": {
                        "code": "exception",
                        "message": str(e),
                        "traceback": traceback.format_exc(),
                    },})
                if stop_on_error:
                    break
            await ctx.report_progress(progress=i, total=total, message=f"Processed {i+1}/{total}")
        # Directory-level manifest
        manifest = {
            "pipeline": tool,
            "run_id": run_id,
            "inputs": inputs,
            "n_images": len(images),
            "n_ok": len(per_page),
            "n_failed": len(failures),
            "pages": per_page,
            "failures": failures,
        }
        manifest_path = out_p / f"process_directory_{run_id}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        outputs = {
            "run_id": run_id,
            "in_dir": str(in_p),
            "out_dir": str(out_p),
            "manifest_path": str(manifest_path),
            "n_images": len(images),
            "n_ok": len(per_page),
            "n_failed": len(failures),
            "pages_top5": per_page[:5],
            "failures_top5": failures[:5],
        }

        artifacts = [{"kind": "manifest", "path": str(manifest_path)}]

        metrics = {
            "ok_rate": (len(per_page) / len(images)) if images else 0.0,
        }

        return ok_result(run_id=run_id, tool=tool, inputs=inputs, outputs=outputs, artifacts=artifacts, metrics=metrics)

    except Exception as e:
        return err_result(tool=tool, code="exception", message=str(e), inputs=inputs, 
                          debug={"traceback": traceback.format_exc()},)

# -------------------------
# MCP server
# -------------------------

def build_mcp_server():

    mcp = FastMCP("Archival Restore", json_response=True)

    @mcp.tool(name='atomic.detect_orientation',
              description="Determine correct orientation of image -- 0, 90, 180, 270 degrees -- and confidence.")
    def detect_orientation_tool(image_path: str) -> Dict[str, Any]:
        rot, conf, osd = pp.detect_orientation(Path(image_path))
        return {"rotate_deg": int(rot), "conf": float(conf), "osd": osd}

    @mcp.tool(name='atomic.ocr_page',
              description="Perform OCR on image and convert to text. Return text & mean confidence. ")
    def ocr_page_tool(image_path: str, lang: str = "eng") -> dict:
        return ocr_page(Path(image_path), lang=lang)
    
    @mcp.tool(name='atomic.score_ocr',
              description="Compute OCR metrics on image.")
    def ScoreOCR(image_path: str, lang: str = "eng", upscale: float=DEFAULT_OCR_UPSCALE, fast: bool=False) -> dict:
        return score_ocr_tool(image_path, lang, upscale=upscale, fast=fast)
    
    @mcp.tool(name='page.preprocess',
              description= """Generate and rank preprocess variants for one page, select the best clean image using OCR scoring. 
                Return chosen clean image + leaderboard + decision flags. No OCR config sweep. No text output.""")
    def Preprocess(
        image_path: str,
        out_path: str,
        steps: list[str] | None = None,
        upscale: float = DEFAULT_OCR_UPSCALE,
        keep_intermediates: bool = True,
    ) -> dict:
        steps = steps or ["basic"]
        steps = [_norm_step(x) for x in steps]
        if not steps:
            raise ValueError("steps must be non-empty")

        in_path = _as_path(image_path)
        final_out = _as_path(out_path)
        final_out.parent.mkdir(parents=True, exist_ok=True)

        trace = []
        cur_in = str(in_path)

        # If multiple steps, write intermediates alongside final_out
        # Example: foo__01_basic.png, foo__02_denoise.png
        stem = final_out.stem
        parent = final_out.parent

        for i, step in enumerate(steps, start=1):
            fn = _PREPROCESS_STEP_FNS.get(step)
            if fn is None:
                raise ValueError(f"Unknown preprocess step: {step}. Supported: {sorted(_PREPROCESS_STEP_FNS.keys())}")

            is_last = (i == len(steps))
            step_out = final_out if is_last else (parent / f"{stem}__{i:02d}_{step}.png")

            meta = fn(cur_in, str(step_out), float(upscale))  # call your existing tool wrapper
            trace.append({
                "step": step,
                "in": cur_in,
                "out": str(step_out),
                "meta": meta,
            })

            cur_in = str(step_out)

        # Optional cleanup
        if not keep_intermediates and len(trace) > 1:
            for t in trace[:-1]:
                try:
                    Path(t["out"]).unlink(missing_ok=True)
                except Exception:
                    pass

        # `final` is EXACTLY the last step tool's return (good for wrapper compatibility)
        final_meta = trace[-1]["meta"] if trace else {}

        return {
            "image_path": str(in_path),
            "out_path": str(final_out),
            "steps": steps,
            "upscale": float(upscale),
            "trace": trace,
            "final": final_meta,
        }

    @mcp.tool(name='page.process_page', 
              description="""End-to-end per-page processing: choose preprocess variant, run OCR baseline, 
              optional rescue and OCR sweep, then emit final clean image and OCR text artifacts with provenance.""")
    def ProcessPage(
        image_path: str,
        out_dir: str,
        lang: str = "eng",
        fast: bool = False,
        enable_preprocess_rescue: bool = True,
        enable_ocr_sweep: bool = True,
        preprocess_rescue_topk: int | None = None,
    ) -> dict:
        return process_page_tool(
            image_path=image_path,
            out_dir=out_dir,
            lang=lang,
            fast=fast,
            enable_preprocess_rescue=enable_preprocess_rescue,
            enable_ocr_sweep=enable_ocr_sweep,
            preprocess_rescue_topk=preprocess_rescue_topk,
        )

    @mcp.tool(name='orchestrate.run_ocr_sweep',
              description='run several images through different preprocessing steps to find the best one.')
    def RunOCRSweep(
        image_paths: list,
        out_dir: str,
        lang: str = "eng",
        preprocess: str = "basic",
        configs: list = None,
        upscales: list = None,
        fast: bool = True, #Since it's a sweep, assume it's done fast (fewer tesseract calls)
    ) -> dict:
        out_dir = Path(_strip_quotes(out_dir))
        image_paths = [Path(_strip_quotes(image_path)) for image_path in image_paths]
        return run_ocr_sweep_tool(image_paths, out_dir, lang, preprocess, configs, upscales, fast=fast)
    

    @mcp.tool(name="orchestration.ProcessDirectory",
              description="Performs full processing of directory of images and return text files.")
    async def ProcessDirectory(
        in_dir: str,
        out_dir: str,
        *,
        lang: str = "eng",
        fast: bool = True,
        recursive: bool = False,
        enable_preprocess_rescue: bool = True,
        enable_ocr_sweep: bool = True,
        stop_on_error: bool = False,
        max_pages: int | None = None,
        ctx:Context,
    ) -> dict:
        return await process_directory_tool(
            in_dir=in_dir,
            out_dir=out_dir,
            lang=lang,
            fast=fast,
            recursive=recursive,
            enable_preprocess_rescue=enable_preprocess_rescue,
            enable_ocr_sweep=enable_ocr_sweep,
            stop_on_error=stop_on_error,
            max_pages=max_pages,
            ctx=ctx
        )

    return mcp

if __name__ == "__main__":
    build_mcp_server().run(transport="streamable-http")
