# Lambda container image: Tesseract (English + Hindi) needs system packages, so it cannot be a zip.
# Build from the repository root:  docker build -f infra/extract/Dockerfile -t liability-lens-extract .
FROM python:3.13-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir awslambdaric boto3 pillow

WORKDIR /var/task
COPY src/liability_lens ./liability_lens
COPY infra/extract/handler.py .

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.handler"]
