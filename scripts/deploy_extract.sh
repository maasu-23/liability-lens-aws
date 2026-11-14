#!/usr/bin/env bash
# Build the Tesseract Lambda image, push it to ECR, and deploy the upload bucket and function.
# Needs Docker and AWS credentials. No account ID is stored anywhere: it is read from STS at run time.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-us-east-1}"
REPO=liability-lens-extract
STACK=liability-lens-extract
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
TAG="$(git rev-parse --short HEAD)-$(date +%s)"  # a new tag each time so Lambda picks up the new image

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" \
       --image-scanning-configuration scanOnPush=true >/dev/null

# Keep only the newest 3 images: every deploy pushes a new one, and old ones only cost storage.
aws ecr put-lifecycle-policy --repository-name "$REPO" --region "$REGION" --lifecycle-policy-text '{"rules":[{"rulePriority":1,"description":"keep the newest 3 images","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":3},"action":{"type":"expire"}}]}' >/dev/null

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
# Lambda rejects multi-platform manifests, so build one linux/amd64 image without provenance attestations.
docker build --platform linux/amd64 --provenance=false -f infra/extract/Dockerfile -t "$REGISTRY/$REPO:$TAG" .
docker push "$REGISTRY/$REPO:$TAG"

aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file infra/extract/template.yaml \
  --parameter-overrides "ImageUri=$REGISTRY/$REPO:$TAG" \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset

aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output text
