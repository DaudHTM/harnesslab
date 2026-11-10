FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==9.2.0
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home agent \
    && mkdir /workspace /grading && chown agent:agent /workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/workspace
WORKDIR /workspace
USER agent
