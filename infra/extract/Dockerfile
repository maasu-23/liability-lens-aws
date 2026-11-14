# Lambda container image: Tesseract (English + Hindi) needs system packages, so it cannot be a zip.
# The same image also serves draft_documents (CMD drafts_handler.handler), so there is one image to build.
# Build from the repository root:  docker build -f infra/extract/Dockerfile -t liability-lens-extract .
FROM python:3.13-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir awslambdaric boto3 pillow
# Separate layer so adding the PDF library does not re-push the layers above.
RUN pip install --no-cache-dir fpdf2==2.9.0

WORKDIR /var/task
COPY src/liability_lens ./liability_lens
COPY infra/extract/handler.py infra/extract/drafts_handler.py ./

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.handler"]
