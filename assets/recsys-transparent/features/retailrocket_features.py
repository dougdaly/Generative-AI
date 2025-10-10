# assets/recsys-transparent/features/retailrocket_features.py
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FEATS = ["pos_inv","pop_ctr","fresh","editorial","hour","dow"]

import pandas as pd
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FEATS = ["pos_inv","pop_ctr","fresh","editorial","hour","dow"]

def build_training(slates_path=DATA/"rr_slates.parquet",
                   items_path=DATA/"rr_items.parquet") -> pd.DataFrame:
    # logged slate rows (has: user,item,session,ts,position,propensity,click)
    s = pd.read_parquet(slates_path).copy()
    it = pd.read_parquet(items_path).copy()

    # ------------------------------
    # Heal missing item attributes
    # ------------------------------
    # 1) last_ts (last time the item was seen in logs)
    if "last_ts" not in it.columns:
        last_ts = s.groupby("item")["ts"].max().rename("last_ts").reset_index()
        it = it.merge(last_ts, on="item", how="left")

    # 2) views_7d (rolling 7d views; if absent, derive quickly from slates)
    if "views_7d" not in it.columns:
        v = (s.assign(day=s["ts"].dt.floor("D"))
               .groupby(["item","day"]).size().rename("views_day").reset_index())
        v = (v.sort_values("day")
               .groupby("item")["views_day"]
               .rolling(7, min_periods=1).sum()
               .reset_index(level=0, drop=True)
               .rename("views_7d").reset_index())
        views7_last = v.sort_values("day").drop_duplicates("item", keep="last")[["item","views_7d"]]
        it = it.merge(views7_last, on="item", how="left")

    # 3) editorial_item (global item-level promotion flag; if missing, synthesize ~10%)
    if "editorial_item" not in it.columns:
        rng = np.random.default_rng(42)
        n = len(it)
        mark = np.zeros(n, dtype=np.int8)
        if n:
            mark[rng.choice(n, size=max(1, int(0.10*n)), replace=False)] = 1
        it["editorial_item"] = mark

    # 4) category may be absent; that’s fine—downstream is tolerant
    # ------------------------------

    # baseline popularity (CTR per item within logs)
    pop = s.groupby("item")["click"].mean().rename("pop_ctr").reset_index()

    # context features
    s["hour"]    = s["ts"].dt.hour
    s["dow"]     = s["ts"].dt.dayofweek
    s["pos_inv"] = 1.0 / s["position"]

    # join item attributes we care about
    have_cols = [c for c in ["item","last_ts","views_7d","category","editorial_item"] if c in it.columns]
    s = s.merge(it[have_cols], on="item", how="left")

    # item-level editorial flag
    s["editorial"] = s["editorial_item"].fillna(0).astype(int)

    # freshness: prefer last_ts; otherwise use views_7d>0 as proxy
    if "last_ts" in s.columns and s["last_ts"].notna().any():
        s["fresh"] = ((s["ts"] - s["last_ts"]).dt.days <= 7).fillna(False).astype(int)
    else:
        s["fresh"] = (s.get("views_7d", 0).fillna(0) > 0).astype(int)

    # popularity join + fill
    s = s.merge(pop, on="item", how="left")
    s["pop_ctr"] = s["pop_ctr"].fillna(0.0)

    # IPS weight (features frame carries weight, not raw propensity)
    s["weight_ips"] = 1.0 / s["propensity"].clip(lower=1e-3)

    cols = ["user","item","session","ts","position","click","weight_ips"] + FEATS
    for c in FEATS:
        if c not in s.columns:
            s[c] = 0
    return s[cols].copy()

