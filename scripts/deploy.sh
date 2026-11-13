#!/usr/bin/env bash
# Deploy the AgentCore project. agentcore.json refers to the extraction Lambda with a placeholder
# account ID (000000000000) so no real ID is ever committed. This swaps in the real one for the
# duration of the deploy and always restores the file afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."

FILE=agentcore/agentcore.json
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
cp "$FILE" "$FILE.bak"
trap 'mv -f "$FILE.bak" "$FILE"' EXIT
sed -i "s/000000000000/$ACCOUNT/g" "$FILE"
agentcore deploy --region "${AWS_REGION:-us-east-1}" "$@"
