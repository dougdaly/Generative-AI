# skills/image_gen.py
from __future__ import annotations
import os, re, torch
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from diffusers import StableDiffusionXLPipeline
from diffusers.schedulers.scheduling_dpmsolver_multistep import DPMSolverMultistepScheduler

# ---------- device helpers ----------
def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    # Apple M-series
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

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

def generate_person_images(
    names_and_years: Iterable[Tuple[str, Optional[str]]],
    outdir: str,
    *,
    steps: int = 25,
    guidance_scale: float = 6.5,
    size: Tuple[int, int] = (512, 768),
    seed: Optional[int] = 1337,       # None for stochastic
    skip_existing: bool = True,
) -> List[str]:
    """
    Generic generator: (name, era_year) -> portrait PNG paths.
    """
    os.makedirs(outdir, exist_ok=True)
    pipe, device = get_sdxl()
    gen = None
    if seed is not None:
        gen = torch.Generator(device=device).manual_seed(seed)

    W, H = size
    from agentic_multimodal.skills.image_prompts import person_prompt  # local import to avoid cycles

    paths: List[str] = []
    for i, (name, year) in enumerate(names_and_years, 1):
        prompt, neg = person_prompt(name, year)
        fname = f"{i:03d}_{_safe_filename(name)}.png"
        fpath = os.path.join(outdir, fname)
        paths.append(fpath)

        if skip_existing and os.path.exists(fpath):
            continue

        image = pipe(
            prompt=prompt,
            negative_prompt=neg,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            width=W, height=H,
            generator=gen,
        ).images[0]
        image.save(fpath)
    return paths
