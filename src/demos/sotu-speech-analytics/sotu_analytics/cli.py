import argparse
from pathlib import Path
import yaml

# NOTE: core functions live in src/sotu_analytics/*

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    p = argparse.ArgumentParser("sotu")
    p.add_argument("--config", default="configs/v1.yaml")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clean")
    sub.add_parser("chunk")
    sub.add_parser("topics")
    sub.add_parser("metrics")

    args = p.parse_args()
    cfg = load_config(args.config)

    if args.cmd == "clean":
        raise NotImplementedError("STUB: implement sotu clean")
    if args.cmd == "chunk":
        raise NotImplementedError("STUB: implement sotu chunk")
    if args.cmd == "topics":
        raise NotImplementedError("STUB: implement sotu topics")
    if args.cmd == "metrics":
        raise NotImplementedError("STUB: implement sotu metrics")

if __name__ == "__main__":
    main()

