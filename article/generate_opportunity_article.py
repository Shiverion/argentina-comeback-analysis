"""Build the Indonesian companion PDF for the opportunity-adjusted analysis."""

from __future__ import annotations

import json
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("OPPORTUNITY_ARTICLE_OUT", str(ROOT / "article" / "argentina-opportunity-adjusted-analysis.pdf")))


def model(manifest: dict, panel: str, tier: str | None = None) -> dict:
    for item in manifest["models"]:
        if item["panel"] == panel and item.get("tier") == tier:
            return item
    raise RuntimeError(f"Missing model {panel}/{tier}")


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def main() -> None:
    manifest = json.loads((ROOT / "results" / "opportunity_analysis_manifest.json").read_text(encoding="utf-8"))
    pmsr = model(manifest, "pmsr_2026")
    world = model(manifest, "statsbomb_world_cup")
    club = model(manifest, "statsbomb_history", "club")
    intl = model(manifest, "statsbomb_history", "intl")
    temporal_manifest_path = ROOT / "results" / "temporal_analysis_manifest.json"
    temporal_manifest = json.loads(temporal_manifest_path.read_text(encoding="utf-8")) if temporal_manifest_path.exists() else None
    temporal_club = next((item for item in (temporal_manifest or {}).get("models", []) if item.get("tier") == "club"), None)
    bridge_manifest_path = ROOT / "results" / "bridge_analysis_manifest.json"
    bridge_manifest = json.loads(bridge_manifest_path.read_text(encoding="utf-8")) if bridge_manifest_path.exists() else None
    bridge_club = next((item for item in (bridge_manifest or {}).get("models", []) if item.get("tier") == "club"), None)
    bridge_world = next((item for item in (bridge_manifest or {}).get("models", []) if item.get("tier") == "world_cup"), None)
    bridge_club_models = {item["variant"]: item for item in (bridge_club or {}).get("models", [])}
    bridge_world_models = {item["variant"]: item for item in (bridge_world or {}).get("models", [])}
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=colors.HexColor("#0b1d3a"), alignment=TA_CENTER, spaceAfter=12)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=11, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#415168"), spaceAfter=20)
    h = ParagraphStyle("H", parent=styles["Heading2"], fontName="Helvetica-Bold", textColor=colors.HexColor("#0b1d3a"), spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=15, spaceAfter=8)
    note = ParagraphStyle("Note", parent=body, backColor=colors.HexColor("#eef3fb"), borderColor=colors.HexColor("#c8d9ef"), borderWidth=0.6, borderPadding=8, spaceBefore=6, spaceAfter=10)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = [
        Spacer(1, 15 * mm),
        p("Argentina, Penalti, dan Peluang Menyerang", title),
        p("Analisis opportunity-adjusted sebagai pendamping studi comeback Argentina vs Egypt", subtitle),
        p("<b>Jawaban singkat.</b> Argentina memimpin penalti resmi 2026 sejauh ini, tetapi angka mentah itu belum membedakan dominasi menyerang dari keputusan yang tidak biasa. Ketika sampel diperluas, hubungan sederhana antara masuk kotak penalti dan penalti lemah; hanya model klub yang sedikit mengalahkan baseline null. Tidak ada hasil di sini yang membuktikan bias, korupsi, atau manipulasi.", note),
        p("Mengapa Possession Saja Tidak Cukup", h),
        p("Possession menjawab berapa banyak bola dikuasai, bukan di mana ancaman terjadi. Analisis ini memprioritaskan entry melalui pass/carry ke kotak penalti, completed receipt di kotak, dan non-penalty xG. Possession PMSR tetap dipertahankan bersama contested possession, bukan dipaksa menjadi 100% untuk dua tim saja.", body),
        p("Panel Resmi FIFA 2026", h),
        p(f"Panel resmi mencakup 96 pertandingan dan 192 team-match rows. Argentina mendapat 3 penalti dalam 5 laga (0,60/laga). Korelasi Spearman match-clustered antara xG dan penalti resmi adalah {pmsr['xg_spearman']['correlation']:.3f}, dengan interval bootstrap 95% {pmsr['xg_spearman']['lower']:.3f} hingga {pmsr['xg_spearman']['upper']:.3f}. Hasil ini bersifat deskriptif karena hanya ada 19 penalti di seluruh turnamen pada saat ekstraksi.", body),
        Image(str(ROOT / "results" / "assets" / "09_pmsr_2026_penalties_vs_xg.png"), width=165 * mm, height=94 * mm),
        p("Apa yang Terjadi pada Sampel Lebih Luas", h),
        p(f"World Cup 2018/2022 memiliki 128 pertandingan dan 47 team-match dengan penalty-shot regulasi. Korelasi entry kotak-penalti terhadap penalty-shot hanya {world['box_entry_spearman']['correlation']:.3f} (95% {world['box_entry_spearman']['lower']:.3f} hingga {world['box_entry_spearman']['upper']:.3f}), dan model out-of-fold tidak mengalahkan null ({world['oof_mean_poisson_deviance']:.3f} vs {world['null_mean_poisson_deviance']:.3f}). Karena itu, residual per tim World Cup sengaja tidak dipublikasikan.", body),
        Image(str(ROOT / "results" / "assets" / "10_statsbomb_world_cup_box_entries_vs_penalty_shots.png"), width=165 * mm, height=94 * mm),
        p("Validasi Mekanisme, Bukan Bukti FIFA", h),
        p(f"Pada 2.193 laga klub terpilih, korelasi yang sama kecil tetapi positif: {club['box_entry_spearman']['correlation']:.3f} (95% {club['box_entry_spearman']['lower']:.3f}-{club['box_entry_spearman']['upper']:.3f}), dan model mengalahkan null secara tipis ({club['oof_mean_poisson_deviance']:.3f} vs {club['null_mean_poisson_deviance']:.3f}). Ini mendukung bahwa akses menyerang memiliki informasi, tetapi tidak dapat digunakan sebagai bukti tentang FIFA. Pada 186 laga timnas non-World-Cup, model tidak mengalahkan null dan residual juga ditahan.", body),
        p("Panel Lima-Menit Sebelum Kejadian", h),
        p(
            f"Ekstensi temporal membentuk {temporal_club['matches'] if temporal_club else 2193} pertandingan klub menjadi window lima-menit dan hanya memakai score state, entry kotak, xG non-penalti, foul, kartu, serta possession sequence sebelum window. Model hazard grouped out-of-fold menghasilkan log loss {temporal_club['oof_log_loss']:.4f} dibanding {temporal_club['null_log_loss']:.4f} untuk baseline null, dengan {temporal_club['positive_events']} penalty-shot events. Perbaikan kecil ini mendukung bahwa konteks sebelum kejadian mengandung informasi, bukan bahwa keputusan wasit salah atau bias.",
            body,
        ) if temporal_club else p("Panel temporal belum tersedia pada saat artikel dibuat.", body),
        Image(str(ROOT / "results" / "assets" / "11_temporal_club_penalty_hazard.png"), width=165 * mm, height=94 * mm) if temporal_club else Spacer(1, 4),
        p("Uji Inferensi dan Robustness", h),
        p(f"Korelasi possession resmi dengan penalty awarded pada PMSR 2026 adalah {pmsr['possession_spearman']['correlation']:.3f}, dengan permutation p-value {pmsr['possession_spearman']['permutation_p_value']:.4f} dan BH q-value {pmsr['possession_spearman']['bh_q_value']:.4f}. Pada sampel klub, possession-sequence share berkorelasi {club['possession_spearman']['correlation']:.3f} dengan penalty-shot event (q={club['possession_spearman']['bh_q_value']:.4f}); World Cup dan international non-World-Cup tidak signifikan setelah struktur pertandingan dan multiple testing dipertahankan. Signifikansi statistik ini tidak sama dengan efek besar atau kausalitas.", body),
        p("Bridge ke Notebook 1", h),
        p(f"Model state-only yang memprediksi regulation result dari waktu, score, kartu merah, dan home indicator memiliki log loss {bridge_club_models.get('state_only', {}).get('log_loss', 0):.4f} pada club panel. Setelah menambahkan opportunity sebelum window, log loss menjadi {bridge_club_models.get('opportunity_augmented', {}).get('log_loss', 0):.4f}; pada World Cup model berubah dari {bridge_world_models.get('state_only', {}).get('log_loss', 0):.4f} menjadi {bridge_world_models.get('opportunity_augmented', {}).get('log_loss', 0):.4f}. Perbedaan arah ini adalah alasan hasil bridge diperlakukan sebagai robustness check, bukan model universal baru.", body) if bridge_club else Spacer(1, 4),
        Image(str(ROOT / "results" / "assets" / "12_bridge_model_skill.png"), width=165 * mm, height=94 * mm) if bridge_club else Spacer(1, 4),
        Image(str(ROOT / "results" / "assets" / "13_penalty_win_impact.png"), width=165 * mm, height=94 * mm) if bridge_club else Spacer(1, 4),
        p("Batas Bukti", h),
        p("Model ini belum mengendalikan score state sebelum keputusan, kekuatan tim, penugasan wasit, atau seluruh kontak potensial di kotak penalti. Langkah berikutnya adalah panel time-aware sebelum keputusan dan ledger insiden yang tervalidasi video. Sampai saat itu, hasil yang tepat adalah association dan partial adjustment, bukan penilaian benar/salah keputusan.", note),
    ]
    table = Table([
        ["Klaim", "Status"],
        ["Argentina memimpin penalti resmi 2026", "Terverifikasi, deskriptif"],
        ["Peluang menyerang menjelaskan seluruh variasi penalti", "Tidak didukung"],
        ["Argentina menerima perlakuan istimewa", "Tidak dapat disimpulkan"],
    ], colWidths=[112 * mm, 53 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1d3a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEADING", (0, 0), (-1, -1), 11),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7fafc")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([p("Kesimpulan", h), table, Spacer(1, 8), p("Sumber dan reproducibility: data/processed/*opportunity_features.csv, data/processed/*temporal_features.csv, results/opportunity_analysis_manifest.json, results/temporal_analysis_manifest.json, dan notebook opportunity_adjusted_officiating_analysis.ipynb.", body)])
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
