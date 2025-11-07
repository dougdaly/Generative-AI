from __future__ import annotations

from types import SimpleNamespace

from agentic_multimodal.services.settings import Settings
from agentic_multimodal.services.llm_factory import build_llm, LLM

from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import WikidataSeries
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo, WikidataGeoSets

from agentic_multimodal.skills.series.positions import PositionsProvider
from agentic_multimodal.skills.series.award import AwardProvider
from agentic_multimodal.skills.series.aliases import PreconfiguredProvider

from agentic_multimodal.skills.geo.europe_flags import EuropeCountriesWithFlags
from agentic_multimodal.skills.geo.subdivisions import SubdivisionsByCountryProvider

from agentic_multimodal.skills.gen_poster_renderer import compose_poster_spec
from agentic_multimodal.skills.gen_map_renderer import render_map
from agentic_multimodal.skills.adapters.people_to_poster import (
    people_to_posterspec_per_person,
    people_to_posterspec_per_term,
)


def make_registry(
    root_path,
    *,
    settings: Settings | None = None,
    llm: LLM | None = None,
    checkpointer=None,
    series: WikidataSeries | None = None,
):
    settings = settings or Settings()          # reads env by default
    llm = llm or build_llm(settings)
    series = series or _build_series()

 # --- GEO dispatcher ---
    geo_client = WikidataGeo.default()
    geo = WikidataGeoSets(geo_client, language="en")

    # generic providers
    geo.register(EuropeCountriesWithFlags())
    geo.register(SubdivisionsByCountryProvider())  # key="subdivisions"

    # handy aliases (preconfigured params)
    # QIDs:
    #   USA ............. Q30
    #   Canada .......... Q16
    #   U.S. state ...... Q35657
    #   CA province ..... Q11828004
    #   CA territory .... Q190113
    class _Alias:
        def __init__(self, key, title, **fixed):
            self.key, self.title, self._fixed = key, title, fixed
        def fetch(self, client, *, language="en", **params):
            base = SubdivisionsByCountryProvider()
            return base.fetch(client, language=language, **{**self._fixed, **params})

    geo.register(_Alias(
        key="us_states_flags",
        title="U.S. states — flags & capital coords",
        country_qid="Q30", instance_of_qids=["Q35657"],
    ))
    geo.register(_Alias(
        key="ca_provinces_territories_flags",
        title="Canada — provinces & territories (flags & capital coords)",
        country_qid="Q16", instance_of_qids=["Q11828004", "Q190113"],
    ))

    try:
        from agentic_multimodal.skills.gen_map_renderer import render_map
    except Exception:
        render_map = None

    from agentic_multimodal.skills.adapters.people_to_poster import (
        people_to_posterspec_per_person,
        people_to_posterspec_per_term,
    )

    render = SimpleNamespace(
        poster=compose_poster_spec,   # may be None if you haven't implemented yet
        map=render_map,               # same
    )

    adapters = SimpleNamespace(
        people_per_person=people_to_posterspec_per_person,
        people_per_term=people_to_posterspec_per_term,
    )

    return SimpleNamespace(
        root=root_path,
        settings=settings,
        llm=llm,
        checkpointer=checkpointer,
        series=series,
        geo=geo,
        render=render,       
        adapters=adapters,
    )

# services/registry.py
def _build_series():
    sparql = WikidataSPARQL()
    s = WikidataSeries(sparql, language="[AUTO_LANGUAGE],en")
    s.register(PositionsProvider())
    s.register(AwardProvider())
    s.register(PreconfiguredProvider("potus","U.S. Presidents", base=PositionsProvider(), position_qids=["Q11696"]))
    s.register(PreconfiguredProvider(
        "monarchs_eng_gb_uk", "Monarchs of England/GB/UK",
        base=PositionsProvider(),
        position_qids=["Q18810062","Q110324075","Q111722535","Q9134365"],
    ))
    s.register(PreconfiguredProvider(
        "nobel_physics", "Nobel Prize in Physics — Laureates",
        base=AwardProvider(), award_qid="Q38104",
    ))
    return s
