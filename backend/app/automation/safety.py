from pathlib import Path

WORKSPACE = (Path.home() / "NOT-Workspace").resolve()
ALLOWED_COMMANDS = {"whoami", "pwd"}

def safe_workspace_path(relative_path: str) -> Path:
    target = (WORKSPACE / relative_path).resolve()
    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise PermissionError("Path is outside the NOT workspace.")
    return target

def require_confirmation(action: str, confirmed: bool = False):
    if not confirmed:
        raise PermissionError(f"Confirmation required before: {action}")
