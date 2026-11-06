FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends xz-utils && rm -rf /var/lib/apt/lists/*
COPY source/ ./source/
RUN cat source/part*.b64 | base64 -d | tar -xJf - -C /srv && pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 astrobuild
USER astrobuild
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers"]
