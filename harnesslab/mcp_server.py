"""Stdio entry point for a scoped MCP tool server. Receives no provider credentials."""
import argparse
import time
from pathlib import Path

from harnesslab.mcp_tools import servers
from harnesslab.models import Task
from harnesslab.sandbox import DockerSandbox, LocalSandbox, MacOSSandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["context", "repo", "exec"], required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--container")
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--allow-unsafe-local", action="store_true")
    parser.add_argument("--macos", action="store_true")
    args = parser.parse_args()
    task = Task.model_validate_json(args.task_json)
    if args.container:
        sandbox = DockerSandbox(Path(args.workspace), image=task.image)
        sandbox.name = args.container  # Attach only; the worker owns container lifecycle.
    elif args.macos:
        sandbox = MacOSSandbox(Path(args.workspace))
    else:
        sandbox = LocalSandbox(Path(args.workspace), allow_unsafe=args.allow_unsafe_local)
    try:
        servers(sandbox, task, cancel=lambda: time.time() >= args.deadline)[args.kind].run(transport="stdio")
    finally:
        if isinstance(sandbox, MacOSSandbox):
            sandbox.__exit__()


if __name__ == "__main__":
    main()
