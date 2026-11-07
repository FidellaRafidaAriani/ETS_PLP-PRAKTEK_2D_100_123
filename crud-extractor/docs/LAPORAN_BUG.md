# Laporan Bug — Anggota 2 (Resolver dan CRUD Analyzer)

Catatan berikut menjelaskan bug yang ditemukan pada codebase awal. Nama anggota dapat ditambahkan oleh kelompok. Akar masalah ditulis sebagai bahan penjelasan teknis dan sebaiknya diparafrasekan kembali oleh anggota yang mempresentasikan.

---

## Bug 1: Pencarian alias mendahulukan scope luar (shadowing terbalik)

**Ditemukan oleh:** Anggota 2 · **Diperbaiki oleh:** Anggota 2

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

## Bug 2: Scope DELETE tidak ditutup

**Ditemukan oleh:** Anggota 2 · **Diperbaiki oleh:** Anggota 2

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

## Bug 3: Resolusi kolom tanpa qualifier belum diimplementasikan (TODO T2)

**Ditemukan oleh:** Anggota 2 · **Diperbaiki oleh:** Anggota 2

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

## Bug 4: Subquery dalam UPDATE salah dihitung sebagai UPDATE

**Ditemukan oleh:** Anggota 2 · **Diperbaiki oleh:** Anggota 2

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

## Bug 5: Mode CLI --ast tidak melaporkan diagnostik resolver secara lengkap

**Ditemukan oleh:** Anggota 2 · **Diperbaiki oleh:** Anggota 2

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

## Batas pekerjaan anggota ini

Perbaikan lexer dan parser (termasuk TODO `INSERT ... SELECT`, komentar blok, normalisasi keyword, operator `<>`, dan error recovery) tidak diubah dalam pekerjaan Anggota 2. Test awal memperlihatkan masalah-masalah tersebut masih ada di codebase dan harus diselesaikan pada bagian anggota yang menangani lexer/parser. Ground truth dua file tetap dilengkapi manual mengikuti SPESIFIKASI.md.
