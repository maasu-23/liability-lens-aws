#!/usr/bin/env bash
# Install the local pre-commit check (git hooks are not part of the repository, so run this once per clone).
set -euo pipefail
cd "$(dirname "$0")/.."
printf '#!/usr/bin/env bash\nexec "$(git rev-parse --show-toplevel)/scripts/check_no_ids.sh"\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/check_no_ids.sh
echo "pre-commit check installed"
