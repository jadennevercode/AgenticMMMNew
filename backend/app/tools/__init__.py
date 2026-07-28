"""Analysis tools — the registry and the explicit-invocation trace.

The S2 data checks and the OLS fit are not anonymous helper functions: they are
**registered tools** with a catalog entry (`ToolSpec`) and a recorded invocation
(`ToolInvocation`) every time a task calls one, so the UI can show *which* tool
ran, with what input, producing what, and how long it took.

The wrappers are deliberately thin — each `Tool.run` delegates straight to the
existing implementation, so registering a computation as a tool can never change
its numbers (`app/tools/_test_tools.py` asserts exactly that, cell for cell).
"""
from app.tools.registry import TOOLS, Tool, get, list_specs
from app.tools.tracing import tool_run, traced

__all__ = ["TOOLS", "Tool", "get", "list_specs", "tool_run", "traced"]
