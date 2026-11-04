"""Test tambahan buatan kelompok.

Bagian A: test regresi lexer/parser (Anggota 1). Gagal sebelum perbaikan, lulus sesudahnya.
Bagian B: lima test kasus tepi lexer/parser.
(Anggota 2: tambahkan test resolver/analyzer di bagian terpisah di bawah, supaya tidak bentrok merge.)
"""
import pytest

from crud import ast_nodes as ast
from crud.lexer import LexError, TokenType as T, tokenize
from crud.parser import parse_sql


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
