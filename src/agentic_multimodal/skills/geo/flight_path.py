from dataclasses import dataclass
from typing import List, Tuple, Optional
import math

EARTH_RADIUS_MILES = 3958.7613

@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float


def haversine_miles(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def _slerp_gc(a: Tuple[float, float], b: Tuple[float, float], f: float) -> Tuple[float, float]:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    def to_vec(lat, lon):
        return (
            math.cos(lat) * math.cos(lon),
            math.cos(lat) * math.sin(lon),
            math.sin(lat)
        )

    x1, y1, z1 = to_vec(lat1, lon1)
    x2, y2, z2 = to_vec(lat2, lon2)

    dot = max(-1.0, min(1.0, x1*x2 + y1*y2 + z1*z2))
    omega = math.acos(dot)

    if omega == 0:
        return (math.degrees(lat1), math.degrees(lon1))

    so = math.sin(omega)
    k1 = math.sin((1 - f) * omega) / so
    k2 = math.sin(f * omega) / so

    x = k1*x1 + k2*x2
    y = k1*y1 + k2*y2
    z = k1*z1 + k2*z2

    lon = math.atan2(y, x)
    hyp = math.sqrt(x*x + y*y)
    lat = math.atan2(z, hyp)

    return (math.degrees(lat), math.degrees(lon))


def great_circle_waypoints(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    step_miles: int = 50
) -> Tuple[List[Waypoint], float]:
    dist = haversine_miles(origin, destination)
    n = max(2, int(dist / step_miles) + 1)

    wps: List[Waypoint] = []
    for i in range(n):
        f = i / (n - 1)
        lat, lon = _slerp_gc(origin, destination, f)
        wps.append(Waypoint(lat=lat, lon=lon))

    return wps, dist


def validate_lat_cap(waypoints: List[Waypoint], lat_cap: float = 70.0) -> None:
    max_abs = max(abs(w.lat) for w in waypoints) if waypoints else 0.0
    if max_abs > lat_cap:
        raise ValueError(
            f"Route exceeds v1 latitude cap of ±{lat_cap}°. "
            "Polar routes intentionally deferred for v1."
        )


def route_bbox(
    waypoints: List[Waypoint],
    pad_degrees: float = 5.0,
    lat_cap: float = 70.0
) -> Optional[Tuple[float, float, float, float]]:
    if not waypoints:
        return None

    lats = [w.lat for w in waypoints]
    lons = [w.lon for w in waypoints]

    # naive dateline check
    if (max(lons) - min(lons)) > 180:
        return None

    min_lat = max(min(lats) - pad_degrees, -lat_cap)
    max_lat = min(max(lats) + pad_degrees,  lat_cap)
    min_lon = min(lons) - pad_degrees
    max_lon = max(lons) + pad_degrees

    return (min_lat, max_lat, min_lon, max_lon)
