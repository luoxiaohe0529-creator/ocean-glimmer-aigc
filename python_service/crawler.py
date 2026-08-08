from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx


class ProductPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.image = ""
        self._in_title = False
        self._skip_depth = 0
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "meta":
            key = values.get("property") or values.get("name") or ""
            content = values.get("content", "").strip()
            if key.lower() in {"description", "og:description"} and not self.description:
                self.description = content
            if key.lower() in {"og:image", "twitter:image"} and not self.image:
                self.image = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title += value
        if not self._skip_depth:
            self.text_parts.append(value)


def fetch_product_page(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    with httpx.Client(follow_redirects=True, timeout=20, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    parser = ProductPageParser()
    parser.feed(response.text)
    text = "\n".join(parser.text_parts)
    return {
        "url": str(response.url),
        "title": parser.title.strip(),
        "description": parser.description,
        "text": text[:30000],
        "image": urljoin(str(response.url), parser.image) if parser.image else "",
    }
