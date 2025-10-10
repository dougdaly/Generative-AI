from pathlib import Path
import sys
import numpy as np

# make project root importable
ROOT = Path(__file__).resolve().parents[1]   # .../assets/recsys-transparent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data"
POOL_PATH = DATA_DIR / "synth_candidates.parquet"


from models.ranker_lgbm import train_ranker, predict_with_decomp
from features.feature_join import build_training

import streamlit as st, pandas as pd, numpy as np
from eval.metrics import ndcg_at_k, ips_ctr

st.title("Transparent Recommender: Why am I seeing this?")

@st.cache_data
def load_pool():
    import pandas as pd
    return pd.read_parquet(POOL_PATH)

pool = load_pool()


@st.cache_data
def load_data(cache_buster:int=0):
    return build_training(
        interactions_path=DATA_DIR / "synth_interactions.parquet",
        items_path=DATA_DIR / "items.parquet",
        cache_buster=cache_buster,   # forces cache refresh when this arg changes
    )


df = load_data(cache_buster=1)
df = load_data()
st.write("Sample of logged interactions (synthetic):", df.head())



# Train (quick)
model = train_ranker(df)

# Controls
w_promo = st.slider("Promotion weight", 0.0, 3.0, 1.0, 0.1)
w_fresh = st.slider("Freshness weight", 0.0, 2.0, 0.5, 0.1)

# Pick a user/session to demo
sid = st.selectbox("Session", sorted(df["session"].unique())[:2000])
g = df[df["session"]==sid].copy()
pred = predict_with_decomp(model, g, w_click=1.0, w_promo=w_promo, w_fresh=w_fresh)
view = g.merge(pred, on=["user","item","session","position"])
view = view.sort_values("score_final", ascending=False)

st.subheader("Reranked slate")
st.dataframe(view[["item","click","position","score_base","score_promo","score_fresh","score_final","editorial","fresh"]])

st.markdown("**This feed is ranked by a base click model + (promotion × weight) + (freshness × weight).** Move the sliders to see who rises or falls and whether quality (NDCG) actually improves.")

def make_why(row):
    reasons = []
    if row.get("editorial") == 1 and w_promo > 0:
        reasons.append(f"Editorial +{row['score_promo']:.2f}")
    if row.get("fresh") == 1 and w_fresh > 0:
        reasons.append(f"Fresh +{row['score_fresh']:.2f}")
    # small base signal hint
    reasons.append(f"Base {row['score_base']:.2f}")
    return " • ".join(reasons)

# Build current view
view["why"] = view.apply(make_why, axis=1)
view["rank_now"] = np.arange(1, len(view)+1)

# Counterfactual ranks with promo=0
pred_cf = predict_with_decomp(model, g, w_click=1.0, w_promo=0.0, w_fresh=w_fresh)
cf_sorted = pred_cf.sort_values("score_final", ascending=False).reset_index(drop=True)
cf_sorted["rank_cf"] = np.arange(1, len(cf_sorted)+1)
view = view.merge(cf_sorted[["item","rank_cf"]], on="item", how="left")
view["Δrank_vs_no_promo"] = view["rank_cf"] - view["rank_now"]  # positive = promo helped

st.subheader("Reranked slate (reasons & counterfactual)")
st.dataframe(view[["item","click","position","rank_now","Δrank_vs_no_promo","why","score_final"]])

# Metrics now vs no-promo
nd_now = ndcg_at_k(view, k=10)
nd_nopromo = ndcg_at_k(
    g.merge(pred_cf, on=["user","item","session","position"]).sort_values("score_final", ascending=False), k=10
)
col1, col2 = st.columns(2)
col1.metric("NDCG@10 (now)", f"{nd_now:.3f}")
col2.metric("NDCG@10 (no promo)", f"{nd_nopromo:.3f}", delta=f"{(nd_now-nd_nopromo):+.3f}")

# Exposure chart: share of editorial items in top-10 vs weight (simple sweep)
# Build a rerank pool for this session
pool_g = pool[pool["session"] == sid].copy()
# Join any features needed by the model (pop_ctr/pos_inv not used here; we just need model features)
# Reuse training df to fetch pop_ctr by item:
pop_map = df.groupby("item")["pop_ctr"].first()
pool_g = pool_g.join(pop_map, on="item")
pool_g["pos_inv"] = 1.0  # pool items don't have logged positions; neutral placeholder
pool_for_model = pool_g[["pos_inv","pop_ctr","fresh","editorial"]].fillna(0)

# Helper to predict on arbitrary frames shaped like training features:
def predict_scores(model, frame):
    import numpy as np
    # columns must match FEATS order in the model
    X = frame[["pos_inv","pop_ctr","fresh","editorial"]].values
    return model.predict(X)

# Exposure sweep
import numpy as np, matplotlib.pyplot as plt
weights = np.linspace(0, 3.0, 16)
exposure = []
base_scores = predict_scores(model, pool_for_model)
for w in weights:
    final = (1.0*base_scores) + (w * pool_g["editorial"].values) + (w_fresh * pool_g["fresh"].values)
    top10 = pool_g.iloc[np.argsort(final)[-10:]]
    exposure.append(top10["editorial"].mean())

fig = plt.figure()
plt.plot(weights, exposure)
plt.xlabel("Promotion weight")
plt.ylabel("Editorial share in Top-10")
plt.title("Exposure vs Promo Weight (rerank from 50-item pool)")
st.pyplot(fig)


# Counterfactual: promo=0
pred_cf = predict_with_decomp(model, g, w_click=1.0, w_promo=0.0, w_fresh=w_fresh)
cf = pred[["item","score_final"]].merge(pred_cf[["item","score_final"]].rename(columns={"score_final":"score_cf"}), on="item")
cf["delta"] = cf["score_final"] - cf["score_cf"]
st.write("Top promo lift items:")
st.dataframe(cf.sort_values("delta", ascending=False).head(10))

# Metrics snapshot
nd = ndcg_at_k(view.assign(score_final=view["score_final"]), k=10)
ctr_ips = ips_ctr(g)  # under logging policy
st.metric("NDCG@10 (reranked)", f"{nd:.3f}")
st.metric("IPS CTR (logged)", f"{ctr_ips:.3f}")
st.caption("Note: M0 uses synthetic propensities; M1 adds off-policy eval properly.")

