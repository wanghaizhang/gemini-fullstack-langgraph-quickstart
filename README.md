# Gemini Fullstack LangGraph Quickstart

This project demonstrates a fullstack application using a React frontend and a LangGraph-powered backend agent. The agent is designed to perform comprehensive research on a user's query by dynamically generating search terms, querying the web through a pluggable search provider, reflecting on the results to identify knowledge gaps, and iteratively refining its search until it can provide a well-supported answer with citations. This application serves as an example of building research-augmented conversational AI using LangGraph and Google's Gemini models.

<img src="./app.png" title="Gemini Fullstack LangGraph" alt="Gemini Fullstack LangGraph" width="90%">

## Features

- 💬 Fullstack application with a React frontend and LangGraph backend.
- 🧠 Powered by a LangGraph agent for advanced research and conversational AI.
- 🔍 Dynamic search query generation using Google Gemini models.
- 🌐 Integrated web research through a pluggable search provider (Google grounding, or `duckduckgo` / `tavily` / `searxng` / `bing` / `serper` / `none`).
- 🔌 Pluggable LLM provider: Gemini, or any OpenAI-compatible endpoint (Ollama / vLLM / DeepSeek / LM Studio) via `LLM_PROVIDER=openai`.
- 🎛️ Model dropdown driven by `frontend/.env` (`VITE_MODEL_OPTIONS`, `VITE_DEFAULT_MODEL`) — swapping models needs no code change.
- 🤔 Reflective reasoning to identify knowledge gaps and refine searches.
- 📄 Generates answers with citations from gathered sources.
- 🔄 Hot-reloading for both frontend and backend during development.

## Project Structure

The project is divided into two main directories:

-   `frontend/`: Contains the React application built with Vite.
-   `backend/`: Contains the LangGraph/FastAPI application, including the research agent logic.

## Getting Started: Development and Local Testing

Follow these steps to get the application running locally for development and testing.

**1. Prerequisites:**

-   Node.js and npm (or yarn/pnpm)
-   Python 3.11+
-   **`GEMINI_API_KEY`**: The backend agent requires a Google Gemini API key.
    1.  Navigate to the `backend/` directory.
    2.  Create a file named `.env` by copying the `backend/.env.example` file.
    3.  Open the `.env` file and add your Gemini API key: `GEMINI_API_KEY="YOUR_ACTUAL_API_KEY"`

**2. Install Dependencies:**

**Backend:**

```bash
cd backend
pip install .
```

**Frontend:**

```bash
cd frontend
npm install
```

**3. Run Development Servers:**

**Backend & Frontend:**

```bash
make dev
```
This will run the backend and frontend development servers.    Open your browser and navigate to the frontend development server URL (e.g., `http://localhost:5173/app`).

_Alternatively, you can run the backend and frontend development servers separately. For the backend, open a terminal in the `backend/` directory and run `langgraph dev`. The backend API will be available at `http://127.0.0.1:2024`. It will also open a browser window to the LangGraph UI. For the frontend, open a terminal in the `frontend/` directory and run `npm run dev`. The frontend will be available at `http://localhost:5173`._

## Development Notes (Windows, measured)

- Python 3.11+. `python` can be the Microsoft Store alias (unusable); use `py -3.11`.
- Install dependencies into the repo's own `.venv` (`pip install -e .` — the project name is `agent`, which is what makes `from agent...` importable). Keep pip caches outside the repo (`--cache-dir <workspace>`); `requirements.txt` mirrors `pyproject.toml` and stays ASCII.
- `langgraph dev` needs `langgraph-cli[inmem]` and `colorlog` (missing `colorlog` → uvicorn `ValueError: Unable to configure formatter 'simple'`), and `PYTHONUTF8=1` (the API reads an OpenAPI file with `f.read()`, which fails under a `gbk` locale).
- In a confined sandbox, run `langgraph dev --no-reload --no-browser`: reload uses multiprocessing named pipes and fails with `WinError 5`.
- `make dev` requires `make`; run `langgraph dev` and `npm run dev` separately if it is unavailable.
- Frontend: use `npm install --ignore-scripts` when postinstall spawns are blocked, and run `npm run dev` in a normal shell — vite bundles its config through esbuild, which spawns a child process.
- vite binds `localhost`, which on some Windows setups resolves to IPv6 `::1`: `http://localhost:5173/app/` answers while `http://127.0.0.1:5173/` does not. Add `--host` to expose it on IPv4/LAN.
- API details: `assistant_id` must be in the body of `POST /threads/{thread_id}/runs` (in the query string it returns 422); the final answer lives in `messages[-1]` — the state has no `answer` key. Every deviation from upstream is recorded in [CHANGES.md](CHANGES.md).

## Pluggable LLM Provider and Search

Nothing is fixed at import time: `backend/src/agent/llm.py` and `backend/src/agent/search.py` read the settings on each call, because `agent/__init__.py` imports `graph` before `load_dotenv()` runs (reading them at import time would see empty values).

Settings live in `backend/.env` — keep that file ASCII only, `python-dotenv` decodes it with the Windows locale and non-ASCII comments raise `UnicodeDecodeError`.

| Variable | Values | Notes |
|---|---|---|
| `LLM_PROVIDER` | `google` \| `openai` | `openai` covers any OpenAI-compatible endpoint (Ollama, vLLM, DeepSeek, LM Studio, official OpenAI) |
| `LOCAL_BASE_URL` | e.g. `http://127.0.0.1:8081/v1` | used when `LLM_PROVIDER=openai` |
| `LOCAL_MODEL` | model name served by the endpoint | default when the request does not carry a model |
| `MODEL_PROVIDER_MAP` | `name=provider` pairs, comma separated | per-model provider, so one dropdown can mix Google and OpenAI-compatible models; unlisted names fall back to `LLM_PROVIDER` |
| `LLM_DEBUG` | `1` | prints the provider/model actually used for every call |
| `SEARCH_PROVIDER` | `duckduckgo` \| `tavily` \| `searxng` \| `bing` \| `serper` \| `none` | `bing` works without a key; Google grounding is used only when the resolved provider is `google` |
| `TAVILY_API_KEY` / `SERPER_API_KEY` / `SEARXNG_URL` | — | required for those providers |
| `GEMINI_API_KEY` | — | required only when the resolved provider is `google` |

Precedence is **per-request `config.configurable` > env > field default** (`Configuration.from_runnable_config`). The frontend sends the dropdown value as `config.configurable.model`, which is what makes it reach every node — `web_research` receives the slim state created by `Send` (`search_query`, `id`) and cannot see a model passed through state input alone.

**Model dropdown (frontend).** Options come from `frontend/.env`, no code change needed:

```
VITE_MODEL_OPTIONS=qwen3.8-flash-next-iq2_xs|Qwen 3.8 Flash,deepseek-chat|DeepSeek
VITE_DEFAULT_MODEL=qwen3.8-flash-next-iq2_xs
```

The list must contain model names the endpoint actually serves. Vite reads `.env` only at startup, so restart `npm run dev` after changing it.

## Research Budget (the Effort dropdown)

The number of rounds is bounded by two numbers the frontend sends with each message ([`frontend/src/App.tsx`](frontend/src/App.tsx)):

| Effort | initial search queries | max research loops |
|---|---|---|
| low | 1 | 1 |
| medium (default) | 3 | 3 |
| high | 5 | 10 |

Each query fans out into its own `web_research` node, and each loop can add one more query per knowledge gap, so a medium run looks like: 1 initial fan-out (3 searches) + up to 3 loops (reflection + follow-up searches) + finalize. The loop exits earlier when the model reports the information as sufficient; weak search results (dictionary pages, ads) keep the knowledge gap open, so the run is more likely to hit the cap. The values are `state` inputs; the backend falls back to `number_of_initial_queries` / `max_research_loops` only when the caller does not send them.

## How the Backend Agent Works (High-Level)

The core of the backend is a LangGraph agent defined in `backend/src/agent/graph.py`. It follows these steps:

<img src="./agent.png" title="Agent Flow" alt="Agent Flow" width="50%">

1.  **Generate Initial Queries:** Based on your input, it generates a set of initial search queries using a Gemini model.
2.  **Web Research:** For each query, it calls the configured model with the configured search provider — Google grounding when the provider is `google`, otherwise a real search API (`duckduckgo` / `tavily` / `searxng` / `bing` / `serper`), and the model summarises the returned snippets.
3.  **Reflection & Knowledge Gap Analysis:** The agent analyzes the search results to determine if the information is sufficient or if there are knowledge gaps. It uses a Gemini model for this reflection process.
4.  **Iterative Refinement:** If gaps are found or the information is insufficient, it generates follow-up queries and repeats the web research and reflection steps (up to a configured maximum number of loops).
5.  **Finalize Answer:** Once the research is deemed sufficient, the agent synthesizes the gathered information into a coherent answer, including citations from the web sources, using a Gemini model.

## CLI Example

For quick one-off questions you can execute the agent from the command line. The
script `backend/examples/cli_research.py` runs the LangGraph agent and prints the
final answer:

```bash
cd backend
python examples/cli_research.py "What are the latest trends in renewable energy?"
```


## Deployment

In production, the backend server serves the optimized static frontend build. LangGraph requires a Redis instance and a Postgres database. Redis is used as a pub-sub broker to enable streaming real time output from background runs. Postgres is used to store assistants, threads, runs, persist thread state and long term memory, and to manage the state of the background task queue with 'exactly once' semantics. For more details on how to deploy the backend server, take a look at the [LangGraph Documentation](https://langchain-ai.github.io/langgraph/concepts/deployment_options/). Below is an example of how to build a Docker image that includes the optimized frontend build and the backend server and run it via `docker-compose`.

_Note: For the docker-compose.yml example you need a LangSmith API key, you can get one from [LangSmith](https://smith.langchain.com/settings)._

_Note: If you are not running the docker-compose.yml example or exposing the backend server to the public internet, you should update the `apiUrl` in the `frontend/src/App.tsx` file to your host. Currently the `apiUrl` is set to `http://localhost:8123` for docker-compose or `http://localhost:2024` for development._

**1. Build the Docker Image:**

   Run the following command from the **project root directory**:
   ```bash
   docker build -t gemini-fullstack-langgraph -f Dockerfile .
   ```
**2. Run the Production Server:**

   ```bash
   GEMINI_API_KEY=<your_gemini_api_key> LANGSMITH_API_KEY=<your_langsmith_api_key> docker-compose up
   ```

Open your browser and navigate to `http://localhost:8123/app/` to see the application. The API will be available at `http://localhost:8123`.

## Technologies Used

- [React](https://reactjs.org/) (with [Vite](https://vitejs.dev/)) - For the frontend user interface.
- [Tailwind CSS](https://tailwindcss.com/) - For styling.
- [Shadcn UI](https://ui.shadcn.com/) - For components.
- [LangGraph](https://github.com/langchain-ai/langgraph) - For building the backend research agent.
- [Google Gemini](https://ai.google.dev/models/gemini) - LLM for query generation, reflection, and answer synthesis (default provider).
- [LangChain OpenAI adapter](https://python.langchain.com/docs/integrations/chat/openai/) - Same agent against any OpenAI-compatible endpoint.
- Pluggable search backends - `duckduckgo` / `tavily` / `searxng` / `bing` / `serper`, or Google grounding when the provider is `google`.

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details. 
