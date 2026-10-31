# Dockerfile for a Hugging Face Space (Docker SDK) that serves the Streamlit chat UI.
# The Space holds only this file and its README; the code is pulled from GitHub at build time,
# so "Factory rebuild" in the Space settings picks up the latest commit on main.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 ANONYMIZED_TELEMETRY=False

WORKDIR /home/user
RUN git clone --depth 1 https://github.com/bikash9cmd/gopya-company-rag app
WORKDIR /home/user/app
RUN pip install --no-cache-dir --user -r requirements.txt && python -m gopya ingest

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
