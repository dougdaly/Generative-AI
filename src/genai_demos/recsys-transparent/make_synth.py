import numpy as np, pandas as pd
from pathlib import Path
import sys

# make project root importable
ROOT = Path(__file__).resolve().parents[1]   # .../assets/recsys-transparent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data"


rng = np.random.default_rng(7)

U, I = 2000, 500    # users, items
T = 40000           # interactions

# latent prefs
user_z = rng.normal(size=(U, 8))
item_z = rng.normal(size=(I, 8))
item_fresh = rng.integers(0, 2, size=I)        # 0/1
item_editorial = rng.integers(0, 2, size=I)    # 0/1

def click_prob(u,i,pos):
    base = 1/(1+np.exp(-(user_z[u]@item_z[i]/4)))
    pos_bias = {1:0.9,2:0.75,3:0.6,4:0.5,5:0.45}.get(pos, 0.35)
    fresh_boost = 0.08*item_fresh[i]
    promo_boost = 0.10*item_editorial[i]
    return np.clip(base*pos_bias + fresh_boost + promo_boost, 0, 0.98)

rows=[]
for t in range(T):
    u = rng.integers(0,U)
    sess = f"s{u}-{t//20}"
    # show top-10 by user dot product + noise as logging policy
    scores = (user_z[u]@item_z.T) + rng.normal(0,1,size=I)
    cand = np.argsort(scores)[-20:]
    shown = cand[-10:][::-1]
    for rank, i in enumerate(shown, start=1):
        p = click_prob(u,i,rank)
        clk = rng.random() < p
        rows.append([u, int(i), sess, rank, p, int(clk), int(item_fresh[i]), int(item_editorial[i])])

df = pd.DataFrame(rows, columns=["user","item","session","position","propensity","click","fresh","editorial"])
df.to_parquet("synth_interactions.parquet", index=False)
pd.DataFrame({"item":range(I),"fresh":item_fresh,"editorial":item_editorial}).to_parquet("items.parquet", index=False)
print(df.head())


cand_rows, log_rows = [], []
for t in range(T):
    u = rng.integers(0,U)
    sess = f"s{u}-{t//20}"
    scores = (user_z[u]@item_z.T) + rng.normal(0,1,size=I)

    # pool of 50; logged slate of 10
    pool = np.argsort(scores)[-50:]
    shown = pool[-10:][::-1]

    # save the pool (no position; this is for future rerank)
    for i in pool:
        cand_rows.append([u, int(i), sess, float(scores[i]),
                          int(item_fresh[i]), int(item_editorial[i])])

    # save the logged slate with propensities/clicks
    for rank, i in enumerate(shown, start=1):
        p = click_prob(u,i,rank)
        clk = rng.random() < p
        log_rows.append([u, int(i), sess, rank, p, int(clk),
                         int(item_fresh[i]), int(item_editorial[i])])

inter = pd.DataFrame(log_rows, columns=["user","item","session","position","propensity","click","fresh","editorial"])
cands = pd.DataFrame(cand_rows, columns=["user","item","session","score_logging","fresh","editorial"])

inter.to_parquet(DATA_DIR / "synth_interactions.parquet", index=False)
cands.to_parquet(DATA_DIR / "synth_candidates.parquet", index=False)
pd.DataFrame({"item":range(I),"fresh":item_fresh,"editorial":item_editorial}).to_parquet(DATA_DIR / "items.parquet", index=False)
print("Wrote interaction+candidate pools.")
