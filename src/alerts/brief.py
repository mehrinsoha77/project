"""Weekly risk brief (PDF) for upazila / union committees, BWDB and NGO partners.

One page per forecast date: the 20 highest-risk 200 m segments with their
calibrated probability, the movement seen on the latest pass and the
plain-language reasons, a small map, the measured skill of the model next to
persistence (only if measured), and the standing safeguards.

CLI::

    python -m src.alerts.brief --date 2024-08-23 --out brief.pdf
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from src import config  # noqa: E402
from src.alerts.send_alert import DISCLAIMER  # noqa: E402

BANK_NAME = {"W": "West bank (Sirajganj side)", "E": "East bank (Tangail side)"}


def _map_png(pred: pd.DataFrame, top: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(2.6, 4.2), dpi=150)
    for _, g in pred.sort_values("chainage_m").groupby("bank"):
        ax.plot(g["lon"], g["lat"], color="#898781", lw=1)
    ax.scatter(top["lon"], top["lat"], s=18, color="#d03b3b", zorder=3, edgecolor="white", linewidth=0.6)
    for _, r in top.head(5).iterrows():
        ax.annotate(str(int(r["rank"])), (r["lon"], r["lat"]), fontsize=6, xytext=(3, 2), textcoords="offset points")
    ax.set_aspect(1 / 0.91)
    ax.tick_params(labelsize=5)
    ax.set_title("Top-20 segments (red)", fontsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _skill_line() -> str:
    p = config.METRICS_DIR / "test_results.json"
    if not p.exists():
        return "Model skill on held-out years: not yet measured."
    r = json.loads(p.read_text())["temporal"]
    m, b = r["M1"]["precision_at_k"], r["B0_persistence"]["precision_at_k"]
    ci = r["M1_minus_B0"]["all_dates"]
    return (f"Measured on 2023–2025 hindcasts: on average {m:.0%} of the top 20 segments lost at least "
            f"the threshold within 28 days, versus {b:.0%} for 'it eroded recently' (persistence); "
            f"difference {ci['mean']:+.1%} (95% CI {ci['lo']:+.1%} to {ci['hi']:+.1%}).")


def build_brief(pred: pd.DataFrame, date: str, out: Path | io.BytesIO) -> None:
    d = pred[pred["forecast_date"] == pd.Timestamp(date)].sort_values("rank")
    if d.empty:
        raise ValueError(f"no predictions for {date}")
    top = d.head(config.TOP_K)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=7, leading=8.5)
    tiny = ParagraphStyle("tiny", parent=ss["Normal"], fontSize=6.5, leading=8, textColor=colors.HexColor("#52514e"))
    doc = SimpleDocTemplate(str(out) if isinstance(out, Path) else out, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"NadiNet risk brief {date}", author="NadiNet")
    story = [
        Paragraph("<b>NadiNet weekly risk brief</b> — Jamuna, Kazipur to Chauhali reach", ss["Title"]),
        Paragraph(f"Issued after the Sentinel-1 pass of <b>{date}</b>. Horizon: next 28 days. "
                  f"Risk = calibrated probability that a 200 m bank segment loses at least "
                  f"{d.attrs.get('threshold_m', 20):.0f} m of land.", small),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>{DISCLAIMER}</b>", small),
        Spacer(1, 3 * mm),
    ]
    rows = [["#", "Segment", "Bank", "Lat, Lon", "Risk", "Latest pass", "Why (model reasons)"]]
    for _, r in top.iterrows():
        reasons = r.get("reasons") or []
        if isinstance(reasons, str):
            reasons = json.loads(reasons)
        moved = r.get("raw_last_change_m")
        moved_s = f"{moved:+.0f} m" if pd.notna(moved) else "–"
        rows.append([int(r["rank"]), r["transect_id"], BANK_NAME.get(r["bank"], r["bank"]).split(" (")[0],
                     f"{r['lat']:.4f}, {r['lon']:.4f}", f"{r['p']:.0%}", moved_s,
                     Paragraph("; ".join(x["text"] for x in reasons[:2]) or "–", tiny)])
    t = Table(rows, colWidths=[7 * mm, 18 * mm, 18 * mm, 27 * mm, 11 * mm, 16 * mm, 66 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 6.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#c3c2b7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f7")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    img = Image(io.BytesIO(_map_png(d, top)), width=46 * mm, height=74 * mm)
    story.append(Table([[t, img]], colWidths=[163 * mm - 46 * mm + 0 * mm, 46 * mm],
                       style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [
        Spacer(1, 3 * mm),
        Paragraph(_skill_line(), small),
        Spacer(1, 2 * mm),
        Paragraph("Tiers: <b>Watch</b> = in this top-20 list. <b>Warning</b> = high risk plus retreat on the "
                  "latest pass; it reaches households only after an official approves it on the dashboard. "
                  "Raw risk maps stay with officials and partners; public views are aggregated to union level.",
                  small),
        Spacer(1, 2 * mm),
        Paragraph("Data: Copernicus Sentinel-1 GRD (ESA), descending track 150, ~05:56 local time; banks traced on "
                  "10 m water masks. Reasons describe what the model used, not proven causes. Segments not seen "
                  "on the latest pass carry no forecast.", tiny),
    ]
    doc.build(story)


def main() -> None:
    from src.api.export import load_predictions

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or (config.PROCESSED / "alerts" / f"brief_{a.date}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    build_brief(load_predictions(), a.date, out)
    print(out)


if __name__ == "__main__":
    main()
