#!/bin/sh
# Build the documentation and publish it to the docs server. Run it on your own
# machine, with DOCS_TARGET in the environment or in .env (host:/path/forums/).
set -eu

cd "$(dirname "$0")/.."
TARGET="${DOCS_TARGET:-$(sed -n 's/^DOCS_TARGET=//p' .env 2>/dev/null)}"
if [ -z "$TARGET" ]; then
    echo "Set DOCS_TARGET, e.g. user@host:/path/forums/" >&2
    exit 1
fi

# Everything in docs/ gets published, git-ignored files too, so only what the nav
# lists may be there. Private notes belong in reviews/.
find docs -type f | while read -r file; do
    if ! grep -qF "\"${file#docs/}\"" zensical.toml; then
        echo "Not published: $file is not in the nav in zensical.toml" >&2
        exit 1
    fi
done

uv run --group docs zensical build --clean
# The folder name must end the target: --delete on the parent would remove the
# other projects' docs.
rsync -a --delete --chmod=D755,F644 site/ "$TARGET"
echo "Published to $TARGET"
