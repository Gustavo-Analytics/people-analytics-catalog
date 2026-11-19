"""Estágio 2: executa código de análise gerado por um modelo, com validação prévia.

ATENÇÃO: isto é um esboço didático, NÃO uma fronteira de segurança. Ele barra o óbvio (import, acesso a
atributos privados, escrita em arquivo, funções perigosas) e expõe só cópias dos dados Gold. Não limita
tempo nem memória. Em produção, rode o código gerado num processo ou contêiner isolado, com limites.
"""
import ast
import builtins

BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr",
                 "globals", "locals", "vars", "input", "breakpoint", "help", "dir", "type"}
BLOCKED_ATTRS = {"read_csv", "read_excel", "read_parquet", "read_pickle", "read_json", "read_sql",
                 "eval", "system", "popen"}
ALLOWED_TO = {"to_dict", "to_string", "to_list", "to_numpy", "to_frame"}
SAFE_BUILTINS = {n: getattr(builtins, n)
                 for n in ("len", "min", "max", "sum", "round", "sorted", "abs", "range", "list",
                           "dict", "enumerate", "zip", "float", "int", "str", "bool", "set", "tuple")}


class SandboxError(Exception):
    pass


def validate(code: str) -> ast.AST:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"código inválido: {e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise SandboxError("import e escopo global não são permitidos")
        if isinstance(node, ast.Name) and (node.id in BLOCKED_NAMES or node.id.startswith("__")):
            raise SandboxError(f"nome bloqueado: {node.id}")
        if isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("_") or a in BLOCKED_ATTRS or (a.startswith("to_") and a not in ALLOWED_TO):
                raise SandboxError(f"atributo bloqueado: {a}")
    return tree


def run_sandboxed(code: str, tables: dict):
    """Executa `code` com `tables` (cópias dos DataFrames Gold) e devolve a variável `result`."""
    tree = validate(code)
    scope = dict(tables)
    scope["__builtins__"] = SAFE_BUILTINS
    try:
        exec(compile(tree, "<generated>", "exec"), scope)
    except Exception as e:
        raise SandboxError(f"falha ao executar: {type(e).__name__}: {e}") from e
    if "result" not in scope:
        raise SandboxError("o código não definiu a variável 'result'")
    return scope["result"]
