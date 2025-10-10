# assets/recsys-transparent/app/rr_dashboard.py
import streamlit as st
from pathlib import Path
import pandas as pd
import numpy as np
import sys
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from features.retailrocket_features import build_training, FEATS
from eval.ips_ndcg import ndcg_at_k, snips_ctr

DATA = ROOT / "data"

# rr_dashboard.py

@st.cache_data
def load_frames():
    s = pd.read_parquet(DATA/"rr_slates.parquet")
    f = build_training(DATA/"rr_slates.parquet", DATA/"rr_items.parquet")
    return s, f

slates, feats = load_frames()

# date filter (same mask for both since both have ts)
min_d = slates["ts"].min().date(); max_d = slates["ts"].max().date()
d1, d2 = st.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
mask = (feats["ts"].dt.date >= d1) & (feats["ts"].dt.date <= d2)

S = feats[mask].copy()   # <<-- use FEATS, not slates
w_promo = st.slider("Promotion weight", 0.0, 3.0, 0.6, 0.1)
w_fresh = st.slider("Freshness weight", 0.0, 2.0, 0.5, 0.1)
K = st.selectbox("Top-K", [5,10,20], index=1)

S["pos_inv"]   = S.get("pos_inv", 1.0 / S["position"])
S["pop_ctr"]   = S.get("pop_ctr", 0.0)
S["editorial"] = S.get("editorial", 0).fillna(0).astype(float)
S["fresh"]     = S.get("fresh", 0).fillna(0).astype(float)


@st.cache_data(show_spinner=False)
def estimate_exam_curve(S: pd.DataFrame, k: int = 10) -> np.ndarray:
    """
    Estimate position exam curve from historical slates with columns:
    ['session','item','position','click'].
    Fallback to 1/log2 if positions unavailable.
    """
    if {"position","click"}.issubset(S.columns):
        g = S.loc[S["position"]>=1].groupby("position")["click"].mean()
        ex = np.array([g.get(pos, g.mean()) for pos in range(1, k+1)], dtype=float)
        # normalize to make scale stable across windows
        ex = ex / (ex[0] + 1e-9)
        return ex
    # Fallback: classical exam curve
    ex = 1.0 / np.log2(np.arange(2, k+2))
    ex = ex / ex[0]
    return ex

K = 10  # your Top-K
EXAM = estimate_exam_curve(S, k=K)


# Create session cache and fast metrics
# --- Build session cache from S (after sliders), keep it in session_state ---
def build_session_cache_from_df(S: pd.DataFrame, k: int = 10, max_sessions: int = 400):
    # small progress bar so it doesn't look frozen
    prog = st.progress(0.0, text="Preparing session cache…")
    sess_ids = S["session"].drop_duplicates()
    if len(sess_ids) > max_sessions:
        sess_ids = sess_ids.sample(max_sessions, random_state=7).reset_index(drop=True)

    need = ["item","editorial","fresh","pop_ctr","pos_inv","click","session"]
    S2 = S[need].copy()

    cache = []
    total = len(sess_ids)
    for i, sid in enumerate(sess_ids, 1):
        g = S2.loc[S2["session"] == sid, ["item","editorial","fresh","pop_ctr","pos_inv","click"]]
        if g.empty:
            continue
        base = (g["pop_ctr"].astype(float).to_numpy() + g["pos_inv"].astype(float).to_numpy())
        cache.append({
            "item":      g["item"].to_numpy(np.int64),
            "editorial": g["editorial"].to_numpy(np.int8),
            "fresh":     g["fresh"].to_numpy(np.int8),
            "click":     g["click"].to_numpy(np.int8),
            "base":      base.astype(np.float32),
        })
        if i % 20 == 0 or i == total:
            prog.progress(i/total)
    prog.empty()
    return cache

# lightweight key so we don't hash big DataFrames
cache_key = (str(d1), str(d2), int(K), int(len(S)))
if st.session_state.get("session_cache_key") != cache_key:
    st.session_state.session_cache_key = cache_key
    st.session_state.session_cache = build_session_cache_from_df(S, k=K, max_sessions=400)

session_cache = st.session_state.session_cache

# lightweight key (don’t hash S)
cache_key = (str(d1), str(d2), int(K), int(len(S)))
if "session_cache_key" not in st.session_state or st.session_state.session_cache_key != cache_key:
    st.session_state.session_cache_key = cache_key
    st.session_state.session_cache = build_session_cache_from_df(S, k=K, max_sessions=400)

session_cache = st.session_state.session_cache

def fast_metrics(session_cache, w_promo: float, w_fresh: float, k: int = 10) -> dict:
    nds, ed_share, fr_share, exp_ctrs = [], [], [], []

    for c in session_cache:
        # standardize freshness per-session for a fair knob
        fr = c["fresh"]
        fr_std = (fr - fr.mean()) / (fr.std() + 1e-6)

        final = c["base"] + w_promo * c["editorial"] + w_fresh * fr_std

        n = final.size
        if n == 0:
            continue
        kk = min(k, n)

        # Top-K indices in score order
        idx = np.argpartition(final, -kk)[-kk:]
        idx = idx[np.argsort(final[idx])[::-1]]

        # --- metrics ---
        # NDCG
        gains = c["click"][idx].astype(float)
        disc  = 1.0 / np.log2(np.arange(2, gains.size + 2))
        dcg   = float((gains * disc).sum())
        ideal = float((np.sort(gains)[::-1] * disc).sum()) or 1.0
        nds.append(dcg / ideal)

        # Exposure shares
        ed_share.append(c["editorial"][idx].mean())
        fr_share.append(fr[idx].mean())

        # Expected CTR proxy = sum of exam by rank
        exp_ctrs.append(float(EXAM[:kk].sum()))

    return {
        "ndcg":         float(np.mean(nds)) if nds else 0.0,
        "exp_editorial":float(np.mean(ed_share)) if ed_share else 0.0,
        "exp_fresh":    float(np.mean(fr_share)) if fr_share else 0.0,
        "exp_ctr":      float(np.mean(exp_ctrs)) if exp_ctrs else 0.0,
        "sessions":     len(session_cache),
    }



# 3) compute scores
S["score_base"]  = (S["pop_ctr"].astype(float) + S["pos_inv"].astype(float))
S["score_final"] = S["score_base"] + w_promo*S["editorial"] + w_fresh*S["fresh"]

# --- Guard: empty after date filter? ---
if S.empty:
    st.warning("No data in the selected date range. Try widening the window.")
    st.stop()

# --- Rank per-session by final score, take Top-K ---
ranked = (S.sort_values(["session", "score_final"], ascending=[True, False])
            .groupby("session", as_index=False, sort=False)
            .head(K)
            .reset_index(drop=True))

# --- Metrics ---
# NDCG@K (macro over sessions)
import numpy as np
def _ndcg_at_k(clicks, k=10):
    clicks = np.asarray(clicks[:k], dtype=float)
    if clicks.size == 0:
        return 0.0
    disc = 1.0 / np.log2(np.arange(2, clicks.size + 2))
    dcg = float((clicks * disc).sum())
    ideal = float((np.sort(clicks)[::-1] * disc).sum()) or 1.0
    return dcg / ideal

nd_vals = []
for _, g in ranked.groupby("session", sort=False):
    nd_vals.append(_ndcg_at_k(g["click"].values, k=K))
ndcg_macro = float(np.mean(nd_vals)) if nd_vals else 0.0

# SNIPS CTR from logs (use the whole filtered window S, not just Top-K
if "weight_ips" in S.columns:
    prop = 1.0 / S["weight_ips"].to_numpy()
    snips = snips_ctr(S["click"].to_numpy(), prop)
else:
    snips = float(S["click"].mean())  # fallback

# Exposure in Top-K
exp_editorial = float(ranked["editorial"].mean())
exp_fresh = float(ranked["fresh"].mean())

# --- Render ---
def sweep_metrics(cache, promo_grid, w_fresh: float, k: int = 10) -> pd.DataFrame:
    rows = []
    for p in promo_grid:
        m = fast_metrics(cache, w_promo=p, w_fresh=w_fresh, k=k)
        rows.append({"promo": p, **m})
    return pd.DataFrame(rows)

# Use current fresh weight; sweep promo on X-axis
promo_grid = np.linspace(0, 3, 13)  # 0, 0.25, ..., 3.0
df = sweep_metrics(session_cache, promo_grid, w_fresh=w_fresh, k=K)

# Header for *current* slider point (optional)
current = fast_metrics(session_cache, w_promo=w_promo, w_fresh=w_fresh, k=K)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Editorial %", f"{current['exp_editorial']*100:.1f}%")
c2.metric("Fresh %",     f"{current['exp_fresh']*100:.1f}%")
c3.metric("NDCG@K",      f"{current['ndcg']:.4f}")
c4.metric("Expected CTR",f"{current['exp_ctr']:.3f}")

st.markdown("#### Policy curves (linked to **Freshness** weight)")

colA, colB, colC = st.columns(3)

with colA:
    st.caption("Exposure vs Promotion")
    fig, ax = plt.subplots()
    ax.plot(df["promo"], df["exp_editorial"]*100, marker="o")
    ax.set_xlabel("Promotion weight")
    ax.set_ylabel("Editorial share (%)")
    st.pyplot(fig, clear_figure=True)

with colB:
    st.caption("Expected CTR vs Promotion")
    fig, ax = plt.subplots()
    ax.plot(df["promo"], df["exp_ctr"], marker="o")
    ax.set_xlabel("Promotion weight")
    ax.set_ylabel("Expected CTR (proxy)")
    st.pyplot(fig, clear_figure=True)

with colC:
    st.caption("NDCG@K vs Promotion")
    fig, ax = plt.subplots()
    ax.plot(df["promo"], df["ndcg"], marker="o")
    ax.set_xlabel("Promotion weight")
    ax.set_ylabel("NDCG@K (macro)")
    st.pyplot(fig, clear_figure=True)

