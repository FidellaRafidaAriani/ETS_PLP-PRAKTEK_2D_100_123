"""Resolver: pass terpisah setelah parsing (Crafting Interpreters bab 11).

Membangun scope untuk setiap SELECT, UPDATE, dan DELETE, menghubungkan
qualifier (p pada p.nama) ke tabel, lalu mengisi ColumnRef.resolved.
Aturan lengkap: SPESIFIKASI.md bagian 4.
"""
from dataclasses import dataclass

from . import ast_nodes as ast


@dataclass
class Diagnostic:
    level: str              # "error" atau "warning"
    message: str
    line: int

    def __str__(self) -> str:
        return f"baris {self.line}: {self.level}: {self.message}"


@dataclass
class ScopeEntry:
    name: str               # nama yang dipakai sebagai qualifier (alias atau nama tabel)
    table: str | None       # nama tabel lengkap; None untuk subquery di FROM
    line: int


class Scope:
    def __init__(self, parent: "Scope | None" = None):
        self.parent = parent
        self.entries: dict[str, ScopeEntry] = {}


def _target_of(entry: ScopeEntry) -> str:
    return entry.table if entry.table is not None else f"<subquery {entry.name}>"


class Resolver:
    def __init__(self):
        self.scope: Scope | None = None
        self.diagnostics: list[Diagnostic] = []

    def resolve_script(self, script: ast.Script) -> list[Diagnostic]:
        """Resolve each statement with an independent top-level scope chain."""
        self.scope = None
        self.diagnostics = []
        for stmt in script.statements:
            # Every statement must return to the top-level (None) scope on its
            # own. Do not forcibly reset here: that would hide a missing _pop.
            for node in ast.iter_nodes(stmt):
                if isinstance(node, ast.ColumnRef):
                    node.resolved = None
            self.resolve_statement(stmt)
        return self.diagnostics

    def resolve_statement(self, stmt) -> None:
        if isinstance(stmt, ast.Select):
            self._select(stmt)
        elif isinstance(stmt, ast.Insert):
            self._insert(stmt)
        elif isinstance(stmt, ast.Update):
            self._update(stmt)
        elif isinstance(stmt, ast.Delete):
            self._delete(stmt)

    # ---- scope ----------------------------------------------------------
    def _push(self) -> None:
        self.scope = Scope(self.scope)

    def _pop(self) -> None:
        self.scope = self.scope.parent

    def _error(self, message: str, line: int) -> None:
        self.diagnostics.append(Diagnostic("error", message, line))

    def _warning(self, message: str, line: int) -> None:
        self.diagnostics.append(Diagnostic("warning", message, line))

    def _declare(self, name: str, table: str | None, line: int) -> None:
        if name in self.scope.entries:
            self._error(f"alias '{name}' dideklarasikan dua kali dalam scope yang sama", line)
            return
        self.scope.entries[name] = ScopeEntry(name, table, line)

    def _declare_source(self, source) -> None:
        if isinstance(source, ast.TableRef):
            name = source.alias or source.name.split(".")[-1]
            self._declare(name, source.name, source.line)
        elif source.alias is None:
            self._warning("subquery di FROM tanpa alias tidak bisa dirujuk", source.line)
        else:
            self._declare(source.alias, None, source.line)

    def _lookup(self, name: str) -> ScopeEntry | None:
        """Cari alias dari scope terdalam ke scope induk (nearest binding)."""
        scope = self.scope
        while scope is not None:
            if name in scope.entries:
                return scope.entries[name]
            scope = scope.parent
        return None

    # ---- statement ------------------------------------------------------
    def _select(self, sel: ast.Select) -> None:
        sources = sel.sources + [j.source for j in sel.joins]
        # Subquery di FROM tidak melihat tabel lain di FROM yang sama,
        # jadi di-resolve sebelum scope SELECT ini dibuat.
        for src in sources:
            if isinstance(src, ast.DerivedTable):
                self._select(src.query)
        self._push()
        try:
            for src in sources:
                self._declare_source(src)
            for item in sel.columns:
                if isinstance(item, ast.SelectItem):
                    self._expr(item.expr)
            for join in sel.joins:
                self._expr(join.condition)
            self._expr(sel.where)
            for expr in sel.group_by:
                self._expr(expr)
            for item in sel.order_by:
                self._expr(item.expr)
        finally:
            self._pop()

    def _insert(self, ins: ast.Insert) -> None:
        for row in ins.values:
            for expr in row:
                self._expr(expr)
        if ins.query is not None:
            self._select(ins.query)

    def _update(self, upd: ast.Update) -> None:
        self._push()
        try:
            self._declare_source(upd.table)
            for assignment in upd.assignments:
                self._column(assignment.column)
                self._expr(assignment.value)
            self._expr(upd.where)
        finally:
            self._pop()

    def _delete(self, dele: ast.Delete) -> None:
        self._push()
        try:
            self._declare_source(dele.table)
            self._expr(dele.where)
        finally:
            self._pop()

    # ---- ekspresi -------------------------------------------------------
    def _expr(self, expr) -> None:
        if expr is None:
            return
        if isinstance(expr, ast.ColumnRef):
            self._column(expr)
        elif isinstance(expr, ast.BinaryOp):
            self._expr(expr.left)
            self._expr(expr.right)
        elif isinstance(expr, ast.UnaryOp):
            self._expr(expr.operand)
        elif isinstance(expr, ast.InExpr):
            self._expr(expr.expr)
            for value in expr.values or []:
                self._expr(value)
            if expr.query is not None:
                self._select(expr.query)
        elif isinstance(expr, ast.Between):
            self._expr(expr.expr)
            self._expr(expr.low)
            self._expr(expr.high)
        elif isinstance(expr, ast.IsNull):
            self._expr(expr.expr)
        elif isinstance(expr, (ast.Exists, ast.Subquery)):
            self._select(expr.query)
        elif isinstance(expr, ast.FunctionCall):
            for arg in expr.args:
                self._expr(arg)

    def _column(self, col: ast.ColumnRef) -> None:
        # Hasil boleh dihitung ulang ketika AST yang sama di-resolve kembali.
        col.resolved = None
        if col.qualifier is not None:
            entry = self._lookup(col.qualifier)
            if entry is None:
                self._error(f"alias '{col.qualifier}' tidak terdefinisi", col.line)
            else:
                col.resolved = _target_of(entry)
            return

        # Nama tanpa qualifier hanya boleh memakai deklarasi di scope
        # terdalam. Tidak ada pencarian ke parent untuk kasus ini.
        entries = self.scope.entries if self.scope is not None else {}
        if not entries:
            self._warning(
                f"kolom '{col.name}' tidak dapat di-resolve karena tidak ada tabel dalam scope",
                col.line,
            )
        elif len(entries) == 1:
            col.resolved = _target_of(next(iter(entries.values())))
        else:
            self._warning(f"kolom '{col.name}' ambigu tanpa skema", col.line)
