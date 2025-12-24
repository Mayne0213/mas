# MAS (Multi-Agent System)

**K8s 인프라 분석 & 의사결정 시스템** - 클러스터를 분석하고 도구 도입 여부를 결정해주는 AI 시스템

## 🎯 What is this?

MAS는 Kubernetes 클러스터 상태를 분석하고, **도구 도입 추천/비추천을 결정**해주는 AI 에이전트 시스템입니다.

**사용 시나리오:**
1. "Tekton 도입 여부를 결정해줘" → 클러스터 분석 → **도입 추천/비추천 결정**
2. 한국어로 이유, 대안, 구현 가이드 제공
3. 기술적 세부사항 없이 **명확한 결론** 제시

## 🤖 Agents

### Planning Agent (Claude 4.5)
- 도구 요구사항 분석
- 필요한 K8s 리소스 파악
- 확인이 필요한 클러스터 정보 정의

### Research Agent (Groq Llama 3.3)
- kubectl 명령어로 클러스터 상태 분석
- 기존 도구 확인 (ArgoCD, Gitea, Prometheus 등)
- 리소스 사용률 및 버전 확인

### Decision Agent (Claude 4.5)
- **도입 추천/비추천 결정** (한국어)
- 명확한 이유 제시
- 대안 제시 (비추천인 경우)
- 간단한 구현 가이드 (추천인 경우)

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

### Example 1: Tekton 도입 여부 결정

```text
User: "Tekton 도입 여부를 결정해줘"

🎼 Orchestrator → 조율

📋 Planning Agent:
  → Tekton 요구사항: Namespace, CRDs, Controllers
  → 필요 리소스: 2 CPU, 4GB RAM
  → 확인 필요: 기존 CI/CD 도구, K8s 버전

🔍 Research Agent:
  → kubectl get nodes: v1.33.6, 3 nodes ✓
  → kubectl get pods -A: ArgoCD 운영 중 발견
  → Gitea Actions 사용 가능 확인

💡 Decision Agent:
  ❌ Tekton 도입 비추천

  이유:
  - ArgoCD + Gitea Actions로 충분
  - 추가 리소스 소비 불필요
  - 학습 곡선 및 유지보수 부담

  대안:
  - Gitea Actions 활용 (이미 설치됨)
  - ArgoCD로 배포 자동화 유지

✨ Output: 명확한 한국어 보고서
```

### Example 2: Harbor 필요성 분석

```text
User: "Harbor가 필요한지 분석해줘"

→ Planning: Harbor 요구사항 분석
→ Research: 기존 registry 확인 (Gitea Container Registry 발견)
→ Decision:
  ❌ Harbor 도입 비추천
  이유: Gitea Container Registry로 충분

✨ 사용자 친화적 한국어 결론
```

### Example 3: Prometheus 설치 여부

```text
User: "Prometheus를 설치해야 할까?"

→ Planning: Monitoring stack 요구사항
→ Research: 이미 Prometheus 운영 중 발견!
→ Decision:
  ✅ 이미 설치되어 있음
  현재 상태: monitoring namespace에서 정상 작동 중

✨ 중복 설치 방지
```

---

## 🔧 Workflow

```
User Input: "X 도입 여부를 결정해줘"
     ↓
Orchestrator (조율)
     ↓
Planning Agent (도구 요구사항 분석)
     ↓
Research Agent (클러스터 상태 분석)
     ↓
Decision Agent (한국어 의사결정 보고서)
     ↓
Output: ✅ 추천 또는 ❌ 비추천 (이유 포함)
```

## 📊 출력 예시

```markdown
# Tekton 도입 분석 결과

## 📊 현재 클러스터 상태
- Kubernetes 버전: v1.33.6
- 노드: 3개 (1 control-plane, 2 workers)
- 기존 CI/CD: ArgoCD, Gitea Actions
- 운영 애플리케이션: 15개

## 💡 권장사항: Tekton 도입 비추천

### ❌ 비추천 이유
1. ArgoCD + Gitea Actions 조합으로 충분
2. 추가 리소스 소비 (2 CPU, 4GB RAM)
3. 학습 곡선 및 운영 부담 증가

### 🔄 권장 대안
- Gitea Actions로 빌드 파이프라인 구성
- ArgoCD로 GitOps 배포 유지
- 필요시 GitHub Actions 연동

## 🎯 결론
현재 인프라로 충분하며, Tekton 도입은 불필요합니다.
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

