FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ANONYMIZED_TELEMETRY=False
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gopya ./gopya
COPY data ./data
COPY app.py .
# The index is built into the image, so a container starts ready and never writes to the docs.
RUN python -m gopya ingest

RUN useradd --create-home gopya && chown -R gopya /app/var
USER gopya
EXPOSE 8000
CMD ["python", "-m", "gopya", "serve", "--port", "8000"]
