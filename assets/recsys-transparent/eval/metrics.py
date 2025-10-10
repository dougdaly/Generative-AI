import numpy as np, pandas as pd

def ndcg_at_k(df: pd.DataFrame, k=10):
    # df must have columns: session, click, score_final
    ndcgs=[]
    for sid, g in df.groupby("session"):
        g = g.sort_values("score_final", ascending=False).head(k)
        dcg = (g["click"]/np.log2(np.arange(2, len(g)+2))).sum()
        ideal = (g.sort_values("click", ascending=False)["click"]/np.log2(np.arange(2, len(g)+2))).sum()
        ndcgs.append(dcg/(ideal or 1.0))
    return float(np.mean(ndcgs))

def ips_ctr(df: pd.DataFrame):
    # inverse propensity scoring for click rate
    w = 1.0/df["propensity"].clip(1e-3, 1.0)
    return float((w*df["click"]).sum()/w.sum())

