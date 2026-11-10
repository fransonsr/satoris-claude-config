"""Tests for check.py: a fake IntelliJ MCP server plays the Windows side, and small raw-socket
servers play a relay whose upstream is down. No Docker or IntelliJ is needed.

Run:  python3 -m unittest -v test_check      (from this directory)
"""
from __future__ import annotations

import contextlib
import io
import json
import queue
import socket
import subprocess
import threading
import unittest
import uuid
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import check

WORKSPACE = "//wsl.localhost/Ubuntu/home/fransonsr/github/records-platform-workspace"
SLS = WORKSPACE + "/repos/services/sls-internal-workers"


class FakeIntelliJ:
    """Speaks just enough of the MCP SSE transport for check.py."""

    def __init__(self, open_projects: list[str], sse_status: int = 200) -> None:
        self.open_projects = open_projects
        self.sse_status = sse_status
        self.sessions: dict[str, queue.Queue[dict[str, Any]]] = {}
        self.stopping = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port: int = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()

    def respond(self, body: dict[str, Any], header_path: str | None) -> dict[str, Any] | None:
        method = body.get("method")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": body["id"],
                    "result": {"serverInfo": {"name": "Fake IDE", "version": "1.2"}}}
        if method != "tools/call":
            return None
        arguments = body["params"].get("arguments", {})
        target = arguments.get("projectPath") or header_path
        if target in self.open_projects:
            modules = {"modules": [{"name": "mod-a", "type": "JAVA_MODULE"}]}
            return {"jsonrpc": "2.0", "id": body["id"],
                    "result": {"isError": False, "content": [{"type": "text", "text": json.dumps(modules)}],
                               "structuredContent": modules}}
        listing = json.dumps({"projects": [{"path": p} for p in self.open_projects]})
        text = "Unable to determine the target project for the current MCP tool call.\n" \
               " Currently open projects: " + listing
        return {"jsonrpc": "2.0", "id": body["id"],
                "result": {"isError": True, "content": [{"type": "text", "text": text}]}}

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            # IntelliJ streams SSE with Transfer-Encoding: chunked; a close-delimited fake hid a
            # shutdown crash in the reader thread, so the fake must chunk too.
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature fixed by base class
                return

            def send_chunk(self, text: str) -> None:
                data = text.encode()
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()

            def do_GET(self) -> None:
                if fake.sse_status != 200:
                    self.send_response(fake.sse_status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                session_id = uuid.uuid4().hex
                events: queue.Queue[dict[str, Any]] = queue.Queue()
                fake.sessions[session_id] = events
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                try:
                    self.send_chunk(f": heartbeat\n\nevent: endpoint\ndata: /message?sessionId={session_id}\n\n")
                    while not fake.stopping.is_set():
                        try:
                            payload = events.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        self.send_chunk(f"event: message\ndata: {json.dumps(payload)}\n\n")
                except OSError:
                    return

            def do_POST(self) -> None:
                session_id = parse_qs(urlparse(self.path).query)["sessionId"][0]
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                reply = fake.respond(body, self.headers.get(check.PROJECT_HEADER))
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                if reply is not None:
                    fake.sessions[session_id].put(reply)

        return Handler


@contextlib.contextmanager
def fake_intellij(open_projects: list[str], sse_status: int = 200) -> Generator[FakeIntelliJ, None, None]:
    fake = FakeIntelliJ(open_projects, sse_status)
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()


@contextlib.contextmanager
def socket_server(hold_open: bool) -> Generator[int, None, None]:
    """Accepts TCP connections and sends nothing: closes at once, or holds the connection open."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(0.1)
    stopping = threading.Event()
    held: list[socket.socket] = []

    def serve() -> None:
        while not stopping.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            if hold_open:
                held.append(conn)
            else:
                conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stopping.set()
        thread.join(timeout=2)
        for conn in held:
            conn.close()
        listener.close()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_check(*argv: str, runner: Any = subprocess.run) -> tuple[int, str]:
    """Run check.main and return (exit code, stdout). Fails the test if anything wrote a traceback
    to stderr, such as an unhandled exception in the SSE reader thread."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check.main(list(argv), runner=runner)
    if "Traceback" in err.getvalue():
        raise AssertionError("check.main wrote a traceback to stderr:\n" + err.getvalue())
    return code, out.getvalue()


def completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class MainAgainstFakeIntelliJTest(unittest.TestCase):
    def test_passes_every_layer_when_the_pinned_project_is_open(self) -> None:
        with fake_intellij([WORKSPACE, SLS]) as ij:
            code, output = run_check("--no-docker", "--port", str(ij.port), "--project-path", WORKSPACE)
        self.assertEqual(check.EXIT_OK, code, output)
        self.assertNotIn("FAIL", output)
        self.assertIn("Fake IDE 1.2", output)
        self.assertIn("mod-a", output)

    def test_lists_open_projects_when_the_pinned_project_is_not_open(self) -> None:
        with fake_intellij([SLS]) as ij:
            code, output = run_check("--no-docker", "--port", str(ij.port), "--project-path", WORKSPACE)
        self.assertEqual(check.EXIT_PROJECT, code, output)
        self.assertIn(SLS, output)

    def test_override_path_reaches_another_open_project(self) -> None:
        with fake_intellij([SLS]) as ij:
            code, output = run_check("--no-docker", "--port", str(ij.port), "--project-path", WORKSPACE,
                                     "--override-path", SLS)
        self.assertEqual(check.EXIT_OK, code, output)

    def test_reports_the_relay_when_nothing_listens_on_the_port(self) -> None:
        code, output = run_check("--no-docker", "--port", str(free_port()), "--timeout", "2")
        self.assertEqual(check.EXIT_RELAY, code, output)
        self.assertIn("nothing is listening", output)

    def test_reports_the_upstream_when_the_relay_closes_the_connection(self) -> None:
        with socket_server(hold_open=False) as port:
            code, output = run_check("--no-docker", "--port", str(port), "--timeout", "2")
        self.assertEqual(check.EXIT_UPSTREAM, code, output)
        self.assertIn("IntelliJ", output)

    def test_reports_the_upstream_when_the_relay_never_answers(self) -> None:
        with socket_server(hold_open=True) as port:
            code, output = run_check("--no-docker", "--port", str(port), "--timeout", "0.5")
        self.assertEqual(check.EXIT_UPSTREAM, code, output)

    def test_reports_a_protocol_failure_when_the_sse_endpoint_is_not_http_200(self) -> None:
        with fake_intellij([WORKSPACE], sse_status=404) as ij:
            code, output = run_check("--no-docker", "--port", str(ij.port))
        self.assertEqual(check.EXIT_PROTOCOL, code, output)
        self.assertIn("404", output)

    def test_stops_at_the_container_layer_without_touching_the_network(self) -> None:
        runner = lambda *_args, **_kwargs: completed(1, stderr="Error: No such object: ij-mcp-relay")  # noqa: E731
        code, output = run_check("--port", str(free_port()), runner=runner)
        self.assertEqual(check.EXIT_CONTAINER, code, output)
        self.assertNotIn("relay port", output)


class CheckContainerTest(unittest.TestCase):
    def test_running_container_is_ok_and_reports_its_restart_policy(self) -> None:
        status, detail = check.check_container("ij", lambda *_args, **_kwargs: completed(0, "running unless-stopped\n"))
        self.assertEqual("OK", status)
        self.assertIn("unless-stopped", detail)

    def test_missing_docker_cli_is_skipped_not_failed(self) -> None:
        def no_docker(*_args: Any, **_kwargs: Any) -> Any:
            raise FileNotFoundError("docker")
        status, _ = check.check_container("ij", no_docker)
        self.assertEqual("SKIP", status)

    def test_unknown_container_fails_with_the_start_command(self) -> None:
        runner = lambda *_args, **_kwargs: completed(1, stderr="Error: No such object: ij")  # noqa: E731
        with self.assertRaises(check.CheckFailed) as caught:
            check.check_container("ij", runner)
        self.assertEqual(check.EXIT_CONTAINER, caught.exception.exit_code)
        self.assertIn("docker run", caught.exception.hint)

    def test_stopped_container_fails_with_the_container_state(self) -> None:
        with self.assertRaises(check.CheckFailed) as caught:
            check.check_container("ij", lambda *_args, **_kwargs: completed(0, "exited unless-stopped\n"))
        self.assertIn("exited", caught.exception.message)

    def test_docker_daemon_error_points_at_docker_desktop(self) -> None:
        runner = lambda *_args, **_kwargs: completed(1, stderr="Cannot connect to the Docker daemon")  # noqa: E731
        with self.assertRaises(check.CheckFailed) as caught:
            check.check_container("ij", runner)
        self.assertIn("Docker Desktop", caught.exception.hint)


class ParseOpenProjectsTest(unittest.TestCase):
    def test_extracts_every_path_from_the_servers_error_text(self) -> None:
        text = 'Unable to determine the target project.\n Currently open projects: ' \
               '{"projects":[{"path":"//a"},{"path":"//b"}]}'
        self.assertEqual(["//a", "//b"], check.parse_open_projects(text))

    def test_returns_nothing_when_the_text_has_no_project_list(self) -> None:
        self.assertEqual([], check.parse_open_projects("some other failure"))

    def test_returns_nothing_when_the_project_list_is_not_valid_json(self) -> None:
        self.assertEqual([], check.parse_open_projects('{"projects":[{"path":}]}'))


if __name__ == "__main__":
    unittest.main()
