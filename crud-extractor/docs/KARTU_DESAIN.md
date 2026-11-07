# Kartu Desain

Tuliskan lima keputusan desain penting dalam pekerjaan kalian. Untuk tiap keputusan, sebutkan
alternatif yang ditolak dan alasannya. Contoh topik (boleh memilih yang lain):

- bagaimana parser membedakan `*` sebagai "semua kolom" dan sebagai perkalian;
- di mana dan bagaimana presedensi `AND`/`OR` dinyatakan;
- mengapa error recovery berhenti di `;`, bukan di keyword `SELECT` berikutnya;
- urutan pencarian scope dan akibatnya pada shadowing serta correlated subquery;
- mengapa kolom tanpa qualifier hanya dilihat di scope terdalam, dan apa kelemahannya;
- bagaimana implementasi `INSERT ... SELECT` atau komentar blok kalian.

| No | Keputusan | Alternatif yang ditolak | Alasan |
| --- | --- | --- | --- |
| 1 | Pembedaan `*` sebagai "semua kolom" dan sebagai perkalian dilakukan di parser. Lexer cuma mengeluarkan satu jenis token, yaitu `STAR`. Di `_select_list`, `STAR` di awal daftar kolom dibaca sebagai `Star()`. Di `_multiplicative`, `STAR` dibaca sebagai operator perkalian. Di `_function_call`, `STAR` tepat setelah `(` dibaca sebagai `COUNT(*)`. | Lexer yang menentukan lewat konteks, misalnya `*` sesudah `SELECT` atau koma dikeluarkan sebagai token "semua kolom" dan `*` lainnya sebagai token perkalian. Alternatif lainnya, menambah jenis token baru di `TokenType`. | Lexer tidak tahu posisi sebuah token di dalam grammar. Kalau dipaksa menebak dari token sebelumnya, aturannya jadi rapuh dan lexer ikut mengurus hal yang seharusnya tugas parser. Komentar di `TokenType.STAR` pada `lexer.py` juga bilang `STAR` dibedakan oleh parser, dan spesifikasi bagian 3.2 hanya menjelaskan artinya menurut posisi (di awal `select_list` berarti semua kolom, di dalam ekspresi berarti perkalian). `TokenType` juga termasuk API publik jadi tidak kuubah. Akibatnya, `SELECT a, * FROM t` ditolak dengan pesan `diharapkan ekspresi, ditemukan '*'`. Ini sesuai grammar karena `*` hanya boleh sendirian di awal `select_list`. Sudah kucoba juga `SELECT 2 * 3 FROM t` dan `SELECT COUNT(*) FROM t`, dua-duanya lolos. |
| 2 | `INSERT ... SELECT` memakai node `Insert` yang sudah ada. Field `values` diisi `[]` dan field `query` diisi hasil `_select()`. | Membuat kelas node baru, misalnya `InsertSelect`. Alternatif lainnya, mengubah `Insert` supaya `values` boleh berisi node `Select`. | Nama kelas dan field AST termasuk API publik (spesifikasi bagian 7) dan test tersembunyi memakainya, jadi tidak boleh kuganti. Field `query` di `Insert` memang sudah disiapkan untuk kasus ini. Resolver dan analyzer juga sudah mengecek `ins.query is not None` (di fungsi `_insert` pada `resolver.py`, serta `analyze_statement` dan `column_usage` pada `analyzer.py`), jadi bagian Anggota 2 tidak perlu diubah sama sekali. Parsing-nya cukup memakai ulang `_select()`, fungsi yang sama dengan yang dipakai subquery, sehingga `SELECT` di dalam `INSERT` otomatis mendapat scope sendiri dari resolver sesuai spesifikasi bagian 4.1. |
| 3 | | | |
| 4 | | | |
| 5 | | | |
