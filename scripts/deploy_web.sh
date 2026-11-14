#!/usr/bin/env bash
# Deploy the web page, the streaming proxy and the sessions table. Run after deploy_extract.sh and deploy.sh.
# The access code lives only in .env.local (git-ignored); one is generated on first run.
# No account ID is stored anywhere: it is read from STS at run time.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-us-east-1}"
STACK=liability-lens-web
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
CODE_BUCKET="liability-lens-artifacts-$ACCOUNT-$REGION"

touch .env.local
if ! grep -q '^LL_ACCESS_CODE=' .env.local; then
  echo "LL_ACCESS_CODE=$(openssl rand -hex 8)" >> .env.local
  echo "Generated an access code in .env.local"
fi
ACCESS_CODE=$(grep '^LL_ACCESS_CODE=' .env.local | cut -d= -f2-)

RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='LiabilityLens_default_agent'].agentRuntimeArn | [0]" --output text)
UPLOAD_BUCKET=$(aws cloudformation describe-stacks --region "$REGION" --stack-name liability-lens-extract \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" --output text)

if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$CODE_BUCKET" --region "$REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$CODE_BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

( cd infra/web/proxy && npm ci --omit=dev --no-audit --no-fund >/dev/null )
ZIP=$(mktemp -d)/proxy.zip
( cd infra/web/proxy && zip -qr "$ZIP" index.mjs package.json node_modules )
KEY="proxy/$(sha256sum "$ZIP" | cut -c1-16).zip"
aws s3 cp "$ZIP" "s3://$CODE_BUCKET/$KEY" --only-show-errors

aws cloudformation deploy --region "$REGION" --stack-name "$STACK" --template-file infra/web/template.yaml \
  --parameter-overrides CodeBucket="$CODE_BUCKET" CodeKey="$KEY" RuntimeArn="$RUNTIME_ARN" \
    UploadBucket="$UPLOAD_BUCKET" AccessCode="$ACCESS_CODE" \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset

out() { aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text; }
aws s3 sync web/ "s3://$(out SiteBucketName)/" --delete --only-show-errors --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$(out DistributionId)" --paths "/*" >/dev/null
echo "Site: $(out SiteUrl)   (access code in .env.local)"
