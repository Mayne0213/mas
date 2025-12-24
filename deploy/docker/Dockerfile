FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치 (kubectl 포함)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libpq-dev \
    postgresql-client \
    wget \
    && rm -rf /var/lib/apt/lists/*

# kubectl 설치
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# pip 업그레이드
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY *.py .
COPY agents/ agents/
COPY tools/ tools/

# Chainlit 설정 디렉토리 미리 생성 (권한 문제 해결)
RUN mkdir -p /root/.chainlit

# Chainlit 포트
EXPOSE 8000

# .chainlit 파일이 있으면 삭제하고 Chainlit 실행
CMD sh -c "test -f /app/.chainlit && rm -f /app/.chainlit || true; chainlit run chainlit_app.py --host 0.0.0.0 --port 8000"

