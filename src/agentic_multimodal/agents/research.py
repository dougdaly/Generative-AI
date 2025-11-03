# src/agents/research.py
import requests, bs4
from schemas import PresidentList, Person

WIKI = "https://en.wikipedia.org/wiki/List_of_presidents_of_the_United_States"

def parse_presidents(html:str):
    soup = bs4.BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.wikitable")  # first main presidents table
    people = []
    for row in table.select("tr")[1:]:
        cols = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cols) < 4: 
            continue
        name = row.select_one("td:nth-of-type(2) a").get_text(strip=True)
        term = cols[3]  # e.g., "January 20, 2025 – present"
        start, end = [t.strip() for t in term.replace("–","-").split("-", 1)]
        people.append(Person(
            name=name,
            start=start,
            end=end,
            image_prompt=f"cartoon portrait, {name}, clean white background, bust, flat shading, friendly, 2D"
        ))
    return PresidentList(people=people)

def research_node(state):
    r = requests.get(WIKI, timeout=20)
    plist = parse_presidents(r.text)
    return {**state, "research": plist.model_dump()}
