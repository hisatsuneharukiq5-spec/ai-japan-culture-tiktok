"""Pluggable outcome checks.

Register a new check type by subclassing BaseCheck and calling register():

    from quiet_pipelines.checks import BaseCheck, register

    @register
    class MyCheck(BaseCheck):
        type_name = "my_check"
        def latest_output(self): ...
"""
from __future__ import annotations

from .base import BaseCheck, CheckError, CheckResult  # noqa: F401
from .feeds import HttpFreshness, RssFreshness
from .repo import RepoFileFreshness
from .youtube import YouTubeLatestUpload

REGISTRY: dict[str, type[BaseCheck]] = {}


def register(cls: type[BaseCheck]) -> type[BaseCheck]:
    if not cls.type_name:
        raise ValueError(f"{cls.__name__} has no type_name")
    REGISTRY[cls.type_name] = cls
    return cls


for _cls in (YouTubeLatestUpload, RssFreshness, HttpFreshness, RepoFileFreshness):
    register(_cls)


def build(spec: dict, **kw) -> BaseCheck:
    """spec = {"name": ..., "type": ..., ...params}"""
    kind = spec.get("type")
    if kind not in REGISTRY:
        raise KeyError(f"unknown check type {kind!r}; known: {', '.join(sorted(REGISTRY))}")
    params = {k: v for k, v in spec.items() if k not in ("name", "type", "workflows", "enabled")}
    return REGISTRY[kind](spec.get("name") or kind, params, **kw)
