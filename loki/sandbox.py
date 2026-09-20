"""Execute generated Python code in a subprocess and capture the result.

Honest framing: this runs code LOCALLY, with the same OS privileges as the
user running Loki. The timeout and output capture are conveniences, not a
security boundary. Never point Loki at goals you don't trust on a machine
you care about — see the SAFETY section in the README.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    """What happened when we ran a piece of generated code."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    elapsed_s: float

    @property
    def succeeded(self) -> bool:
        """True when the process finished on its own with exit code 0."""
        return not self.timed_out and self.exit_code == 0


def run_code(
    code: str,
    workdir: str | Path,
    filename: str = "attempt.py",
    timeout: float = 30.0,
) -> ExecutionResult:
    """Write *code* to *workdir/filename* and run it with this Python.

    Returns an ExecutionResult with stdout, stderr, exit code, whether the
    timeout killed it, and elapsed seconds. Never raises for code failures —
    a crash is data the agent learns from, not an exception for us.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / filename
    script.write_text(code, encoding="utf-8")

    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            check=False,
        )
        elapsed = time.monotonic() - started
        return ExecutionResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
            elapsed_s=round(elapsed, 2),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return ExecutionResult(
            stdout=out,
            stderr=(err + f"\n[TIMEOUT] process killed after {timeout:g}s").strip(),
            exit_code=-1,
            timed_out=True,
            elapsed_s=round(elapsed, 2),
        )
