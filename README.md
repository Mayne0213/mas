# MAS (Multi-Agent System)

**K8s Infrastructure Planning System** - AI agents that analyze your Kubernetes cluster and generate implementation plans.

## 🎯 What is this?

MAS는 Kubernetes 클러스터 상태를 분석하고, 인프라 배포 계획을 수립하는 AI 에이전트 시스템입니다.

**사용 시나리오:**
1. "Tekton을 도입하고 싶어" → 클러스터 분석 → YAML 구조 설계 → 구현 가이드 생성
2. 생성된 Markdown 프롬프트를 복사해서 다른 AI (Claude Code, ChatGPT 등)에 붙여넣기
3. 실제 코드 구현은 다른 AI가 담당

## 🤖 Agents

### Planning Agent (Claude 4.5)
- 폴더 구조 설계 (deploy/tool/base, overlays/prod, etc.)
- YAML 파일 조직화
- K8s 리소스 계획 (Namespace, Deployment, Service, etc.)

### Research Agent (Groq Llama 3.3)
- kubectl 명령어로 클러스터 상태 분석
- 기존 리소스 확인 (namespaces, storage classes, quotas)
- 호환성 검토

### Prompt Generator (Claude 4.5)
- Markdown 형식의 구현 가이드 생성
- YAML 예시 포함
- 검증 명령어 제공

### Tech stack
- **Backend**: LangGraph + LangChain + FastAPI
- **UI**: Chainlit (chat-style UI)
- **Database**: PostgreSQL (CNPG)
- **Cache**: Redis
- **LLMs**: Claude API (Orchestrator, Planning, Prompt Gen) + Groq Llama 3.3 (Research)
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

### Example 1: Deploy Tekton

```text
User: "Tekton을 도입하고 싶어"

🎼 Orchestrator:
  → routes to Planning Agent

📋 Planning Agent:
  → designs folder structure: deploy/tekton/{base,overlays/prod}
  → plans K8s resources: Namespace, RBAC, Deployments, Services
  → identifies research needs

🔍 Research Agent:
  → runs: kubectl get namespaces, kubectl get storageclasses
  → checks: existing tekton resources, cluster version
  → analyzes: available resources and quotas

📝 Prompt Generator:
  → generates comprehensive Markdown implementation guide
  → includes: YAML examples, folder structure, validation commands

✨ Output: Markdown prompt ready to copy-paste into Claude Code/ChatGPT
```

### Example 2: Deploy Harbor Registry

```text
User: "Harbor를 배포하려고 해"

→ Planning: folder structure + YAML organization
→ Research: storage classes, ingress controllers, TLS setup
→ Prompt Gen: Markdown guide with Harbor Helm values, ingress config, etc.

✨ Copy the prompt → Paste into another AI → Get actual implementation
```

### Example 3: Deploy Prometheus

```text
User: "Prometheus를 설치하고 싶어"

→ Planning: monitoring stack structure (Prometheus, Grafana, AlertManager)
→ Research: existing ServiceMonitors, PVC requirements
→ Prompt Gen: Complete implementation guide

✨ Result: Ready-to-use prompt for code generation
```

---

## 🔧 Workflow

```
User Input: "Deploy X"
     ↓
Orchestrator (조율)
     ↓
Planning Agent (구조 설계)
     ↓
Research Agent (클러스터 분석)
     ↓
Prompt Generator (가이드 생성)
     ↓
Output: Markdown Implementation Guide
     ↓
User copies → Pastes to Claude Code/ChatGPT → Gets actual code
```

## 🤝 Contributing

Contributions are welcome:
- Improve Planning Agent prompts for better folder structures
- Enhance Research Agent kubectl commands
- Add more infrastructure tools (Harbor, Tekton, CNPG, MetalLB, etc.)
- Better Markdown template for Prompt Generator

Feel free to open issues or PRs in your Git repository.

---

## 📄 License

MIT

