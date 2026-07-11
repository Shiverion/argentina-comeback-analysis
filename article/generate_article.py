# -*- coding: utf-8 -*-
"""Builds the PDF article from the charts already committed under results/assets/.

Usage (from the project root):
    uv run --with playwright python article/generate_article.py
    (run `uv run --with playwright python -m playwright install chromium` once first)
"""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "results" / "assets"
OUT_HTML = Path(__file__).resolve().parent / "argentina-comeback-golden-child.html"
OUT_PDF = Path(__file__).resolve().parent / "argentina-comeback-golden-child.pdf"
REPO_URL = "https://github.com/Shiverion/argentina-comeback-analysis"

CHARTS = [
    "01_goal_difference_timeline",
    "02_historical_continuation_probability",
    "03_discipline_percentile_by_edition",
    "04_pmsr_2026_penalties",
    "05_focal_model_probabilities",
    "06_scenario_only_impact",
]


def img(name: str) -> str:
    data = (ASSETS / f"{name}.png").read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def build_html() -> str:
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Argentina 0-2, Menit 79. Lalu Apa?</title>
<style>
  @page {{ size: A4; margin: 20mm 18mm 22mm 18mm; }}
  @page :first {{ margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Georgia', 'Times New Roman', serif;
    color: #1a1a1a;
    line-height: 1.65;
    font-size: 11.3pt;
    margin: 0;
  }}
  h1, h2, h3, .kicker, .stat-label, .caption, .footer, .tag {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
  }}

  .cover {{
    height: 297mm;
    width: 210mm;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background: linear-gradient(160deg, #0b1d3a 0%, #16305c 55%, #6fa8dc 150%);
    color: #f5f7fa;
    padding: 18mm 16mm;
    page-break-after: always;
    position: relative;
  }}
  .cover::before {{
    content: "";
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at 80% 15%, rgba(255,255,255,0.10), transparent 45%);
  }}
  .kicker {{
    text-transform: uppercase;
    letter-spacing: 2.5px;
    font-size: 9.5pt;
    font-weight: 700;
    color: #a9c6f5;
    margin-bottom: 10mm;
  }}
  .cover h1 {{
    font-family: Georgia, serif;
    font-size: 34pt;
    line-height: 1.15;
    margin: 0 0 6mm 0;
    font-weight: 700;
    max-width: 150mm;
  }}
  .cover .sub {{
    font-size: 13pt;
    color: #dfe8f7;
    max-width: 140mm;
    margin: 0 0 12mm 0;
    font-family: Georgia, serif;
    font-style: italic;
  }}
  .cover .meta {{
    font-size: 9.5pt;
    color: #a9c6f5;
    border-top: 1px solid rgba(255,255,255,0.25);
    padding-top: 5mm;
  }}
  .scoreline {{
    position: absolute;
    top: 18mm; right: 16mm;
    font-family: Georgia, serif;
    font-size: 42pt;
    font-weight: 700;
    color: rgba(255,255,255,0.18);
    letter-spacing: 2px;
  }}

  .content {{ padding: 0 2mm; }}
  .content h2 {{
    font-size: 16.5pt;
    color: #0b1d3a;
    border-bottom: 2.5px solid #0b1d3a;
    padding-bottom: 2mm;
    margin: 12mm 0 5mm 0;
    page-break-after: avoid;
  }}
  .content h3 {{
    font-size: 12.5pt;
    color: #16305c;
    margin: 7mm 0 3mm 0;
    page-break-after: avoid;
  }}
  p {{ margin: 0 0 4mm 0; text-align: justify; }}
  .drop p:first-of-type::first-letter {{
    float: left;
    font-size: 44pt;
    line-height: 0.8;
    font-weight: 700;
    padding: 1mm 2mm 0 0;
    color: #0b1d3a;
    font-family: Georgia, serif;
  }}
  .pull {{
    font-family: Georgia, serif;
    font-style: italic;
    font-size: 14pt;
    color: #16305c;
    border-left: 4px solid #6fa8dc;
    padding: 3mm 0 3mm 6mm;
    margin: 6mm 4mm 6mm 0;
    line-height: 1.45;
  }}
  .callout {{
    background: #eef3fb;
    border: 1px solid #c9d9f0;
    border-radius: 3mm;
    padding: 5mm 6mm;
    margin: 5mm 0;
    font-size: 10.3pt;
    page-break-inside: avoid;
  }}
  .callout .tag {{
    display: inline-block;
    font-size: 8.3pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #16305c;
    background: #c9d9f0;
    padding: 0.8mm 2.5mm;
    border-radius: 2mm;
    margin-bottom: 2.5mm;
  }}
  .callout.warn {{ background: #fdf1ee; border-color: #f0c9bd; }}
  .callout.warn .tag {{ background: #f0c9bd; color: #7a2e12; }}
  .callout.fix {{ background: #eef7ee; border-color: #c8e3c8; }}
  .callout.fix .tag {{ background: #c8e3c8; color: #205020; }}

  figure {{ margin: 6mm 0; page-break-inside: avoid; }}
  figure img {{ width: 100%; display: block; border-radius: 2mm; border: 1px solid #e2e2e2; }}
  figcaption {{
    font-size: 8.8pt;
    color: #555;
    margin-top: 2mm;
    line-height: 1.4;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 9.3pt;
    margin: 4mm 0 6mm 0;
    page-break-inside: avoid;
  }}
  th, td {{
    border: 1px solid #d8d8d8;
    padding: 1.8mm 2.5mm;
    text-align: left;
  }}
  th {{ background: #0b1d3a; color: #fff; font-family: Arial, sans-serif; font-size: 8.6pt; }}
  tr:nth-child(even) td {{ background: #f5f7fa; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}

  .statrow {{
    display: flex;
    gap: 4mm;
    margin: 6mm 0;
    page-break-inside: avoid;
  }}
  .stat {{
    flex: 1;
    background: #0b1d3a;
    color: #fff;
    border-radius: 2mm;
    padding: 4mm 3mm;
    text-align: center;
  }}
  .stat .num-big {{ font-family: Arial, sans-serif; font-size: 19pt; font-weight: 700; display: block; }}
  .stat .stat-label {{ font-size: 7.6pt; text-transform: uppercase; letter-spacing: 0.5px; color: #a9c6f5; margin-top: 1.5mm; display: block; }}

  .verdict-table td:first-child {{ font-weight: 700; white-space: nowrap; }}

  .footer {{
    margin-top: 14mm;
    padding-top: 5mm;
    border-top: 1px solid #ccc;
    font-size: 8.6pt;
    color: #555;
    page-break-inside: avoid;
  }}
  .footer a {{ color: #16305c; }}
  code {{ background: #eef3fb; padding: 0.3mm 1.2mm; border-radius: 1mm; font-size: 92%; }}
  .section-break {{ page-break-before: always; }}
</style>
</head>
<body>

<div class="cover">
  <div class="scoreline">0&ndash;2 &rarr; 3&ndash;2</div>
  <div class="kicker">Analisis Data &middot; Piala Dunia FIFA 2026</div>
  <h1>Menit 79, Argentina Tertinggal 0&ndash;2.<br>Sepuluh Menit Kemudian, Semuanya Berubah.</h1>
  <p class="sub">Comeback itu nyata &mdash; dan datanya bisa mengukur seberapa langka. Tapi ada pertanyaan yang lebih tajam beredar di linimasa sejak itu: apakah Argentina memang "anak emas" FIFA sejak 2022? Kami menguji klaim itu dengan data, bukan opini &mdash; dan mengukur juga seberapa jauh data itu bisa dipercaya.</p>
  <div class="meta">Riset data reproducible &middot; seluruh dataset, kode, dan notebook tersedia publik di<br>{REPO_URL}</div>
</div>

<div class="content">

<div class="drop">
<p>Papan skor di Atlanta Stadium menyala <strong>Argentina 0 &ndash; Egypt 2</strong>. Jam pertandingan menunjukkan menit ke-66, dan Mostafa Zico baru saja menggandakan keunggulan Mesir. Bagi siapa pun yang menonton, ini terasa seperti permainan yang sudah selesai. Argentina, juara bertahan, tersingkir dari Piala Dunia 2026 di babak 16 besar &mdash; oleh Mesir.</p>

<p>Yang terjadi setelahnya sudah jadi legenda dalam semalam: Cristian Romero di menit 78, Lionel Messi di menit 82, dan Enzo Fern&aacute;ndez di menit 91 membalikkan keadaan menjadi <strong>3&ndash;2</strong>. Tapi ada satu detail yang nyaris hilang dari cerita "comeback ajaib" ini &mdash; di menit 20, jauh sebelum semua drama itu, Messi sendiri gagal mengeksekusi penalti yang seharusnya bisa mencegah Argentina tertinggal sejak awal. Tendangannya diblok kiper Mesir, tercatat resmi di laporan pertandingan FIFA. Argentina bukan cuma nyaris kalah karena keajaiban di akhir &mdash; mereka juga sempat menyia-nyiakan peluang emas di awal.</p>
</div>

<p class="pull">"Seberapa mustahil sebenarnya comeback ini? Dan benarkah Argentina memang lebih 'disayang' wasit sejak 2022?"</p>

<p>Dua pertanyaan itu ramai dibahas di internet begitu peluit akhir dibunyikan. Yang satu soal statistik olahraga murni. Yang satu lagi jauh lebih sensitif &mdash; tuduhan bahwa FIFA secara sistematis menguntungkan Argentina sejak final Qatar 2022. Artikel ini menjawab keduanya dengan cara yang sama: bukan dengan opini, tapi dengan data yang bisa diperiksa ulang oleh siapa saja. Seluruh dataset, kode analisis, dan notebook yang menghasilkan setiap angka di artikel ini <strong>tersedia terbuka</strong> di <code>{REPO_URL}</code> &mdash; termasuk bagian-bagian di mana data itu sendiri tidak cukup kuat untuk menjawab pasti.</p>

<h2>Bagian 1 &middot; Seberapa Langka Comeback Ini, Sebenarnya?</h2>

<p>Untuk menjawab ini secara adil, kami tidak membandingkan dengan perasaan atau ingatan subjektif soal pertandingan-pertandingan dramatis lain. Kami menelusuri <strong>964 pertandingan Piala Dunia pria</strong> dari 1930 hingga 2022 (basis data Fjelstul World Cup Database) dan menghitung: dari semua tim yang pernah tertinggal 2 gol atau lebih di menit-menit akhir, berapa persen yang akhirnya menang dalam waktu normal?</p>

<div class="statrow">
  <div class="stat"><span class="num-big">0 dari 278</span><span class="stat-label">Comeback tertinggal 2+ gol pada menit 70&prime;</span></div>
  <div class="stat"><span class="num-big">0 dari 316</span><span class="stat-label">Comeback tertinggal 2+ gol pada menit 80&prime;</span></div>
  <div class="stat"><span class="num-big">&lt; 1.4%</span><span class="stat-label">Batas atas kemungkinan (interval 95%)</span></div>
</div>

<p>Angkanya konsisten dan tegas: <strong>tidak ada satu pun</strong> tim, dari 964 pertandingan Piala Dunia pria sepanjang sejarah, yang berhasil membalikkan defisit 2 gol di menit 70, 75, 78, atau 80 untuk menang dalam waktu normal &mdash; sampai Argentina melakukannya pada 2026. Bahkan batas atas dari interval ketidakpastian statistiknya tetap di bawah 1,4%.</p>

<figure>
  <img src="{img('01_goal_difference_timeline')}" alt="Timeline selisih gol">
  <figcaption>Grafik 1. Selisih gol Argentina sepanjang pertandingan. Area merah = Argentina tertinggal; area biru = unggul. Gol penyeimbang (82&prime;) dan gol kemenangan (91&prime;) sama-sama terjadi di sembilan menit terakhir waktu normal.</figcaption>
</figure>

<div class="callout">
  <span class="tag">Cek Ketahanan</span>
  Supaya hasil ini tidak dianggap cuma kebetulan karena memasukkan data era 1930-an yang gaya mainnya sangat berbeda, kami mengulang perhitungan yang sama hanya dengan pertandingan sejak 1970, 1998, dan 2010. Hasilnya tetap sama di semua era: <strong>nol comeback</strong>, di semua ambang batas menit. Yang berubah hanya lebar interval ketidakpastiannya (makin sempit sampelnya, makin lebar batas atasnya &mdash; naik sampai 5,7% di irisan data 2010 ke atas) &mdash; tapi arah temuannya tidak goyah.
</div>

<div class="callout fix">
  <span class="tag">Sampel Lebih Besar</span>
  Kami juga menguji ulang dengan data yang jauh lebih besar: 2.193 pertandingan klub top (Liga Champions, lima liga top Eropa, dll) di luar Piala Dunia. Hasilnya: comeback seperti ini <strong>bukan nol mutlak</strong> &mdash; ada 2 kejadian dari 701 pertandingan yang relevan (sekitar 1 banding 300&ndash;700), yaitu <strong>Leicester City</strong> (tertinggal 0&ndash;2 dari Aston Villa) dan <strong>West Ham United</strong> (tertinggal 0&ndash;2 dari Everton), keduanya di Liga Inggris musim 2015/2016. Ini memperjelas, bukan membatalkan, temuan awal: comeback seperti ini tetap sangat langka, bukan mustahil secara matematis.
</div>

<h3>Tapi Berapa Peluang Argentina, Tepatnya?</h3>

<p>Di sinilah kejujuran data menjadi penting. Ada dua cara sah untuk menghitung peluang Argentina menang saat tertinggal 0&ndash;2, dan keduanya memberi jawaban yang <strong>beda sepuluh kali lipat</strong>. Metode pertama membandingkan ke <em>semua</em> tim dalam sejarah yang pernah tertinggal segitu &mdash; termasuk tim-tim lemah yang memang jarang mampu membalas. Metode kedua hanya membandingkan ke situasi di mana tim yang tertinggal punya kekuatan setara Argentina (memakai rating Elo) &mdash; lebih relevan, tapi sampelnya jadi sangat kecil (kadang cuma 1&ndash;3 pertandingan pembanding).</p>

<figure>
  <img src="{img('05_focal_model_probabilities')}" alt="Peluang menang model dengan anotasi jumlah data">
  <figcaption>Grafik 2. Peluang menang Argentina di setiap momen kunci pertandingan, dari model yang membandingkan hanya ke tim-tim sekuat Argentina. Titik merah = jumlah data pembanding terlalu sedikit untuk dipercaya penuh (n = 1&ndash;14); titik biru = data cukup (n = 28&ndash;37).</figcaption>
</figure>

<p>Kesimpulan jujurnya: peluang Argentina di menit 66&ndash;80 saat tertinggal 0&ndash;2 hampir pasti kecil &mdash; kemungkinan besar di kisaran satu digit rendah sampai belasan persen &mdash; tapi data yang ada tidak cukup untuk memastikan angka tunggal yang presisi. Siapa pun yang mengutip "hanya X% peluang menang" dari momen ini tanpa menyebut dari berapa data itu dihitung, sedang menyederhanakan sesuatu yang sebenarnya tidak sesederhana itu.</p>

<h2 class="section-break">Bagian 2 &middot; Kalau Gol Mesir yang Dianulir Itu Disahkan?</h2>

<p>Salah satu momen paling diperdebatkan di pertandingan ini: sebuah gol Mesir yang dianulir VAR saat skor masih 0&ndash;1. Laporan publik belum sepakat soal menit persisnya (58, 62, atau 67), dan insiden ini <strong>belum diverifikasi lewat video resmi</strong> &mdash; artinya kami tidak bisa dan tidak akan mengklaim keputusan itu salah. Yang bisa kami lakukan: menghitung, <em>jika saja</em> gol itu disahkan, seberapa besar itu akan mengubah peluang menang Argentina secara statistik.</p>

<figure>
  <img src="{img('06_scenario_only_impact')}" alt="Dampak skenario gol dianulir">
  <figcaption>Grafik 3. Perubahan peluang menang Argentina jika gol yang dianulir tersebut disahkan, dihitung pada tiga kemungkinan menit kejadian. Garis vertikal = interval ketidakpastian dari bootstrap statistik.</figcaption>
</figure>

<div class="callout warn">
  <span class="tag">Batasan Penting</span>
  Di ketiga asumsi menit, mengesahkan gol tersebut (mengubah defisit Argentina dari 1 gol menjadi 2 gol lebih awal) akan menurunkan peluang menang Argentina sebesar <strong>3&ndash;5 poin persentase</strong> &mdash; dan interval ketidakpastiannya tidak menyentuh nol di skenario manapun. Ini artinya dampaknya <em>secara statistik cukup berarti</em>. Tapi ini <strong>bukan</strong> bukti bahwa keputusan wasit salah, apalagi bukti kecurangan &mdash; itu memerlukan tinjauan video dan aturan resmi yang di luar cakupan analisis data pertandingan publik seperti ini.
</div>

<h2>Bagian 3 &middot; Jadi, Benarkah Argentina "Anak Emas" FIFA Sejak 2022?</h2>

<p>Ini pertanyaan yang jauh lebih besar dari satu pertandingan. Narasi yang beredar: sejak final Piala Dunia 2022, Argentina mendapat keputusan wasit yang secara sistematis menguntungkan mereka. Untuk mengujinya secara adil &mdash; bukan cuma untuk pertandingan ini, tapi lintas tahun dan lintas tim &mdash; kami menghitung berapa banyak penalti, kartu kuning, dan kartu merah yang didapat Argentina dibanding <em>seluruh peserta</em> di setiap edisi Piala Dunia sejak 1930, lalu memeringkatnya sebagai persentil dalam lapangan tim di edisi yang sama.</p>

<figure>
  <img src="{img('03_discipline_percentile_by_edition')}" alt="Persentil disiplin Argentina per edisi">
  <figcaption>Grafik 4. Persentil Argentina dibanding seluruh tim peserta di edisi yang sama, untuk tiga metrik berbeda. Merah = edisi 2022. Kartu hanya dihitung sejak 1970 (sebelum itu sistem kartu belum ada).</figcaption>
</figure>

<div class="callout fix">
  <span class="tag">Koreksi Jujur</span>
  Draf awal analisis ini sempat salah menghitung persentil kartu merah Argentina 2022 sebagai <strong>88%</strong> (terkesan sangat tinggi). Setelah diperiksa ulang, ternyata rumus lama salah menangani nilai yang sama (banyak tim sama-sama nol kartu merah). Argentina sebenarnya nol kartu merah di 2022, dan <strong>28 dari 32 tim</strong> di edisi itu juga nol &mdash; jadi persentil yang benar adalah <strong>43,5%</strong>, hampir persis di tengah lapangan, bukan outlier. Kami perbaiki ini secara terbuka karena kesalahan itu <em>membesar-besarkan</em> narasi bias, dan bukan sebaliknya.
</div>

<p>Yang benar secara data: tingkat penalti Argentina di 2022 memang tinggi (persentil 100, tertinggi di edisi itu) dan kartu kuningnya di atas rata-rata (persentil 84%). Tapi ini <strong>bukan pola yang mulai di 2022</strong>. Argentina juga mencapai persentil 100 untuk penalti pada edisi 1958, dan edisi 1982 serta 1990 justru punya persentil kartu merah yang sama atau lebih tinggi dari 2022. Kalau ini benar-benar perlakuan istimewa yang "dimulai sejak 2022," seharusnya ada lompatan tajam yang baru muncul di titik itu &mdash; datanya tidak menunjukkan itu. Pola yang ada lebih terlihat seperti ciri khas tim yang secara konsisten menyerang habis-habisan dan menguasai bola lebih lama di kotak penalti lawan, lintas generasi dan lintas era wasit yang berbeda-beda.</p>

<h3>Bagaimana dengan 2026?</h3>

<p>Untuk memeriksa data terkini, kami mengambil <strong>seluruh 96 pertandingan</strong> Piala Dunia 2026 yang sudah dimainkan sampai babak 16 besar (bukan sampel &mdash; sensus penuh) dari laporan resmi FIFA, dan menghitung jumlah penalti yang <em>diberikan</em> ke setiap tim (bukan hanya yang dikonversi jadi gol &mdash; termasuk penalti Messi yang gagal di menit 20 tadi).</p>

<figure>
  <img src="{img('04_pmsr_2026_penalties')}" alt="Perbandingan penalti 2026">
  <figcaption>Grafik 5. Penalti yang diberikan per pertandingan untuk setiap tim di Piala Dunia 2026 (sampai babak 16 besar), dari 48 tim. Argentina memimpin lapangan.</figcaption>
</figure>

<div class="callout">
  <span class="tag">Catatan Metodologi</span>
  Angka 2026 ini ("penalti diberikan") dan angka 1930&ndash;2022 di atas ("penalti dikonversi jadi gol") mengukur hal yang berbeda dari sumber dokumen yang berbeda pula &mdash; keduanya <strong>tidak boleh digabung</strong> jadi satu angka.
</div>

<p>Argentina memang memimpin lapangan 48 tim dengan 3 penalti dari 5 pertandingan (0,60 per pertandingan), sedikit di atas Brasil, Swiss, dan Inggris (0,40). Tapi ini turnamen yang masih berjalan, dengan setiap tim baru bermain 3&ndash;5 pertandingan, dan median lapangan masih nol. Dibaca bersama grafik 1930&ndash;2022 di atas, ini adalah titik data kedua yang searah dengan pola 2022 &mdash; bukan bukti independen yang berdiri sendiri, dan sama konsistennya dengan penjelasan sederhana (tim elite yang menguasai bola dan menyerang terus-menerus akan secara mekanis lebih sering memicu penalti) seperti halnya dengan cerita perlakuan istimewa.</p>

<h2 class="section-break">Kesimpulan: Apa yang Bisa &mdash; dan Tidak Bisa &mdash; Disimpulkan</h2>

<table class="verdict-table">
<tr><th>Klaim</th><th>Didukung Data?</th></tr>
<tr><td>Comeback ini langka secara statistik</td><td><strong>Ya, kuat.</strong> Nol kejadian serupa dari 964 pertandingan historis, di semua ambang batas menit dan semua irisan era.</td></tr>
<tr><td>Ada sensitivitas berarti pada satu keputusan wasit</td><td><strong>Ya, bersyarat.</strong> Skenario gol dianulir menunjukkan dampak 3&ndash;5 poin persentase &mdash; tapi berstatus "belum dinilai kebenarannya," bukan insiden tervalidasi.</td></tr>
<tr><td>Ada pola berulang keputusan wasit yang menguntungkan satu arah</td><td><strong>Belum terbukti.</strong> Tidak ada insiden di pertandingan ini yang statusnya sudah "terverifikasi lewat video/resmi."</td></tr>
<tr><td>Argentina sengaja dimanipulasi/diistimewakan FIFA</td><td><strong>Tidak bisa dinilai</strong> dari data pertandingan publik semacam ini sama sekali.</td></tr>
</table>

<p>Data statistik pertandingan publik &mdash; sekaya apapun &mdash; punya batas. Ia bisa memberi tahu kita seberapa langka sebuah hasil, seberapa besar dampak sebuah skenario alternatif, dan apakah sebuah pola angka konsisten lintas waktu. Ia <strong>tidak bisa</strong> membaca niat wasit, membuktikan korupsi, atau memutuskan kebenaran sebuah keputusan tanpa tinjauan video dan aturan resmi. Comeback Argentina memang, secara statistik, salah satu yang paling langka dalam sejarah Piala Dunia. Tapi "langka" dan "dicurangi" adalah dua klaim yang sama sekali berbeda &mdash; dan hanya satu dari keduanya yang bisa dijawab data ini.</p>

<div class="footer">
  <strong>Metodologi &amp; transparansi.</strong> Seluruh angka di artikel ini dihasilkan dari pipeline data reproducible &mdash; bukan diketik manual. Kode ETL, notebook Jupyter yang dieksekusi penuh tanpa error, dataset mentah (laporan resmi FIFA, Fjelstul World Cup Database, rating Elo JGravier), dan laporan teknis lengkap dengan seluruh denominator dan interval ketidakpastian tersedia terbuka di:<br>
  <a href="{REPO_URL}">{REPO_URL}</a><br><br>
  Notebook: <code>output/jupyter-notebook/argentina_egypt_comeback_analysis.ipynb</code> &middot; Laporan teknis lengkap: <code>results/analysis_report.md</code> &middot; Provenance data: <code>config/sources.json</code>
</div>

</div>
</body>
</html>
"""


def main() -> None:
    from playwright.sync_api import sync_playwright

    html = build_html()
    OUT_HTML.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(OUT_HTML.as_uri())
        page.pdf(path=str(OUT_PDF), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
