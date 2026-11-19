"""Desktop control is intentionally disabled until explicit permissions are designed."""
def click(x: int, y: int, confirmed: bool = False):
    from app.automation.safety import require_confirmation
    require_confirmation("desktop mouse control", confirmed)
    raise NotImplementedError("Desktop control is not enabled in this starter scaffold.")
