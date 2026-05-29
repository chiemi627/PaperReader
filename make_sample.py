"""論文っぽい体裁のサンプルPDFを生成（テスト用）."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Frame, PageTemplate, BaseDocTemplate
)
from reportlab.lib.units import inch

OUT = "sample_paper.pdf"

# 2段組テンプレート
doc = BaseDocTemplate(OUT, pagesize=letter,
                      leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch)

frame1 = Frame(doc.leftMargin, doc.bottomMargin,
               (doc.width - 0.3 * inch) / 2, doc.height, id='col1')
frame2 = Frame(doc.leftMargin + (doc.width + 0.3 * inch) / 2, doc.bottomMargin,
               (doc.width - 0.3 * inch) / 2, doc.height, id='col2')

def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.drawCentredString(letter[0] / 2, 0.4 * inch, str(doc.page))
    canvas.drawString(0.5 * inch, letter[1] - 0.4 * inch,
                      "Proceedings of NTUT Accessibility Workshop 2026")
    canvas.restoreState()

doc.addPageTemplates([PageTemplate(id='TwoCol', frames=[frame1, frame2], onPage=header_footer)])

styles = getSampleStyleSheet()
body = ParagraphStyle('body', parent=styles['BodyText'], fontSize=9.5,
                      leading=12, alignment=4, spaceAfter=4)
h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=12, spaceBefore=8, spaceAfter=4)
title = ParagraphStyle('title', parent=styles['Title'], fontSize=14, alignment=1, spaceAfter=10)
abst = ParagraphStyle('abst', parent=styles['BodyText'], fontSize=9, leading=11,
                       leftIndent=10, rightIndent=10, spaceAfter=6)
caption = ParagraphStyle('caption', parent=styles['BodyText'], fontSize=8.5,
                          alignment=1, spaceAfter=6, fontName='Helvetica-Oblique')

story = []
story.append(Paragraph("Multi-Camera Pipeline for Non-Manual Signal Capture in JSL", title))
story.append(Paragraph("<b>Anonymous Authors</b>", body))
story.append(Spacer(1, 6))

story.append(Paragraph("<b>Abstract</b>", h1))
story.append(Paragraph(
    "Capturing non-manual signals (NMS) in Japanese Sign Language is challenging "
    "because the signer's hands frequently occlude facial regions. We propose a "
    "multi-camera MediaPipe pipeline that fuses landmarks from three viewpoints "
    "to recover occluded facial expressions. Experiments on 1,200 utterances show "
    "a 27% reduction in landmark dropout compared to a single-camera baseline [1].",
    abst))

story.append(Paragraph("1. Introduction", h1))
story.append(Paragraph(
    "Non-manual signals such as eyebrow position, mouth shape, and head tilt are "
    "essential grammatical markers in Japanese Sign Language (JSL) [2, 3]. Prior "
    "work has explored single-camera capture (Smith et al., 2020), but hand-over-"
    "face occlusion remains a persistent problem. Wakatsuki and colleagues (Wakatsuki, 2023) "
    "reported that up to 38% of frames in conversational JSL contain partial occlusion "
    "of the lower face. This paper introduces a synchronized three-camera setup "
    "and a fusion algorithm that selects the most visible landmarks per frame. "
    "Our contribution is twofold: a hardware-light capture protocol, and an open "
    "evaluation dataset of NMS annotations. The dataset will be released at https://example.org/nms2026 "
    "(doi: 10.1234/nms.2026.001).",
    body))

story.append(Paragraph("2. Related Work", h1))
story.append(Paragraph(
    "Several systems address occlusion in sign language recognition. AutoSign [4] "
    "uses temporal interpolation to fill missing keypoints. The MSLR-ICCV2025 "
    "challenge [5, 6, 7] introduced standardized benchmarks for continuous "
    "recognition. However, none of these approaches address the specific case "
    "of NMS, which requires fine-grained facial landmarks rather than the body-"
    "centric features typical of CSLR systems [8].",
    body))

story.append(Paragraph("Figure 1: Camera placement diagram showing three viewpoints "
                       "arranged at 0°, 45°, and 90° azimuth relative to the signer.", caption))

story.append(Paragraph("3. Method", h1))
story.append(Paragraph(
    "Our pipeline consists of three stages: synchronized capture, per-frame "
    "landmark extraction with MediaPipe Face Landmarker, and confidence-weighted "
    "fusion. Let x_i denote the landmark vector from camera i, and c_i its "
    "confidence score returned by MediaPipe. We compute the fused landmark as "
    "x_fused = Σ c_i x_i / Σ c_i. When all three cameras return low confidence "
    "(c_i < 0.3 for all i), we fall back to temporal interpolation from "
    "neighboring frames.",
    body))
story.append(Paragraph("∂L/∂x = Σ ∇f(x_i) ⊙ c_i", body))
story.append(Paragraph(
    "Calibration is performed once per session using a planar checkerboard. "
    "The three cameras are synchronized via hardware trigger with sub-millisecond "
    "jitter.",
    body))

story.append(Paragraph("Table 1: Comparison of single-camera and multi-camera dropout rates.", caption))

story.append(Paragraph("4. Experiments", h1))
story.append(Paragraph(
    "We collected 1,200 JSL utterances from six native signers (three deaf, three "
    "hearing fluent signers) covering interrogatives, conditionals, and topic "
    "markers — all of which rely heavily on NMS. Inter-annotator agreement on "
    "the NMS labels was κ = 0.81. The single-camera baseline showed landmark "
    "dropout in 38.4% of frames, while our three-camera fusion reduced this to "
    "11.2% — a 27 percentage point improvement. Downstream classification "
    "accuracy on a five-way NMS category task improved from 71.3% to 84.6%.",
    body))

story.append(Paragraph("5. Discussion", h1))
story.append(Paragraph(
    "The improvement is most pronounced for the puff-cheek marker (パピプペポ "
    "mouth gesture, not to be confused with Japanese phonetic mouthing), which "
    "is frequently obscured by the dominant hand during one-handed signs. Our "
    "approach has limitations: the three-camera setup is impractical for in-the-"
    "wild capture, and synchronization quality degrades under USB bandwidth "
    "constraints when using consumer webcams.",
    body))

story.append(Paragraph("6. Conclusion", h1))
story.append(Paragraph(
    "We presented a multi-camera pipeline for robust NMS capture in JSL. Future "
    "work includes extending the approach to mobile capture using smartphone "
    "clusters, and integrating the fused landmarks into avatar-driven JSL "
    "synthesis systems.",
    body))

story.append(Paragraph("References", h1))
story.append(Paragraph("[1] A. Smith and B. Jones. Single-camera sign capture. ACL 2020.", body))
story.append(Paragraph("[2] C. Tanaka. Grammar of JSL. NTUT Press, 2018.", body))
story.append(Paragraph("[3] D. Wakatsuki. Non-manual markers in JSL conversation. Sign Lang Studies, 2023.", body))
story.append(Paragraph("[4] E. Chen et al. AutoSign: continuous recognition. CVPR 2024.", body))
story.append(Paragraph("[5] F. Liu. MSLR challenge overview. ICCV 2025.", body))

doc.build(story)
print(f"Generated: {OUT}")
