"""A small, interpreted Python subset. Generated code is never eval/exec'd.

Allowed: act(string), check(predicate), call(version_id, keyword bindings),
if/else, bounded for/range, assignments to strings, and f-strings. No arbitrary
attributes, imports, Python builtins, filesystem, network, or unbounded loops.
"""
import ast
from .domain import ActionError, BudgetExceeded, Predicate


class InvalidProgram(ValueError):
    pass


class Program:
    def __init__(self, source, parameters=()):
        if not isinstance(source, str) or len(source) > 20000:
            raise InvalidProgram("program must be a string of at most 20000 characters")
        self.parameters = set(parameters)
        try:
            self.tree = ast.parse(source)
        except (SyntaxError, RecursionError) as exc:
            raise InvalidProgram(str(exc)) from exc
        if not self.tree.body or len(list(ast.walk(self.tree))) > 2000:
            raise InvalidProgram("empty or oversized program")
        self._validate(self.tree.body, set(parameters))

    def _expr(self, node, names):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bool, int)):
            if isinstance(node.value, str) and len(node.value) > 4000:
                raise InvalidProgram("string too long")
            return
        if isinstance(node, ast.Name) and node.id in names:
            return
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    if part.format_spec is not None or part.conversion != -1:
                        raise InvalidProgram("format specifications are not allowed")
                    self._expr(part.value, names)
                else:
                    self._expr(part, names)
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._expr(node.operand, names)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in {"act", "check", "call"} or len(node.args) != 1:
                raise InvalidProgram("only act, check and call with one positional argument are allowed")
            if name != "call" and node.keywords:
                raise InvalidProgram("keywords are only allowed for skill calls")
            self._expr(node.args[0], names)
            for kw in node.keywords:
                if kw.arg is None or kw.arg.startswith("_"):
                    raise InvalidProgram("invalid call binding")
                self._expr(kw.value, names)
            return
        raise InvalidProgram(f"unsupported expression: {type(node).__name__}")

    def _validate(self, nodes, names):
        for node in nodes:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._expr(node.value, names)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name.startswith("_") or name in {"act", "check", "call", "range"}:
                    raise InvalidProgram("reserved name")
                self._expr(node.value, names)
                names.add(name)
            elif isinstance(node, ast.If):
                self._expr(node.test, names)
                self._validate(node.body, set(names))
                self._validate(node.orelse, set(names))
            elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                it = node.iter
                if (not isinstance(it, ast.Call) or not isinstance(it.func, ast.Name)
                        or it.func.id != "range" or len(it.args) != 1 or it.keywords
                        or not isinstance(it.args[0], ast.Constant)
                        or type(it.args[0].value) is not int or not 0 <= it.args[0].value <= 20
                        or node.orelse or node.target.id.startswith("_")
                        or node.target.id in {"act", "check", "call", "range"}):
                    raise InvalidProgram("loops must use range(integer between 0 and 20)")
                self._validate(node.body, names | {node.target.id})
            else:
                raise InvalidProgram(f"unsupported statement: {type(node).__name__}")

    def run(self, episode, bindings, call_skill, budget=1000):
        if set(bindings) != self.parameters or any(not isinstance(v, str) for v in bindings.values()):
            raise InvalidProgram("bindings must match the typed string parameters")
        names = dict(bindings)
        remaining = budget

        def value(node):
            nonlocal remaining
            remaining -= 1
            if remaining < 0:
                raise BudgetExceeded("program instruction budget exhausted")
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return names[node.id]
            if isinstance(node, ast.JoinedStr):
                return "".join(str(value(p.value if isinstance(p, ast.FormattedValue) else p)) for p in node.values)
            if isinstance(node, ast.UnaryOp):
                return not value(node.operand)
            arg = value(node.args[0])
            if not isinstance(arg, str):
                raise InvalidProgram("action, predicate, and skill id must be strings")
            if node.func.id == "check":
                return episode.env.state.holds(Predicate.parse(arg))
            if node.func.id == "act":
                return episode.act(arg)
            return call_skill(arg, {kw.arg: value(kw.value) for kw in node.keywords})

        def block(nodes):
            nonlocal remaining
            for node in nodes:
                remaining -= 1
                if remaining < 0:
                    raise BudgetExceeded("program instruction budget exhausted")
                if isinstance(node, ast.Expr):
                    value(node.value)
                elif isinstance(node, ast.Assign):
                    names[node.targets[0].id] = value(node.value)
                elif isinstance(node, ast.If):
                    block(node.body if value(node.test) else node.orelse)
                else:
                    for i in range(node.iter.args[0].value):
                        names[node.target.id] = i
                        block(node.body)
        block(self.tree.body)

    def render(self):
        # A fixed, lossless rule: numbering preserves all branches and indentation.
        lines = ast.unparse(self.tree).splitlines()
        return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
