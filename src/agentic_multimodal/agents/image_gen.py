from pathlib import Path
import torch, os, sys

PROJECT_ROOT = Path(__file__).resolve().parents[4] if "__file__" in globals() else Path.cwd().resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))  # insert at front so it wins precedence
from assets.support import get_device
from diffusers import StableDiffusionXLPipeline
#from schemas import PresidentList

# Set up diffusion model for image generation
def get_sdxl(device=None, model_id="stabilityai/stable-diffusion-xl-base-1.0"):
    if device is None:
        device = get_device()
    dtype = torch.float16 if device.type=="cuda" else torch.float32
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        add_watermark=False,             # avoid stray watermark/text tokens
        use_safetensors=True,
    )

    # Use a DPMSolver++ w/ Karras sigmas (very stable for portraits)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        use_karras_sigmas=True,
        algorithm_type="dpmsolver++",
        solver_order=2,
    )

    pipe.to(device)

    # Memory helpers
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    if device == "cuda":
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass

    return pipe, device


def generate_portrait(pipe, subject, seed=42):
    pos = (
        f"{subject}, official portrait, single subject, solo, one person, centered, "
        "bust-length headshot, looking at camera, studio backdrop, sharp focus, high detail, cartoon style"
    )
    neg = (
        "group, crowd, second person, extra face, extra head, duplicate, twins, "
        "reflection, mirror, collage, background portrait, statues, disembodied face, "
        "text, watermark, logo, hands"
    )

    g = torch.Generator(device=pipe.device).manual_seed(seed)

    image = pipe(
        prompt=pos,
        negative_prompt=neg,
        num_inference_steps=32,      # 30–36 is the sweet spot here
        guidance_scale=6.0,          # try 5.5–6.5; avoid >7 for portraits
        guidance_rescale=0.7,        # tames CFG artifacts (incl. duplicates)
        width=896, height=1152,      # portrait AR reduces multi-subject drift
        generator=g,
    ).images[0]
    return image


def ensure_pipe(device):
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", 
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )
    pipe.to(device)
    pipe.enable_attention_slicing()
    return pipe

def image_node(state):
    plist = PresidentList(**state["research"])
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    pipe = ensure_pipe(device)
    out = {}
    os.makedirs("out/presidents", exist_ok=True)
    for i, p in enumerate(plist.people, 1):
        prompt = p.image_prompt + ", simple background"
        img = pipe(prompt=prompt, num_inference_steps=25, guidance_scale=6.5, height=768, width=512).images[0]
        path = f"out/presidents/{i:02d}_{p.name.replace(' ','_')}.png"
        img.save(path)
        out[str(i)] = path
    return {**state, "images": out}
