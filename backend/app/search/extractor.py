import httpx
from bs4 import BeautifulSoup
from trafilatura import extract as extract_main_text

async def extract_page(url: str) -> dict:
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True,
        headers={"User-Agent": "NOTAssistant/0.1 (+local personal assistant)"}
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    html = response.text
    text = extract_main_text(html) or BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return {"url": str(response.url), "title": BeautifulSoup(html, "html.parser").title.string
            if BeautifulSoup(html, "html.parser").title else "", "text": text[:30000]}
