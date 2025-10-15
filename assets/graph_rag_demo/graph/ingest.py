from pathlib import Path
import csv

# Loads a bunch of markdown docs as free text.
def load_docs(dir_path: Path) -> dict[str,str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in dir_path.glob("*.md")}

# assets/graph_rag_demo/graph/ingest.py
import pandas as pd
from pathlib import Path

def load_icd(csv_path: Path) -> list[dict]:
    """Load ICD codes from pipe-delimited CSV with columns: code|name."""
    df = pd.read_csv(
        csv_path,
        sep="|",
        dtype=str,
        usecols=["code", "name"],
        encoding="utf-8",
        keep_default_na=False,
    )
    # Trim whitespace and drop empties
    df["code"] = df["code"].str.strip()
    df["name"] = df["name"].str.strip()
    df = df[(df["code"] != "") & (df["name"] != "")]
    # De-dup on code (keep first)
    df = df.drop_duplicates(subset=["code"], keep="first")
    return df.to_dict(orient="records")

def load_procedures(csv_path: Path) -> list[dict]:
    df = pd.read_csv(csv_path, sep="|", dtype=str, usecols=["code","name"],
                     keep_default_na=False, encoding="utf-8")
    df["code"] = df["code"].str.strip()
    df["name"] = df["name"].str.strip()
    df = df[(df["code"]!="") & (df["name"]!="")].drop_duplicates("code")
    return df.to_dict("records")

def load_modifiers(csv_path: Path) -> list[dict]:
    df = pd.read_csv(csv_path, sep="|", dtype=str, usecols=["code","name"],
                     keep_default_na=False, encoding="utf-8")
    df["code"] = df["code"].str.strip()
    df["name"] = df["name"].str.strip()
    df = df[(df["code"]!="") & (df["name"]!="")].drop_duplicates("code")
    return df.to_dict("records")


def load_synonyms(csv_path: Path) -> list[tuple[str,str,str]]:
    df = pd.read_csv(csv_path, sep="|", dtype=str,
                     usecols=["term","label","code"],
                     keep_default_na=False, encoding="utf-8")
    for col in ["term","label","code"]:
        df[col] = df[col].str.strip()
    df = df[(df["term"]!="") & (df["label"]!="") & (df["code"]!="")]
    return list(df.itertuples(index=False, name=None))
