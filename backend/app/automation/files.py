from app.automation.safety import safe_workspace_path

def create_folder(relative_path: str):
    path = safe_workspace_path(relative_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

def write_text(relative_path: str, content: str):
    path = safe_workspace_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)

def search_files(relative_path: str = ".", pattern: str = "*"):
    root = safe_workspace_path(relative_path)
    if not root.exists():
        return []
    return [str(path) for path in root.rglob(pattern) if path.is_file()][:200]
