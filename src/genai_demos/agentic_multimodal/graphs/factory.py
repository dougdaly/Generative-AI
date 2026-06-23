from .person_flow import build_graph as _build_person
from .geo_flow    import build_graph as _build_geo
from .group_poster_flow import build_graph as _build_group_poster

BUILDERS = {
    "person:v1": _build_person,
    "geo:v1":    _build_geo,
    "group_poster:v1": _build_group_poster,
}

def build(flow_key, registry, **kw):
    try:
        builder = BUILDERS[flow_key]
    except KeyError:
        opts = ", ".join(sorted(BUILDERS))
        raise KeyError(f"Unknown flow '{flow_key}'. Options: {opts}")
    return builder(registry, **kw)


# Optional alias if you like the name:
def build_graph(flow_key, registry, **kw):
    return build(flow_key, registry, **kw)
