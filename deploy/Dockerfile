FROM python:3.12-slim

# rsync and ping are used by Source pulls from device shares mounted on the NAS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends rsync iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt xisf

COPY astro_tracker ./astro_tracker
COPY *.html *.json fits_header_analyzer.py ./

ENV ASTRO_TRACKER_DB=/data/catalog.db
EXPOSE 8000
CMD ["python", "-m", "astro_tracker.server", "--host", "0.0.0.0", "--port", "8000", "--db", "/data/catalog.db"]
