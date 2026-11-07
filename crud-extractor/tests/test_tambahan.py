"""Test tambahan buatan kelompok.

Bagian A: test regresi lexer/parser (Anggota 1). Gagal sebelum perbaikan, lulus sesudahnya.
Bagian B: lima test kasus tepi lexer/parser.
(Anggota 2: tambahkan test resolver/analyzer di bagian terpisah di bawah, supaya tidak bentrok merge.)
"""
import csv

import pytest

from crud import ast_nodes as ast
from crud.lexer import LexError, TokenType as T, tokenize
from crud.parser import parse_sql
from crud.analyzer import analyze_statement
from crud.cli import main
from crud.pipeline import analyze_source
from crud.resolver import Resolver


def _one(sql):
    script = parse_sql(sql)
    assert script.errors == [], script.errors
    assert len(script.statements) == 1
    return script.statements[0]


# ======================= A. REGRESI LEXER / PARSER ==========================
def test_regresi_keyword_tidak_peka_huruf_besar_kecil():
    # Bug: 'select' jadi IDENT karena `text in KEYWORDS` membandingkan teks mentah.
    for kata in ("select", "Select", "SELECT"):
        tok = tokenize(kata)[0]
        assert tok.type == T.KEYWORD and tok.value == "SELECT"


def test_regresi_operator_tidak_sama_satu_token():
    # Bug: '<>' terpecah jadi '<' lalu '>' (maximal munch tidak dipenuhi).
    toks = [t for t in tokenize("a <> b") if t.type != T.EOF]
    assert [t.value for t in toks] == ["a", "<>", "b"]
    assert toks[1].type == T.OP


def test_regresi_kutip_ganda_dalam_string():
    # Bug: 'O''Brien' terpecah jadi dua STRING ('O' dan 'Brien').
    toks = [t for t in tokenize("'O''Brien'") if t.type != T.EOF]
    assert len(toks) == 1 and toks[0].type == T.STRING and toks[0].value == "O'Brien"


def test_regresi_komentar_blok_lintas_baris():
    # TODO(T3): sebelumnya selalu LexError. Posisi token sesudahnya harus tetap benar.
    toks = tokenize("/* a\n b * c */ SELECT")
    assert toks[0].value == "SELECT" and toks[0].line == 2


def test_regresi_komentar_blok_tidak_ditutup():
    with pytest.raises(LexError):
        tokenize("SELECT /* belum ditutup")


def test_regresi_presedensi_and_lebih_tinggi_dari_or():
    # Bug: AND dan OR ditangani satu fungsi -> (a OR b) AND c. Seharusnya a OR (b AND c).
    w = _one("SELECT x FROM t WHERE a = 1 OR b = 2 AND c = 3").where
    assert w.op == "OR"
    assert w.left.op == "=" and w.right.op == "AND"


def test_regresi_and_lalu_or():
    w = _one("SELECT x FROM t WHERE a = 1 AND b = 2 OR c = 3").where
    assert w.op == "OR" and w.left.op == "AND" and w.right.op == "="


def test_regresi_left_outer_join():
    # Bug: "LEFT OUTER JOIN" ditolak ('OUTER' tidak dikenali parser).
    s = _one("SELECT a.id FROM a LEFT OUTER JOIN b ON b.a_id = a.id")
    assert s.joins[0].kind == "LEFT" and s.joins[0].source.name == "b"


def test_regresi_recovery_berhenti_di_titik_koma():
    # Bug: _synchronize membuang SEMUA token sampai EOF -> statement valid sesudahnya hilang.
    script = parse_sql("SELECT id nama, FROM x;\nSELECT 1 FROM y;\nDELETE FROM z;")
    assert len(script.errors) == 1
    assert [type(s).__name__ for s in script.statements] == ["Select", "Delete"]


def test_regresi_insert_select():
    # TODO(T1): sebelumnya ParseError "INSERT ... SELECT belum didukung".
    s = _one("INSERT INTO arsip SELECT id FROM pesanan")
    assert isinstance(s.query, ast.Select) and s.values == [] and s.columns == []
    assert s.query.sources[0].name == "pesanan"


# ======================= B. KASUS TEPI ======================================
def test_tepi_komentar_blok_langsung_tutup():
    # '/**/' dan '/*/': penutup harus dicari SETELAH '/*', jangan memakai '*' pembuka.
    assert [t.type for t in tokenize("/**/ a")] == [T.IDENT, T.EOF]
    with pytest.raises(LexError):
        tokenize("/*/ a")


def test_tepi_string_hanya_kutip_dan_string_kosong():
    # "''" = string kosong, "''''" = satu karakter kutip. Mudah salah saat mengurai '' berurutan.
    assert tokenize("''")[0].value == ""
    assert tokenize("''''")[0].value == "'"


def test_tepi_kata_berawalan_keyword_adalah_ident():
    # 'selection' dan 'fromage' hanya diawali keyword -> tetap IDENT.
    toks = tokenize("selection fromage")
    assert [t.type for t in toks[:2]] == [T.IDENT, T.IDENT]


def test_tepi_between_and_milik_between():
    # AND di BETWEEN bukan operator logika; AND sesudahnya tetap AND biasa.
    w = _one("SELECT x FROM t WHERE a BETWEEN 1 AND 2 AND b = 3").where
    assert w.op == "AND" and isinstance(w.left, ast.Between)


def test_tepi_semicolon_beruntun_dan_error_di_akhir_input():
    # Statement kosong diabaikan; error di EOF (tanpa ';') tetap tepat satu error & tidak loop.
    assert parse_sql(";;SELECT a FROM t;;").errors == []
    sc = parse_sql("SELECT a FROM")
    assert len(sc.errors) == 1 and sc.statements == []


# ======================= C. RESOLVER / ANALYZER / CLI (Anggota 2) =======================
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
