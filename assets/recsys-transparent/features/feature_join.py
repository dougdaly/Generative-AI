import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def build_training(interactions_path=DATA/"synth_interactions.parquet",
                   items_path=DATA/"items.parquet",
                   cache_buster:int=0):  # pass any int to bust Streamlit cache
    df = pd.read_parquet(interactions_path)
    df = df.drop(columns=["fresh","editorial"], errors="ignore")
    items = pd.read_parquet(items_path)

    # ensure expected columns exist
    if "item" not in df.columns:
        raise ValueError("interactions missing 'item' column")
    if not {"fresh","editorial"}.issubset(items.columns):
        # fallback: try to grab from interactions or default to zeros
        if {"fresh","editorial"}.issubset(df.columns):
            items = df[["item","fresh","editorial"]].drop_duplicates("item")
        else:
            items = pd.DataFrame({
                "item": df["item"].unique(),
                "fresh": 0,
                "editorial": 0
            })

    # align dtypes before merge
    df["item"] = df["item"].astype("int64")
    items["item"] = items["item"].astype("int64")

    pop = df.groupby("item")["click"].mean().rename("pop_ctr").reset_index()

    f = (df.merge(pop, on="item", how="left")
           .merge(items[["item","fresh","editorial"]], on="item", how="left"))

    f["pos_inv"] = 1.0 / f["position"]
    cols = ["user","item","session","position","pos_inv","pop_ctr","fresh","editorial","click","propensity"]
    # fill any missing promo flags with 0 to be safe
    f[["fresh","editorial"]] = f[["fresh","editorial"]].fillna(0).astype(int)
    return f[cols]

