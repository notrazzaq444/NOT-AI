from datetime import datetime
from zoneinfo import ZoneInfo

def current_datetime(timezone: str = "Asia/Karachi"):
    return datetime.now(ZoneInfo(timezone)).isoformat()

def calculate(expression: str):
    """Intentionally limited arithmetic evaluator. No Python eval."""
    import ast, operator
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
           ast.Mod: operator.mod}
    def walk(node):
        if isinstance(node, ast.Expression): return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops: return ops[type(node.op)](walk(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in ops: return ops[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError("Only basic arithmetic expressions are allowed.")
    tree = ast.parse(expression, mode="eval")
    return walk(tree)
