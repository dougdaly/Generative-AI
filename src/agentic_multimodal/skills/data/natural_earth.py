# skills/data/natural_earth.py
from __future__ import annotations
import json, os, pathlib, tempfile

_ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets" / "ne"
_ASSETS.mkdir(parents=True, exist_ok=True)

_URLS = {
    "50m": [
        # Kelso’s official mirror
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson",
    ],
    "110m": [
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson",
        # very rough fallback
        "https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson",
    ],
}

def _path_for(res: str) -> pathlib.Path:
    return _ASSETS / f"ne_{res}_admin_0_countries.geojson"

def _ensure_geojson(res: str) -> None:
    p = _path_for(res)
    if p.is_file() and p.stat().st_size > 100_000:
        return
    for url in _URLS.get(res, []):
        try:
            import requests
            r = requests.get(url, timeout=25, headers={"User-Agent":"agentic-multimodal/1.0"})
            if r.status_code == 200 and r.content:
                with tempfile.NamedTemporaryFile("wb", delete=False) as tmp:
                    tmp.write(r.content)
                    tmp_path = tmp.name
                os.replace(tmp_path, p)
                return
        except Exception:
            pass
    # leave missing; caller will try a lower resolution

def _bbox_overlap(b1, b2):
    w1,s1,e1,n1 = b1; w2,s2,e2,n2 = b2
    return not (e1 < w2 or e2 < w1 or n1 < s2 or n2 < s1)

def iter_admin0_polys(view_bbox, *, res: str = "50m"):
    """
    Yields:
      {"name": str,
       "polys": [ {"outer":[(lon,lat)...], "holes":[[(lon,lat)...], ...]}, ... ] }
    Tries 50m first (crisper), falls back to 110m if missing.
    """
    for attempt in (res, "110m"):
        _ensure_geojson(attempt)
        p = _path_for(attempt)
        if not p.is_file():
            continue
        with open(p, "r") as f:
            gj = json.load(f)

        out = []
        for feat in gj.get("features", []):
            props = feat.get("properties", {}) or feat.get("Properties", {})
            name  = props.get("NAME") or props.get("name") or ""
            geom  = feat.get("geometry", {})
            bbox  = feat.get("bbox", None)
            if bbox and not _bbox_overlap(view_bbox, bbox):
                continue

            polys = []
            t = geom.get("type")
            coords = geom.get("coordinates", [])
            if t == "Polygon":
                if coords:
                    outer = [(float(x), float(y)) for x,y in coords[0]]
                    holes = [[(float(x), float(y)) for x,y in ring] for ring in coords[1:]]
                    polys.append({"outer": outer, "holes": holes})
            elif t == "MultiPolygon":
                for poly in coords:
                    if poly:
                        outer = [(float(x), float(y)) for x,y in poly[0]]
                        holes = [[(float(x), float(y)) for x,y in ring] for ring in poly[1:]]
                        polys.append({"outer": outer, "holes": holes})
            if polys:
                out.append({"name": name, "polys": polys})
        if out:
            return out
    return []
