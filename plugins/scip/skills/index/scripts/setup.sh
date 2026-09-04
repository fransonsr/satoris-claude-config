#!/usr/bin/env bash
# setup.sh — install `scip` and `scip-java` if either is missing. Idempotent: re-running
# with both already present is a fast no-op.
#
# `scip` ships as a prebuilt release binary. `scip-java` does not — it's installed via
# Coursier's `cs bootstrap --standalone`, which produces a fully self-contained jar; Coursier
# itself is only needed for that one-time build and isn't kept around afterward.
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

need_scip=1
need_scip_java=1

if command -v scip >/dev/null 2>&1; then
  echo "scip already installed: $(scip --version)"
  need_scip=0
fi

if command -v scip-java >/dev/null 2>&1; then
  echo "scip-java already installed at $(command -v scip-java)"
  need_scip_java=0
fi

if [[ "$need_scip" -eq 0 && "$need_scip_java" -eq 0 ]]; then
  echo "Nothing to do — both tools already installed."
  exit 0
fi

if ! command -v java >/dev/null 2>&1; then
  echo "java not found on PATH — scip-java (and its Coursier bootstrap) both need a JDK." >&2
  exit 1
fi

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux) os_tag="linux" ;;
  Darwin) os_tag="darwin" ;;
  *) echo "Unsupported OS for scip setup: $OS" >&2; exit 1 ;;
esac

case "$ARCH" in
  x86_64|amd64) arch_tag="amd64" ;;
  arm64|aarch64) arch_tag="arm64" ;;
  *) echo "Unsupported architecture for scip setup: $ARCH" >&2; exit 1 ;;
esac

if [[ "$need_scip" -eq 1 ]]; then
  echo "Installing scip ($os_tag-$arch_tag)..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL -o "$tmp/scip.tar.gz" \
    "https://github.com/scip-code/scip/releases/latest/download/scip-${os_tag}-${arch_tag}.tar.gz"
  tar -xzf "$tmp/scip.tar.gz" -C "$tmp"
  chmod +x "$tmp/scip"
  mv "$tmp/scip" "$BIN_DIR/scip"
  rm -rf "$tmp"
  trap - EXIT
  echo "Installed: $("$BIN_DIR/scip" --version)"
fi

if [[ "$need_scip_java" -eq 1 ]]; then
  # Coursier has no prebuilt linux-arm64 release binary as of this writing.
  case "${OS}-${ARCH}" in
    Linux-x86_64|Linux-amd64) cs_asset="cs-x86_64-pc-linux.gz" ;;
    Darwin-x86_64|Darwin-amd64) cs_asset="cs-x86_64-apple-darwin.gz" ;;
    Darwin-arm64|Darwin-aarch64) cs_asset="cs-aarch64-apple-darwin.gz" ;;
    *)
      echo "No prebuilt Coursier binary for ${OS}-${ARCH}." >&2
      echo "Install Coursier manually (https://get-coursier.io) then re-run setup." >&2
      exit 1
      ;;
  esac

  scip_java_version="$(curl -fsSL https://api.github.com/repos/scip-code/scip-java/releases/latest \
    | jq -r '.tag_name' | sed 's/^v//')"
  if [[ -z "$scip_java_version" || "$scip_java_version" == "null" ]]; then
    echo "Couldn't determine the latest scip-java release from the GitHub API." >&2
    exit 1
  fi
  echo "Installing scip-java $scip_java_version via Coursier ($cs_asset)..."

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fLo "$tmp/cs.gz" "https://github.com/coursier/coursier/releases/latest/download/$cs_asset"
  gunzip "$tmp/cs.gz"
  chmod +x "$tmp/cs"
  "$tmp/cs" bootstrap --standalone -o "$tmp/scip-java" \
    "org.scip-code:scip-java:${scip_java_version}" --main org.scip_code.scip_java.ScipJava
  chmod +x "$tmp/scip-java"
  mv "$tmp/scip-java" "$BIN_DIR/scip-java"
  rm -rf "$tmp"
  trap - EXIT
  echo "Installed scip-java $scip_java_version to $BIN_DIR/scip-java"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not on PATH — add it so 'scip'/'scip-java' resolve directly." ;;
esac
