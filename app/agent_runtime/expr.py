"""Restricted expression evaluation — for computed columns in table panels.

Security boundary: only "field names + numbers + arithmetic + parentheses" are
allowed; function calls, attribute access, subscripts, comprehensions, etc. are
all forbidden. The LLM may *declare* a column's formula (e.g.
``current_price * shares``) but can never execute arbitrary code — consistent
with sparrow's guiding principle: the LLM emits declarations, not code.

Usage:
    safe_eval('current_price * shares', {'current_price': 10, 'shares': 100})  # -> 1000
    safe_eval('(current_price - avg_cost) / avg_cost * 100', row)             # P&L %
"""
import ast
import operator

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class ExprError(Exception):
    pass


def _to_num(v):
    """Coerce a field value to a number; non-numeric values (e.g. string names)
    are returned as-is so text columns keep working."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _eval_node(node, row):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, row)
    # Field name
    if isinstance(node, ast.Name):
        if node.id not in row:
            return 0  # missing field -> 0, so the whole column doesn't crash
        return _to_num(row[node.id])
    # Numeric / string constant
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str)):
            return node.value
        raise ExprError(f'unsupported constant: {node.value!r}')
    # Binary operation
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if not op:
            raise ExprError(f'unsupported operator: {type(node.op).__name__}')
        left, right = _eval_node(node.left, row), _eval_node(node.right, row)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return 0  # text in arithmetic -> safe fallback
        try:
            return op(left, right)
        except ZeroDivisionError:
            return 0
    # Unary operation
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if not op:
            raise ExprError(f'unsupported unary op: {type(node.op).__name__}')
        return op(_eval_node(node.operand, row))
    raise ExprError(f'disallowed expression node: {type(node).__name__}')


def safe_eval(expr, row):
    """Evaluate an expression against a single row. Returns None on failure
    (the render layer shows a placeholder)."""
    try:
        tree = ast.parse(str(expr), mode='eval')
        val = _eval_node(tree, row)
        if isinstance(val, float):
            return round(val, 2)
        return val
    except (ExprError, SyntaxError, ValueError):
        return None


def is_safe_expr(expr):
    """Static check: does the expression contain only whitelisted nodes?
    (used when validating a panel spec at creation time)."""
    try:
        tree = ast.parse(str(expr), mode='eval')
    except SyntaxError:
        return False
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant,
               ast.Load) + tuple(_BINOPS) + tuple(_UNARYOPS)
    for n in ast.walk(tree):
        if not isinstance(n, allowed):
            return False
    return True
