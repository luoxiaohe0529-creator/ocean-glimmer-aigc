"""
Product page crawler.
- JD/Taobao → curl_cffi mobile site (bypasses anti-bot)
- Amazon → Playwright Node service (port 9876)
- Everything else → httpx
"""

import re
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

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


def _parse_html(html: str, base_url: str) -> dict:
    parser = ProductPageParser()
    parser.feed(html)
    text = "\n".join(parser.text_parts)
    return {
        "url": base_url,
        "title": parser.title.strip(),
        "description": parser.description,
        "text": text[:30000],
        "image": urljoin(base_url, parser.image) if parser.image else "",
    }


# ---- URL conversion for e-commerce mobile sites ----
def _convert_to_mobile(url: str) -> str:
    """Convert desktop e-commerce URLs to mobile versions."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # JD: item.jd.com/xxx.html → item.m.jd.com/product/xxx.html
    if 'jd.com' in domain:
        match = re.search(r'/(\d+)\.html', parsed.path)
        if match:
            return f'https://item.m.jd.com/product/{match.group(1)}.html'
        # Also handle jd.com direct links
        match = re.search(r'/(\d+)', parsed.path)
        if match:
            return f'https://item.m.jd.com/product/{match.group(1)}.html'

    # Taobao/Tmall: use main mobile site (SPA but loads product data)
    if 'taobao.com' in domain or 'tmall.com' in domain:
        for pattern in [r'id=(\d+)', r'item_id=(\d+)', r'/(\d{10,})\.html', r'/(\d{10,})(?:$|\?)']:
            match = re.search(pattern, parsed.path + parsed.query)
            if match:
                return f'https://main.m.taobao.com/detail/index.html?id={match.group(1)}'

    # Amazon: use mobile site
    if 'amazon.' in domain:
        match = re.search(r'/dp/([A-Z0-9]+)', parsed.path)
        if match:
            # Keep amazon domain but use mobile-friendly path
            return url  # Amazon already handles mobile well

    return url


def _extract_sku_id(url: str) -> str:
    """Extract SKU/product ID from e-commerce URL."""
    for pattern in [r'/(\d{6,})\.html', r'/(\d{6,})(?:$|\?)', r'id=(\d{6,})']:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


# ---- curl_cffi fetch for JD/Taobao ----
def _curlcffi_fetch(url: str) -> dict:
    """Use curl_cffi with Chrome TLS fingerprint impersonation."""
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return _blocked_result(url, "curl_cffi 未安装")

    mobile_url = _convert_to_mobile(url)
    fast_mode = os.getenv("STAGE1_FAST_MODE", "1").strip() == "1"
    max_attempts = 1 if fast_mode else 3
    request_timeout = 12 if fast_mode else 20

    try:
        import time, random
        for attempt in range(1, max_attempts + 1):
            # Small random delay between retries to avoid rate limiting
            if attempt > 1:
                time.sleep(random.uniform(2, 5))
            
            # Rotate User-Agent slightly to avoid fingerprinting
            ua_suffix = str(random.randint(0, 99))
            resp = curl_requests.get(
                mobile_url,
                impersonate='chrome131',
                headers={
                    'Accept': 'text/html,application/xhtml+xml',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Referer': 'https://www.google.com/',
                    'User-Agent': f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.{ua_suffix} Safari/537.36',
                },
                timeout=request_timeout,
            )
            final_url = str(resp.url)

            if resp.status_code != 200:
                if attempt < max_attempts:
                    continue
                return _blocked_result(final_url, f"HTTP {resp.status_code}")

            # Anti-bot pages: always retry
            is_blocked = any(kw in final_url.lower() for kw in ["risk_handler", "captcha", "verify"])
            # Also detect non-product pages by title
            boring_titles = ["天貓淘寶海外", "淘宝网", "天猫", "京东验证", "拼多多", "Amazon.com"]
            is_boring_page = any(t in (resp.text[:2000]) for t in boring_titles) and len(resp.text) < 10000
            
            if is_blocked or is_boring_page:
                if attempt < max_attempts:
                    continue
                return _blocked_result(final_url, f"反爬拦截: {final_url[:120]}")

            if len(resp.text) < 500:
                if attempt < max_attempts:
                    continue
                return _blocked_result(final_url, f"页面内容过短 ({len(resp.text)} chars)")

            # Success!
            result = _parse_html(resp.text, final_url)
            result["url"] = final_url
            if not result["image"]:
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', resp.text)
                if m:
                    result["image"] = m.group(1)
            return result

        return _blocked_result(mobile_url, "多次重试均被拦截")

    except Exception as e:
        return _blocked_result(mobile_url, str(e)[:200])


# ---- Playwright service fetch for stubborn sites ----
def _playwright_fetch(url: str) -> dict:
    """Use the standalone Node.js Playwright scraper service."""
    try:
        scraper_base_url = os.getenv("SCRAPER_SERVICE_URL", "http://127.0.0.1:9876").rstrip("/")
        resp = httpx.post(
            f"{scraper_base_url}/scrape",
            json={"url": _convert_to_mobile(url)},
            timeout=20 if os.getenv("STAGE1_FAST_MODE", "1").strip() == "1" else 35,
        )
        if resp.status_code != 200:
            return _blocked_result(url, f"Scraper HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("ok"):
            return _blocked_result(url, data.get("block_reason") or data.get("error") or "Scraper error")
        return {
            "url": data.get("url", url),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "text": data.get("text", ""),
            "image": data.get("image", ""),
        }
    except Exception as e:
        return _blocked_result(url, f"Scraper unavailable: {str(e)[:100]}")


# ---- httpx for non-ecommerce ----
def _httpx_fetch(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    request_timeout = 12 if os.getenv("STAGE1_FAST_MODE", "1").strip() == "1" else 20
    with httpx.Client(follow_redirects=True, timeout=request_timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    final_url = str(response.url)
    if any(kw in final_url.lower() for kw in ["risk_handler", "captcha", "verify", "login"]):
        return _blocked_result(final_url, f"反爬拦截: {final_url[:120]}")
    return _parse_html(response.text, final_url)


def _blocked_result(url: str, reason: str) -> dict:
    return {"url": url, "title": "", "description": "", "text": "", "image": "",
            "blocked": True, "block_reason": reason}


# ---- E-commerce detection ----
_ECOMMERCE = {"jd.com", "taobao.com", "tmall.com", "amazon.com", "amazon.cn",
              "pinduoduo.com", "yangkeduo.com", "1688.com", "suning.com", "vip.com"}


def is_ecommerce(url: str) -> bool:
    try:
        return any(d in urlparse(url).netloc.lower() for d in _ECOMMERCE)
    except Exception:
        return False


# ---- Short link resolution ----
def _resolve_short_link(url: str) -> str:
    """Resolve JD/Taobao short links (3.cn, t.cn, etc.) to full product URLs."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    short_domains = {'3.cn', 'u.jd.com', 'm.tb.cn', 's.click.taobao.com'}
    if domain not in short_domains:
        return url
    try:
        request_timeout = 6 if os.getenv("STAGE1_FAST_MODE", "1").strip() == "1" else 10
        resp = httpx.get(url, follow_redirects=False, timeout=request_timeout,
                         headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'})
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get('location', '')
            if location:
                from urllib.parse import urljoin as uj
                resolved = uj(url, location)
                # If still a short link, follow one more level
                parsed2 = urlparse(resolved)
                if parsed2.netloc.lower() in short_domains:
                    resp2 = httpx.get(resolved, follow_redirects=False, timeout=request_timeout,
                                     headers={'User-Agent': 'Mozilla/5.0'})
                    if resp2.status_code in (301, 302, 303, 307, 308):
                        loc2 = resp2.headers.get('location', '')
                        if loc2:
                            return uj(resolved, loc2)
                    return str(resp2.url) if resp2.status_code == 200 else resolved
                return resolved
    except Exception:
        pass
    return url


def fetch_product_page(url: str) -> dict:
    if not url or not url.startswith("http"):
        return {"url": url or "", "title": "", "description": "", "text": "", "image": ""}
    # Resolve short links first
    url = _resolve_short_link(url)

    if is_ecommerce(url):
        # JD: curl_cffi mobile site (bypasses anti-bot)
        # Taobao/Tmall: Try curl_cffi first, then Playwright (SPA needs JS render)
        result = _curlcffi_fetch(url)
        if not result.get("blocked"):
            return result
        # Taobao SPA — try browser rendering
        from urllib.parse import urlparse as up
        domain = up(url).netloc.lower()
        if 'taobao.com' in domain or 'tmall.com' in domain:
            result2 = _playwright_fetch(url)
            if not result2.get("blocked"):
                return result2
        return result  # blocked result

    try:
        return _httpx_fetch(url)
    except Exception as e:
        return _blocked_result(url, str(e)[:200])
