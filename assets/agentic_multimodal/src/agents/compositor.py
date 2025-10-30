from PIL import Image, ImageDraw, ImageFont
from schemas import PresidentList
import math, os

def compose_node(state):
    plist = PresidentList(**state["research"])
    imgs = [state["images"][str(i+1)] for i in range(len(plist.people))]
    tiles_w, tiles_h = 6, math.ceil(len(imgs)/6)
    tile_w, tile_h = 512, 860  # include caption band
    margin, pad = 40, 20
    W = margin*2 + tiles_w*tile_w + (tiles_w-1)*pad
    H = margin*2 + tiles_h*tile_h + (tiles_h-1)*pad
    poster = Image.new("RGB", (W,H), "white")
    draw = ImageDraw.Draw(poster)
    font = ImageFont.load_default()

    for idx, path in enumerate(imgs):
        r, c = divmod(idx, tiles_w)
        x = margin + c*(tile_w+pad)
        y = margin + r*(tile_h+pad)
        im = Image.open(path).convert("RGB").resize((512,768))
        poster.paste(im, (x, y))
        person = plist.people[idx]
        caption = f"{person.name}\n{person.start} – {person.end}"
        draw.multiline_text((x+10, y+768+10), caption, fill="black", font=font, spacing=2)

    os.makedirs("out", exist_ok=True)
    out_path = "out/presidents_poster.png"
    poster.save(out_path, optimize=True)
    return {**state, "artifact": out_path}
