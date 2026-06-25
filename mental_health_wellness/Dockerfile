# SentiMind FastAPI backend — production image (Hugging Face Spaces / Docker).
# Frontend is NOT here; Vercel builds the Next.js app directly. DB is Supabase.

FROM python:3.11-slim

# System packages required by audio analysis (librosa + praat-parselmouth)
#   - build-essential : compile native extensions if a wheel is unavailable
#   - libsndfile1     : libsndfile backend used by librosa/soundfile
#   - ffmpeg          : audio decoding/resampling
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libsndfile1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep Python lean & logs unbuffered for container log streaming.
# PORT=7860 is the Hugging Face Spaces default. api_server.py reads $PORT, and
# platforms that inject their own PORT (e.g. Render) override this automatically.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    HF_HOME=/app/.cache/huggingface

# 1) Install Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 2) Generate the Prisma client (needs only the schema, no DB connection)
COPY prisma/ ./prisma/
RUN python -m prisma generate

# 3) Copy the rest of the application
COPY . .

# Hugging Face Spaces serves on 7860 (Render/Koyeb override $PORT at runtime)
EXPOSE 7860

# api_server.py launches uvicorn on 0.0.0.0:$PORT with reload disabled
CMD ["python", "api_server.py"]
