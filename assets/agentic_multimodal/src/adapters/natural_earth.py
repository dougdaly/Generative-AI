# adapters/natural_earth.py
import geopandas as gpd
NE_10M_ADMIN0 = "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries.zip"

def load_countries():
    return gpd.read_file(NE_10M_ADMIN0)

def filter_region(df, *, continent=None, name_in=None, iso_in=None):
    gdf = df
    if continent:
        gdf = gdf[gdf["CONTINENT"] == continent]
    if name_in:
        gdf = gdf[gdf["NAME_EN"].isin(name_in)]
    if iso_in:
        gdf = gdf[gdf["ISO_A2"].isin(iso_in)]
    return gdf
