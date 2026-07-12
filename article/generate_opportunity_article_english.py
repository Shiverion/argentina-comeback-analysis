"""Build the English companion PDF for the opportunity-adjusted analysis."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "article" / "argentina-opportunity-adjusted-analysis-en.pdf"


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def model(manifest: dict, panel: str, tier: str | None = None) -> dict:
    for item in manifest["models"]:
        if item["panel"] == panel and item.get("tier") == tier:
            return item
    raise RuntimeError(f"Missing model {panel}/{tier}")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d8e0ea"))
    canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6b7a90"))
    canvas.drawString(18 * mm, 8 * mm, "Argentina Opportunity-Adjusted Analysis")
    canvas.drawRightString(192 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()


def main() -> None:
    manifest = json.loads((ROOT / "results" / "opportunity_analysis_manifest.json").read_text(encoding="utf-8"))
    temporal = json.loads((ROOT / "results" / "temporal_analysis_manifest.json").read_text(encoding="utf-8"))
    bridge_manifest = json.loads((ROOT / "results" / "bridge_analysis_manifest.json").read_text(encoding="utf-8"))
    pmsr = model(manifest, "pmsr_2026")
    world = model(manifest, "statsbomb_world_cup")
    club = model(manifest, "statsbomb_history", "club")
    temporal_club = model(temporal, "statsbomb_history", "club")
    bridge_club = next(item for item in bridge_manifest["models"] if item["tier"] == "club")
    bridge_world = next(item for item in bridge_manifest["models"] if item["tier"] == "world_cup")
    bridge_club_models = {item["variant"]: item for item in bridge_club["models"]}
    bridge_world_models = {item["variant"]: item for item in bridge_world["models"]}

    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=colors.HexColor("#0b1d3a"), alignment=TA_CENTER, spaceAfter=12)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=11, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#415168"), spaceAfter=20)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#0b1d3a"), spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=15, spaceAfter=8, textColor=colors.HexColor("#25344a"))
    note = ParagraphStyle("Note", parent=body, backColor=colors.HexColor("#eef3fb"), borderColor=colors.HexColor("#c8d9ef"), borderWidth=0.6, borderPadding=8, spaceBefore=6, spaceAfter=10)
    accent = ParagraphStyle("Accent", parent=body, textColor=colors.HexColor("#2f6f8f"), fontName="Helvetica-Bold")

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm)
    story = [
        Spacer(1, 12 * mm),
        paragraph("Penalties, Attacking Opportunity, and Argentina", title),
        paragraph("A reproducible companion analysis for the Argentina comeback research project", subtitle),
        paragraph("<b>Bottom line.</b> Argentina led the official 2026 penalty count in the extracted tournament sample. That is a real descriptive fact, but it is not evidence of favoritism by itself. Across broader event data, the useful question is whether pre-decision attacking opportunity explains where penalty-shot events occur. The new time-aware model finds a small, out-of-fold improvement over a null rate in the club panel. It still cannot judge whether any individual decision was correct or biased.", note),
        paragraph("What This Analysis Can Measure", heading),
        paragraph("Possession alone is an incomplete exposure measure. A team may control the ball far from the opponent box, while another team may create more decisive entries with less total possession. We therefore retain possession alongside passes and carries into the penalty area, completed receipts in the area, non-penalty xG, shots in the box, fouls, and cards.", body),
        paragraph("The source lanes remain separate. FIFA PMSR 2026 counts official penalties awarded. StatsBomb event data counts regulation penalty shots as an event proxy. These quantities are not merged into one statistic.", body),
        paragraph("The 2026 Official Panel", heading),
        paragraph(f"The PMSR panel covers 96 matches and 192 team-match rows. Argentina recorded 3 official penalties in 5 matches. The match-clustered Spearman association between team-match xG and penalties awarded is {pmsr['xg_spearman']['correlation']:.3f}, with a 95 percent bootstrap interval from {pmsr['xg_spearman']['lower']:.3f} to {pmsr['xg_spearman']['upper']:.3f}. Only 19 awards were observed across the tournament snapshot, so this lane is descriptive rather than a stable multi-variable estimate.", body),
        Image(str(ROOT / "results" / "assets" / "09_pmsr_2026_penalties_vs_xg.png"), width=165 * mm, height=94 * mm),
        paragraph("A Broader Mechanism Check", heading),
        paragraph(f"The selected club panel contains {club['matches']} matches and {club['rows']} team-match rows. The raw Spearman association between box entries and penalty shots is {club['box_entry_spearman']['correlation']:.3f} (95 percent interval {club['box_entry_spearman']['lower']:.3f} to {club['box_entry_spearman']['upper']:.3f}). Its simple out-of-fold Poisson model only slightly improves on the null deviance: {club['oof_mean_poisson_deviance']:.4f} versus {club['null_mean_poisson_deviance']:.4f}. This supports a mechanism check, not a FIFA-specific conclusion.", body),
        Image(str(ROOT / "results" / "assets" / "10_statsbomb_world_cup_box_entries_vs_penalty_shots.png"), width=165 * mm, height=94 * mm),
        paragraph("The Five-Minute Pre-Decision Panel", heading),
        paragraph(f"The temporal extension creates a row for each team and five-minute window. Predictors are calculated strictly before the window: score state, recent box entries and receipts, non-penalty xG, fouls, cards, and event-derived possession sequences. The label is whether a penalty-shot event occurs inside the next window. Across {temporal_club['matches']} club matches there are {temporal_club['positive_events']} penalty-shot events and {temporal_club['rows']} team-windows. The grouped out-of-fold hazard model has log loss {temporal_club['oof_log_loss']:.4f}, compared with {temporal_club['null_log_loss']:.4f} for the null rate.", body),
        Image(str(ROOT / "results" / "assets" / "11_temporal_club_penalty_hazard.png"), width=165 * mm, height=94 * mm),
        paragraph("Formal Inference and Robustness", heading),
        paragraph(f"Official PMSR possession and penalties in the 2026 snapshot have Spearman correlation {pmsr['possession_spearman']['correlation']:.3f}, with a whole-match permutation p-value of {pmsr['possession_spearman']['permutation_p_value']:.4f} and Benjamini-Hochberg q-value of {pmsr['possession_spearman']['bh_q_value']:.4f}. The club event panel shows a smaller but statistically detectable association between possession-sequence share and penalty-shot events ({club['possession_spearman']['correlation']:.3f}, q={club['possession_spearman']['bh_q_value']:.4f}); the World Cup and non-World-Cup international lanes do not. Statistical significance is not the same as a large effect or causality.", body),
        paragraph("The Notebook 1 Bridge", heading),
        paragraph(f"The club state-only model has out-of-fold log loss {bridge_club_models['state_only']['log_loss']:.4f}; the opportunity-augmented model improves this to {bridge_club_models['opportunity_augmented']['log_loss']:.4f}. In the World Cup lane, the corresponding values move from {bridge_world_models['state_only']['log_loss']:.4f} to {bridge_world_models['opportunity_augmented']['log_loss']:.4f}. This mixed direction is useful robustness evidence: opportunity features help in one population but should not be treated as a universal upgrade.", body),
        Image(str(ROOT / "results" / "assets" / "12_bridge_model_skill.png"), width=165 * mm, height=94 * mm),
        Image(str(ROOT / "results" / "assets" / "13_penalty_win_impact.png"), width=165 * mm, height=94 * mm),
        paragraph("The improvement is modest and should be read carefully. It means that pre-window context contains some information about where event-feed penalty shots occur. It does not mean the model knows whether a foul was real, whether a referee should have awarded a penalty, or whether a pattern was intentional.", note),
        paragraph("What the Evidence Does Not Establish", heading),
        paragraph("The data does not provide a complete denominator of all potential contacts in the penalty area. It also does not provide a validated adjudication of decision correctness for every incident. Argentina-specific estimation remains underpowered: the history panel contains only six Argentina rows, the 2018/2022 World Cup panel contains eleven, and the 2026 PMSR panel contains five.", body),
        paragraph("Conclusion", heading),
    ]
    table = Table([
        ["Question", "Evidence status"],
        ["Did Argentina lead the extracted 2026 official penalty count?", "Verified, descriptive"],
        ["Does pre-window attacking context contain information about penalty-shot events?", "Supported modestly in the club panel"],
        ["Does the result prove referee bias or intent?", "No"],
        ["Can the data adjudicate every penalty decision?", "Not with the current denominator"],
    ], colWidths=[112 * mm, 53 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1d3a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEADING", (0, 0), (-1, -1), 11), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 8), paragraph("Reproducibility: the ETL code, pinned source definitions, processed temporal panels, executed notebook, manifests, and charts are stored in this repository. The definitive technical contract is in docs/opportunity_adjusted_analysis.md.", body)])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
