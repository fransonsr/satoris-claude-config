#!/usr/bin/env python3
"""Diagnose the WSL -> Docker relay -> IntelliJ MCP chain, one layer at a time.

Stops at the first failing layer and says what to fix. Standard library only.

    ./check.py                                  # defaults match the Dockerfile header
    ./check.py --project-path //wsl.localhost/Ubuntu/home/fransonsr/github/<repo>
    ./check.py --override-path <other open project>   # also tests the per-call projectPath

Layers, in order, with the exit code each failure returns:
    11  container     the relay container is missing, stopped, or Docker is not answering
    12  relay port     nothing accepts connections on the published port
    13  IntelliJ       the relay accepts, but IntelliJ behind it does not answer
    14  handshake      the SSE stream or the MCP initialize exchange is wrong
    15  project        IntelliJ cannot pick a project for the header (open projects are listed)
Exit 0 means every layer passed. Exit 2 is a usage error (argparse).
"""
from __future__ import annotations

import argparse
import http.client
import json
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65429
DEFAULT_CONTAINER = "ij-mcp-relay"
DEFAULT_PROJECT_PATH = "//wsl.localhost/Ubuntu/home/fransonsr/github/records-platform-workspace"
DEFAULT_TIMEOUT_SECONDS = 8.0
PROJECT_HEADER = "IJ_MCP_SERVER_PROJECT_PATH"

EXIT_OK = 0
EXIT_CONTAINER = 11
EXIT_RELAY = 12
EXIT_UPSTREAM = 13
EXIT_PROTOCOL = 14
EXIT_PROJECT = 15

LAYER_LABELS = {
    EXIT_CONTAINER: "container",
    EXIT_RELAY: "relay port",
    EXIT_UPSTREAM: "IntelliJ",
    EXIT_PROTOCOL: "handshake",
    EXIT_PROJECT: "project",
}

START_HINT = ("start it with: docker run -d --name ij-mcp-relay --restart unless-stopped "
              "-p 127.0.0.1:65429:65428 ij-mcp-relay   (build first; see the Dockerfile header)")
RELAY_HINT = ("the relay container is not running or publishes a different host port (try --port), "
              "or Docker Desktop is not running")
UPSTREAM_HINT = ("IntelliJ is not running, its MCP server is off, or it listens on a port other than the "
                 "relay's target; rebuild the relay with --build-arg IJ_MCP_PORT=<port> if the port changed")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Event = tuple[str, str]


class CheckFailed(Exception):
    def __init__(self, exit_code: int, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message
        self.hint = hint


def check_container(name: str, runner: Runner = subprocess.run) -> tuple[str, str]:
    """Return ("OK" | "SKIP", detail); raise CheckFailed when the container is not running."""
    command = ["docker", "inspect", "--format", "{{.State.Status}} {{.HostConfig.RestartPolicy.Name}}", name]
    try:
        done = runner(command, capture_output=True, text=True, timeout=15, check=False)
    except FileNotFoundError:
        return "SKIP", "docker CLI not found on PATH; container state not checked"
    except subprocess.TimeoutExpired:
        raise CheckFailed(EXIT_CONTAINER, "docker did not answer within 15s",
                          "Docker Desktop may be starting or hung") from None
    if done.returncode != 0:
        error = done.stderr.strip()
        if "no such" in error.lower():
            raise CheckFailed(EXIT_CONTAINER, f"container {name} does not exist", START_HINT)
        raise CheckFailed(EXIT_CONTAINER, f"docker inspect failed: {error or 'no output'}",
                          "Docker Desktop may not be running (check its WSL integration)")
    status, _, policy = done.stdout.strip().partition(" ")
    if status != "running":
        raise CheckFailed(EXIT_CONTAINER, f"container {name} is {status or 'in an unknown state'}",
                          f"docker start {name}")
    return "OK", f"{name} running (restart policy: {policy or 'none'})"


def parse_open_projects(text: str) -> list[str]:
    """Pull the project paths out of IntelliJ's 'Currently open projects: {...}' error text."""
    match = re.search(r'\{"projects":\s*\[.*?\]\s*\}', text, re.DOTALL)
    if match is None:
        return []
    try:
        projects = json.loads(match.group(0))["projects"]
        return [entry["path"] for entry in projects]
    except (ValueError, KeyError, TypeError):
        return []


class McpSession:
    """One MCP SSE session: GET /sse for responses, POST to the announced endpoint for requests."""

    def __init__(self, host: str, port: int, project_path: str, timeout: float) -> None:
        self._host = host
        self._port = port
        self._project_path = project_path
        self._timeout = timeout
        self._stream: http.client.HTTPConnection | None = None
        self._reader: threading.Thread | None = None
        self._endpoint: str | None = None
        self._events: queue.Queue[Event | None] = queue.Queue()

    def connect(self) -> None:
        """Layer 'relay port': can we open a TCP connection at all?"""
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.connect()
        except ConnectionRefusedError:
            raise CheckFailed(EXIT_RELAY, f"nothing is listening on {self._host}:{self._port}", RELAY_HINT) from None
        except TimeoutError:
            raise CheckFailed(EXIT_RELAY, f"connecting to {self._host}:{self._port} timed out", RELAY_HINT) from None
        except OSError as error:
            raise CheckFailed(EXIT_RELAY, f"cannot connect to {self._host}:{self._port}: {error}", RELAY_HINT) from None
        self._stream = connection

    def open_stream(self) -> None:
        """Layer 'IntelliJ': does GET /sse come back with a stream and an endpoint event?"""
        connection = self._require_stream()
        try:
            connection.request("GET", "/sse", headers=self._headers({"Accept": "text/event-stream"}))
            response = connection.getresponse()
        except TimeoutError:
            raise CheckFailed(EXIT_UPSTREAM, f"the relay accepted the connection but IntelliJ did not answer "
                                             f"within {self._timeout:g}s", UPSTREAM_HINT) from None
        except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
            raise CheckFailed(EXIT_UPSTREAM, "the relay accepted the connection and then closed it without a reply",
                              UPSTREAM_HINT) from None
        except (http.client.HTTPException, OSError) as error:
            raise CheckFailed(EXIT_PROTOCOL, f"GET /sse failed: {error}") from None
        if response.status != 200:
            raise CheckFailed(EXIT_PROTOCOL, f"GET /sse returned HTTP {response.status}, expected 200")
        content_type = response.getheader("Content-Type", "")
        if "text/event-stream" not in content_type:
            raise CheckFailed(EXIT_PROTOCOL, f"GET /sse returned Content-Type {content_type!r}, "
                                             "expected text/event-stream")
        if connection.sock is not None:
            connection.sock.settimeout(None)  # the stream idles between heartbeats
        self._reader = threading.Thread(target=self._read_events, args=(response,), daemon=True)
        self._reader.start()
        self._endpoint = self._await_endpoint()

    def call(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self._timeout
        while True:
            _, data = self._next_event(deadline)
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                return message

    def notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def close(self) -> None:
        """Wake the reader by shutting the socket down, wait for it, and only then close the
        connection, so the reader never reads from a half-closed response."""
        if self._stream is None:
            return
        if self._stream.sock is not None:
            try:
                self._stream.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._reader is not None:
            self._reader.join(timeout=2)
        self._stream.close()

    def _require_stream(self) -> http.client.HTTPConnection:
        if self._stream is None:
            raise RuntimeError("connect() must succeed before open_stream()")
        return self._stream

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {PROJECT_HEADER: self._project_path}
        headers.update(extra or {})
        return headers

    def _read_events(self, response: http.client.HTTPResponse) -> None:
        event = "message"
        try:
            while True:
                raw = response.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    self._events.put((event, line[len("data:"):].strip()))
                    event = "message"
        except Exception:  # noqa: BLE001 - any read failure, including a torn-down chunked body, means "stream ended"
            pass
        finally:
            self._events.put(None)

    def _next_event(self, deadline: float) -> Event:
        try:
            item = self._events.get(timeout=max(deadline - time.monotonic(), 0.01))
        except queue.Empty:
            raise CheckFailed(EXIT_PROTOCOL, f"no event from IntelliJ within {self._timeout:g}s") from None
        if item is None:
            self._events.put(None)
            raise CheckFailed(EXIT_PROTOCOL, "the SSE stream closed before the expected event arrived")
        return item

    def _await_endpoint(self) -> str:
        deadline = time.monotonic() + self._timeout
        while True:
            event, data = self._next_event(deadline)
            if event == "endpoint":
                return data

    def _post(self, payload: dict[str, Any]) -> None:
        if self._endpoint is None:
            raise RuntimeError("open_stream() must succeed before posting")
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request("POST", self._endpoint, body=json.dumps(payload),
                               headers=self._headers({"Content-Type": "application/json"}))
            response = connection.getresponse()
            response.read()
        except (http.client.HTTPException, OSError) as error:
            raise CheckFailed(EXIT_PROTOCOL, f"POST {self._endpoint} failed: {error}") from None
        finally:
            connection.close()
        if response.status not in (200, 202, 204):
            raise CheckFailed(EXIT_PROTOCOL, f"POST {self._endpoint} returned HTTP {response.status}")


def handshake(session: McpSession) -> str:
    reply = session.call("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "intellij-mcp-relay-check", "version": "1"},
    }, request_id=1)
    info = (reply.get("result") or {}).get("serverInfo")
    if not isinstance(info, dict):
        raise CheckFailed(EXIT_PROTOCOL, f"initialize returned no serverInfo: {json.dumps(reply)[:200]}")
    session.notify("notifications/initialized")
    return f"{info.get('name', '?')} {info.get('version', '')}".strip()


def check_project(session: McpSession, override_path: str | None) -> str:
    arguments = {"projectPath": override_path} if override_path else {}
    reply = session.call("tools/call", {"name": "get_project_modules", "arguments": arguments}, request_id=2)
    return describe_modules_reply(reply)


def describe_modules_reply(reply: dict[str, Any]) -> str:
    result = reply.get("result")
    if not isinstance(result, dict):
        raise CheckFailed(EXIT_PROJECT, f"get_project_modules failed: {json.dumps(reply.get('error'))[:200]}")
    content = result.get("content") or [{}]
    text = str(content[0].get("text", ""))
    if result.get("isError"):
        open_projects = parse_open_projects(text)
        if open_projects:
            listing = "; ".join(open_projects)
            raise CheckFailed(EXIT_PROJECT, f"IntelliJ cannot pick a project for this header. Open projects: {listing}",
                              "open the repo in IntelliJ, or pass --project-path / --override-path "
                              "with one of those paths")
        raise CheckFailed(EXIT_PROJECT, f"get_project_modules returned an error: {text[:200]}")
    modules = (result.get("structuredContent") or {}).get("modules") or []
    names = ", ".join(str(module.get("name")) for module in modules)
    return f"resolved; modules: {names or '(none)'}"


def report(status: str, label: str, detail: str, hint: str = "") -> None:
    print(f"[{status:^4}] {label:<10} {detail}")
    if hint:
        print(f"       {'':<10} -> {hint}")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose the WSL -> relay -> IntelliJ MCP chain.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="host port the relay publishes")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--project-path", default=DEFAULT_PROJECT_PATH,
                        help=f"value of the {PROJECT_HEADER} header, as IntelliJ reports it")
    parser.add_argument("--override-path", help="also pass this as the per-call projectPath argument")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="seconds per step")
    parser.add_argument("--no-docker", action="store_true", help="skip the container check")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, runner: Runner = subprocess.run) -> int:
    args = parse_args(argv)
    session = McpSession(args.host, args.port, args.project_path, args.timeout)
    try:
        if not args.no_docker:
            status, detail = check_container(args.container, runner)
            report(status, LAYER_LABELS[EXIT_CONTAINER], detail)
        session.connect()
        report("OK", LAYER_LABELS[EXIT_RELAY], f"{args.host}:{args.port} accepts connections")
        session.open_stream()
        report("OK", LAYER_LABELS[EXIT_UPSTREAM], "SSE stream open, endpoint received")
        report("OK", LAYER_LABELS[EXIT_PROTOCOL], handshake(session))
        report("OK", LAYER_LABELS[EXIT_PROJECT], check_project(session, args.override_path))
    except CheckFailed as failure:
        report("FAIL", LAYER_LABELS.get(failure.exit_code, "check"), failure.message, failure.hint)
        print("Stopped at the first failing layer; later layers were not checked.")
        return failure.exit_code
    finally:
        session.close()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
