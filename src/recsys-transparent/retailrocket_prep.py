# assets/recsys-transparent/data/retailrocket_prep.py
from __future__ import annotations
import pandas as pd
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW  = DATA / "raw"    # drop RetailRocket CSVs here

# Expected raw file names (RetailRocket provides these)
EV_PATH = RAW / "events.csv"           # columns: visitorid,event,itemid,transactionid,timestamp
IT_PATH = RAW / "item_properties_part1.csv"
IT2_PATH= RAW / "item_properties_part2.csv"
CAT_PATH= RAW / "category_tree.csv"    # optional (sometimes missing)

def load_events(nrows:int|None=None) -> pd.DataFrame:
    df = pd.read_csv(EV_PATH, nrows=nrows)
    # normalize
    df = df.rename(columns={
        "visitorid":"user", "itemid":"item", "timestamp":"ts", "event":"event"
    })[["user","item","ts","event"]]
    # ts is milliseconds since epoch
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    # keep only view/addtocart/transaction
    df = df[df["event"].isin(["view","addtocart","transaction"])].copy()
    df["user"] = df["user"].astype("int64")
    df["item"] = df["item"].astype("int64")
    return df.sort_values(["user","ts"])

def latest_item_props() -> pd.DataFrame:
    # properties: itemid, timestamp, property, value
    p1 = pd.read_csv(IT_PATH)
    p2 = pd.read_csv(IT2_PATH)
    props = pd.concat([p1,p2], ignore_index=True)
    props = props.rename(columns={"itemid":"item","timestamp":"ts"})
    props["ts"] = pd.to_datetime(props["ts"], unit="ms", utc=True)
    props = props.sort_values(["item","property","ts"]).drop_duplicates(["item","property"], keep="last")
    # pivot a few useful props (categoryid, price if present)
    keep = props[props["property"].isin(["categoryid","price"])]
    wide = keep.pivot(index="item", columns="property", values="value").reset_index()
    # enforce types
    if "categoryid" in wide.columns:
        wide["categoryid"] = pd.to_numeric(wide["categoryid"], errors="coerce").astype("Int64")
    if "price" in wide.columns:
        wide["price"] = pd.to_numeric(wide["price"], errors="coerce")
    return wide.rename(columns={"categoryid":"category"})

# Convert events into sessions by when either the user changes or the gap > a certain min value.
def sessionize(ev: pd.DataFrame, gap_min:int=30) -> pd.DataFrame:
    # session = break when gap > gap_min or user changes
    ev = ev.sort_values(["user","ts"]).copy()
    gap = ev.groupby("user")["ts"].diff().dt.total_seconds().div(60).fillna(0)
    new_sess = (gap > gap_min).astype(int)
    sess_num = new_sess.groupby(ev["user"]).cumsum()
    ev["session"] = ev["user"].astype(str) + "-" + sess_num.astype(str)
    return ev

def build_logged_slates(ev: pd.DataFrame, topk:int=10) -> pd.DataFrame:
    """
    Construct a per-session 'logged slate' from view events.
    We keep the first time each item was viewed in the session,
    assign a logging position by timestamp order (proxy UI rank),
    and fabricate simple propensities by position: P(pos=r) ∝ 1/log2(r+1).
    """
    v = (ev[ev["event"]=="view"]
         .sort_values(["user","session","ts"])
         .drop_duplicates(["session","item"], keep="first"))
    # position within session by time
    v["position"] = v.groupby("session").cumcount() + 1
    v = v[v["position"] <= topk].copy()

    # binary click label: clicked if user later add-to-cart OR transaction for that item in same session
    act = ev[ev["event"].isin(["addtocart","transaction"])]
    clicked = (act.groupby(["session","item"]).size() > 0).rename("click").astype(int).reset_index()
    v = v.merge(clicked, on=["session","item"], how="left")
    v["click"] = v["click"].fillna(0).astype(int)

    # simple position propensities (Plackett-Luce proxy)
    import numpy as np
    disc = 1.0/np.log2(v["position"]+1)   # higher for top ranks
    # normalize per session to make them probabilities over shown slots
    v["propensity"] = (disc / disc.groupby(v["session"]).transform("sum")).clip(1e-3, 1.0)

    # keep what we need
    return v[["user","item","session","ts","position","propensity","click"]].reset_index(drop=True)

def main(nrows:int|None=None):
    print("Loading events…")
    ev = load_events(nrows=nrows)
    print(f"events: {len(ev):,}")

    print("Sessionizing…")
    ev = sessionize(ev)

    print("Latest item props…")
    items = latest_item_props()

    print("Building logged slates…")
    slates = build_logged_slates(ev, topk=10)

    # popularity & recency (for features later)
    pop7 = (ev[ev["event"]=="view"]
              .assign(day=lambda d: d["ts"].dt.floor("D"))
              .groupby(["item","day"]).size()
              .groupby("item").rolling(7, min_periods=1).sum().reset_index(level=0, drop=True)
              .rename("views_7d").reset_index())
    last_view = ev.groupby("item")["ts"].max().rename("last_ts").reset_index()
    items = items.merge(last_view, on="item", how="left")
    items = items.merge(pop7.sort_values("day").drop_duplicates("item", keep="last")[["item","views_7d"]],
                        on="item", how="left")
    items["views_7d"] = items["views_7d"].fillna(0)
    rng = np.random.default_rng(42)
    ids = items["item"].to_numpy()
    mark = np.zeros(len(ids), dtype=np.int8)
    mark[rng.choice(len(ids), size=max(1, int(0.10*len(ids))), replace=False)] = 1
    items["editorial_item"] = mark
    items.to_parquet(DATA/"rr_items.parquet", index=False)
    ev.to_parquet(DATA/"rr_events.parquet", index=False)
    slates.to_parquet(DATA/"rr_slates.parquet", index=False)
    print("Wrote rr_events.parquet, rr_slates.parquet, rr_items.parquet")

if __name__ == "__main__":
    main()

