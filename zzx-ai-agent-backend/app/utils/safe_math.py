"""基于 AST 白名单的有限数学表达式计算器。"""
import ast
import math
import operator


MAX_EXPRESSION_LENGTH = 128
MAX_AST_NODES = 64
MAX_INTEGER_BITS = 4096
MAX_ABSOLUTE_RESULT = 1e100
MAX_EXPONENT = 10

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class SafeMathError(ValueError):
    pass


def _check_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeMathError("只允许数字")
    if isinstance(value, int) and value.bit_length() > MAX_INTEGER_BITS:
        raise SafeMathError("计算结果过大")
    if isinstance(value, float) and (not math.isfinite(value) or abs(value) > MAX_ABSOLUTE_RESULT):
        raise SafeMathError("计算结果超出范围")
    return value


def evaluate_math_expression(expression):
    expression = str(expression or "").strip()
    if not expression or len(expression) > MAX_EXPRESSION_LENGTH:
        raise SafeMathError("表达式为空或过长")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise SafeMathError("表达式语法无效") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise SafeMathError("表达式过于复杂")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return _check_number(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _check_number(_UNARY_OPERATORS[type(node.op)](visit(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Pow):
                if not isinstance(right, int) or abs(right) > MAX_EXPONENT:
                    raise SafeMathError("指数必须是绝对值不超过 10 的整数")
            try:
                return _check_number(_BINARY_OPERATORS[type(node.op)](left, right))
            except (ArithmeticError, OverflowError) as exc:
                raise SafeMathError("表达式无法计算") from exc
        raise SafeMathError("表达式包含未批准的语法")

    return visit(tree)

