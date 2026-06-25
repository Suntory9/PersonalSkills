#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY="$REPO_DIR/localagentskills"
BIN_DIR="$HOME/.local/bin"
TARGET="$BIN_DIR/localagentskills"

if [ ! -f "$ENTRY" ]; then
  echo "localagentskills entrypoint not found: $ENTRY" >&2
  exit 1
fi

chmod +x "$ENTRY"
mkdir -p "$BIN_DIR"
ln -sf "$ENTRY" "$TARGET"

echo "Installed command shim: $TARGET -> $ENTRY"

case ":$PATH:" in
  *":$BIN_DIR:"*)
    ;;
  *)
    echo ""
    echo "Warning: $BIN_DIR is not in PATH for this shell."
    echo "Add this to your shell profile, then restart the shell:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

echo ""
echo "Run:"
echo "  localagentskills list"
