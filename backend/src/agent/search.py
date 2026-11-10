"""Search provider switch (替代 Gemini 的 google_search grounding).

Google Search grounding 是 Gemini 专有能力，换模型后必须换成真正的检索工具。
环境变量:
  SEARCH_PROVIDER      duckduckgo | tavily | searxng | none     默认 duckduckgo
  SEARCH_MAX_RESULTS   每个 query 取几条，默认 5
  TAVILY_API_KEY       tavily 时需要
  SEARXNG_URL          searxng 时的实例地址（自托管或公共实例）

返回统一结构，与前端/上游 citations 形状一致：
  {"label": str, "short_url": str, "value": str, "snippet": str}

none = 不检索（纯模型路径，用于离线自检或无网络的端点测试）。
"""

import os
from urllib.parse import urlparse

def get_search_provider() -> str:
    """读取时取值：graph.py 的 load_dotenv() 晚于本模块 import。"""
    return (os.getenv("SEARCH_PROVIDER") or "duckduckgo").lower()


def get_max_results() -> int:
    return int(os.getenv("SEARCH_MAX_RESULTS", "5"))


def make_label(url: str, title: str = "") -> str:
    """域名短标签（前端 ActivityTimeline 显示用），域名缺失时退回标题首词。"""
    netloc = urlparse(url).netloc
    if netloc:
        return netloc.replace("www.", "")[:40]
    if title:
        return title.split(".")[0].strip()[:40]
    return "source"


def _item(url: str, title: str, snippet: str) -> dict:
    return {
        "label": make_label(url, title),
        "short_url": url,
        "value": url,
        "snippet": snippet or "",
    }


def _duckduckgo(query: str, n: int) -> list[dict]:
    try:
        from ddgs import DDGS  # 新版包名（duckduckgo_search 已改名 ddgs）
    except ImportError:
        from duckduckgo_search import DDGS  # 旧包名回退

    out = []
    with DDGS(timeout=15) as ddgs:
        for r in ddgs.text(query, max_results=n):
            url = r.get("url") or r.get("href") or ""
            if url:
                out.append(_item(url, r.get("title", ""), r.get("body", "")))
    return out


def _tavily(query: str, n: int) -> list[dict]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("SEARCH_PROVIDER=tavily 需要 TAVILY_API_KEY")
    from tavily import TavilyClient

    res = TavilyClient(api_key=key).search(query, max_results=n)
    return [
        _item(r.get("url", ""), r.get("title", ""), r.get("content", ""))
        for r in res.get("results", [])
        if r.get("url")
    ]


def _searxng(query: str, n: int) -> list[dict]:
    url = os.getenv("SEARXNG_URL")
    if not url:
        raise ValueError("SEARCH_PROVIDER=searxng 需要 SEARXNG_URL")
    import requests

    resp = requests.get(
        url.rstrip("/") + "/search",
        params={"q": query, "format": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        _item(r.get("url", ""), r.get("title", ""), r.get("content", ""))
        for r in resp.json().get("results", [])[:n]
        if r.get("url")
    ]


def _decode_bing(href: str) -> str:
    """Bing 结果链接是 https://www.bing.com/ck/a?...&u=a1<base64url> 跳转，解码回原始 URL。"""
    import base64
    import html as html_mod
    import re

    href = html_mod.unescape(href)
    m = re.search(r"u=a1([A-Za-z0-9_-]+)", href)
    if not m:
        return href
    s = m.group(1)
    s += "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s).decode("utf-8", "ignore")
    except Exception:
        return href


def _bing(query: str, n: int) -> list[dict]:
    """免 key 的 HTML 抓取（本机实测可达；DDG/Brave API 在本机连不通）。"""
    import html as html_mod
    import re

    import requests

    resp = requests.get(
        "https://www.bing.com/search",
        params={"q": query, "count": n},
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=15,
    )
    resp.raise_for_status()
    strip = lambda s: html_mod.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    out = []
    for block in re.findall(r'<li class="b_algo".*?</li>', resp.text, re.DOTALL)[:n]:
        anchor = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"', block)
        if not anchor:
            continue
        title_m = re.search(r"<h2[^>]*>.*?</h2>", block, re.DOTALL)
        sn_m = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        out.append(
            _item(
                _decode_bing(anchor.group(1)),
                strip(title_m.group(0)) if title_m else "",
                strip(sn_m.group(1))[:400] if sn_m else "",
            )
        )
    return out


def _serper(query: str, n: int) -> list[dict]:
    """SERP API（serper.dev），需要 SERPER_API_KEY。"""
    key = os.getenv("SERPER_API_KEY")
    if not key:
        raise ValueError("SEARCH_PROVIDER=serper 需要 SERPER_API_KEY")
    import requests

    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": key},
        json={"q": query, "num": n},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        _item(r.get("link", ""), r.get("title", ""), r.get("snippet", ""))
        for r in resp.json().get("organic", [])
        if r.get("link")
    ]


def run_search(query: str, n: int | None = None) -> list[dict]:
    """Run one search query and return citation-shaped results."""
    limit = n or get_max_results()
    provider = get_search_provider()
    if provider == "none":
        return []
    if provider in ("duckduckgo", "ddg"):
        return _duckduckgo(query, limit)
    if provider == "tavily":
        return _tavily(query, limit)
    if provider == "searxng":
        return _searxng(query, limit)
    if provider == "bing":
        return _bing(query, limit)
    if provider == "serper":
        return _serper(query, limit)
    raise ValueError(f"未知 SEARCH_PROVIDER: {provider}")
