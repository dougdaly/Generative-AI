from __future__ import annotations

from types import SimpleNamespace, MethodType

from agentic_multimodal.services.settings import Settings
from agentic_multimodal.services.llm_factory import build_llm, LLM

from agentic_multimodal.skills.data.wikidata_sparql import WikidataSPARQL
from agentic_multimodal.skills.data.wikidata_series import WikidataSeries
from agentic_multimodal.skills.data.wikidata_geo import WikidataGeo, WikidataGeoSets, geocode_place

from agentic_multimodal.skills.series.positions import PositionsProvider
from agentic_multimodal.skills.series.award import AwardProvider
from agentic_multimodal.skills.series.aliases import PreconfiguredProvider

from agentic_multimodal.skills.geo.region_flags import RegionCountriesWithFlags
from agentic_multimodal.skills.geo.subdivisions import SubdivisionsByCountryProvider

from agentic_multimodal.skills.gen_poster_renderer import compose_poster_spec
from agentic_multimodal.skills.gen_map_renderer import render_map
from agentic_multimodal.skills.adapters.people_to_poster import (
    people_to_posterspec_per_person,
    people_to_posterspec_per_term,
)
from agentic_multimodal.skills.series.candidates import AthletesByCitizenship, CurrentNationalLeaders
from agentic_multimodal.skills.series.rankers import PageviewsRanker, OverridesRanker
from agentic_multimodal.skills.series.per_country import PerCountrySelector
from agentic_multimodal.skills.selectors.famous_by_country import FamousPersonsByCountry
from agentic_multimodal.graphs.factory import build


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
    geo.register(RegionCountriesWithFlags())
    geo.register(SubdivisionsByCountryProvider())  # key="subdivisions"
    geo.register(FamousPersonsByCountry())

    # handy aliases (preconfigured params)
    # QIDs:
    #   USA ............. Q30
    #   Canada .......... Q16
    #   U.S. state ...... Q35657
    #   CA province ..... Q11828004
    #   CA territory .... Q190113
    class _GeoCountryAlias:
        def __init__(self, key, title, **fixed):
            self.key, self.title, self._fixed = key, title, fixed
        def fetch(self, client, *, language="en", **params):
            base = SubdivisionsByCountryProvider()
            return base.fetch(client, language=language, **{**self._fixed, **params})
    class _GeoContinentAlias:
        def __init__(self, key, title, **fixed):
            self.key, self.title, self._fixed = key, title, fixed
        def fetch(self, client, *, language="en", **params):
            base = RegionCountriesWithFlags()
            return base.fetch(client, language=language, **{**self._fixed, **params})

    geo.register(_GeoContinentAlias(
        key="europe_countries_flags",
        title="Europe — countries, flags & capital coords",
        region_qids=["Q46"],                   # Europe
        instance_of_qids=["Q6256"],            # sovereign states
    ))
    geo.register(_GeoContinentAlias(
        key="asia_countries_flags",
        title="Asia — countries, flags & capital coords",
        region_qids=["Q48"],
        instance_of_qids=["Q6256"],
    ))
    geo.register(_GeoCountryAlias(
        key="us_states_flags",
        title="U.S. states — flags & capital coords",
        country_qid="Q30", instance_of_qids=["Q35657"],
    ))
    geo.register(_GeoCountryAlias(
        key="ca_provinces_territories_flags",
        title="Canada — provinces & territories (flags & capital coords)",
        country_qid="Q16", instance_of_qids=["Q11828004", "Q190113"],
    ))

    render = SimpleNamespace(
        poster=compose_poster_spec, 
        map=render_map,
    )

    adapters = SimpleNamespace(
        people_per_person=people_to_posterspec_per_person,
        people_per_term=people_to_posterspec_per_term,
    )

    reg = SimpleNamespace(
        root=root_path,
        settings=settings,
        llm=llm,
        checkpointer=checkpointer,
        series=series,
        geo=geo,
        render=render,       
        adapters=adapters,
    )

    reg.graphs = SimpleNamespace(
        geo=build("geo:v1", reg, checkpointer=checkpointer),
    )
    reg.geo.geocode_place = MethodType(geocode_place, reg.geo)
    return reg

# services/registry.py
def _build_series() -> WikidataSeries:
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
    # Generic selectors:
    pv = PageviewsRanker(days=60)
    s.register(PerCountrySelector(
        key="per_country_popular_person_sports",
        title="Most popular sportsperson by country",
        provider=AthletesByCitizenship(),
        ranker=pv,
    ))
    s.register(PerCountrySelector(
        key="per_country_current_leader",
        title="Current national leader by country",
        provider=CurrentNationalLeaders(),
        ranker=pv,   # pageviews also works for leaders; swap if you prefer sitelinks
    ))
    return s
