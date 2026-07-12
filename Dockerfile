FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --system retrofy \
    && useradd --system --gid retrofy --home-dir /app retrofy

COPY requirements.lock /app/
RUN pip install --only-binary=:all: --require-hashes -r requirements.lock

COPY app.py /app/
COPY templates /app/templates
COPY static /app/static

EXPOSE 8888

ENV DB_PATH=/srv/sqlite/ma_base.sqlite \
    IMAGES_DIR=/data/images

RUN mkdir -p /data/images /srv/sqlite && chown -R retrofy:retrofy /app /data/images /srv/sqlite

USER retrofy

CMD ["python", "app.py"]
