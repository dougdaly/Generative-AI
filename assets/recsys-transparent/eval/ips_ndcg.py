# assets/recsys-transparent/eval/ips_ndcg.py
import numpy as np
import pandas as pd

def ndcg_at_k(clicks: np.ndarray, k:int=10) -> float:
    gains = clicks[:k].astype(float)
    if gains.size == 0: return 0.0
    disc = 1.0/np.log2(np.arange(2, gains.size+2))
    dcg = float((gains*disc).sum())
    ideal = float((np.sort(gains)[::-1]*disc).sum()) or 1.0
    return dcg / ideal

def ips_ndcg_for_slate(df_slate: pd.DataFrame, k:int=10) -> float:
    # df_slate must have columns: click, propensity; already sorted by model target order
    w = 1.0 / df_slate["propensity"].to_numpy().clip(1e-6)
    gains = (w * df_slate["click"].to_numpy())
    gains = gains[:k]
    disc = 1.0/np.log2(np.arange(2, gains.size+2))
    dcg = float((gains*disc).sum())
    # ideal with same weights but sorted by click (weighted ideal)
    ideal = float((np.sort(gains)[::-1]*disc).sum()) or 1.0
    return dcg / ideal

def snips_ctr(clicks: np.ndarray, prop: np.ndarray) -> float:
    w = 1.0/np.clip(prop, 1e-6, 1.0)
    return float((w*clicks).sum() / w.sum())

def macro_avg_ndcg(slates: pd.DataFrame, by="session", k=10) -> float:
    vals = []
    for _, g in slates.groupby(by):
        # assume already sorted by final score
        vals.append(ndcg_at_k(g["click"].to_numpy(), k))
    return float(np.mean(vals)) if vals else 0.0

