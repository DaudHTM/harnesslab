FROM node:22-slim AS ui
WORKDIR /ui
RUN npm install -g pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git docker.io \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md requirements-lock.txt ./
COPY harnesslab/ harnesslab/
RUN pip install --no-cache-dir -r requirements-lock.txt && pip install --no-cache-dir --no-deps .
ENV PYTHONPATH=/app
COPY benchmarks/ benchmarks/
COPY scripts/ scripts/
COPY configs/ configs/
COPY --from=ui /ui/dist /app/frontend/dist
CMD ["harnesslab", "serve", "--host", "0.0.0.0"]
