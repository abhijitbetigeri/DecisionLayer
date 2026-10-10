"""Turn an HTML response into what a fetch-style agent actually sees.

Like most agent fetch tools, this does not execute JavaScript: scripts and styles are
dropped, links stay visible with their targets, and JSON-LD structured data is kept
because agents do read it. A price that only exists after JS runs is invisible here,
which is exactly the failure the control variant should exhibit.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

MAX_CHARS = 8000


def page_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    structured = [s.get_text() for s in soup.find_all("script", type="application/ld+json")]
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            a.replace_with(f"{a.get_text(strip=True)} [{href}]")
    title = soup.title.get_text(strip=True) if soup.title else ""
    body = soup.get_text("\n", strip=True)
    text = f"TITLE: {title}\n\n{body}"
    if structured:
        text += "\n\nSTRUCTURED DATA (JSON-LD):\n" + "\n".join(structured)
    return text[:MAX_CHARS]
