#!/usr/bin/env bash
#
# rtwi — install the standalone `rtwi` binary (PyInstaller onedir build).
#
#   curl -fsSL https://raw.githubusercontent.com/vispar-tech/rtwi/main/install.sh | bash
#
# Downloads the rtwi onedir build (launcher + _internal/ payload) for the
# current macOS/architecture and installs it into ~/.local.
#
# Each app gets its own lib directory (~/.local/lib/rtwi/) to avoid conflicts
# with other PyInstaller-bundled apps that share ~/.local/bin/_internal/.
#
# Env overrides:
#   RTWI_BIN_URL    full URL to the prebuilt binary archive
#   RTWI_VERSION    default tag/version for the download (default: latest)
#   RTWI_PREFIX     install directory (default: ~/.local)

set -euo pipefail

PREFIX="${RTWI_PREFIX:-$HOME/.local}"
VERSION="${RTWI_VERSION:-latest}"
BIN_URL="${RTWI_BIN_URL:-}"

GH_REPO="vispar-tech/rtwi"

say()  { printf '\033[36m[rtwi]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[rtwi]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[rtwi]\033[0m %s\n' "$*" >&2; exit 1; }

lib_dir="$PREFIX/lib/rtwi"
bin_dir="$PREFIX/bin"
URL_BASE="${BIN_URL:-https://github.com/$GH_REPO/releases/download/$VERSION}"

arch() {
    case "$(uname -m)" in
        aarch64|arm64) echo "aarch64" ;;
        *) die "Unsupported arch: $(uname -m) (rtwi ships only aarch64)" ;;
    esac
}

# ---------------------------------------------------------------------------
# Download + install the binary
# ---------------------------------------------------------------------------
download_binary() {
    local file="rtwi-$VERSION-macos-$(arch).tar.gz"
    local url="$URL_BASE/$file"
    local tmp
    tmp="$(mktemp -d)"
    say "Downloading $url"
    curl -fsSL -o "$tmp/$file" "$url"
    tar -xzf "$tmp/$file" -C "$tmp"
    # Accept both a flat payload (launcher `rtwi` + `_internal/` sibling at the
    # archive root) and an archive that wraps them in an `rtwi/` dir.
    local src="$tmp"
    if [ -d "$tmp/rtwi" ] && [ -x "$tmp/rtwi/rtwi" ]; then
        src="$tmp/rtwi"
    fi
    mkdir -p "$lib_dir"
    install -m 0755 "$src/rtwi" "$lib_dir/rtwi"
    if [ -d "$src/_internal" ]; then
        rm -rf "$lib_dir/_internal"
        cp -R "$src/_internal" "$lib_dir/_internal"
        chmod -R u+rwX,go+rX "$lib_dir/_internal"
    fi
    rm -rf "$tmp"
    # Symlink binary into ~/.local/bin/
    mkdir -p "$bin_dir"
    ln -sf "../lib/rtwi/rtwi" "$bin_dir/rtwi"
    say "Installed rtwi to $lib_dir/rtwi"
    if ! echo "$PATH" | grep -q "$bin_dir"; then
        warn "Add $bin_dir to your PATH:"
        warn '  echo '\''export PATH="'"$bin_dir"':$PATH"'\'' >> ~/.zshrc'
    fi
}

# ---------------------------------------------------------------------------
# Resolve the latest release tag when RTWI_VERSION is unset
# ---------------------------------------------------------------------------
resolve_latest() {
    [ "$VERSION" != "latest" ] && return 0
    VERSION="$(curl -fsSL -m 20 \
        https://api.github.com/repos/$GH_REPO/releases/latest \
        | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1 || true)"
    [ -n "$VERSION" ] || { VERSION="latest"; warn "Could not resolve latest release tag; using '$VERSION'"; }
    URL_BASE="https://github.com/$GH_REPO/releases/download/$VERSION"
    say "Latest release: $VERSION"
}

# ---------------------------------------------------------------------------
main() {
    [ "$(uname -s)" = "Darwin" ] || die "Unsupported OS. rtwi targets macOS."
    say "rtwi installer (standalone binary)"
    resolve_latest
    download_binary
    "$lib_dir/rtwi" --version
    say "Done. Run 'rtwi --help' to get started."
}

main "$@"
