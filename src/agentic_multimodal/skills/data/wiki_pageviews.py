import requests, time
from datetime import date, timedelta

UA = "agentic-multimodal/0.1 (mailto:you@example.com)"

def en_wiki_title(entity_label: str) -> str:
    # Minimal normalization: spaces->_, strip weird punctuation if needed
    return entity_label.replace(" ", "_")

def last_n_days_pageviews(title: str, days: int = 60) -> int:
    end   = date.today()
    start = end - timedelta(days=days)
    url   = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
             "en.wikipedia/all-access/user/{title}/daily/{s}/{e}"
    ).format(title=en_wiki_title(title),
             s=start.strftime("%Y%m%d"),
             e=end.strftime("%Y%m%d"))
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    if r.status_code != 200:
        return 0
    data = r.json().get("items", [])
    return sum(it.get("views", 0) for it in data)
