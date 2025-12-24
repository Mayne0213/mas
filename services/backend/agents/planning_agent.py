"""
Planning Agent (Claude 4.5)
작업 계획 수립 및 단계별 태스크 정의
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json


# Claude 4.5 모델 초기화
claude_planning = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.3  # 계획은 더 deterministic하게
)


PLANNING_PROMPT = """당신은 Multi-Agent System의 **Planning Agent**입니다.

## 역할
- 사용자 요청을 분석하여 구체적인 작업 계획 수립
- 단계별 태스크 정의 및 우선순위 설정
- 필요한 정보 수집 항목 명시
- 성공 기준 정의

## 계획 수립 프로세스
1. 요청 분석: 사용자가 원하는 것이 무엇인지 명확히 파악
2. 작업 분류: Backend / Frontend / Infrastructure 중 어느 영역인지
3. 단계 분해: 큰 작업을 작은 단계로 나누기
4. 정보 필요성 파악: 어떤 정보를 수집해야 하는지
5. 성공 기준 설정: 언제 작업이 완료된 것으로 볼지

## 자동 탐색 요청 처리
사용자가 다음과 같은 요청을 하면:
- "폴더/파일 찾아서 해줘"
- "현재 k8s 상태 분석해서 해결책 제시해줘"
- "Projects에 어떤 레포가 있는지 확인해줘"
- "문제를 찾아서 해결해줘"

**research_needed에 자동 탐색이 필요함을 명시**하세요:
- "Projects 폴더 내의 모든 Git 레포지토리 목록 조사"
- "Kubernetes 클러스터 전체 상태 분석 (Pod, Deployment, Service)"
- "특정 폴더/파일 자동 탐색 및 위치 확인"
- "에러 로그 분석 및 원인 파악"

Research Agent는 경로를 모르더라도 자동으로 찾아서 작업할 수 있습니다.

## 출력 형식 (JSON)
반드시 다음 JSON 형식으로 출력하세요:
```json
{
  "task_type": "backend | frontend | infrastructure | mixed",
  "summary": "작업 요약 (1-2문장)",
  "steps": [
    {"step": 1, "description": "단계 설명", "agent": "research|code_backend|code_frontend|code_infrastructure"},
    {"step": 2, "description": "단계 설명", "agent": "research|code_backend|code_frontend|code_infrastructure"}
  ],
  "research_needed": [
    "수집할 정보 1",
    "수집할 정보 2"
  ],
  "success_criteria": [
    "성공 기준 1",
    "성공 기준 2"
  ]
}
```

## 예시
요청: "PostgreSQL 데이터베이스에 사용자 테이블 추가"
출력:
```json
{
  "task_type": "backend",
  "summary": "PostgreSQL에 users 테이블을 생성하고 기본 스키마 정의",
  "steps": [
    {"step": 1, "description": "현재 DB 스키마 확인", "agent": "research"},
    {"step": 2, "description": "users 테이블 마이그레이션 스크립트 작성", "agent": "code_backend"},
    {"step": 3, "description": "테이블 생성 및 검증", "agent": "code_backend"}
  ],
  "research_needed": [
    "기존 PostgreSQL 테이블 목록",
    "현재 사용 중인 ORM/마이그레이션 도구"
  ],
  "success_criteria": [
    "users 테이블이 정상적으로 생성됨",
    "기본 컬럼(id, name, email, created_at)이 포함됨"
  ]
}
```
"""


def planning_node(state: AgentState) -> AgentState:
    """
    Planning 노드: 작업 계획 수립
    """
    messages = state["messages"]
    user_request = messages[0]["content"] if messages else ""

    # Claude 호출
    response = claude_planning.invoke([
        SystemMessage(content=PLANNING_PROMPT),
        HumanMessage(content=f"사용자 요청: {user_request}")
    ])

    content = response.content

    # JSON 파싱 시도
    try:
        # JSON 블록 추출
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content

        task_plan = json.loads(json_str)
    except Exception as e:
        task_plan = {
            "task_type": "mixed",
            "summary": "계획 파싱 실패, Research Agent로 이동",
            "steps": [{"step": 1, "description": "정보 수집", "agent": "research"}],
            "research_needed": ["사용자 요청 관련 정보"],
            "success_criteria": ["작업 완료"],
            "error": str(e)
        }

    # 상태 업데이트
    state["task_plan"] = task_plan
    state["messages"].append({
        "role": "planning",
        "content": content
    })
    state["current_agent"] = "orchestrator"  # 다시 orchestrator로 반환

    return state
