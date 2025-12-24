"""
공유 상태 정의 (AgentState)
K8s 인프라 분석 및 계획 수립에 특화
"""
from typing import TypedDict, Optional


class AgentState(TypedDict):
    """에이전트 간 공유되는 상태"""
    messages: list                      # 대화 메시지 이력
    current_agent: str                  # 현재 활성 에이전트
    task_plan: Optional[dict]           # Planning Agent 출력 (폴더 구조, YAML 설계)
    research_data: Optional[dict]       # Research Agent 출력 (K8s 클러스터 상태)
    implementation_prompt: Optional[str] # Prompt Generator 출력 (Markdown 프롬프트)
    iteration_count: int                # 반복 횟수 (최대 2회)
    error: Optional[str]                # 에러 메시지
