"""Search provider switch (替代 Gemini 的 google_search grounding).

Google Search grounding 是 Gemini 专有能力，换模型后必须换成真正的检索工具。
环境变量:
  SEARCH_PROVIDER      duckduckgo | tavily | searxng | bing | serper | brave | none     默认 duckduckgo
  SEARCH_MAX_RESULTS   每个 query 取几条，默认 5
  SEARCH_PROXY         例 http://127.0.0.1:10808；requests 与 ddgs 都会走它（本机直连常被反爬拦）
  TAVILY_API_KEY       tavily 时需要
  SERPER_API_KEY       serper 时需要
  BRAVE_API_KEY        brave 时需要
  SEARXNG_URL          searxng 实例地址；公共实例多数禁用 format=json（实测 searx.be 走代理 200 但返回 antibot 页），需要自托管实例

返回统一结构，与前端/上游 citations 形状一致：
  {"label": str, "short_url": str, "value": str, "snippet": str}

none = 不检索（纯模型路径，用于离线自检或无网络的端点测试）。
"""

import inspect
import os
import time
from urllib.parse import urlparse

def get_search_provider() -> str:
    """读取时取值：graph.py 的 load_dotenv() 晚于本模块 import。"""
    return (os.getenv("SEARCH_PROVIDER") or "duckduckgo").lower()


def get_max_results() -> int:
    return int(os.getenv("SEARCH_MAX_RESULTS", "5"))


def get_retries() -> int:
    return int(os.getenv("SEARCH_RETRIES", "3"))


def get_fallback() -> str:
    return (os.getenv("SEARCH_FALLBACK") or "").lower()


def get_proxy() -> str:
    """读取时取值。注意 git/requests 不会读 Windows 系统代理（IE 设置），必须显式给。"""
    return os.getenv("SEARCH_PROXY") or ""


def _proxies() -> dict | None:
    proxy = get_proxy()
    return {"http": proxy, "https": proxy} if proxy else None


def _ddgs_kwargs(ddgs_cls) -> dict:
    """ddgs 的参数名随版本变（新版 proxy=，旧版 proxies=）；按签名挑，挑不到就靠 env 代理。"""
    kw = {"timeout": 15}
    proxy = get_proxy()
    if not proxy:
        return kw
    try:
        params = inspect.signature(ddgs_cls.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    if "proxy" in params:
        kw["proxy"] = proxy
    elif "proxies" in params:
        kw["proxies"] = {"http": proxy, "https": proxy}
    return kw


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
    with DDGS(**_ddgs_kwargs(DDGS)) as ddgs:
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
        proxies=_proxies(),
        timeout=15,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise ValueError(
            "searxng 实例未启用 format=json（公共实例常见，实测 searx.be 走代理 200 但返回 antibot HTML）；"
            "改用自托管实例，或换 SEARCH_PROVIDER=bing / serper / brave"
        )
    return [
        _item(r.get("url", ""), r.get("title", ""), r.get("content", ""))
        for r in data.get("results", [])[:n]
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
    """免 key 的 HTML 抓取。直连可达；DDG/Brave 走 SEARCH_PROXY 才稳定（见文件头）。"""
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
        proxies=_proxies(),
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
        proxies=_proxies(),
        timeout=15,
    )
    resp.raise_for_status()
    return [
        _item(r.get("link", ""), r.get("title", ""), r.get("snippet", ""))
        for r in resp.json().get("organic", [])
        if r.get("link")
    ]


def _brave(query: str, n: int) -> list[dict]:
    """Brave Search API，需要 BRAVE_API_KEY。HTML 端点走代理也会被限流（实测 429），API 路径正常。"""
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        raise ValueError("SEARCH_PROVIDER=brave 需要 BRAVE_API_KEY")
    import requests

    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": n},
        headers={"Accept": "application/json", "X-Subscription-Token": key},
        proxies=_proxies(),
        timeout=15,
    )
    resp.raise_for_status()
    return [
        _item(r.get("url", ""), r.get("title", ""), r.get("description", ""))
        for r in resp.json().get("web", {}).get("results", [])[:n]
        if r.get("url")
    ]


def _sync_proxy_env() -> None:
    """第三方 SDK（tavily 等）靠 env 代理；这里把 SEARCH_PROXY 同步过去，只在未设置时写。"""
    proxy = get_proxy()
    if not proxy:
        return
    os.environ.setdefault("HTTP_PROXY", proxy)
    os.environ.setdefault("HTTPS_PROXY", proxy)


def run_search(query: str, n: int | None = None) -> list[dict]:
    """Run one search query and return citation-shaped results.

    DDG 间歇性抛 No results found（反爬），重试常能拿到结果；重试仍空时按 SEARCH_FALLBACK 换 provider。
    """
    limit = n or get_max_results()
    provider = get_search_provider()
    if provider == "none":
        return []

    dispatch = {
        "duckduckgo": _duckduckgo,
        "ddg": _duckduckgo,
        "tavily": _tavily,
        "searxng": _searxng,
        "bing": _bing,
        "serper": _serper,
        "brave": _brave,
    }
    fn = dispatch.get(provider)
    if fn is None:
        raise ValueError(f"未知 SEARCH_PROVIDER: {provider}")

    _sync_proxy_env()
    last_error = None
    for attempt in range(get_retries()):
        try:
            out = fn(query, limit)
            if out:
                return out
        except Exception as exc:  # 反爬 / 限流 / 网络，重试或回退
            last_error = exc
        if attempt + 1 < get_retries():
            time.sleep(1)

    fallback = get_fallback()
    if fallback and fallback != provider and fallback in dispatch:
        return dispatch[fallback](query, limit)
    if last_error:
        raise last_error
    return []
