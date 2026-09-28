FROM python:3.11-slim

# 시스템 라이브러리 및 ffmpeg 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스 복사
COPY . .

# 업로드 및 출력 폴더 권한 부여
RUN mkdir -p uploads outputs static && chmod -R 777 uploads outputs static

# 클라우드 호스팅용 포트 (기본 7860 / 8000)
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
