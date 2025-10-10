import pandas as pd
def covis_candidates(df: pd.DataFrame, topn=50):
    # co-visitation by session
    pairs = (df[["session","item"]].merge(df[["session","item"]], on="session")
             .query("item_x != item_y").groupby(["item_x","item_y"]).size().rename("w").reset_index())
    top = (pairs.sort_values(["item_x","w"], ascending=[True,False])
                 .groupby("item_x").head(topn))
    return top.rename(columns={"item_x":"item","item_y":"cand","w":"covis_w"})

