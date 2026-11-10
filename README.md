# LangGraph 研究 Agent（本 fork）

上游是 `google-gemini/gemini-fullstack-langgraph-quickstart`（Apache-2.0）。这份 README 只描述**我们自己的版本**——上游原文在 git 历史里（`main` = `e34e569`），改动逐条登记在 [CHANGES.md](CHANGES.md)。

本 fork 解决两件事：

1. **不依赖 Gemini 也能跑**：LLM provider 与检索 provider 都可插拔（上游把两者都硬绑在 Gemini 上，Google grounding 是 Gemini 专有能力）。
2. **前端的模型选择真正生效**：上游的 `Configuration.from_runnable_config` 让 env 永远赢，下拉框的值被静默丢弃。

工作分支 `feat/model-agnostic`（上游 `main` 不动）。

## 我们改了什么

| # | 位置 | 上游行为 | 本 fork | 验证方式 |
|---|---|---|---|---|
| 1 | `backend/src/agent/llm.py`（新增） | provider/model 硬绑 Gemini，import 时检查 key | `get_llm(model, temp, max_retries, provider)` 按 `LLM_PROVIDER` 返回 `ChatGoogleGenerativeAI` 或 `ChatOpenAI`；`resolve_provider(model)` 支持 `MODEL_PROVIDER_MAP`（一个下拉框混跑 google/openai）；`invoke_structured()` 带 JSON 文本回退（本地小模型上 `with_structured_output` 经常失败）；`LLM_DEBUG=1` 打印每次实际用的 provider/model | 离线守卫 1–6、12 |
| 2 | `backend/src/agent/search.py`（新增） | 只能用 Gemini 的 Google Search grounding | `duckduckgo` / `tavily` / `searxng` / `bing` / `serper` / `none`，返回形状与上游 `sources_gathered` 及前端 ActivityTimeline 一致 | 守卫 7–8；实跑 bing 返回 5 条 |
| 3 | `backend/src/agent/configuration.py` | `os.environ.get(name.upper(), configurable.get(name))` ⇒ env 永远赢，前端选择被吃掉 | 优先级 `config.configurable > env > 字段默认值`；新增 `model` 字段与 `resolve_model(node_default, state_value)` | 守卫 9–12 |
| 4 | `backend/src/agent/graph.py` | 四个节点各写各的模型名；无 key 时 import 就抛 `ValueError` | 四个节点统一走 `resolve_model()`；`web_research` 的非 google 分支（检索 + 归纳）；key 检查与 `genai_client` 只在 provider=google 时生效 | 实跑 run `01a1c036-f06d-710b-867a-8a1690866053` |
| 5 | `backend/src/agent/prompts.py` | 提示词假定 Google grounding 的 `vertexaisearch` 短链引用格式 | `search_summary_instructions`（把检索结果喂给模型并要求 markdown 引用）与 `answer_instructions_plain`（不依赖短链的引用格式） | 实跑输出引用为 markdown `[n]` |
| 6 | 前端 `src/lib/modelOptions.ts`（新增）、`InputForm.tsx`、`App.tsx`、`vite-env.d.ts`、`.env.example` | 下拉框硬编码三个 Gemini 名字，换模型要改代码 | 选项来自 `VITE_MODEL_OPTIONS` / `VITE_DEFAULT_MODEL`；提交走 `config.configurable.model`（`Send` 出来的 `web_research` state 只有 `search_query`/`id`，只靠 state input 拿不到选择） | `tsc --noEmit` exit=0；vite 转换后模块头部已 inlined 两个变量 |
| 7 | `backend/requirements.txt`（新增）、`pyproject.toml` | 无 requirements；缺 `colorlog`（uvicorn `ValueError: Unable to configure formatter 'simple'`） | 与 `pyproject.toml` 一致的清单（含 `langgraph-cli[inmem]`、`colorlog`、`langchain-openai`、`ddgs`），装法写明：装进**项目目录内的 `.venv`** | pip 装完，服务正常起 |
| 8 | `backend/test_adapter.py`（新增） | — | 12 条离线守卫（不联网、不调模型）：provider 切换、JSON 回退、citations 形状、config 优先级、provider map | 12/12 PASS（2026-11-10 复跑，exit 0） |

## 配置

`backend/.env`（**必须纯 ASCII**：`python-dotenv` 按 Windows locale 解码，中文注释直接 `UnicodeDecodeError`）。

| 变量 | 取值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `google` \| `openai` | `openai` 覆盖任何 OpenAI 兼容端点（Ollama / vLLM / DeepSeek / LM Studio / 官方） |
| `LOCAL_BASE_URL` | 例 `http://127.0.0.1:8081/v1` | `LLM_PROVIDER=openai` 时使用 |
| `LOCAL_MODEL` | 端点服务的模型名 | 请求没带 model 时的默认值 |
| `MODEL_PROVIDER_MAP` | `name=provider` 逗号分隔 | 按模型指定 provider，未列出的回退 `LLM_PROVIDER` |
| `LLM_DEBUG` | `1` | 每次调用打印实际 provider/model（排查"选择有没有生效"用这个） |
| `SEARCH_PROVIDER` | `duckduckgo` \| `tavily` \| `searxng` \| `bing` \| `serper` \| `none` | `bing` 免 key；Google grounding 只在解析出的 provider 是 `google` 时启用 |
| `TAVILY_API_KEY` / `SERPER_API_KEY` / `SEARXNG_URL` | — | 对应 provider 需要 |
| `GEMINI_API_KEY` | — | 仅 provider=google 时需要 |

前端下拉框在 `frontend/.env`（Vite 只在启动时读 `.env`，改后必须重启）：

```
VITE_MODEL_OPTIONS=qwen3.8-flash-next-iq2_xs|Qwen 3.8 Flash,deepseek-chat|DeepSeek
VITE_DEFAULT_MODEL=qwen3.8-flash-next-iq2_xs
```

列表里必须写端点**实际服务**的模型名。

## 跑法（本机实测）

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt --cache-dir D:\demo\.pip-cache
.venv\Scripts\pip install -e .            # 让 `agent` 包可 import；或 $env:PYTHONPATH="backend\src"
$env:PYTHONUTF8="1"
langgraph dev --no-reload --no-browser    # http://127.0.0.1:2024，assistant `agent`

cd ..\frontend
npm install --ignore-scripts
npm run dev                               # http://localhost:5173/app/
```

`make dev` 需要 `make`（本机没有），分别跑两边即可。vite 绑 `localhost`，本机解析到 `::1`，用 `http://localhost:5173/app/`；要 IPv4/局域网加 `--host`。

## 轮数（Effort 下拉框）

轮数被两个数限死，前端随每条消息下发（[frontend/src/App.tsx](frontend/src/App.tsx)）：

| Effort | 初始检索词 | 最大回环 |
|---|---|---|
| low | 1 | 1 |
| medium（默认） | 3 | 3 |
| high | 5 | 10 |

每条检索词各开一个 `web_research` 节点，每轮可再补若干 follow-up query，所以 medium 的形状是：1 次初始扇出（3 检索）+ 最多 3 轮回环（reflection + 追加检索）+ finalize。提前退出条件是模型判定信息足够（`is_sufficient`）；检索结果质量差（词典页、推广页）会让缺口判不出来，更容易跑满上限。

## 已验证（数字与日期）

- **2026-11-09 15:44** — 端点 `http://127.0.0.1:8081/v1`：PONG 2.34 s、结构化输出 5.28 s（走 `with_structured_output`，JSON 回退未触发）、bing 检索 5 条 3.6 s，全链路（generate_query → web_research → reflection → finalize_answer）产出带 markdown 引用的答案。
- **2026-11-09 16:45** — `langgraph dev` 起在 `http://127.0.0.1:2024`（assistant `agent` / `pro-search-agent`），`POST /threads` → `POST /threads/{id}/runs` `status=success`，答案含 20 条引用来源。
- **2026-11-09 17:15** — 探针验证 config 优先级：进程 env `MODEL=probe-env-default`（假值）+ `LLM_DEBUG=1`，请求 `config.configurable.model` 传真模型名 → 四个节点都打印 config 的值（run `01a1c036-f06d-710b-867a-8a1690866053`）。
- **2026-11-09 16:56** — 前端页面 200、`runs/stream` 200（SSE 92 行，含 values 事件与引用来源）。
- **2026-11-10** — 离线守卫 12/12 PASS；前端 `tsc --noEmit -p tsconfig.json` exit=0；commit `64793bf`（17 文件 +816/−72）推送到 fork 的 `feat/model-agnostic`，`main` 保持上游 `e34e569`。

## 已知边界

- 本机网络：`bing`(200) / `serper`(200) / `tavily`(401，需 key) 可达；`duckduckgo`、`searx.be`、`search.brave.com` 连不通 ⇒ 默认 `SEARCH_PROVIDER=bing`。
- 版本漂移：实装 `langgraph 1.2.20` / `langchain 1.4.9`（仓库要求 `>=0.2.6` / `>=0.3.19`），import 与图编译通过。
- 文件沙盒内跑 vite / `langgraph dev` 会撞 named pipe 边界（esbuild 派生子进程、reload 走 multiprocessing），在正常终端里不存在这个问题。
- 调用口径易踩：`runs` 的 `input` 必须给 `messages`（研究主题取自 `get_research_topic(state["messages"])`，给 `input.query` 会被忽略）；`assistant_id` 必须在 POST body；最终答案在 `messages[-1]`（state 里没有 `answer` 键）。

## 许可

Apache License 2.0，见 [LICENSE](LICENSE) 文件。上游项目：[google-gemini/gemini-fullstack-langgraph-quickstart](https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart)。
