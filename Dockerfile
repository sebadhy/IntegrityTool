FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS frontend
WORKDIR /build
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Integrity Tool" \
      org.opencontainers.image.source="https://github.com/sebadhy/IntegrityTool" \
      org.opencontainers.image.revision=$REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    INTEGRITY_WORKER_MODE=external \
    INTEGRITY_ASSISTED_ENABLED=false \
    APP_CORPUS_PROCESSED_DIR=/tmp/integrity/extracted_text
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 integrity \
    && useradd --uid 10001 --gid integrity --create-home integrity
COPY requirements.txt requirements-azure.txt ./
RUN python -m pip install --no-cache-dir -r requirements-azure.txt \
    && python -m pip check \
    && python -m pip freeze > /app/installed-packages.txt
COPY src/ ./src/
COPY --from=frontend /build/dist/ ./frontend/dist/
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "src.container_start"]
CMD ["api"]
