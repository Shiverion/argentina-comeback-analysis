# Menit 66. Argentina 0-2. Tiga Gol. Satu Comeback.

## Seberapa langka comeback Argentina melawan Mesir, dan apakah data mendukung narasi "Argentina anak emas FIFA"?

**Riset data reproducible | Data cutoff: 13 Juli 2026**

Papan skor di Atlanta Stadium menunjukkan Argentina tertinggal 0-2 dari Mesir pada menit ke-66. Sepuluh menit kemudian, Cristian Romero mencetak gol. Lionel Messi menyamakan skor pada menit ke-82, lalu Enzo Fernandez mencetak gol kemenangan pada menit ke-91.

Hasil akhirnya 3-2. Tetapi ada dua pertanyaan yang berbeda di balik cerita comeback ini:

1. Seberapa langka comeback dari defisit dua gol di fase akhir pertandingan?
2. Apakah data benar-benar mendukung klaim bahwa Argentina lebih diuntungkan keputusan wasit sejak 2022?

Artikel ini menjawab keduanya dengan data pertandingan, model probabilitas, dan counterfactual yang batasannya dijelaskan secara terbuka.

> Catatan penting: artikel ini mengukur kelangkaan dan sensitivitas skenario. Artikel ini tidak membuktikan bias, korupsi, atau manipulasi wasit.

## 1. Seberapa langka comeback ini?

Kami menelusuri **964 pertandingan Piala Dunia pria dari 1930 sampai 2022** dan menghitung semua team-state yang tertinggal dua gol atau lebih pada menit 70, 75, 78, dan 80.

![Timeline selisih gol Argentina](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/01_goal_difference_timeline.png)

Hasilnya: sebelum Argentina melakukannya pada 2026, tidak ada satu pun comeback dari defisit dua gol pada semua cutoff tersebut dalam catatan Piala Dunia yang dianalisis. Batas atas interval ketidakpastian 95% tetap berada di bawah 1,4%.

Namun, "tidak ditemukan di 964 pertandingan" bukan berarti "mustahil". Karena itu kami menambahkan baseline klub yang lebih besar.

## 2. Baseline klub: langka, bukan mustahil

Sampel StatsBomb yang dipin mencakup 2.193 pertandingan klub dan 186 pertandingan timnas non-Piala Dunia. Populasi klub dan timnas tetap dipisahkan dan tidak digabung menjadi satu angka.

![Kelangkaan comeback lintas baseline](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/07_broader_baseline_rarity.png)

Pada cutoff 70 menit, ditemukan 2 comeback dari 703 team-state klub yang tertinggal dua gol atau lebih. Keduanya terjadi di Premier League 2015/16:

- Leicester City melawan Aston Villa.
- West Ham United melawan Everton.

Pada cutoff 75 menit, hanya ada 1 dari 733. Pada cutoff 79 menit, tidak ada: 0 dari 759.

![Continuation probability](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/08_broader_baseline_continuation.png)

Kesimpulan yang paling defensible adalah bahwa comeback tersebut sangat langka, tetapi bukan kejadian yang secara matematis mustahil.

## 3. Clean comeback atau dibantu penalti?

Kami kemudian menelusuri event-level StatsBomb untuk melihat apakah comeback dari defisit dua gol biasanya dibantu penalti. Di sini "penalti" berarti penalty-shot event pada feed StatsBomb, bukan keputusan wasit yang sudah diaudit secara independen.

Pada cutoff 70 menit:

- Comeback klub: **2 dari 703**.
- Clean strict, tanpa penalty-shot event dari kedua tim: **2 dari 703**.
- Comeback dengan penalty-shot event sendiri: **0 dari 703**.
- Comeback dengan gol penalti sendiri: **0 dari 703**.
- Comeback dengan tiga atau lebih penalty-shot event sendiri: **0 dari 703**.

Argentina juga diklasifikasikan sebagai clean setelah fase 0-2. Tetapi ada detail waktu yang penting: pada menit 79, gol Romero di menit 78 sudah mengubah skor menjadi 1-2. Jadi Argentina bukan lagi team-state 0-2 pada menit 79.

Penalti Messi pada menit ke-20 memang ada dan tercatat sebagai saved penalty. Penalti itu relevan untuk cerita seluruh pertandingan, tetapi tidak masuk definisi clean post-cutoff.

## 4. Apakah penalti benar-benar mengubah defisit?

Analisis ini tidak mensyaratkan tim akhirnya menang. Kami mengambil semua team-state yang tertinggal dua gol atau lebih, lalu melihat apakah mereka:

- mencetak penalti saat masih tepat dua gol tertinggal, sehingga skor berubah dari 2-0 menjadi 2-1;
- menyamakan skor melalui penalti, dari 2-1 menjadi 2-2;
- atau menyamakan skor melalui open play.

Pada cutoff 70 menit:

- Penalti saat masih tepat dua gol tertinggal: **14 dari 703** atau 1,99%.
- Equalizer melalui penalti: **2 dari 703** atau 0,28%.
- Equalizer melalui open play: **19 dari 703** atau 2,70%.
- Semua equalizer: **21 dari 703** atau 2,99%.

Dengan kata lain, dari 21 equalizer yang terjadi, hanya 2 atau sekitar 9,5% yang berasal dari penalti. Sebanyak 19 berasal dari open play.

Pada cutoff 79 menit, hasilnya lebih kecil:

- Penalti saat masih tepat dua gol tertinggal: **4 dari 759**.
- Equalizer melalui penalti: **1 dari 759**.
- Equalizer melalui open play: **9 dari 759**.
- Semua equalizer: **10 dari 759**.

Penalti memang bisa menjadi mekanisme pemulihan, tetapi bukan jalur mayoritas dalam sample ini.

## 5. Dua penalti dalam sepuluh menit

Untuk menguji skenario yang lebih ekstrem, kami menghitung dua penalty-shot event oleh tim yang sama dalam rolling window sepuluh menit.

Pada seluruh cohort late state yang tertinggal dua gol atau lebih, hasilnya **nol pada semua cutoff 70, 75, 78, 79, dan 80 menit**. Tidak ada satu pun team-state relevan yang memiliki dua penalty-shot event sendiri dalam sepuluh menit. Tidak ada pula yang memiliki dua gol penalti dalam sepuluh menit.

Tetapi klaim ini harus dibatasi. Dalam seluruh pertandingan klub, semua menit, ditemukan:

- **8 dari 2.193** pertandingan dengan dua penalty-shot event tim yang sama dalam sepuluh menit.
- **5 dari 2.193** pertandingan dengan dua gol penalti tim yang sama dalam sepuluh menit.

Jadi kalimat yang benar bukan "hal ini tidak pernah terjadi dalam sejarah sepak bola". Kalimat yang benar adalah:

> Tidak ada analog historis langsung dalam sample ini untuk sebuah tim yang sedang tertinggal dua gol di fase akhir lalu memperoleh dua penalti dalam sepuluh menit.

Bahkan jika dua penalti Argentina diberikan dan keduanya masuk, skornya baru menjadi 2-2. Gol ketiga tetap harus tercipta untuk mencapai 3-2.

## 6. Berapa peluang Argentina sebenarnya?

Ada dua pendekatan yang masuk akal, dan keduanya menghasilkan angka yang berbeda jauh.

Pendekatan pertama membandingkan semua team-state historis dengan defisit yang sama. Ini menghasilkan peluang yang sangat kecil, sekitar low single digits pada fase akhir, tetapi pool-nya mencakup semua jenis tim.

Pendekatan kedua memakai model yang membatasi pembanding pada situasi dengan kekuatan pra-pertandingan yang mendekati Argentina. Ini lebih relevan, tetapi jumlah pembandingnya sangat kecil, kadang hanya satu sampai tiga pertandingan.

![Peluang menang Argentina](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/05_focal_model_probabilities.png)

Kesimpulan yang jujur bukan satu angka tunggal. Peluang Argentina saat 0-2 tertinggal di menit 66 sampai 80 hampir pasti rendah, tetapi data belum cukup untuk menentukan angka focal yang presisi tanpa false precision.

## 7. Bagaimana jika gol Mesir yang dianulir disahkan?

Laporan publik berbeda mengenai menit persis gol Mesir yang dianulir: 58, 62, atau 67. Insiden itu belum diverifikasi melalui video resmi, sehingga kami tidak menyimpulkan apakah keputusan wasit benar atau salah.

Counterfactual pertama hanya mengubah state langsung dari Argentina tertinggal satu gol menjadi tertinggal dua gol.

![Dampak skenario gol dianulir](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/06_scenario_only_impact.png)

Dalam tiga asumsi waktu, pengesahan gol tersebut menurunkan probabilitas menang Argentina sekitar **3 sampai 5 poin persentase**. Ini adalah sensitivitas material, bukan bukti keputusan tersebut salah.

### Bagaimana jika perubahan skor mengubah seluruh jalannya pertandingan?

Ini adalah keberatan yang valid. Jika gol Mesir disahkan, gol Mesir pada menit 66 bisa membuat skor menjadi 0-3. Tetapi setelah 0-3, Argentina mungkin mengambil risiko lebih awal dan Mesir mungkin bertahan lebih dalam. Gol-gol berikutnya tidak boleh dianggap tetap sama.

Karena itu kami memakai dua cabang:

1. **Fixed-score branch:** model hanya mengubah state 0-2 menjadi 0-3. Pada sample klub, mean modelled win probability turun dari 0,46% menjadi 0,04%. Pada sample World Cup, turun dari 0,80% menjadi 0,09%.
2. **Adaptive historical branch:** kami melihat pertandingan yang benar-benar mencapai defisit tiga gol. Terdapat 75 pertandingan klub pada window 50-70 menit, tanpa kemenangan dalam sample tersebut. Ini bukan probabilitas Argentina yang presisi karena jumlah kasus dan path dependence terlalu terbatas.

Dua cabang ini mendukung kesimpulan directional bahwa 0-3 jauh lebih buruk daripada 0-2. Keduanya tidak dapat memastikan apakah Argentina masih akan comeback 3-2.

## 8. Apakah Argentina benar-benar anak emas FIFA sejak 2022?

Kami membandingkan penalti, kartu kuning, dan kartu merah Argentina dengan seluruh tim dalam edisi Piala Dunia yang sama.

![Persentil disiplin Argentina](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/03_discipline_percentile_by_edition.png)

Hasilnya:

- Penalti yang menjadi gol Argentina pada 2022 berada di persentil 100.
- Kartu kuning Argentina berada di sekitar persentil 84.
- Persentil kartu merah 2022 yang benar adalah 43,5%, bukan 88%, karena banyak tim sama-sama memiliki nol kartu merah.
- Argentina juga mencapai persentil 100 untuk penalti pada 1958.
- Edisi 1982 dan 1990 memiliki metrik kartu yang sama atau lebih tinggi.

Tidak terlihat lonjakan unik yang baru dimulai pada 2022. Pola tersebut juga konsisten dengan penjelasan yang lebih sederhana: Argentina adalah tim elite, menyerang, menguasai bola, dan sering berada di area penalti lawan.

### Data 2026

FIFA Performance Summary Reports untuk seluruh 96 pertandingan yang tersedia sampai Round of 16 menunjukkan Argentina menerima 3 penalti dalam 5 pertandingan, atau 0,60 penalti per pertandingan.

![Penalti 2026](https://raw.githubusercontent.com/Shiverion/argentina-comeback-analysis/codex/comeback-penalty-sequences/results/assets/04_pmsr_2026_penalties.png)

Angka ini adalah penalti yang diberikan, termasuk saved dan missed penalty. Angka 1930-2022 adalah penalty goals scored. Keduanya tidak boleh digabung menjadi satu statistik.

## Kesimpulan

- Comeback Argentina sangat langka secara statistik.
- Dalam sample StatsBomb, comeback dari defisit dua gol pada cutoff 70 hanya 2 dari 703 team-state klub.
- Dua comeback tersebut clean; tidak ada comeback yang dibantu gol penalti sendiri.
- Tidak ada team-state late two-goal deficit yang memperoleh dua penalty-shot event dalam sepuluh menit.
- Namun, dalam seluruh pertandingan klub, delapan pertandingan memang memiliki dua penalty-shot event dalam sepuluh menit. Jadi klaimnya harus dibatasi pada situasi late two-goal deficit.
- Dua penalti yang masuk hanya membuat skor 2-2. Gol ketiga tetap diperlukan untuk menang 3-2.
- Counterfactual gol Mesir menunjukkan sensitivitas material, tetapi tidak membuktikan keputusan wasit salah.
- Data disiplin tidak menunjukkan pola unik yang baru dimulai pada 2022.

> Data statistik pertandingan publik dapat mengukur kelangkaan hasil dan sensitivitas skenario. Data ini tidak dapat membaca niat wasit, membuktikan korupsi, atau menetapkan kebenaran keputusan tanpa video dan aturan resmi.

## Sumber dan reproduksibilitas

- [Repository dan kode analisis](https://github.com/Shiverion/argentina-comeback-analysis)
- [Technical report](https://github.com/Shiverion/argentina-comeback-analysis/blob/codex/comeback-penalty-sequences/results/analysis_report.md)
- [FIFA Performance Summary Report Argentina vs Egypt](https://www.fifatrainingcentre.com/media/native/tournaments/fifa-world-cup/2026/PMSR-M95-ARG-V-EGY.pdf)
- [Fjelstul World Cup Database, pinned commit](https://github.com/jfjelstul/worldcup/tree/35a8667f518b07469182ae16d35574dd0e7a00fb)
- [StatsBomb Open Data, pinned commit](https://github.com/statsbomb/open-data/tree/b0bc9f22dd77c206ddedc1d742893b3bbe64baec)
- [JGravier soccer Elo, pinned commit](https://github.com/JGravier/soccer-elo/tree/a24d031e0ed81cbb4206ff84a2209bbf000ee6d6)

Seluruh angka di artikel ini dihasilkan oleh pipeline ETL dan notebook yang dapat dijalankan ulang. Dataset StatsBomb adalah sample berdasarkan availability, bukan sensus seluruh pertandingan sepak bola.
