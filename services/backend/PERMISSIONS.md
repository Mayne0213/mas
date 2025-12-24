# MAS v2.0 권한 보고서

## 📋 에이전트별 권한 요약

### ✅ FULL WRITE ACCESS (bash_tools 사용)

모든 주요 에이전트가 `execute_bash` 도구를 통해 **무제한 write 권한**을 가지고 있습니다.

| 에이전트 | 모델 | bash_tools | 주요 권한 |
|----------|------|------------|-----------|
| **Orchestrator** | Claude 4.5 | ✅ | 모든 시스템 조회/검증, 긴급 직접 실행 |
| **Planning Agent** | Claude 4.5 | ❌ | 계획 수립만 (write 불필요) |
| **Research Agent** | Groq | ✅ | K8s, DB, Git, 파일 시스템 조회 |
| **Backend Agent** | Groq | ✅ | 파일 생성, Git 커밋, DB 마이그레이션 |
| **Frontend Agent** | Groq | ✅ | 컴포넌트/스타일 파일 생성, 빌드 |
| **Infrastructure Agent** | Groq | ✅ | YAML 생성, kubectl apply, 배포 |
| **Review Agent** | Claude | ✅ | 테스트 실행, 린터 실행, 배포 확인 |

## 🔧 bash_tool 권한 범위

### execute_bash 함수 분석

```python
def execute_bash(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    result = subprocess.run(
        command,
        shell=True,          # ⚠️ 무제한 bash 접근
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd
    )
```

**특징:**
- ❌ **샌드박스 없음**: `shell=True`로 모든 bash 명령어 실행 가능
- ❌ **권한 제한 없음**: sudo, rm -rf, dd 등 위험한 명령어도 실행 가능
- ❌ **경로 제한 없음**: 모든 파일 시스템 경로 접근 가능
- ✅ **타임아웃 설정**: 기본 30초, 최대 무제한 (파라미터로 조정 가능)
- ✅ **작업 디렉토리 지정**: `cwd` 파라미터로 실행 위치 제어 가능

### 실행 가능한 작업 예시

#### ✅ 조회 (Read)
```bash
# Kubernetes
kubectl get pods -n mas
kubectl describe deployment myapp

# PostgreSQL
psql -U bluemayne -d postgres -c "SELECT * FROM users"

# Git
git log -10 --oneline
git status

# 파일 시스템
ls -la /app/repos/
cat /app/repos/project/README.md
find /app/repos -name "*.yaml"

# Prometheus
curl http://prometheus:9090/api/v1/query?query=up
```

#### ✅ 생성/수정 (Write)
```bash
# 파일 생성
cat > /app/repos/project/api/users.py << EOF
code content here
EOF

# 디렉토리 생성
mkdir -p /app/repos/project/models

# Git 작업
cd /app/repos/project && git add . && git commit -m "Add feature"
cd /app/repos/project && git push origin main

# Kubernetes 배포
kubectl apply -f /app/repos/infrastructure/deployment.yaml
kubectl delete pod failing-pod -n mas

# Database 마이그레이션
cd /app/repos/project && alembic upgrade head

# Docker 빌드
docker build -t myapp:latest /app/repos/project

# 파일 수정
sed -i 's/old/new/g' /app/repos/project/config.yaml
```

#### ⚠️ 위험한 작업 (가능하지만 주의 필요)
```bash
# 파일 삭제
rm -rf /app/repos/old-project

# 권한 변경
chmod 777 /app/repos/project

# 시스템 명령어
sudo systemctl restart service
kill -9 <pid>

# 환경 변수 조작
export SECRET_KEY=new_value
```

## 🛡️ 보안 고려사항

### 현재 상태
- **보안 수준**: ⚠️ 낮음
- **이유**: 모든 에이전트가 무제한 bash 접근 권한 보유
- **리스크**:
  - LLM이 잘못된 명령어 생성 시 시스템 손상 가능
  - Prompt Injection 공격에 취약
  - 민감 정보 노출 가능

### 권장 보안 개선사항

#### 1. 경로 화이트리스트 (우선순위: 높음)
```python
ALLOWED_PATHS = [
    "/app/repos/",
    "/tmp/mas/",
    "/var/log/mas/"
]

def is_safe_path(command: str) -> bool:
    # 명령어에서 경로 추출 및 검증
    return any(path in command for path in ALLOWED_PATHS)
```

#### 2. 명령어 블랙리스트 (우선순위: 높음)
```python
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777",
    "sudo",
]
```

#### 3. 역할별 권한 분리 (우선순위: 중간)
```python
AGENT_PERMISSIONS = {
    "orchestrator": ["read", "write"],
    "planning": [],  # No bash access needed
    "research": ["read"],
    "code_backend": ["read", "write"],
    "code_frontend": ["read", "write"],
    "code_infrastructure": ["read", "write", "kubectl"],
    "review": ["read", "test"],
}
```

#### 4. 승인 워크플로우 (우선순위: 낮음)
```python
# 위험한 작업은 사용자 승인 필요
REQUIRES_APPROVAL = [
    "kubectl delete",
    "git push",
    "docker build",
    "rm -r",
]
```

## 📊 에이전트별 상세 권한

### 1. Orchestrator (Claude 4.5) ✅
**권한**: Full Write Access

**목적**:
- 긴급 상황 대응
- 빠른 상태 확인
- 다른 에이전트 실패 시 직접 실행

**사용 예시**:
```bash
kubectl get pods -n mas  # Pod 상태 확인
git status               # Git 상태 확인
cat /app/repos/project/README.md  # 빠른 파일 조회
```

---

### 2. Planning Agent (Claude 4.5) ❌
**권한**: No bash access

**이유**: 계획 수립만 수행, 실행 권한 불필요

---

### 3. Research Agent (Groq) ✅
**권한**: Full Write Access (주로 Read 사용)

**목적**:
- Kubernetes 클러스터 상태 조회
- PostgreSQL 데이터베이스 탐색
- Git 레포지토리 분석
- 파일 시스템 검색
- Prometheus 메트릭 수집

**사용 예시**:
```bash
# K8s 조회
kubectl get deployments -A
kubectl describe pod myapp-123 -n mas

# DB 조회
psql -U bluemayne -d postgres -c "\dt"
psql -U bluemayne -d postgres -c "SELECT * FROM users LIMIT 10"

# Git 조회
git log -10 --oneline
git diff main..feature-branch

# 파일 검색
find /app/repos -name "*.yaml"
grep -r "API_KEY" /app/repos/project/
```

---

### 4. Backend Agent (Groq) ✅
**권한**: Full Write Access

**목적**:
- FastAPI/Node.js 코드 작성
- 데이터베이스 마이그레이션
- API 파일 생성
- Git 커밋

**사용 예시**:
```bash
# 파일 생성
cat > /app/repos/project/api/users.py << 'EOF'
from fastapi import APIRouter
router = APIRouter()
EOF

# DB 마이그레이션
cd /app/repos/project && alembic upgrade head

# Git 커밋
cd /app/repos/project && git add . && git commit -m "Add user API"

# 테스트 실행
cd /app/repos/project && pytest tests/
```

---

### 5. Frontend Agent (Groq) ✅
**권한**: Full Write Access

**목적**:
- React/Next.js 컴포넌트 작성
- CSS/Tailwind 스타일 파일 생성
- 빌드 검증

**사용 예시**:
```bash
# 컴포넌트 생성
cat > /app/repos/project/src/components/UserCard.tsx << 'EOF'
export default function UserCard() { ... }
EOF

# 스타일 생성
cat > /app/repos/project/src/styles/UserCard.module.css << 'EOF'
.card { ... }
EOF

# 빌드 테스트
cd /app/repos/project && npm run build
cd /app/repos/project && npm test
```

---

### 6. Infrastructure Agent (Groq) ✅
**권한**: Full Write Access

**목적**:
- Kubernetes YAML 생성
- kubectl apply 실행
- Docker 빌드
- ArgoCD 설정

**사용 예시**:
```bash
# YAML 생성
cat > /app/repos/infrastructure/apps/myapp/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
...
EOF

# Kubernetes 배포
kubectl apply -f /app/repos/infrastructure/apps/myapp/

# Docker 빌드
docker build -t gitea0213.kro.kr/bluemayne/myapp:latest .
docker push gitea0213.kro.kr/bluemayne/myapp:latest

# ArgoCD 동기화
kubectl apply -f /app/repos/infrastructure/argocd/myapp.yaml
```

---

### 7. Review Agent (Claude) ✅
**권한**: Full Write Access (주로 Test 실행)

**목적**:
- 테스트 실행
- 린터 실행
- 빌드 검증
- 배포 확인

**사용 예시**:
```bash
# 테스트 실행
cd /app/repos/project && pytest tests/ -v
cd /app/repos/project && npm test

# 린터 실행
cd /app/repos/project && pylint src/
cd /app/repos/project && eslint src/

# 빌드 검증
cd /app/repos/project && docker build -t test:latest .

# 배포 확인
kubectl get pods -n mas
kubectl logs myapp-123 -n mas --tail=50
```

## 🎯 결론

### ✅ 모든 에이전트에 Write 권한 부여 완료

1. **Orchestrator**: ✅ bash_tools 추가 완료
2. **Planning**: ⚠️ 계획 수립만 수행, write 불필요
3. **Research**: ✅ 기존에 보유
4. **Backend**: ✅ 기존에 보유
5. **Frontend**: ✅ 기존에 보유
6. **Infrastructure**: ✅ 기존에 보유
7. **Review**: ✅ bash_tools 추가 완료

### 📈 권한 통계
- **bash_tools 보유**: 6/7 에이전트 (86%)
- **Write 작업 가능**: 6개 에이전트
- **Read 전용**: 0개 (Research도 write 권한 보유)
- **권한 없음**: 1개 (Planning Agent - 의도적)

### ⚠️ 주의사항
- 현재 **샌드박스 없음**, 모든 bash 명령어 실행 가능
- LLM의 올바른 프롬프트 엔지니어링이 보안의 핵심
- 프로덕션 환경에서는 위 보안 개선사항 적용 권장

---

**생성일**: 2024-12-24
**버전**: v2.0
**상태**: ✅ 모든 에이전트 write 권한 확인 완료
