# CHANGES.md — 本地改动登记（上游 google-gemini/gemini-fullstack-langgraph-quickstart 的 fork）

工作分支：`feat/model-agnostic`（上游 `main` 保持原样）。

## 2026-11-09 — 模型与检索层改为可插拔（不依赖 Gemini）

| 文件 | 改动 | 原因 | 验证方式 |
|---|---|---|---|
| `backend/src/agent/llm.py`（新增） | `get_llm()` 按 `LLM_PROVIDER` 返回 `ChatGoogleGenerativeAI` 或 `ChatOpenAI`（OpenAI 兼容端点：Ollama / vLLM / DeepSeek / 官方）；`invoke_structured()` 带 JSON 文本回退 | 原代码把 provider 和 model 硬绑在 Gemini 上；`with_structured_output` 在本地小模型上经常失败，需要可解析的退化路径 | `backend/test_adapter.py` guard 1–6 |
| `backend/src/agent/search.py`（新增） | `run_search()` 支持 `duckduckgo` / `tavily` / `searxng` / `bing` / `serper` / `none`，返回 `{label, short_url, value, snippet}` | Google Search grounding 是 Gemini 专有能力，换模型后必须换成真实检索工具；返回形状与上游 `sources_gathered` / 前端 ActivityTimeline 一致 | guard 7–8；实跑：`SEARCH_PROVIDER=bing` 返回 5 条（langchain.com / docs.langchain.com / github.com） |
| `backend/src/agent/graph.py` | 三处 LLM 初始化改 `get_llm()`；`web_research` 增加非 google 分支（检索 + 归纳）；key 检查只在 `LLM_PROVIDER=google` 时生效；`genai_client` 仅在 google 时创建 | 无 Gemini key 时原本 import 就抛 `ValueError`，无法跑 | 离线编译检查：节点 `[generate_query, web_research, reflection, finalize_answer]` 完整，import 不报错 |
| `backend/src/agent/prompts.py` | 新增 `search_summary_instructions`（把检索结果喂给模型并要求 markdown 引用）与 `answer_instructions_plain`（不含 vertexaisearch 短链的引用格式） | 原提示词假定 Google grounding 的短链格式，非 Gemini 路径没有该格式 | 文本层检查；运行时看输出引用 |
| `backend/test_adapter.py`（新增） | 8 条离线守卫（不联网、不调模型） | 需要在无 key、无端点的情况下验证 provider 切换、JSON 回退、citations 形状 | `cd backend && .\.venv\Scripts\python.exe test_adapter.py` → 8 passed, 0 failed |
| `backend/.env.example` | 补 `LLM_PROVIDER` / `LOCAL_BASE_URL` / `LOCAL_MODEL` / `SEARCH_PROVIDER` 等 | 记录新的开关 | — |
| `backend/requirements.txt`（新增） | 与 `pyproject.toml` 一致的依赖清单（含 `langchain-openai`、`ddgs`、`langgraph-cli[inmem]`），并写明装法：装进**项目目录内的 `.venv`**，不装工作区根或全局环境 | 用户约定：依赖必须写进 requirements.txt 并装到项目目录 | 首版含中文注释 → pip `auto_decode` 用 Windows locale（gbk）解码失败：`UnicodeDecodeError: 'gbk' codec can't decode byte 0x94`；改纯 ASCII 后重跑 |

## 环境口径（Windows，已实测）

- Python：`python` 命令是 Microsoft Store 别名（不可用）；用 `py -3.11`（`D:\installfiles\Python\Python311`）。venv 在仓库内 `.venv`。
- pip：官方 PyPI 慢/挂，用 `http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com`，并加 `--cache-dir <工作区路径>`（沙盒内写 `AppData` 会被拒）。
- npm：沙盒内 `npm install` 的 postinstall 会 spawn 子进程（named pipe 是文档边界）→ `spawn EPERM`；用 `--ignore-scripts` + `--cache <工作区路径>` 可装完。`npm run build` / `npm run dev` 需要在自己的终端跑（或在工作区内置 `TMP` 且 full access）。
- `make` 本机不可用（Git Bash 不带），`make dev` 用不了；分别跑 `langgraph dev` 和 `npm run dev`。
- 版本漂移：实装的是 `langgraph 1.2.20` / `langchain 1.4.9`（仓库要求 `>=0.2.6` / `>=0.3.19`），离线 import 与图编译通过，实跑未验证。

## 2026-11-09 — 实跑验证（端点 `http://127.0.0.1:8081/v1`，模型 `qwen3.8-flash-next-iq2_xs`）

- 环境变量读取改为**调用时取值**（`get_provider()` / `get_base_url()` / `get_search_provider()` 等）：`agent/__init__.py` 会先 import `graph`，而 `load_dotenv()` 在其后，import 时固化会读到空值（实测触发 `GEMINI_API_KEY is not set`）。
- `guard1` 语义随之改为"env 为空时退回 google"；`backend/.env` 会覆盖进程 env。
- 离线守卫 8/8 PASS。
- 实跑全链路（`generate_query` → `web_research` → `reflection` → `finalize_answer`）跑通：PONG 2.34 s、结构化输出 5.28 s（走 `with_structured_output`，JSON 文本回退未触发）、Bing 检索 5 条 3.6 s，答案含 markdown 引用。
- 网络可达性（本机实测）：`www.bing.com` 200、`serper.dev` 200、`api.tavily.com` 401（需 key）、`duckduckgo.com` / `html.duckduckgo.com` / `searx.be` / `search.brave.com` 连接超时或 202 ⇒ 本机默认走 `SEARCH_PROVIDER=bing`（免 key）。
- `langgraph dev` 需要 `langgraph-cli[inmem]`（`langgraph_api` 模块），当前 venv 未装；`make dev` 本机不可用。
- 前端：`npm run build` 在允许 spawn 子进程且 `TMP` 可写的条件下成功（`dist/assets/index-ChDCK4qh.js` 571.53 kB、`index-C9TXUUZZ.css` 37.13 kB）；沙盒内失败点是 esbuild spawn（named pipe）与写系统 temp 被拒，不是 Node 版本/legacy 问题。

## 2026-11-09 16:45 — `langgraph dev` 实跑验证（服务端已起，HTTP 端到端跑通）

| 项 | 结论 | 证据 |
|---|---|---|
| `colorlog` | 必需依赖，已补进 `backend/requirements.txt`（此前缺失 → uvicorn `ValueError: Unable to configure formatter 'simple'`） | `pip install colorlog` 后该报错消失 |
| `.env` / `.env.example` 必须纯 ASCII | `python-dotenv` 按 Windows locale（gbk）解码，中文注释触发 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x80` | 改纯 ASCII 后 `langgraph.json` 的 `"env": ".env"` 正常加载 |
| `PYTHONUTF8=1`（或 `chcp 65001`）必需 | `langgraph_api/validation.py:14` 用 `f.read()` 读 openapi 文件，中文 locale 下 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94` | 设 `PYTHONUTF8=1` 后服务正常启动 |
| `agent` 包必须可 import | `langgraph.json` 的 graph 是 `./src/agent/graph.py`，但代码 import 的是 `from agent...`；不装项目时 `ModuleNotFoundError: No module named 'agent'` | 两种解法：`cd backend; pip install -e .`（`pyproject.toml` 的 project name 就是 `agent`），或 `$env:PYTHONPATH="D:\...\backend\src"` |
| 沙盒内必须 `--no-reload` | `langgraph dev` 默认 reload=True → multiprocessing 需要 named pipe，沙盒内 `PermissionError: [WinError 5]`（文档边界）；`--no-reload` 后 uvicorn 单进程可跑 | 服务起在 `http://127.0.0.1:2024`，assistant `agent`（`pro-search-agent`）加载成功 |
| 端到端 HTTP 验证 | `POST /threads` → `POST /threads/{id}/runs` → `status=success`，答案含 20 条引用来源 | run `01a1bf80-31c2-7282-8d64-a3c873ca0a1a`；`POST /assistants/search` 返回 assistant_id `fe096781-5601-53d2-b2f6-0d3403f7e9ca` |
| 输入口径（易踩） | `generate_query` 取的研究主题是 `get_research_topic(state["messages"])`，不是 `input.query`；`input` 必须给 `messages`，给 `query` 会被忽略并退化成"当前日期相关通用检索" | 传 `query` 时生成通用 queries；传 `messages` 时 queries 紧扣问题 |

## 2026-11-09 17:15 — 前端 model 下拉框真正生效（此前被 env 静默忽略）

| 文件 | 改动 | 原因 | 验证方式 |
|---|---|---|---|
| `backend/src/agent/configuration.py` | 优先级改为 `config.configurable > env > 字段默认值`；新增 `model` 字段与 `resolve_model(node_default, state_value)` | 原写法 `os.environ.get(name.upper(), configurable.get(name))` 让 env 永远赢 ⇒ 前端下拉框的值被静默丢弃（`.env` 里三个模型名正好都是本地模型，所以看起来"正常"） | guard 9–11 |
| `backend/src/agent/llm.py` | `get_llm(model, temp, max_retries, provider=None)`；新增 `resolve_provider(model)` 支持 `MODEL_PROVIDER_MAP`（`name=provider` 对，未列出的回退 `LLM_PROVIDER`）；`get_model_default()`；`LLM_DEBUG=1` 时打印每次实际用的 provider/model | 一个下拉框可能同时含 Google 与 OpenAI 兼容模型；且需要能看到节点实际解析成哪个模型 | guard 12；实跑日志 4 行 `[llm] provider=openai model=qwen3.8-flash-next-iq2_xs` |
| `backend/src/agent/graph.py` | 四个节点统一走 `configurable.resolve_model(...)`；`web_research` 的 google grounding 分支加 `resolve_provider(model) != "google"` 判断 | `WebSearchState`（`Send` 传的精简 state）不含 `reasoning_model`，只靠 state input 时该节点拿不到前端选择 | 实跑 run `01a1bf95-3366-7181-8c38-d690b0326fd6`：进程 env `MODEL=probe-env-default`，请求 config 传真实模型名 → 四个节点日志都打印 config 的值，status=success |
| `frontend/src/lib/modelOptions.ts`（新增） | 下拉框选项来自 `VITE_MODEL_OPTIONS`（`name|label` 逗号分隔），默认值 `VITE_DEFAULT_MODEL`，空则回退三个 Gemini 名 | 硬编码的 Gemini 名字与 OpenAI 兼容端点服务的模型无关；换模型不应改代码 | 实跑：`frontend/.env` 设 `VITE_MODEL_OPTIONS=qwen3.8-flash-next-iq2_xs|Qwen 3.8 Flash` |
| `frontend/src/components/InputForm.tsx` | Model 下拉框由硬编码三项改为遍历 `MODEL_OPTIONS`；默认 `DEFAULT_MODEL` | 同上 | Node 24 type-stripping 直跑该模块：`parseOptions("qwen3.8-flash-next-iq2_xs|Qwen 3.8 Flash,deepseek-chat|DeepSeek")` → 2 项，空串 → 回退三项 Gemini，默认取第一项 |
| `frontend/src/App.tsx` | `thread.submit(values, { config: { configurable: { model } } })` | 后端 config_schema 是 `Configuration`，model 必须走 config 才能覆盖所有节点（state input 只对部分节点可见） | `SubmitOptions.config` 是 SDK 支持的入参（`@langchain/langgraph-sdk` 0.0.74 `dist/react/stream.d.ts`） |
| `backend/test_adapter.py` | 新增 guard 9–12（config 优先、env 作默认、resolve_model 顺序、provider map） | 锁住"前端选择被 env 吃掉"这个回归 | `cd backend && .\.venv\Scripts\python.exe test_adapter.py` → 12 passed, 0 failed |

## 2026-11-10 — README 更新（把实测口径写进文档）

| 文件 | 改动 | 原因 | 验证方式 |
|---|---|---|---|
| `README.md` | 新增三节：`Pluggable LLM Provider and Search`（env 表：`LLM_PROVIDER` / `LOCAL_BASE_URL` / `LOCAL_MODEL` / `MODEL_PROVIDER_MAP` / `LLM_DEBUG` / `SEARCH_PROVIDER` + 各 key；优先级 `config.configurable > env > 字段默认值`；前端 `VITE_MODEL_OPTIONS` / `VITE_DEFAULT_MODEL` 与"改后需重启"）、`Research Budget (the Effort dropdown)`（low 1/1、medium 3/3、high 5/10，回环退出条件与检索质量影响）、`Development Notes (Windows, measured)`（纯 ASCII env/requirements、`PYTHONUTF8=1`、`colorlog`、`pip install -e .` 或 `PYTHONPATH=backend\src`、沙盒内 `--no-reload`、`make` 不可用、vite 绑 `localhost` → `::1`、`assistant_id` 必须在 body、答案在 `messages[-1]`）；开头与 Features 把"Google Search API / Gemini 绑定"改成可插拔口径；Technologies 补 OpenAI 兼容与检索 provider | README 仍写着必须 `GEMINI_API_KEY` 与 Google Search，实际已经可插拔且模型选择走 config；文档与代码不符 | 第二通道 `Get-Content` 复核：175 行，三个新节标题与关键串（`MODEL_PROVIDER_MAP`、`LLM_DEBUG`、`VITE_MODEL_OPTIONS`、Effort 表）均在盘上 |
