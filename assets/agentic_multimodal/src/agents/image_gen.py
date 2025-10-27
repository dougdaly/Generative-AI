# src/agents/image_gen.py
import torch, os
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageDraw, ImageFont
from schemas import PresidentList

# Set up diffusion model for image generation

def get_sdxl(device=None, model_id="stabilityai/stable-diffusion-xl-base-1.0"):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float16 if device=="cuda" else torch.float32
    pipe = StableDiffusionXLPipeline.from_pretrained(model_id, torch_dtype=dtype)
    pipe.to(device)
    pipe.enable_attention_slicing()
    return pipe, device



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
