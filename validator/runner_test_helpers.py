"""
Test doubles for ``validator.runner``.

These fakes let ``execute()`` be unit-tested without a Docker daemon (CI has no
Docker-in-Docker). A ``FakeDockerClient`` mimics the slice of the docker-py API
the runner touches — ``client.containers.run(...) -> container`` and the
container's ``wait`` / ``logs`` / ``kill`` / ``remove`` — and records what it was
called with so tests can assert the hardening flags were passed and that the
container was removed even on timeout.

The fakes raise the *real* exception types the runner catches: a timeout raises
``requests.exceptions.ReadTimeout`` (what docker-py raises when ``wait`` exceeds
its timeout) and a launch failure raises ``docker.errors.APIError``. The docker
SDK and requests are core dependencies, so importing them here is always safe.

This module lives next to ``runner.py`` (not under ``tests/``) so it ships with
the package and the runner and its doubles version together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from docker.errors import APIError


@dataclass
class FakeContainer:
    """Stand-in for a detached docker-py ``Container``.

    Configure the finished-process result via ``status_code`` / ``stdout`` /
    ``stderr``; set ``timeout=True`` to make ``wait`` raise the timeout
    exception the runner treats as a wall-clock expiry. ``wait_error`` injects a
    non-timeout ``DockerException`` from ``wait``.
    """

    status_code: int = 0
    stdout: bytes = b""
    stderr: bytes = b""
    timeout: bool = False
    wait_error: BaseException | None = None

    # Observed interactions, for assertions.
    wait_calls: list[float | None] = field(default_factory=list)
    killed: bool = False
    removed: bool = False
    remove_force: bool | None = None

    def wait(self, **kwargs: Any) -> dict[str, Any]:
        self.wait_calls.append(kwargs.get("timeout"))
        if self.timeout:
            raise requests.exceptions.ReadTimeout("fake wait timed out")
        if self.wait_error is not None:
            raise self.wait_error
        return {"StatusCode": self.status_code, "Error": None}

    def logs(self, **kwargs: Any) -> bytes:
        want_stdout = kwargs.get("stdout", True)
        want_stderr = kwargs.get("stderr", False)
        if want_stdout and not want_stderr:
            return self.stdout
        if want_stderr and not want_stdout:
            return self.stderr
        return self.stdout + self.stderr

    def kill(self, *args: Any, **kwargs: Any) -> None:
        self.killed = True

    def remove(self, *args: Any, **kwargs: Any) -> None:
        self.removed = True
        self.remove_force = kwargs.get("force")


@dataclass
class FakeContainers:
    """Stand-in for ``client.containers``; records every ``run`` call."""

    container: FakeContainer
    run_error: BaseException | None = None
    run_calls: list[dict[str, Any]] = field(default_factory=list)

    def run(self, image: str, **kwargs: Any) -> FakeContainer:
        self.run_calls.append({"image": image, **kwargs})
        if self.run_error is not None:
            raise self.run_error
        return self.container


@dataclass
class FakeDockerClient:
    """Minimal ``docker.from_env()`` stand-in exposing ``.containers``."""

    container: FakeContainer = field(default_factory=FakeContainer)
    run_error: BaseException | None = None
    containers: FakeContainers = field(init=False)

    def __post_init__(self) -> None:
        self.containers = FakeContainers(self.container, self.run_error)


def succeeding_client(stdout: bytes, *, status_code: int = 0) -> FakeDockerClient:
    """A client whose container exits ``status_code`` with ``stdout`` on stdout."""
    return FakeDockerClient(FakeContainer(status_code=status_code, stdout=stdout))


def timing_out_client() -> FakeDockerClient:
    """A client whose container never finishes within the wait timeout."""
    return FakeDockerClient(FakeContainer(timeout=True))


def failing_to_start_client(message: str = "no such image") -> FakeDockerClient:
    """A client whose ``containers.run`` raises a docker ``APIError``."""
    return FakeDockerClient(run_error=APIError(message))


__all__ = [
    "FakeContainer",
    "FakeContainers",
    "FakeDockerClient",
    "failing_to_start_client",
    "succeeding_client",
    "timing_out_client",
]
