# Laporan Bug

Salin blok di bawah untuk setiap bug. Bagian **Akar masalah** wajib ditulis dengan kata-kata
sendiri dan memakai konsep dari *Crafting Interpreters* (sebutkan bab). Bagian ini diuji lisan.

Bug 1 sampai 8 adalah bagian Anggota 1 (lexer, parser, AST). Bug berikutnya ditulis oleh
Anggota 2 (resolver, analyzer), dimulai dari Bug 9.

---

## Bug 1: Keyword huruf kecil tidak dikenali

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** Input `select id from t` ditolak parser dengan pesan
`Baris 1, kolom 1: diharapkan awal statement (SELECT, INSERT, UPDATE, DELETE), ditemukan 'select'`.
Lexer menjadikan kata `select` token `IDENT`, bukan `KEYWORD`. SPESIFIKASI.md bagian 2.2
menyebutkan keyword tidak peka huruf besar/kecil dan nilai token keyword selalu huruf besar,
jadi seharusnya yang keluar adalah `KEYWORD` bernilai `SELECT`. Akibatnya `pemeliharaan.sql`,
yang ditulis dengan huruf kecil, tidak bisa diparse sama sekali.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
select id from t
```

**Akar masalah.** Di fungsi `_word`, lexeme yang sudah terbaca langsung dicek dengan
`text in KEYWORDS`, padahal isi `KEYWORDS` huruf besar semua. Jadi `select` dan `Select` tidak
pernah cocok dan jatuh menjadi `IDENT`. Pada bab 4 (bagian Reserved Words and Identifiers),
scanner membaca satu lexeme utuh dulu, baru mencarinya di tabel kata cadangan untuk menentukan
jenis tokennya. Lox peka huruf besar/kecil sehingga pencarian langsung cukup, sedangkan SQL
tidak, jadi kunci pencariannya harus dinormalisasi lebih dulu. Nilai token keyword juga harus
ikut dinormalisasi karena parser membandingkan `tok.value` dengan string seperti `"SELECT"` dan
`"FROM"`.

**Perbaikan.** File `crud/lexer.py`, fungsi `_word`: pengecekan diganti menjadi
`text.upper() in KEYWORDS` dan yang disimpan sebagai nilai token keyword adalah `text.upper()`.
Nilai `IDENT` tidak kuubah karena menurut spesifikasi 2.2 yang menjadikannya huruf kecil adalah
parser. Alternatif yang sempat kupikirkan adalah mengubah seluruh teks SQL menjadi huruf besar
sebelum di-scan. Tidak kupilih karena isi string seperti `'LUNAS'` dan `'lunas'` bisa berbeda
artinya, jadi tidak boleh ikut berubah.

**Test regresi.** `test_regresi_keyword_tidak_peka_huruf_besar_kecil` di `tests/test_tambahan.py`.
Sebelum perbaikan gagal karena tipe tokennya `IDENT`, sesudahnya lulus.

**Peran AI.** AI membantu menunjukkan baris di `_word` yang menjadi penyebab. Aku
memverifikasinya sendiri dengan memanggil `tokenize("select")` sebelum dan sesudah perbaikan,
lalu menjalankan `pytest`. Test bawaan `test_keyword_huruf_kecil` yang tadinya gagal menjadi
lulus.

---

## Bug 2: Operator `<>` pecah jadi dua token

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** Untuk `SELECT a FROM t WHERE a <> 1`, lexer menghasilkan token `<` lalu `>`, dan
parser berhenti dengan `Baris 1, kolom 26: diharapkan ekspresi, ditemukan '>'`. Menurut
SPESIFIKASI.md bagian 2.5, `<>` harus menjadi satu token `OP` (maximal munch).
`laporan_penjualan.sql` memakai `<>`, sehingga file itu ikut gagal diparse.

**Reproduksi minimal.**

```sql
SELECT a FROM t WHERE a <> 1
```

**Akar masalah.** Cabang untuk karakter `<` di `_scan_token` hanya mengecek satu kemungkinan,
yaitu `=` untuk membentuk `<=`. Karakter `>` tidak pernah dicek, sehingga `<` keluar sendirian
dan `>` terbaca sebagai token berikutnya. Ini melanggar prinsip maximal munch di bab 4 (bagian
Longer Lexemes): kalau beberapa lexeme bisa cocok di posisi yang sama, scanner harus mengambil
yang paling panjang. Untuk `<` ada tiga kandidat, yaitu `<`, `<=`, dan `<>`, dan ketiganya harus
diperiksa.

**Perbaikan.** File `crud/lexer.py`, cabang `<` di `_scan_token`: kutambahkan pengecekan
`self._match(">")` yang menghasilkan `<>`. Alternatif yang sempat kupikirkan adalah membiarkan
lexer apa adanya dan meminta parser menggabungkan `<` dan `>` yang berurutan. Tidak kupilih
karena itu memindahkan pekerjaan scanner ke parser, dan `a < > b` yang berspasi ikut tergabung
padahal seharusnya salah.

**Test regresi.** `test_regresi_operator_tidak_sama_satu_token`. Sebelum perbaikan gagal karena
token-nya terpecah dua, sesudahnya lulus.

**Peran AI.** AI menunjukkan bahwa cabang `<` belum lengkap. Aku memverifikasinya dengan
mencetak daftar token untuk `a <> b` sebelum dan sesudah perbaikan.

---

## Bug 3: Dua kutip berurutan di dalam string memecah string

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** String `'O''Brien'` menjadi dua token `STRING`, yaitu `O` dan `Brien`. Untuk
`SELECT a FROM t WHERE n = 'O''Brien'` parser melaporkan
`Baris 1, kolom 30: diharapkan ';' di akhir statement, ditemukan 'Brien'`. Menurut
SPESIFIKASI.md bagian 2.4, dua kutip berurutan di dalam string mewakili satu karakter kutip,
jadi hasil yang benar adalah satu token `STRING` bernilai `O'Brien`. `pemeliharaan.sql` memakai
`'O''Brien'` dan `'O''Neil'`.

**Reproduksi minimal.**

```sql
SELECT a FROM t WHERE n = 'O''Brien'
```

**Akar masalah.** Fungsi `_string` langsung berhenti begitu bertemu kutip penutup pertama, tanpa
melihat karakter sesudahnya. Pada bab 4 (bagian String literals), scanner membaca isi string
sampai bertemu penutupnya. Di SQL, kutip bisa menjadi bagian dari isi string kalau ditulis dua
kali, jadi satu kutip saja belum cukup untuk memutuskan string sudah selesai. Scanner perlu
lookahead satu karakter: setelah membaca `'`, karakter berikutnya diintip. Kalau ternyata `'`
lagi, itu escape dan string berlanjut. Kalau bukan, string memang selesai.

**Perbaikan.** File `crud/lexer.py`, fungsi `_string`: saat bertemu `'` dan `_peek()` juga `'`,
kutip kedua dikonsumsi, satu karakter `'` ditambahkan ke isi string, lalu loop dilanjutkan. Kalau
tidak, string selesai. Alternatif yang sempat kupikirkan adalah memakai regex untuk mengambil
seluruh string sekaligus. Tidak kupilih karena lexer ini dibuat per karakter seperti di bab 4,
dan posisi baris dan kolom tetap harus dihitung oleh `_advance`.

**Test regresi.** `test_regresi_kutip_ganda_dalam_string`. Sebelum perbaikan gagal karena
hasilnya dua token, sesudahnya lulus. Ada juga test kasus tepi terkait,
`test_tepi_string_hanya_kutip_dan_string_kosong`, untuk `''` dan `''''`.

**Peran AI.** AI menjelaskan bahwa ini kasus lookahead. Aku memverifikasinya dengan mencetak
token untuk `'O''Brien'`, `''`, dan `''''`.

---

## Bug 4: AND dan OR punya presedensi yang sama

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** Kondisi `a = 1 OR b = 2 AND c = 3` diparse sebagai `(a = 1 OR b = 2) AND c = 3`.
SPESIFIKASI.md bagian 3.1 menetapkan bentuk yang benar, yaitu `a = 1 OR (b = 2 AND c = 3)`. Bug
ini muncul di `audit.sql` dan `pemeliharaan.sql` yang punya `WHERE ... OR ... AND ...`. Daftar
tabel di CRUD matrix tidak berubah karenanya, tetapi bentuk pohonnya salah dan melanggar
spesifikasi.

**Reproduksi minimal.**

```sql
SELECT x FROM t WHERE a = 1 OR b = 2 AND c = 3
```

Sebelum perbaikan, akar pohonnya `AND` dengan anak kiri `OR`. Yang benar, akarnya `OR` dengan anak
kanan `AND`.

**Akar masalah.** Fungsi `_logical` menangani `AND` dan `OR` dalam satu loop
`while self._check_kw("AND", "OR")`, sehingga keduanya mengikat sama kuat dan asosiatif kiri.
Pada recursive descent (bab 6, Parsing Expressions), presedensi dinyatakan lewat struktur
fungsi: satu fungsi untuk satu tingkat presedensi, dan fungsi tingkat yang lebih rendah
memanggil fungsi tingkat yang lebih tinggi untuk mengambil operandnya. Grammar di spesifikasi
sudah memisahkan `or_expr` dan `and_expr`, tetapi kodenya menggabungkan keduanya, sehingga `AND`
tidak pernah ditelan lebih dulu sebagai operand `OR`.

**Perbaikan.** File `crud/parser.py`: `_logical` kuganti menjadi dua fungsi. `_or` berisi loop
`OR` dengan operand dari `_and`, dan `_and` berisi loop `AND` dengan operand dari `_not`.
`_expr` sekarang memanggil `_or`. Alternatif yang sempat kupikirkan adalah precedence climbing
dengan tabel presedensi. Tidak kupilih karena seluruh parser ini sudah memakai satu fungsi per
aturan grammar, jadi cara ini perubahannya paling kecil dan paling mudah dicocokkan dengan
grammar.

**Test regresi.** `test_regresi_presedensi_and_lebih_tinggi_dari_or` (gagal sebelum perbaikan)
dan `test_regresi_and_lalu_or`. Test yang kedua ternyata sudah lulus di kode lama karena
asosiatif kiri kebetulan menghasilkan bentuk yang benar untuk `a AND b OR c`, jadi fungsinya
hanya sebagai penjaga, bukan bukti bug. Test kasus tepi terkait:
`test_tepi_between_and_milik_between`, untuk memastikan `AND` milik `BETWEEN` tidak tertukar
dengan `AND` logika.

**Peran AI.** AI menemukan masalah ini dengan membandingkan `_logical` dengan tabel presedensi di
spesifikasi. Aku memverifikasinya dengan mencetak AST memakai `pretty()` sebelum dan sesudah
perbaikan.

---

## Bug 5: Error recovery membuang semua sisa file

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** Untuk file berikut:

```sql
SELECT id nama, FROM x;
SELECT 1 FROM y;
DELETE FROM z;
```

parser melaporkan satu error (ini benar), tetapi daftar `statements` kosong. Dua statement valid
sesudahnya ikut hilang. Menurut SPESIFIKASI.md bagian 6, setelah error token dibuang sampai dan
termasuk `;` berikutnya, lalu statement sesudahnya tetap diproses. Akibatnya satu salah sintaks
di tengah file menghapus semua baris CRUD sesudahnya dari matrix.

**Reproduksi minimal.**

```sql
SELECT id nama, FROM x;
SELECT 1 FROM y;
```

**Akar masalah.** `_synchronize` hanya berisi `while not self._at_end(): self._advance()`, yaitu
membuang token terus sampai akhir input tanpa pernah berhenti. Ini panic mode yang tidak punya
titik sinkronisasi. Pada bab 6 (bagian Panic mode error recovery dan Synchronizing a recursive
descent parser), setelah error parser membuang token sampai bertemu batas statement yang aman,
baru parsing dilanjutkan. Untuk SQL batas amannya adalah `;`, jadi loop harus berhenti setelah
mengonsumsi token `;`.

**Perbaikan.** File `crud/parser.py`, fungsi `_synchronize`: di dalam loop kutambahkan
`if self._advance().type == T.SEMICOLON: return`. Loop tetap berhenti kalau sudah di EOF.
Alternatif yang sempat kupikirkan adalah berhenti sebelum keyword statement berikutnya
(`SELECT`, `INSERT`, dan seterusnya) seperti Lox yang berhenti di keyword deklarasi. Tidak
kupilih karena `SELECT` juga muncul di dalam subquery sehingga parser bisa berhenti di tengah
statement yang rusak, dan spesifikasi memang menetapkan `;` sebagai batasnya.

**Test regresi.** `test_regresi_recovery_berhenti_di_titik_koma`. Sebelum perbaikan gagal karena
tidak ada statement yang tersisa, sesudahnya lulus. Test kasus tepi terkait:
`test_tepi_semicolon_beruntun_dan_error_di_akhir_input`, untuk memastikan error di EOF tidak
membuat loop tak berujung.

**Peran AI.** AI menunjukkan bahwa `_synchronize` tidak pernah berhenti. Aku memverifikasinya
dengan menjalankan contoh di atas dan menghitung jumlah error dan statement sebelum dan sesudah
perbaikan, lalu menjalankan CLI pada `campuran_error.sql`.

---

## Bug 6: LEFT OUTER JOIN ditolak

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** `SELECT a FROM t LEFT OUTER JOIN u ON u.x = t.x` menghasilkan
`Baris 1, kolom 22: diharapkan JOIN, ditemukan 'OUTER'`. Grammar di spesifikasi bagian 3 menulis
`"LEFT" [ "OUTER" ]`, artinya `OUTER` boleh ada. `pemeliharaan.sql` memakai `left outer join`.

**Reproduksi minimal.**

```sql
SELECT a FROM t LEFT OUTER JOIN u ON u.x = t.x
```

**Akar masalah.** `_join` langsung meminta `JOIN` setelah `LEFT`, tanpa tempat untuk elemen
opsional `OUTER`. Pada bab 5 dan 6, setiap aturan grammar diterjemahkan menjadi kode, dan elemen
opsional `[ ... ]` diterjemahkan menjadi `if match(...)`. Parser harus menerima persis bahasa
yang didefinisikan grammar, sedangkan di sini ada kalimat yang valid menurut grammar tetapi
ditolak.

**Perbaikan.** File `crud/parser.py`, fungsi `_join`: setelah `LEFT` kutambahkan
`self._match_kw("OUTER")`. Jenis join tetap `"LEFT"` karena AST hanya membedakan `INNER` dan
`LEFT`, jadi bentuk AST tidak berubah dan resolver tidak terpengaruh.

**Test regresi.** `test_regresi_left_outer_join`. Sebelum perbaikan gagal dengan `ParseError`,
sesudahnya lulus.

**Peran AI.** AI membandingkan `_join` dengan grammar baris demi baris dan menemukan `OUTER` yang
terlewat. Aku memverifikasinya dengan menjalankan SQL di atas lalu memeriksa `joins[0].kind` dan
nama tabelnya.

---

## Bug 7: Komentar blok belum didukung (TODO T3)

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** Setiap `/*` langsung melempar `LexError: komentar blok belum didukung`.
SPESIFIKASI.md bagian 2.3 mengharuskan komentar blok boleh lintas baris, tidak bersarang, boleh
berisi `*`, dan komentar yang tidak ditutup adalah `LexError`. `pemeliharaan.sql` dibuka dengan
komentar blok, jadi seluruh file itu tidak bisa diproses.

**Reproduksi minimal.**

```sql
/* komentar */ SELECT a FROM t
```

**Akar masalah.** Ini bukan logika yang salah, tetapi fitur yang memang belum ditulis: di kode
awal cabang `/*` hanya berisi `raise LexError` dengan penanda `TODO(T3)`. Konsep yang
dipakai ada di bab 4 (bagian Longer Lexemes, tempat komentar `//` ditangani). Scanner membuang
komentar dan tidak menghasilkan token apa pun, sehingga parser tidak pernah melihatnya. Yang
membedakan komentar blok dari komentar baris adalah komentar blok bisa melewati beberapa baris.
Karena itu scanner tetap harus menghitung baris baru di dalam komentar (di lexer ini dilakukan
`_advance`), kalau tidak nomor baris semua token sesudahnya bergeser dan CRUD matrix
melaporkan baris yang salah. Komentar yang tidak ditutup juga harus dilaporkan sebagai error,
bukan dibiarkan menelan sisa file.

**Perbaikan.** File `crud/lexer.py`, fungsi `_scan_token`: setelah `/*`, karakter `*` pembuka
dikonsumsi, lalu loop berjalan sampai bertemu `*` yang langsung diikuti `/`. Kalau input habis
lebih dulu, dilempar `LexError` dengan posisi awal komentar. Karena semua karakter dibaca lewat
`_advance`, nomor baris ikut bertambah. Penutup dicari setelah `*` pembuka, jadi `/*/` bukan
komentar yang utuh sedangkan `/**/` valid. Alternatif yang sempat kupikirkan adalah regex
`/\*.*?\*/`. Tidak kupilih karena posisi baris dan kolom tetap harus dihitung oleh lexer.

**Test regresi.** `test_regresi_komentar_blok_lintas_baris` (gagal sebelum perbaikan, sekaligus
memeriksa nomor baris token sesudah komentar) dan `test_regresi_komentar_blok_tidak_ditutup`.
Test yang kedua sebenarnya juga lulus di kode lama karena kode lama selalu `LexError`, jadi
fungsinya sebagai penjaga. Test kasus tepi terkait: `test_tepi_komentar_blok_langsung_tutup`
(`/**/` valid, `/*/` tidak).

**Peran AI.** AI membantu menulis kerangka loop-nya. Aku memverifikasinya dengan menjalankan
`pemeliharaan.sql` lewat CLI dan memeriksa nomor baris token pertama sesudah komentar.

---

## Bug 8: INSERT ... SELECT belum didukung (TODO T1)

**Ditemukan oleh:** Fidella Rafida Ariani · **Diperbaiki oleh:** Fidella Rafida Ariani

**Gejala.** `INSERT INTO arsip SELECT id FROM pesanan` menghasilkan
`Baris 1, kolom 19: INSERT ... SELECT belum didukung, ditemukan 'SELECT'`. Grammar `insert_stmt`
mengizinkan `select_stmt` sebagai sumber data, dan `laporan_penjualan.sql` serta
`pemeliharaan.sql` memakainya.

**Reproduksi minimal.**

```sql
INSERT INTO arsip SELECT id FROM pesanan
```

**Akar masalah.** Seperti Bug 7, ini fitur yang belum ditulis, bukan logika yang keliru: cabang
`SELECT` di `_insert` sengaja dibiarkan melempar error dengan penanda `TODO(T1)`. Konsepnya ada
di bab 5 dan 6. Aturan `insert_stmt` punya dua alternatif sumber data, yaitu `VALUES ...` atau
`select_stmt`. Pada recursive descent, setiap alternatif dalam satu aturan menjadi satu cabang
`if` di fungsi aturan itu, dan kode awal baru punya cabang untuk `VALUES`. Akibatnya parser
menolak kalimat yang valid menurut grammar. Cabang yang kurang itu juga tidak perlu parsing
baru: sumber datanya cukup memakai ulang aturan `select_stmt` dengan memanggil `_select()`,
seperti subquery di bagian lain yang juga memakai aturan yang sama.

**Perbaikan.** File `crud/parser.py`, fungsi `_insert`: di cabang `SELECT`, panggil
`self._select()` lalu kembalikan `ast.Insert(table, columns, [], query, line=start.line)`. Field
`values` diisi `[]` dan `query` diisi node `Select`, sesuai definisi di `ast_nodes.py`, jadi
resolver dan analyzer (yang sudah mengecek `ins.query is not None`) tidak perlu diubah.

**Test regresi.** `test_regresi_insert_select`. Sebelum perbaikan gagal dengan `ParseError`,
sesudahnya lulus. Test bawaan `test_insert_select` juga ikut lulus.

**Peran AI.** AI menulis perubahan kecil ini. Aku memverifikasinya dengan menjalankan `pytest`
dan memeriksa bahwa `query.sources[0].name` berisi `pesanan`.

---

## Bug 9: Pencarian alias mendahulukan scope luar (shadowing terbalik)

**Ditemukan oleh:** Syadida Tsaqifa Nada· **Diperbaiki oleh:** Syadida Tsaqifa Nada

**Gejala.** Pada subquery yang mendeklarasikan alias sama dengan query luar, `ColumnRef.resolved` dapat menunjuk tabel dari scope luar. Ini melanggar SPESIFIKASI.md bagian 4.3: qualifier dicari dari scope terdalam ke luar.

**Reproduksi minimal.**

```sql
SELECT x.id FROM pelanggan x
WHERE EXISTS (SELECT x.id FROM pesanan x)
```

**Akar masalah.** Fungsi `_lookup()` mengumpulkan rantai scope mulai dari scope aktif, tetapi kemudian memeriksanya dengan urutan terbalik. Akibatnya binding di lingkungan luar menang atas binding lokal. Dalam konsep lexical scope/resolver (Crafting Interpreters, Bab 11), pencarian harus dimulai dari environment terdekat; parent hanya menjadi fallback ketika nama belum ditemukan di scope saat ini.

**Perbaikan.** `crud/resolver.py`, fungsi `Resolver._lookup()`: pencarian sekarang berjalan langsung dari `self.scope` ke `scope.parent`. Dengan demikian alias subquery melakukan shadowing dan alias outer tetap dapat diakses jika tidak ditimpa.

**Test regresi.** `test_resolver_shadowing_memilih_alias_scope_terdalam` dan `test_resolver_korelasi_subquery_tetap_menemukan_alias_luar`.

**Peran AI.** AI membantu mengidentifikasi arah pencarian yang terbalik dan menyarankan test shadowing serta correlated subquery. Verifikasi dilakukan dengan memeriksa `ColumnRef.resolved` pada kedua level dan menjalankan test regresi.

---

## Bug 10: Scope DELETE tidak ditutup

**Ditemukan oleh:** Syadida Tsaqifa Nada· **Diperbaiki oleh:** Syadida Tsaqifa Nada

**Gejala.** Alias yang dideklarasikan oleh `DELETE` dapat tetap berada di rantai scope dan berpotensi terlihat oleh statement berikutnya. SPESIFIKASI.md bagian 4.5 menyatakan setiap statement berdiri sendiri dan tidak boleh meninggalkan scope.

**Reproduksi minimal.**

```sql
DELETE FROM sesi lama;
SELECT lama.id FROM pengguna baru;
```

**Akar masalah.** `_delete()` memanggil `_push()` untuk membuat scope lokal, tetapi tidak memanggil `_pop()` setelah memproses kondisi. Berbeda dari `_select()` dan `_update()`, umur scope `DELETE` tidak diseimbangkan. Dalam model environment bertingkat (Crafting Interpreters, Bab 11), scope lokal harus dilepas saat keluar dari statement agar binding lokal tidak bocor ke pemrosesan selanjutnya.

**Perbaikan.** `crud/resolver.py`, fungsi `_delete()`: deklarasi target dan resolusi `WHERE` dibungkus `try/finally`, lalu `_pop()` selalu dijalankan. `resolve_script()` juga memulai tiap statement dari rantai scope tingkat atas yang bersih.

**Test regresi.** `test_resolver_delete_menutup_scope_sebelum_statement_berikutnya` dan `test_resolver_alias_outer_dan_inner_scope_terpisah_per_statement`.

**Peran AI.** AI membantu membaca ketidakseimbangan push/pop dan menyusun kasus regresi lintas statement. Verifikasi dilakukan dengan memastikan qualifier `lama` pada statement kedua menghasilkan error alias tidak terdefinisi.

---

## Bug 11: Resolusi kolom tanpa qualifier belum diimplementasikan (TODO T2)

**Ditemukan oleh:** Syadida Tsaqifa Nada · **Diperbaiki oleh:** Syadida Tsaqifa Nada

**Gejala.** Kolom seperti `nama` pada `SELECT nama FROM pelanggan` tetap memiliki `resolved = None`, padahal hanya ada satu tabel dalam scope. Kolom ambigu juga tidak menghasilkan warning sesuai SPESIFIKASI.md bagian 4.3.

**Reproduksi minimal.**

```sql
SELECT nama FROM pelanggan;
SELECT id FROM pelanggan p JOIN pesanan o ON p.id = o.id;
```

**Akar masalah.** Cabang `_column()` untuk `ColumnRef.qualifier is None` berhenti pada `pass`. Resolver belum menerapkan aturan keputusan berdasarkan isi scope. Resolusi nama tanpa qualifier juga tidak boleh melakukan pencarian ke scope parent: spesifikasi secara eksplisit membatasi pencarian pada scope terdalam.

**Perbaikan.** `crud/resolver.py`, fungsi `_column()`: bila scope terdalam memiliki tepat satu deklarasi, `resolved` diisi dengan target tabel atau `"<subquery alias>"`; bila memiliki lebih dari satu deklarasi, resolver memberi warning `kolom 'nama' ambigu tanpa skema` dan membiarkan `resolved=None`; bila tidak ada deklarasi, resolver memberi warning bahwa kolom tidak dapat di-resolve karena tidak ada tabel dalam scope.

**Test regresi.** `test_resolver_tanpa_qualifier_satu_tabel_diresolve`, `test_resolver_tanpa_qualifier_multi_tabel_ambigu`, dan `test_resolver_kolom_tanpa_scope_memberi_warning`.

**Peran AI.** AI membantu menerjemahkan butir spesifikasi menjadi tiga cabang kondisi dan contoh test. Verifikasi dilakukan dengan memeriksa nilai `resolved`, level diagnostik, dan pesan warning.

---

## Bug 12: Subquery dalam UPDATE salah dihitung sebagai UPDATE

**Ditemukan oleh:** Syadida Tsaqifa Nada · **Diperbaiki oleh:** Syadida Tsaqifa Nada

**Gejala.** Tabel yang dibaca melalui subquery pada `SET` atau `WHERE` dapat memperoleh operasi `U`, padahal tabel sumber subquery harus memperoleh `R`. SPESIFIKASI.md bagian 5 menetapkan target UPDATE sebagai `U`, sedangkan tabel yang dibaca subquery selalu `R`.

**Reproduksi minimal.**

```sql
UPDATE pesanan
SET status = (SELECT status FROM arsip)
WHERE id IN (SELECT pesanan_id FROM pelanggan);
```

**Akar masalah.** `analyze_statement()` meneruskan label operasi `U` ke `_collect()` untuk seluruh ekspresi assignment dan kondisi `WHERE`. Fungsi rekursif itu juga memakai label yang sama saat turun ke AST subquery, sehingga konteks operasi target menular ke tabel sumber. Analyzer perlu membedakan operasi pada tabel target dari operasi baca pada tabel di dalam SELECT.

**Perbaikan.** `crud/analyzer.py`, cabang `ast.Update` pada `analyze_statement()`: target tetap ditandai `U`, sedangkan ekspresi assignment dan `WHERE` ditelusuri dengan label `R`. `_collect()` lalu menandai subquery sumber sebagai pembacaan.

**Test regresi.** `test_analyzer_subquery_update_selalu_dihitung_read` dan `test_pipeline_update_subquery_matrix_dan_column_usage`.

**Peran AI.** AI membantu melacak parameter operasi yang diteruskan ke traversal AST. Verifikasi dilakukan dengan membandingkan matrix hasil terhadap aturan lokal CRUD: `pesanan=U`, `arsip=R`, dan `pelanggan=R`.

---

## Bug 13: Mode CLI --ast tidak melaporkan diagnostik resolver secara lengkap

**Ditemukan oleh:** Syadida Tsaqifa Nada · **Diperbaiki oleh:** Syadida Tsaqifa Nada

**Gejala.** Mode `--ast` mencetak AST hasil parsing, tetapi mengabaikan hasil diagnostik resolver dan selalu mengembalikan exit code sukses. Error alias tidak terdefinisi jadi tidak terlihat oleh pengguna CLI.

**Reproduksi minimal.**

```sql
SELECT x.id FROM pelanggan p;
```

Jalankan `python -m crud.cli FILE.sql --ast`.

**Akar masalah.** `_print_ast()` memanggil resolver tetapi membuang list diagnostiknya. Jalur `--ast` juga tidak mengagregasi kondisi error menjadi status proses. Ini membuat antarmuka tidak menyajikan hasil lengkap dari urutan pipeline lexer, parser, resolver.

**Perbaikan.** `crud/cli.py`, fungsi `_print_ast()` dan `main()`: diagnostik resolver dicetak ke stderr; error leksikal ditangani; parse error dan resolver error membuat exit code menjadi 1. Untuk mode normal, resolver diagnostic berlevel `error` juga memengaruhi exit code.

**Test regresi.** `test_cli_ast_menampilkan_diagnostik_resolver_dan_exit_nonzero` dan `test_cli_matrix_memasukkan_operasi_dan_kembalikan_error_resolver`.

**Peran AI.** AI membantu meninjau jalur integrasi CLI dan merancang test terhadap output serta exit code. Verifikasi dilakukan dengan menjalankan `main()` pada file SQL sementara dan membaca CSV/output diagnostik.

---