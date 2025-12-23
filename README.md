# MAS (Multi-Agent System)

MAS is a unified UI and orchestration layer for multiple AI agents (similar to ChatGPT, Claude, Gemini), running on your own Kubernetes cluster.

## 🎯 Architecture

### Agents
- **Claude Code (Orchestrator)**: overall coordinator & DevOps expert  
- **Qwen Backend**: backend engineer (FastAPI, Node.js)  
- **Qwen Frontend**: frontend engineer (Next.js, React)  
- **Qwen SRE**: monitoring & reliability engineer  

### Tech stack
- **Backend**: LangGraph + LangChain + FastAPI  
- **UI**: Chainlit (chat-style UI)  
- **Database**: PostgreSQL (CNPG)  
- **Cache**: Redis  
- **LLMs**: Claude API + **Groq Llama 3.x** (OpenAI-compatible API)  
- **Deploy**: Kubernetes + ArgoCD  

---

## 🚀 Local development

### 1. Run with Docker Compose

```bash
cd deploy/docker

# Copy or create .env and fill in your API keys
# (ANTHROPIC_API_KEY, GROQ_API_KEY, etc.)

# Start the full stack
docker compose up -d

# Tail logs
docker compose logs -f mas
```

Open: `http://localhost:8000`

### 2. Run backend directly (Python)

```bash
cd services/backend

# Create venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# Edit .env and set your API keys

# Run Chainlit app
chainlit run chainlit_app.py
```

---

## ☸️ Kubernetes deployment

### 1. Create namespace and secrets

```bash
kubectl create namespace mas

kubectl create secret generic mas-api-keys \
  --from-literal=anthropic-api-key=YOUR_CLAUDE_KEY \
  --from-literal=openai-api-key=YOUR_OPENAI_KEY \
  --from-literal=google-api-key=YOUR_GEMINI_KEY \
  -n mas
```

### 2. Deploy via ArgoCD

```bash
# Create ArgoCD Application
kubectl apply -f deploy/argocd/mas.yaml

# Sync and check status
argocd app sync mas
argocd app get mas
```

### 3. Deploy from your server (example)

```bash
# SSH into your k3s master
ssh oracle-master

# Apply ArgoCD Application
sudo kubectl apply -f /path/to/deploy/argocd/mas.yaml

# Check status
sudo kubectl get pods -n mas
sudo kubectl logs -f deployment/mas -n mas
```

Ingress example (if configured): `https://mas.mayne.vcn`

---

## 🎨 UI customization

### Chainlit theme & behavior

You can customize the UI via `services/backend/.chainlit`:

```toml
[UI]
name = "MAS"
show_readme_as_default = true
default_collapse_content = true
```

### Agent prompts

System prompts for each agent live in `services/backend/agents.py`.  
You can tune:
- how the **Orchestrator** routes tasks  
- coding style of backend/frontend agents  
- SRE troubleshooting behavior  

---

## 📊 Observability

### Prometheus ServiceMonitor (example)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mas
  namespace: mas
spec:
  selector:
    matchLabels:
      app: mas
  endpoints:
  - port: http
    path: /metrics
```

### Grafana dashboards

Recommended panels:
- LangGraph workflow metrics  
- Per-agent latency & error rate  
- Token usage and cost estimates  
- Backend API latency & 5xx rate  

---

## 🔧 Advanced features

### 1. MCP (Model Context Protocol) with Claude

Using Claude Code as Orchestrator, MAS can access:
- Filesystem (read/write project files)  
- Git (status, commit, push, PR)  
- SSH (run remote commands on your servers)  
- PostgreSQL (schema inspection, migrations, queries)  
- Kubernetes (kubectl via MCP tool)  

This allows fully automated workflows like:
- “Create a new service, add deployment manifests, and deploy to k3s.”  
- “Debug failing pods and propose a fix, then open a PR.”  

### 2. Multi-agent collaboration (LangGraph)

Typical workflow:

```text
User request
  ↓
Claude Orchestrator
  ↓ decides which agent(s) to call
Backend Dev → Frontend Dev → SRE
  ↓
Claude Orchestrator (review & summary)
  ↓
Final answer to user
```

Examples:
- Full‑stack feature (API + UI + monitoring)  
- Infra rollout (Harbor, Tekton, CNPG, MetalLB) with validation  

---

## 📝 Usage examples

### Backend API request

```text
User: "Create a signup API with FastAPI.
       Use PostgreSQL and JWT tokens."

🎼 Orchestrator:
  → routes to Qwen Backend

⚙️ Qwen Backend:
  → generates FastAPI router, Pydantic models, DB schema, JWT logic

🎼 Orchestrator:
  → reviews, suggests improvements, and outputs final code snippet & file layout
```

### Frontend component request

```text
User: "Build a responsive dashboard chart component using Recharts."

🎼 Orchestrator:
  → routes to Qwen Frontend

🎨 Qwen Frontend:
  → generates a Next.js/React component with TypeScript and responsive styles

🎼 Orchestrator:
  → explains how to integrate it into your existing app
```

### Infra / SRE request

```text
User: "Prometheus is firing high memory alerts for the PostgreSQL pod.
       Help me stabilize it."

🎼 Orchestrator:
  → routes to Qwen SRE

📊 Qwen SRE:
  → analyzes metrics & logs (conceptually),
    proposes tuning (Postgres config, indexes, pooler),
    and suggests alert threshold adjustments.
```

---

## 🤝 Contributing

Contributions are welcome:
- New agents (e.g., data engineer, security engineer)  
- New tools (Harbor, Tekton, CNPG, MetalLB integrations)  
- Better prompts and workflows  
- Docs and examples  

Feel free to open issues or PRs in your Git repository.

---

## 📄 License

MIT

