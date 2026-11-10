"""离线守卫（不联网、不调模型）: 验证 provider 切换与检索层形状。

跑法:
  cd backend
  ..\\.venv\\Scripts\\python.exe test_adapter.py

成功判据: 6 条守卫全 PASS，且不调用任何网络。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# agent/__init__.py 会 import graph，graph 在 import 时做 key 检查；
# 离线自检给一个占位 key，不发起任何网络调用。
os.environ.setdefault("GEMINI_API_KEY", "offline-test-key")

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"FAIL {name} — {detail}")


# guard 1: 环境变量为空时退回 google（上游行为不变）；注意 backend/.env 会覆盖进程 env
os.environ["LLM_PROVIDER"] = ""
from agent import llm as llm_mod

check("guard1 default when env empty", llm_mod.get_provider() == "google", f"provider={llm_mod.get_provider()}")

# guard 2: openai provider + base_url 生效（用 stub，不真连）
os.environ["LLM_PROVIDER"] = "openai"
os.environ["LOCAL_BASE_URL"] = "http://127.0.0.1:11434/v1"
os.environ["LOCAL_API_KEY"] = "sk-test"
import importlib

importlib.reload(llm_mod)
check("guard2 env switch", llm_mod.get_provider() == "openai" and llm_mod.get_base_url() and llm_mod.get_api_key(),
      f"base={llm_mod.get_base_url()} key={llm_mod.get_api_key()}")

try:
    from langchain_openai import ChatOpenAI

    model = llm_mod.get_llm("qwen3:8b", 0.0)
    check("guard3 get_llm builds ChatOpenAI", isinstance(model, ChatOpenAI),
          f"base_url={getattr(model, 'openai_api_base', None)}")
except ImportError:
    check("guard3 get_llm builds ChatOpenAI", False, "langchain-openai 未安装（pip 未完成）")

# guard 4: 无 base_url 时不注入 base_url（退回官方 OpenAI）
os.environ.pop("LOCAL_BASE_URL", None)
importlib.reload(llm_mod)
check("guard4 no base_url", llm_mod.get_base_url() is None, "无 base_url 时应走默认端点")

# guard 5: JSON 回退解析（本地小模型常不按 structured output 返回）
from agent.llm import _extract_json
from agent.tools_and_schemas import Reflection

sample = 'Here is my analysis:\n```json\n{"is_sufficient": false, "knowledge_gap": "缺少基准数据", "follow_up_queries": ["benchmarks"]}\n```'
data = _extract_json(sample)
check("guard5 json fallback", data is not None and data.get("is_sufficient") is False, repr(data)[:80])
if data:
    obj = Reflection.model_validate(data)
    check("guard6 fallback validates", obj.knowledge_gap == "缺少基准数据", obj.follow_up_queries)

# guard 7: 检索层形状与前端期望一致（SEARCH_PROVIDER=none，不联网）
os.environ["SEARCH_PROVIDER"] = "none"
from agent import search as search_mod
importlib.reload(search_mod)

item = search_mod._item("https://example.com/a-page", "example.com. Some title", "snippet text")
check("guard7 citation shape",
      set(item) == {"label", "short_url", "value", "snippet"} and item["label"] == "example.com",
      json.dumps(item, ensure_ascii=False))
check("guard8 none provider returns list", search_mod.run_search("test query") == [], "SEARCH_PROVIDER=none")

# guard 9: 前端选择的 model（config.configurable）必须赢过 env —— 此前 env 优先会静默忽略下拉框
os.environ["MODEL"] = "env-default-model"
os.environ["LLM_PROVIDER"] = "openai"
from agent.configuration import Configuration

cfg = Configuration.from_runnable_config({"configurable": {"model": "chosen-by-frontend"}})
check("guard9 config beats env", cfg.model == "chosen-by-frontend", f"model={cfg.model}")

# guard 10: env 仍是默认值（前端不选时）
cfg2 = Configuration.from_runnable_config(None)
check("guard10 env as default", cfg2.model == "env-default-model", f"model={cfg2.model}")

# guard 11: resolve_model 优先级 config > state > node default
check(
    "guard11 resolve_model order",
    cfg.resolve_model(cfg.reflection_model, "state-model") == "chosen-by-frontend"
    and Configuration(model=None).resolve_model("node-default", "state-model") == "state-model"
    and Configuration(model=None).resolve_model("node-default") == "node-default",
)

# guard 12: 混合 provider 的映射（一个下拉框可同时含 google 与 OpenAI 兼容模型）
os.environ["MODEL_PROVIDER_MAP"] = "gemini-2.5-pro=google,qwen-test=openai"
check(
    "guard12 provider map",
    llm_mod.resolve_provider("qwen-test") == "openai" and llm_mod.resolve_provider("gemini-2.5-pro") == "google"
    and llm_mod.resolve_provider("unlisted") == "openai",
    f"unlisted falls back to LLM_PROVIDER={llm_mod.get_provider()}",
)

# guard 13: 检索走代理（本机直连常被反爬拦），env 读取时取值
os.environ["SEARCH_PROXY"] = "http://127.0.0.1:10808"
importlib.reload(search_mod)
check("guard13 search proxy env", search_mod.get_proxy() == "http://127.0.0.1:10808"
      and search_mod._proxies() == {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"},
      f"proxies={search_mod._proxies()}")

# guard 14: ddgs 参数名随版本变（新版 proxy=，旧版 proxies=）——按签名挑，离线用假类
class NewStyle:
    def __init__(self, proxy=None, timeout=None):
        pass

class OldStyle:
    def __init__(self, proxies=None, timeout=None):
        pass

check("guard14 ddgs kwargs by signature",
      search_mod._ddgs_kwargs(NewStyle) == {"timeout": 15, "proxy": "http://127.0.0.1:10808"}
      and search_mod._ddgs_kwargs(OldStyle) == {"timeout": 15, "proxies": {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}},
      "new=proxy= / old=proxies=")

# guard 15: 第三方 SDK（tavily）靠 env 代理；只补空，不覆盖已有值
os.environ.pop("HTTP_PROXY", None)
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9999"
search_mod._sync_proxy_env()
check("guard15 proxy env synced without overwrite",
      os.environ.get("HTTP_PROXY") == "http://127.0.0.1:10808" and os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:9999",
      f"HTTP_PROXY={os.environ.get('HTTP_PROXY')} HTTPS_PROXY={os.environ.get('HTTPS_PROXY')}")

# guard 16: brave provider 需要 key（不联网，只验错误信息可读）
os.environ.pop("BRAVE_API_KEY", None)
os.environ["SEARCH_PROVIDER"] = "brave"
importlib.reload(search_mod)
try:
    search_mod.run_search("q")
    check("guard16 brave requires key", False, "不应在无 key 时成功")
except ValueError as e:
    check("guard16 brave requires key", "BRAVE_API_KEY" in str(e), str(e))

# guard 17: 重试 + 回退（DDG 间歇性反爬）——离线用 stub，不联网
os.environ["SEARCH_PROVIDER"] = "duckduckgo"
os.environ["SEARCH_RETRIES"] = "2"
os.environ["SEARCH_FALLBACK"] = "bing"
importlib.reload(search_mod)

calls = {"ddg": 0, "bing": 0}
search_mod._duckduckgo = lambda q, n: (calls.__setitem__("ddg", calls["ddg"] + 1), [])[1]
search_mod._bing = lambda q, n: (calls.__setitem__("bing", calls["bing"] + 1), [search_mod._item("https://x.com/a", "x.com", "s")])[1]
out = search_mod.run_search("q")
check("guard17 retry then fallback", calls["ddg"] == 2 and len(out) == 1, f"ddg calls={calls['ddg']}, out={out}")

# guard 18: 无回退时把最后一次异常抛出（不静默返回空）
os.environ["SEARCH_FALLBACK"] = ""
os.environ["SEARCH_RETRIES"] = "3"
calls["ddg"] = 0
def failing_ddg(q, n):
    calls["ddg"] += 1
    raise RuntimeError("anti-bot")

search_mod._duckduckgo = failing_ddg
try:
    search_mod.run_search("q")
    check("guard18 raises when no fallback", False, "应抛异常")
except RuntimeError as e:
    check("guard18 raises when no fallback", calls["ddg"] == 3 and "anti-bot" in str(e), f"calls={calls['ddg']}, {e}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
