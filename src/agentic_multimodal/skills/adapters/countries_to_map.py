# skills/adapters/countries_to_map.py
from typing import List
from agentic_multimodal.schemas.entities import Country
from agentic_multimodal.schemas.artifacts import MapSpec, MapMarker

def countries_to_map_spec(
    countries: List[Country],
    *,
    title: str,
    region_key: str = "custom",
) -> MapSpec:
    markers: List[MapMarker] = []
    for c in countries:
        if not c.capital_coords:
            continue
        lon, lat = c.capital_coords
        markers.append(
            MapMarker(
                lon=lon,
                lat=lat,
                label=c.name if c.name else "",
                image=None,  # renderer will use meta.flag_svg_url if present
                meta={"flag_svg_url": c.flag_svg_url, "capital_name": c.capital_name},
            )
        )
    return MapSpec(region=region_key, markers=markers, title=title)

