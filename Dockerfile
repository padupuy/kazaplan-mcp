FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 kazaplan \
    && mkdir /data && chown kazaplan /data

USER kazaplan
ENV KZ_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME ["/data"]
ENTRYPOINT ["kazaplan-mcp"]
