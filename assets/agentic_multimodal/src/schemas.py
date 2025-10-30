# schemas.py
from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class SeriesItem(BaseModel):
    id: str                 # stable ID (e.g., Q-code)
    name: str
    start: Optional[str]    # ISO date or year
    end: Optional[str]
    extra: dict = {}        # role, title, etc.
    prompt_hint: Optional[str] = None
    emblem_url: Optional[HttpUrl] = None  # crest/flag if you have one

class Series(BaseModel):
    title: str
    ordered_by: str         # 'start', 'ordinal', etc.
    items: List[SeriesItem]

class GeoFeature(BaseModel):
    id: str                 # stable ID (Q-code, ISO)
    name: str
    type: str               # 'country','state','province','capital','point'
    iso2: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    props: dict = {}

class GeoSet(BaseModel):
    title: str
    crs: str                # target projection
    region_filter: dict     # e.g., {"continent":"Europe"} or {"country":"United States"}
    areas: List[GeoFeature] # polygons or area IDs
    points: List[GeoFeature]# capitals, cities, etc.

class Person(BaseModel):
    id: str           # QID
    name: str
    birth: str|None
    death: str|None
    roles: list[str]  # e.g., "President of the United States"
    image_url: str|None
    meta: dict = {}   # source, conf, aliases

class Place(BaseModel):
    id: str           # QID
    name: str
    country: str|None
    capital: str|None
    polygon: list[tuple[float,float]]|None  # simplified ring
    center: tuple[float,float]|None
    meta: dict = {}
