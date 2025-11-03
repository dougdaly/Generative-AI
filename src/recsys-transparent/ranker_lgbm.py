import lightgbm as lgb, pandas as pd
FEATS = ["pos_inv","pop_ctr","fresh","editorial"]

def train_ranker(train_df: pd.DataFrame):
    train_df = train_df.sort_values(["session","position"])
    group = train_df.groupby("session").size().values
    y = train_df["click"].values
    X = train_df[FEATS].values
    dtrain = lgb.Dataset(X, label=y, group=group, feature_name=FEATS, free_raw_data=False)
    params = dict(objective="lambdarank", metric="ndcg", ndcg_at=[10],
                  learning_rate=0.1, num_leaves=31, min_data_in_leaf=50, verbose=-1)
    model = lgb.train(params, dtrain, num_boost_round=200)
    return model

def predict_with_decomp(model, df: pd.DataFrame, w_click=1.0, w_promo=1.0, w_fresh=0.5):
    # predict base scores
    X = df[FEATS].values
    base = model.predict(X)

    # policy terms
    promo = w_promo * df["editorial"].values
    fresh = w_fresh * df["fresh"].values
    final = w_click*base + promo + fresh

    # build output with flexible columns
    base_cols = ["user","item","session"]
    if "position" in df.columns:
        base_cols.append("position")
    out = df[base_cols].copy()
    out["score_base"] = base
    out["score_promo"] = promo
    out["score_fresh"] = fresh
    out["score_final"] = final
    return out
