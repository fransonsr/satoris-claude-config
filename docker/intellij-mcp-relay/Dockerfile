# TCP relay that lets WSL reach the IntelliJ MCP server running on Windows.
#
# Why it exists: under WSL2's default NAT networking, 127.0.0.1 inside WSL is
# not Windows' loopback, and the IntelliJ MCP server listens on Windows
# loopback only. Docker Desktop's `host.docker.internal` does reach Windows
# loopback, so this container forwards a port from there into WSL.
#
# Build:
#   docker build -t ij-mcp-relay docker/intellij-mcp-relay
#
# Run (these flags cannot live in a Dockerfile):
#   docker run -d --name ij-mcp-relay --restart unless-stopped \
#     -p 127.0.0.1:65429:65428 ij-mcp-relay
#
# The host port is 65429, not 65428. Docker Desktop also binds published ports
# on the Windows side, where IntelliJ already holds 65428, so publishing 65428
# fails with "ports are not available".
#
# Claude Code entry (user scope; ~/.claude.json). The header selects the
# IntelliJ project; other open projects are reached with a per-call
# `projectPath` argument:
#   claude mcp add --scope user --transport sse intellij \
#     http://127.0.0.1:65429/sse \
#     --header "IJ_MCP_SERVER_PROJECT_PATH: //wsl.localhost/Ubuntu/home/fransonsr/github/records-platform-workspace"
#
# If IntelliJ's MCP port changes (Settings > Tools > MCP Server), rebuild with
#   --build-arg IJ_MCP_PORT=<port>
# and publish that port's container side accordingly.

# alpine/socat:latest as of 2026-11-10, pinned by digest so a rebuild matches.
# Its ENTRYPOINT is already `socat`.
FROM alpine/socat@sha256:e8a6e8868a8e6e01d9c2c321a8f8d4474d2d741d962462e5c5a124a8e66a0055

ARG IJ_MCP_PORT=65428
ENV IJ_MCP_PORT=${IJ_MCP_PORT}

EXPOSE ${IJ_MCP_PORT}

# `fork` serves each SSE client in its own process; `reuseaddr` lets the relay
# restart immediately. Shell form so $IJ_MCP_PORT expands at start-up.
ENTRYPOINT ["/bin/sh", "-c", "exec socat tcp-listen:${IJ_MCP_PORT},fork,reuseaddr tcp:host.docker.internal:${IJ_MCP_PORT}"]
