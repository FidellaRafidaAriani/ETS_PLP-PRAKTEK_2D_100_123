"""Regresi resolver/analyzer dan kasus tepi untuk integrasi pipeline."""
import csv

from crud import ast_nodes as ast
from crud.analyzer import analyze_statement
from crud.cli import main
from crud.parser import parse_sql
from crud.pipeline import analyze_source
from crud.resolver import Resolver


def parse_one(sql):
    script = parse_sql(sql)
    assert script.errors == [], script.errors
    assert len(script.statements) == 1
    return script.statements[0]


def resolve(sql):
    script = parse_sql(sql)
    assert script.errors == [], script.errors
    diagnostics = Resolver().resolve_script(script)
    return script, diagnostics


def column_refs(node):
    return [n for n in ast.iter_nodes(node) if isinstance(n, ast.ColumnRef)]


# --- Regresi bug resolver -------------------------------------------------

def test_resolver_shadowing_memilih_alias_scope_terdalam():
    # Alias x pada subquery harus menutupi alias x pada SELECT luar.
    script, diagnostics = resolve(
        "SELECT x.id FROM pelanggan x "
        "WHERE EXISTS (SELECT x.id FROM pesanan x)"
    )
    refs = column_refs(script)
    assert [ref.resolved for ref in refs] == ["pelanggan", "pesanan"]
    assert diagnostics == []


def test_resolver_korelasi_subquery_tetap_menemukan_alias_luar():
    # Alias yang tidak dideklarasikan ulang tetap dapat dirujuk dari subquery.
    script, diagnostics = resolve(
        "SELECT p.id FROM pelanggan p "
        "WHERE EXISTS (SELECT b.id FROM pembayaran b "
        "WHERE b.pelanggan_id = p.id)"
    )
    correlated = [ref for ref in column_refs(script) if ref.qualifier == "p"]
    assert len(correlated) == 2
    assert all(ref.resolved == "pelanggan" for ref in correlated)
    assert diagnostics == []


def test_resolver_delete_menutup_scope_sebelum_statement_berikutnya():
    # Bug lama: _delete tidak memanggil _pop sehingga alias 'lama' bocor.
    script, diagnostics = resolve(
        "DELETE FROM sesi lama; SELECT lama.id FROM pengguna baru"
    )
    assert len(script.statements) == 2
    assert [d.level for d in diagnostics] == ["error"]
    assert "alias 'lama' tidak terdefinisi" in diagnostics[0].message


def test_resolver_tanpa_qualifier_satu_tabel_diresolve():
    script, diagnostics = resolve("SELECT nama FROM pelanggan WHERE aktif = 1")
    assert {ref.resolved for ref in column_refs(script)} == {"pelanggan"}
    assert diagnostics == []


def test_resolver_tanpa_qualifier_multi_tabel_ambigu():
    script, diagnostics = resolve("SELECT id FROM a JOIN b ON a.id = b.id")
    bare = [ref for ref in column_refs(script) if ref.qualifier is None]
    assert len(bare) == 1 and bare[0].resolved is None
    assert len(diagnostics) == 1
    assert diagnostics[0].level == "warning"
    assert "kolom 'id' ambigu tanpa skema" in diagnostics[0].message


def test_resolver_kolom_tanpa_scope_memberi_warning():
    # INSERT tidak membuat scope; nama kolom di VALUES tidak punya tabel sumber.
    script, diagnostics = resolve("INSERT INTO log_event VALUES (nama_sumber)")
    ref = column_refs(script)[0]
    assert ref.resolved is None
    assert len(diagnostics) == 1 and diagnostics[0].level == "warning"
    assert "tidak ada tabel dalam scope" in diagnostics[0].message


def test_resolver_duplicate_alias_dalam_scope_menghasilkan_error():
    _, diagnostics = resolve("SELECT a.id FROM pelanggan a JOIN pesanan a ON a.id = a.id")
    assert [d.level for d in diagnostics] == ["error"]
    assert "dideklarasikan dua kali" in diagnostics[0].message


# --- Regresi bug analyzer -------------------------------------------------

def test_analyzer_subquery_update_selalu_dihitung_read():
    # Tabel target UPDATE = U; kedua subquery di SET dan WHERE = R.
    stmt = parse_one(
        "UPDATE pesanan p "
        "SET status = (SELECT status FROM arsip a WHERE a.id = p.id) "
        "WHERE p.id IN (SELECT pesanan_id FROM pelanggan)"
    )
    usage = analyze_statement(stmt)
    assert usage == {
        "pesanan": {"U"},
        "arsip": {"R"},
        "pelanggan": {"R"},
    }


def test_pipeline_update_subquery_matrix_dan_column_usage():
    # Memastikan resolver -> analyzer terhubung dan operasi kolom tetap tepat.
    result = analyze_source(
        "UPDATE pesanan p SET status = "
        "(SELECT status FROM arsip a WHERE a.id = p.id) "
        "WHERE p.id IN (SELECT pesanan_id FROM pelanggan)"
    )
    assert result.parse_errors == [] and result.lex_error is None
    assert result.matrix() == {"arsip": "R", "pelanggan": "R", "pesanan": "U"}
    cols = result.statements[0].columns
    assert ("pesanan", "status", "U") in cols
    assert ("arsip", "status", "R") in cols
    assert ("pelanggan", "pesanan_id", "R") in cols


def test_analyzer_insert_select_target_create_dan_sumber_read():
    # Bentuk AST langsung agar test analyzer tidak bergantung pada TODO parser
    # INSERT ... SELECT yang merupakan tugas lexer/parser anggota lain.
    query = parse_one("SELECT id FROM pesanan WHERE total > 10")
    stmt = ast.Insert(
        table=ast.TableRef("arsip"), columns=["id"], values=[], query=query
    )
    assert analyze_statement(stmt) == {"arsip": {"C"}, "pesanan": {"R"}}


# --- Kasus tepi / integrasi ------------------------------------------------

def test_resolver_subquery_from_diresolve_sebelum_scope_pemuat():
    script, diagnostics = resolve(
        "SELECT turunan.id FROM (SELECT id FROM pelanggan) turunan"
    )
    refs = column_refs(script)
    # Traversal AST mengunjungi kolom SELECT luar sebelum source derived table.
    assert [ref.resolved for ref in refs] == ["<subquery turunan>", "pelanggan"]
    assert diagnostics == []


def test_resolver_subquery_from_tanpa_alias_memberi_warning():
    _, diagnostics = resolve("SELECT id FROM (SELECT id FROM pelanggan)")
    assert any("subquery di FROM tanpa alias" in d.message for d in diagnostics)


def test_resolver_alias_outer_dan_inner_scope_terpisah_per_statement():
    # Nama alias boleh dipakai ulang di statement berikutnya tanpa dianggap duplikat.
    script, diagnostics = resolve(
        "SELECT a.id FROM pelanggan a; SELECT a.id FROM pesanan a"
    )
    assert len(script.statements) == 2
    assert diagnostics == []
    assert [ref.resolved for ref in column_refs(script)] == ["pelanggan", "pesanan"]


def test_cli_ast_menampilkan_diagnostik_resolver_dan_exit_nonzero(tmp_path, capsys):
    sql_file = tmp_path / "alias_salah.sql"
    sql_file.write_text("SELECT x.id FROM pelanggan p", encoding="utf-8")
    exit_code = main([str(sql_file), "--ast"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "alias 'x' tidak terdefinisi" in captured.err
    assert "Select" in captured.out


def test_cli_matrix_memasukkan_operasi_dan_kembalikan_error_resolver(tmp_path):
    sql_file = tmp_path / "query.sql"
    out_file = tmp_path / "matrix.csv"
    sql_file.write_text("SELECT x.id FROM pelanggan p", encoding="utf-8")
    exit_code = main([str(sql_file), "--out", str(out_file)])
    assert exit_code == 1
    with out_file.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows == [["file", "pelanggan"], ["query.sql", "R"]]
