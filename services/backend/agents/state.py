"""
공유 상태 정의 (AgentState)
"""
from typing import TypedDict, Optional


class AgentState(TypedDict):
    """에이전트 간 공유되는 상태"""
    messages: list                  # 대화 메시지 이력
    current_agent: str              # 현재 활성 에이전트
    task_plan: Optional[dict]       # Planning Agent 출력
    research_data: Optional[dict]   # Research Agent 출력
    code_outputs: dict              # Code Agent(s) 출력
    review_feedback: Optional[dict] # Review Agent 출력
    iteration_count: int            # 반복 횟수 (최대 3회)
    is_approved: bool               # 최종 승인 여부
    error: Optional[str]            # 에러 메시지
