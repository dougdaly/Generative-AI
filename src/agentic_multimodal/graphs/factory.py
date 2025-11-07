from .person_flow import build_graph as _build_person
from .geo_flow    import build_graph as _build_geo

BUILDERS = {
    "person:v1": _build_person,
    "geo:v1":    _build_geo,
}

def build(flow_key, registry, **kw):
    if flow_key not in BUILDERS:
        raise KeyError(f"Unknown flow '{flow_key}'. Options: {list(BUILDERS)}")
    # any KeyError below is a real wiring error; let it propagate
    return BUILDERS[flow_key](registry, **kw)

# Optional alias if you like the name:
def build_graph(flow_key, registry, **kw):
    return build(flow_key, registry, **kw)
