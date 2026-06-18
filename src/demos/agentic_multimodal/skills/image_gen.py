# skills/image_gen.py
from __future__ import annotations
import os, re, torch
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from diffusers import StableDiffusionXLPipeline
from diffusers.schedulers.scheduling_dpmsolver_multistep import DPMSolverMultistepScheduler
from diffusers import StableDiffusionXLImg2ImgPipeline
from PIL import Image
import requests, io
from functools import lru_cache

from diffusers import StableDiffusionXLPipeline
from diffusers.schedulers import DPMSolverMultistepScheduler

from src.support import get_device


def ensure_sdxl_img2img(device):
    device = torch.device(device)
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16 if device.type == "cuda" else torch.float32,
        use_safetensors=True,
    ).to(device)
    pipe.enable_attention_slicing()
    pipe.enable_vae_tiling()
    return pipe

def stylize_from_reference(ref_url, *, out_w=512, out_h=768, seed=1337,
                           strength=0.35, cfg=4.5, style_prompt="clean vector-cartoon, flat shading"):
    # download
    r = requests.get(ref_url, timeout=15)
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    # smart center-crop to portrait
    w,h = im.size
    crop = min(w, int(h*0.85))
    left = (w - crop)//2; top = max(0, (h - int(crop*1.3))//2)
    im = im.crop((left, top, left+crop, top+int(crop*1.3))).resize((out_w, out_h), Image.LANCZOS)

    pipe = ensure_sdxl_img2img(get_device())
    g = torch.Generator(device=pipe.device).manual_seed(seed)
    out = pipe(
        prompt=style_prompt,
        image=im,
        strength=strength,
        guidance_scale=cfg,
        num_inference_steps=28,
        generator=g,
    ).images[0]
    return out

_DEFAULT_SDXL = "stabilityai/stable-diffusion-xl-base-1.0"

def _coerce_model_id(model_id):
    # precedence: explicit arg → env → default
    mid = (model_id or os.getenv("SDXL_MODEL_ID") or _DEFAULT_SDXL)
    # allow Path objects
    if isinstance(mid, Path): mid = str(mid)
    # final guard
    if not isinstance(mid, str) or not mid.strip():
        mid = _DEFAULT_SDXL
    return mid

def ensure_sdxl(model_id=None, device_str=None):
    model_id = _coerce_model_id(model_id)
    device   = torch.device(device_str) if device_str else get_device()
    dtype    = torch.float16 if device.type == "cuda" else torch.float32

    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        add_watermark=False,
        use_safetensors=True,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        use_karras_sigmas=True,
        algorithm_type="dpmsolver++",
        solver_order=2,
    )
    pipe.to(device)
    # memory helpers
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    if device.type == "cuda":
        try: pipe.enable_xformers_memory_efficient_attention()
        except Exception: pass
    return pipe, device

# ---------- font resolver (reused by poster renderer) ----------
def resolve_font(preferred: Optional[str] = None) -> str:
    if preferred and os.path.isfile(preferred):
        return preferred
    candidates = [
        "assets/fonts/Inter-SemiBold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # fallback to PIL-bundled DejaVu
    from PIL import ImageFont
    try:
        ImageFont.truetype("DejaVuSans.ttf", size=10)
        return "DejaVuSans.ttf"
    except Exception:
        raise FileNotFoundError(
            "No usable TTF font found. Put a .ttf in assets/fonts/ and pass its path."
        )

# ---------- SDXL pipeline (cached) ----------
_PIPE: Optional[StableDiffusionXLPipeline] = None
_DEVICE: Optional[torch.device] = None

def get_sdxl(
    device: Optional[torch.device] = None,
    model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
) -> Tuple[StableDiffusionXLPipeline, torch.device]:
    """
    Load and cache an SDXL pipeline tuned for portrait gen.
    """
    global _PIPE, _DEVICE
    if _PIPE is not None:
        return _PIPE, _DEVICE  # type: ignore

    device = device or get_device()
    dtype = torch.float16 if device.type == "cuda" else torch.float32

    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        add_watermark=False,
        use_safetensors=True,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        use_karras_sigmas=True,
        algorithm_type="dpmsolver++",
        solver_order=2,
    )
    pipe.to(device)

    # Memory/perf tweaks
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    if device.type == "cuda":
        # ok if this fails quietly
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass

    _PIPE, _DEVICE = pipe, device
    return pipe, device

# ---------- basic portrait generator ----------
def _safe_filename(s: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", s).strip("_")

def _norm(item):
    # tuple ("Name", "YYYY" or None)
    if isinstance(item, (tuple, list)):
        n, y = (item + (None,))[:2]
        return {"name": n, "year": y, "ref_url": None, "seed": None}
    # dict form
    d = dict(item)
    return {
        "name": d.get("name"),
        "year": d.get("year"),
        "ref_url": d.get("ref_url"),
        "seed": d.get("seed"),
    }

def _person_prompt(name, year):
    era = f", circa {year}" if year else ""
    return (f"{name}{era}, official portrait, single subject, centered, "
            "bust-length, clean background, sharp focus, vector-cartoon style")

def _download_and_portrait_crop(url, size):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        w, h = im.size
        # center portrait crop; tolerant for landscape
        target_ar = size[0] / size[1]
        # simple smart-crop: keep center, bias to headroom
        crop_w = min(w, int(h * target_ar * 0.95))
        crop_h = min(h, int(w / target_ar * 1.05))
        left = max(0, (w - crop_w)//2)
        top  = max(0, (h - crop_h)//3)   # bias up to include head
        im = im.crop((left, top, left+crop_w, top+crop_h)).resize(size, Image.LANCZOS)
        return im
    except Exception:
        return None


def generate_person_images(
    pairs,                      # [(name, year)] OR [{"name":..., "year":..., "ref_url":...}, ...]
    outdir,
    steps=28,
    cfg=6.0,
    size=(512, 768),
    seed=1337,
    style_prompt="clean vector-cartoon, flat shading, studio backdrop",
    ref_strength=0.35,          # img2img strength (0.25–0.40 good)
    ref_cfg=4.5,                # img2img CFG (3.5–5.0 good)
    skip_existing=True,
    device=None,
):
    """
    If an item has 'ref_url', use SDXL img2img to stylize the reference.
    Otherwise fall back to text2img with (name, year).
    Returns: list[str] of paths aligned with input order.
    """
    os.makedirs(outdir, exist_ok=True)
    device_str = str(device) if device is not None else None
    pipe_txt, dev = ensure_sdxl(device_str=device_str)
    pipe_ref  = ensure_sdxl_img2img(dev)                # add this helper (from prior message)
    gen = None
    if seed is not None:
        gen = torch.Generator(device=device).manual_seed(seed)

    W, H = size

    paths: List[str] = []
    for i, raw in enumerate(pairs, 1):
        p = _norm(raw)
        assert p["name"], f"missing name at index {i}"

        # filename
        base = f"{i:03d}_{p['name']}".replace("/", "_")
        out_path = os.path.join(outdir, f"{base}.png")
        if skip_existing and os.path.exists(out_path):
            paths.append(out_path); continue

        g = torch.Generator(device=dev).manual_seed(p["seed"] or (seed + i))

        if p["ref_url"]:
            # --- img2img path ---
            im = _download_and_portrait_crop(p["ref_url"], size)
            if im is None:
                # fallback to text prompt if download failed
                prompt = _person_prompt(p["name"], p["year"])
                img = pipe_txt(prompt=prompt, num_inference_steps=steps,
                            guidance_scale=cfg, generator=g, width=size[0], height=size[1]).images[0]
            else:
                img = pipe_ref(
                    prompt=style_prompt,
                    image=im,
                    strength=ref_strength,
                    guidance_scale=ref_cfg,
                    num_inference_steps=min(36, steps+2),
                    generator=g,
                ).images[0]
        else:
            # --- text2img path ---
            prompt = _person_prompt(p["name"], p["year"])
            img = pipe_txt(prompt=prompt, num_inference_steps=steps,
                        guidance_scale=cfg, generator=g, width=size[0], height=size[1]).images[0]

        img.save(out_path)
        paths.append(out_path)

    return paths

def generate_prompt_images(
    picks,                      # [{"name":..., "prompt":..., "ref_url":..., "seed":...}, ...]
    outdir,
    steps=28,
    cfg=6.0,
    size=(512, 768),
    seed=1337,
    style_prompt="clean vector-cartoon, flat shading, studio backdrop",
    ref_strength=0.35,
    ref_cfg=4.5,
    negative_prompt="text, letters, watermark, logo, caption, typography",
    skip_existing=True,
    device=None,
):
    """
    Generic SDXL generator.
    - If pick has ref_url: img2img stylize (uses style_prompt)
    - Else: text2img using pick["prompt"]

    Returns list[str] paths aligned with input order.
    """
    os.makedirs(outdir, exist_ok=True)

    # NOTE: do not pass `device` positionally here.
    # ensure_sdxl signature is (model_id=None, device_str=None)
    device_str = str(device) if device is not None else None
    pipe_txt, dev = ensure_sdxl(device_str=device_str)
    pipe_ref = ensure_sdxl_img2img(dev)

    paths: List[str] = []
    for i, raw in enumerate(picks, 1):
        p = dict(raw)
        name = p.get("name")
        prompt = p.get("prompt")
        ref_url = p.get("ref_url")
        item_seed = p.get("seed")

        assert name, f"missing name at index {i}"
        assert prompt or ref_url, f"missing prompt/ref_url for {name!r} at index {i}"

        base = f"{i:03d}_{name}".replace("/", "_")
        out_path = os.path.join(outdir, f"{base}.png")

        if skip_existing and os.path.exists(out_path):
            paths.append(out_path)
            continue

        g = torch.Generator(device=dev).manual_seed(item_seed or (seed + i))

        if ref_url:
            im = _download_and_portrait_crop(ref_url, size)
            if im is None:
                # fallback: text2img using prompt
                img = pipe_txt(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=steps,
                    guidance_scale=cfg,
                    generator=g,
                    width=size[0],
                    height=size[1],
                ).images[0]
            else:
                img = pipe_ref(
                    prompt=style_prompt,
                    negative_prompt=negative_prompt,
                    image=im,
                    strength=ref_strength,
                    guidance_scale=ref_cfg,
                    num_inference_steps=min(36, steps + 2),
                    generator=g,
                ).images[0]
        else:
            img = pipe_txt(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                guidance_scale=cfg,
                generator=g,
                width=size[0],
                height=size[1],
            ).images[0]

        img.save(out_path)
        paths.append(out_path)

    return paths

def batch_generate_subject_images(picks, *, outdir="cache/group_subjects", **kw) -> list[str]:
    """
    Convenience wrapper used by group_poster_flow.
    """
    return generate_prompt_images(picks, outdir=outdir, **kw)
