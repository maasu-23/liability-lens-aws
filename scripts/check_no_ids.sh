#!/usr/bin/env bash
# Refuse to commit AWS account IDs, ARNs with account IDs, access keys, secrets, emails or identifier files.
# Installed as .git/hooks/pre-commit by scripts/install_hooks.sh. The placeholder 000000000000 is allowed.
set -uo pipefail

bad=0
files=$(git diff --cached --name-only --diff-filter=AM)
if echo "$files" | grep -E '(^|/)(aws-targets\.json|deployed-state\.json|\.env[^/]*|.*\.pem|.*\.bak)$' | grep -v '\.env\.example$'; then
  echo "pre-commit: identifier or secret file staged (above)"; bad=1
fi

added=$(git diff --cached -U0 --diff-filter=AM -- . ':!scripts/check_no_ids.sh' | grep -E '^\+[^+]' || true)
check() {  # pattern, description
  if hits=$(echo "$added" | grep -E -e "$1" | grep -v -E '000000000000'); [ -n "$hits" ]; then
    echo "pre-commit: $2:"; echo "$hits" | cut -c1-120 | head -3; bad=1
  fi
}
check 'arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:[0-9]{12}' "ARN containing an account ID"
check '[0-9]{12}\.dkr\.ecr' "ECR registry with an account ID"
check '(account|accountId|account_id|AWS_ACCOUNT_ID)"?[[:space:]]*[:=][[:space:]]*"?[0-9]{12}' "account ID assignment"
check '(AKIA|ASIA)[0-9A-Z]{16}' "AWS access key ID"
check '(secret_access_key|aws_secret|SecretAccessKey|BEGIN (RSA |EC )?PRIVATE KEY)' "secret material"
check '[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail|proton)\.(com|me)' "personal email address"

[ "$bad" -eq 0 ] || { echo "pre-commit: blocked. Remove or git-ignore these, then commit again."; exit 1; }
