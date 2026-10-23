"""Request-scoped ownership and paths, including legacy Rayflow processors."""
from contextvars import ContextVar, copy_context
from pathlib import Path
import os

workspace_id: ContextVar[str | None] = ContextVar('rayflow_workspace', default=None)
account: ContextVar[dict | None] = ContextVar('rayflow_account', default=None)


def owner() -> str:
    value = workspace_id.get()
    if not value:
        raise PermissionError('A workspace session is required.')
    return value


def scoped_target(function):
    context = copy_context()
    return lambda *args, **kwargs: context.run(function, *args, **kwargs)


class WorkspacePath(os.PathLike):
    """Resolve imported path constants at use time, not application import time."""
    def __init__(self, root, *parts):
        self.root = Path(root)
        self.parts = parts

    def path(self):
        identity = workspace_id.get()
        root = self.root / 'workspaces' / identity if identity else self.root
        return root.joinpath(*self.parts)

    def __truediv__(self, part):
        return WorkspacePath(self.root, *self.parts, part)

    def __fspath__(self):
        return str(self.path())

    def __str__(self):
        return str(self.path())

    def __getattr__(self, name):
        return getattr(self.path(), name)

    def __repr__(self):
        return repr(self.path())
