# Laporan Akhir

## 1. Hasil evaluasi

Evaluasi dijalankan pada empat file di `data/sample` dengan ground truth sebanyak 27 triple
(file, baris statement, tabel, operasi). Sepuluh triple untuk `campuran_error.sql` dan
`laporan_penjualan.sql` sudah ada dari awal. Tujuh belas sisanya, untuk `audit.sql` dan
`pemeliharaan.sql`, dilengkapi Syadida dengan menghitung ulang setiap statement secara manual.

```text
Dievaluasi: audit.sql, campuran_error.sql, laporan_penjualan.sql, pemeliharaan.sql (27 triple)

Metode   Precision  Recall     F1
parser        1.00    1.00   1.00
regex         0.65    0.81   0.72

[regex]
  salah ditemukan (FP): ('audit.sql', 16, 'sesi', 'R')
  salah ditemukan (FP): ('campuran_error.sql', 4, 'pesanan', 'R')
  salah ditemukan (FP): ('campuran_error.sql', 8, 'keranjang', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pelanggan', 'D')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pelanggan', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pesanan', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'rahasia', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 15, 'pesanan', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'crm.alamat', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'crm.pelanggan', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'pelanggan_lama', 'U')
  salah ditemukan (FP): ('pemeliharaan.sql', 15, 'crm.alamat', 'R')
  terlewat (FN):       ('audit.sql', 2, 'pesanan', 'R')
  terlewat (FN):       ('laporan_penjualan.sql', 3, 'pelanggan', 'R')
  terlewat (FN):       ('laporan_penjualan.sql', 3, 'pesanan', 'R')
  terlewat (FN):       ('pemeliharaan.sql', 3, 'crm.alamat', 'R')
  terlewat (FN):       ('pemeliharaan.sql', 3, 'crm.pelanggan', 'R')
```

Sebelum bug di lexer dan parser diperbaiki, parser hanya mendapat recall 0,41 (F1 0,58) pada
ground truth yang sama, lebih rendah dari regex. Dari 27 triple, 16 terlewat. Seluruh isi
`pemeliharaan.sql` (7 triple) hilang karena komentar blok di baris 1 langsung menghentikan lexer.
Di `laporan_penjualan.sql`, operator `<>` di baris 6 terpecah menjadi `<` dan `>` sehingga
statement pertama error, lalu error recovery membuang semua sisa file, jadi 7 triple ikut hilang.
Di `campuran_error.sql`, error di baris 4 membuang dua statement valid sesudahnya. `audit.sql`
tidak terpengaruh. Setelah Bug 1 sampai 8 di `LAPORAN_BUG.md` diperbaiki, precision, recall, dan
F1 parser sama-sama 1,00. Angka regex tidak berubah karena baseline itu memang tidak boleh
diperbaiki.

Satu catatan tentang angka ini: `evaluate.py` hanya menilai tabel dan operasi per statement.
Kerja resolver untuk alias dan kolom tidak ikut terukur.

## 2. Tiga kasus di mana regex salah

Regex salah 12 kali (FP) dan terlewat 5 kali (FN). Kami ambil tiga kasus dengan penyebab yang
berbeda. Ketiganya, ditambah satu FP kecil di akhir bagian ini, menjelaskan seluruh daftar di atas.

### Kasus 1: komentar dan isi string dibaca sebagai SQL

Potongan dari `laporan_penjualan.sql`, baris 1 sampai 7:

```sql
-- Laporan penjualan bulanan
-- DELETE FROM pelanggan   (baris ini komentar, bukan perintah)
SELECT p.nama, SUM(o.total) AS omzet
FROM pelanggan p
JOIN pesanan o ON o.pelanggan_id = p.id
WHERE o.status = 'LUNAS' AND o.catatan <> 'FROM rahasia'
GROUP BY p.nama;
```

Regex memotong teks per tanda `;`, lalu mencari kata kunci pertama di tiap potongan. Karena
komentar ikut terbaca, kata `DELETE` di baris 2 dianggap awal statement. Akibatnya statement
dicatat di baris 2, bukan baris 3, tabel `pelanggan` dihitung `D` padahal itu isi komentar, dan
`FROM rahasia` yang ada di dalam string dibaca sebagai tabel bernama `rahasia`. Hasilnya empat FP
dan dua FN. Pola yang sama terjadi di `pemeliharaan.sql`, di mana komentar blok berisi
`UPDATE pelanggan_lama` menghasilkan tiga FP dan dua FN. Jadi kasus ini menyumbang tujuh dari
dua belas FP dan empat dari lima FN.

Parser benar karena pekerjaan ini selesai di lexer sebelum parser bekerja. Saat bertemu `--`,
lexer membuang karakter sampai akhir baris, dan saat bertemu `/*` ia membuang sampai `*/`.
Keduanya tidak menghasilkan token apa pun. Isi `'FROM rahasia'` dibaca sebagai satu token STRING,
jadi kata `FROM` di dalamnya tidak pernah menjadi keyword. Nomor baris statement diambil dari
token `SELECT`, sehingga hasilnya baris 3. Ini konsep scanning di *Crafting Interpreters* bab 4:
komentar dibuang dan string literal adalah satu lexeme.

### Kasus 2: `DELETE FROM` dihitung sebagai hapus sekaligus baca

Contoh dari `audit.sql`, baris 16:

```sql
DELETE FROM sesi s WHERE s.kedaluwarsa < :sekarang;
```

Regex punya satu pola untuk `FROM nama` (operasi `R`) dan satu pola lain untuk `DELETE FROM nama`
(operasi `D`). Keduanya dijalankan sendiri-sendiri pada potongan yang sama, jadi `sesi` mendapat
`D` dan juga `R`. Yang benar hanya `D`. Kesalahan yang sama muncul di `campuran_error.sql` baris
8, `laporan_penjualan.sql` baris 15, dan `pemeliharaan.sql` baris 15, jadi ada empat FP dari satu
penyebab ini.

Parser benar karena arti sebuah kata kunci ditentukan oleh posisinya dalam aturan grammar, bukan
oleh tulisannya. Di `_delete`, kata `FROM` dibaca sebagai bagian dari aturan DELETE, bukan aturan
SELECT. Analyzer lalu memberi `D` pada tabel target, dan `R` hanya diberikan pada tabel di dalam
subquery. Ini konsep recursive descent di *Crafting Interpreters* bab 6, satu fungsi untuk satu
aturan.

### Kasus 3: tabel kedua setelah koma terlewat

Contoh dari `audit.sql`, baris 2 sampai 6:

```sql
SELECT p.id, p.nama
FROM pelanggan p, pesanan o
WHERE o.pelanggan_id = p.id
  AND o.tanggal BETWEEN :mulai AND :akhir
  OR p.level = 'gold' AND p.aktif = 1;
```

Regex hanya mengambil satu nama tepat setelah kata `FROM`, yaitu `pelanggan`. Tabel `pesanan` yang
ditulis setelah koma tidak pernah terbaca, sehingga `('audit.sql', 2, 'pesanan', 'R')` muncul
sebagai FN.

Parser benar karena grammar untuk daftar sumber tabel berbentuk satu `table_ref` yang boleh diikuti
koma dan `table_ref` lagi. Di `_select`, bentuk ini ditulis sebagai satu pembacaan lalu loop
selama ketemu koma, dan analyzer menelusuri semua sumber di daftar itu. Perulangan dalam grammar
(bab 5) diterjemahkan jadi loop di kode (bab 6).

Satu FP yang tersisa ada di `campuran_error.sql` baris 4, `SELECT id nama, FROM pesanan;`.
Statement itu salah sintaks, tetapi regex tetap mencatat `pesanan` sebagai `R`. Parser
melaporkan error, membuang token sampai `;`, lalu lanjut ke statement berikutnya, sehingga tabel
dari statement yang rusak itu tidak masuk matrix.

## 3. Batas pendekatan kami

Empat hal berikut tidak bisa ditangani dengan benar oleh tool ini walaupun semua bug sudah
diperbaiki. Contoh SQL di nomor 1 sampai 3 dan contoh view di nomor 4 kami jalankan langsung lewat
`analyze_source`. Bagian cascade dan trigger terjadi di sisi database, jadi hanya bisa dijelaskan
dan tidak bisa dicoba dari tool ini.

1. **Kolom tanpa qualifier di query multi-tabel dan `SELECT *`.** Contoh:
   `SELECT nama FROM pelanggan p JOIN pesanan o ON p.id = o.pelanggan_id;`. Resolver hanya mau
   menentukan tabel dari kolom tanpa qualifier kalau scope terdalam punya satu tabel. Di sini ada
   dua, jadi hasilnya cuma warning `kolom 'nama' ambigu tanpa skema` dan kolom `nama` tidak masuk
   daftar penggunaan kolom. `SELECT *` juga tidak bisa diuraikan menjadi kolom. CRUD matrix level
   tabel tetap benar (kedua tabel `R`), yang kurang adalah penggunaan kolomnya. Informasi yang
   dibutuhkan adalah skema database, yaitu daftar kolom tiap tabel.

2. **Sintaks di luar subset yang kami dukung.** Contoh: `HAVING`, `UNION`, `WITH`, `CASE`,
   `LIMIT`, dan `TRUNCATE`. Untuk `SELECT x FROM t GROUP BY x HAVING COUNT(*) > 1;`, parser
   berhenti dengan `diharapkan ';' di akhir statement, ditemukan 'HAVING'`. Seluruh statement
   dibuang, jadi tabel `t` tidak muncul di matrix dan hanya tercatat sebagai parse error.
   Untuk `SELECT id FROM a UNION SELECT id FROM b;`, kedua tabelnya hilang. Dampaknya matrix
   bisa lebih sedikit dari kenyataan. Yang dibutuhkan adalah grammar yang diperluas, node AST
   baru, dan aturan analyzer untuk konstruk itu.

3. **SQL dinamis dan nama tabel dari parameter.** Contoh: `SELECT id FROM :tabel;` ditolak
   dengan `diharapkan nama tabel, ditemukan ':tabel'`. Contoh lain, `EXEC('SELECT id FROM
   rahasia');` ditolak karena `EXEC` bukan awal statement yang dikenal, dan isi string tidak dibaca
   sebagai SQL karena lexer memperlakukannya sebagai data. Dua-duanya membuat tabel tidak muncul
   di matrix. Informasi yang dibutuhkan adalah nilai parameter saat program berjalan atau log
   query yang benar-benar dieksekusi.

4. **Efek tidak langsung lewat view, trigger, dan cascade.** Contoh: `SELECT * FROM v_laporan;`
   hanya menghasilkan `v_laporan` dengan operasi `R`, padahal tabel asli di balik view itu tidak
   diketahui tool. Begitu pula `DELETE FROM pelanggan;` yang di database bisa ikut menghapus
   data tabel anak lewat `ON DELETE CASCADE`, atau memicu trigger yang menulis ke tabel log.
   Matrix hanya mencatat `D` pada `pelanggan`. Informasi yang dibutuhkan adalah definisi view,
   trigger, dan constraint foreign key dari database.

## 4. Pembagian kerja

Kami membagi pekerjaan menurut tahap pipeline. Fidella mengerjakan lexer, parser, dan node AST
(`lexer.py`, `parser.py`, `ast_nodes.py`). Dari situ keluar Bug 1 sampai 8 di `LAPORAN_BUG.md`,
termasuk dua TODO bawaan (komentar blok dan `INSERT ... SELECT`), lima belas test di bagian A dan
B pada `test_tambahan.py`, dan dua keputusan pertama di `KARTU_DESAIN.md`. Syadida mengerjakan
resolver, analyzer, dan CLI. Bagiannya adalah Bug 9 sampai 13 (urutan pencarian scope, scope
`DELETE` yang tidak ditutup, TODO resolusi kolom tanpa qualifier, subquery di `UPDATE`, dan
diagnostik di mode `--ast`), lima belas test di bagian C, lima keputusan desain berikutnya, serta
17 label baru di `ground_truth.csv`. `pipeline.py` diperiksa dan tidak perlu diubah. `LOG_AI.md`
diisi oleh masing-masing sesuai AI yang dipakai.

Pemeriksaan kami lakukan silang supaya tidak hanya paham bagian sendiri. Syadida memeriksa seluruh
isi zip dan menemukan delapan masalah yang tersisa di lexer dan parser. Fidella membaca
`analyzer.py` dan menemukan bahwa salah satu test yang gagal berasal dari subquery `UPDATE` yang
dihitung `U`, bukan `R`. Setelah kedua pekerjaan digabung lewat merge di Git, Fidella
menyelesaikan konflik di dokumen dan `test_tambahan.py`, lalu seluruh test dan `evaluate.py`
dijalankan pada hasil gabungan. Hasilnya 60 test lulus dan F1 parser 1,00. Hasil dari AI juga
tidak langsung kami percaya. AI beberapa kali keliru, misalnya soal nomor TODO dan penyebab
sebuah test gagal, dan semuanya ketahuan setelah dicek ke kode dan dijalankan.
