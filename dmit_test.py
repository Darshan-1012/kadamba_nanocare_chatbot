from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Flowable

W, H = A4

# ── Colour palette ─────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1B3A6B")
BLUE    = colors.HexColor("#185FA5")
BLUE_L  = colors.HexColor("#E6F1FB")
TEAL    = colors.HexColor("#0F6E56")
TEAL_L  = colors.HexColor("#E1F5EE")
AMBER   = colors.HexColor("#854F0B")
AMBER_L = colors.HexColor("#FAEEDA")
RED_L   = colors.HexColor("#FCEBEB")
RED_D   = colors.HexColor("#A32D2D")
GREEN_L = colors.HexColor("#EAF3DE")
GREEN_D = colors.HexColor("#3B6D11")
GRAY_L  = colors.HexColor("#F5F5F3")
GRAY_M  = colors.HexColor("#888780")
GRAY_D  = colors.HexColor("#444441")
WHITE   = colors.white
BLACK   = colors.HexColor("#1A1A1A")
CORAL_L = colors.HexColor("#FAECE7")
CORAL_D = colors.HexColor("#712B13")
PURPLE_L= colors.HexColor("#EEEDFE")
PURPLE_D= colors.HexColor("#3C3489")

# ── Styles ──────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    base = kw.pop("parent", "Normal")
    return ParagraphStyle(name, parent=styles[base], **kw)

sTitle   = S("sTitle",   fontSize=22, textColor=NAVY,   alignment=TA_CENTER, spaceAfter=2,  leading=26, fontName="Helvetica-Bold")
sSub     = S("sSub",     fontSize=10, textColor=GRAY_M, alignment=TA_CENTER, spaceAfter=4,  leading=13)
sSec     = S("sSec",     fontSize=9,  textColor=BLUE,   spaceAfter=6,        leading=11,    fontName="Helvetica-Bold", spaceBefore=14, textTransform="uppercase", letterSpacing=1)
sBody    = S("sBody",    fontSize=9,  textColor=GRAY_D, spaceAfter=3,        leading=14)
sSmall   = S("sSmall",   fontSize=8,  textColor=GRAY_M, spaceAfter=2,        leading=11)
sBold    = S("sBold",    fontSize=9,  textColor=BLACK,  fontName="Helvetica-Bold", leading=13)
sBadge   = S("sBadge",   fontSize=8,  textColor=BLUE,   alignment=TA_CENTER, leading=10)
sCard    = S("sCard",    fontSize=8,  textColor=GRAY_D, leading=12)
sCardHd  = S("sCardHd",  fontSize=9,  textColor=BLACK,  fontName="Helvetica-Bold", leading=12, spaceAfter=3)
sTip     = S("sTip",     fontSize=8,  textColor=GRAY_D, leading=12, leftIndent=8)
sLabel   = S("sLabel",   fontSize=7,  textColor=GRAY_M, leading=9,  spaceAfter=1, fontName="Helvetica")
sMetricV = S("sMetricV", fontSize=20, textColor=NAVY,   fontName="Helvetica-Bold", leading=22, alignment=TA_CENTER)
sMetricL = S("sMetricL", fontSize=7,  textColor=GRAY_M, alignment=TA_CENTER, leading=9)
sMetricS = S("sMetricS", fontSize=8,  textColor=GRAY_M, alignment=TA_CENTER, leading=10)

# ── Helper: horizontal rule ─────────────────────────────────────────────────
def HR(color=GRAY_L, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=4, spaceBefore=4)

# ── Helper: section heading ─────────────────────────────────────────────────
def SectionTitle(text):
    return [
        Spacer(1, 6),
        Paragraph(text, sSec),
        HRFlowable(width="100%", thickness=0.5, color=BLUE_L, spaceAfter=6),
    ]

# ── Helper: colour badge ────────────────────────────────────────────────────
def badge_table(items, bg=BLUE_L, fg=BLUE):
    cells = [[Paragraph(t, ParagraphStyle("b", fontSize=8, textColor=fg, alignment=TA_CENTER, leading=10))] for t in items]
    t = Table([cells], colWidths=[3.8*cm]*len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("ROUNDEDCORNERS", [4,4,4,4]),
        ("TOPPADDING",(0,0),(-1,-1),3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("GRID",(0,0),(-1,-1),0, WHITE),
    ]))
    return t

# ── Helper: metric card row ─────────────────────────────────────────────────
def metric_cards(data):
    """data = list of (value, label, sublabel, color)"""
    cells = []
    for val, lbl, sub, col in data:
        inner = Table([
            [Paragraph(val, ParagraphStyle("mv", fontSize=20, textColor=col, fontName="Helvetica-Bold", leading=22, alignment=TA_CENTER))],
            [Paragraph(lbl, sMetricL)],
            [Paragraph(sub, sMetricS)],
        ], colWidths=[3.8*cm])
        inner.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), GRAY_L),
            ("ROUNDEDCORNERS",[4,4,4,4]),
            ("TOPPADDING",(0,0),(-1,-1),8),
            ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ]))
        cells.append(inner)
    t = Table([cells], colWidths=[3.9*cm]*len(data), hAlign="LEFT")
    t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4)]))
    return t

# ── Helper: progress bar ────────────────────────────────────────────────────
class ProgressBar(Flowable):
    def __init__(self, label, pct, bar_color, width=16*cm):
        super().__init__()
        self.label = label
        self.pct = pct
        self.bar_color = bar_color
        self.bar_width = width
        self.height = 18

    def draw(self):
        c = self.canv
        label_w = 3.8*cm
        val_w   = 1.2*cm
        bar_w   = self.bar_width - label_w - val_w - 8
        y = 4

        c.setFont("Helvetica", 8)
        c.setFillColor(GRAY_D)
        c.drawString(0, y, self.label)

        bg_x = label_w + 4
        c.setFillColor(GRAY_L)
        c.roundRect(bg_x, y, bar_w, 6, 3, fill=1, stroke=0)

        fill_w = bar_w * (self.pct / 100)
        c.setFillColor(self.bar_color)
        c.roundRect(bg_x, y, fill_w, 6, 3, fill=1, stroke=0)

        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(BLACK)
        c.drawRightString(self.bar_width, y+1, f"{self.pct}%")

# ── Helper: SWOT card ───────────────────────────────────────────────────────
def swot_cell(title, items, bg, fg):
    content = [Paragraph(title, ParagraphStyle("sw", fontSize=8, textColor=fg, fontName="Helvetica-Bold", leading=11, spaceAfter=4))]
    for item in items:
        content.append(Paragraph(f"• {item}", ParagraphStyle("si", fontSize=7.5, textColor=fg, leading=11)))
    t = Table([[content]], colWidths=[7.8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), bg),
        ("TOPPADDING",(0,0),(-1,-1),8),
        ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),8),
        ("ROUNDEDCORNERS",[4,4,4,4]),
    ]))
    return t

def swot_grid(s_items, w_items, o_items, t_items):
    top = Table([
        [swot_cell("Strengths", s_items, GREEN_L, GREEN_D),
         swot_cell("Weaknesses", w_items, RED_L, RED_D)]
    ], colWidths=[8.0*cm, 8.0*cm], hAlign="LEFT")
    top.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    bot = Table([
        [swot_cell("Opportunities", o_items, BLUE_L, BLUE),
         swot_cell("Threats", t_items, AMBER_L, AMBER)]
    ], colWidths=[8.0*cm, 8.0*cm], hAlign="LEFT")
    bot.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return [top, Spacer(1,4), bot]

# ── Helper: two-col card ────────────────────────────────────────────────────
def two_col_card(left_title, left_items, right_title, right_items):
    def col(title, items, bg, fg):
        content = [Paragraph(title, ParagraphStyle("ct", fontSize=9, textColor=fg, fontName="Helvetica-Bold", leading=12, spaceAfter=5))]
        for item in items:
            content.append(Paragraph(f"→ {item}", ParagraphStyle("ci", fontSize=8, textColor=GRAY_D, leading=12)))
        t = Table([[content]], colWidths=[7.8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), bg),
            ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("ROUNDEDCORNERS",[4,4,4,4]),
        ]))
        return t
    row = Table([[
        col(left_title,  left_items,  TEAL_L,  TEAL),
        col(right_title, right_items, CORAL_L, CORAL_D),
    ]], colWidths=[8.0*cm, 8.0*cm])
    row.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return row

# ══════════════════════════════════════════════════════════════════════════════
# Build story
# ══════════════════════════════════════════════════════════════════════════════
story = []

# ── Cover header ────────────────────────────────────────────────────────────
cover_data = [[
    Paragraph("DMIT Consolidated Report", sTitle),
]]
cover = Table(cover_data, colWidths=[16*cm])
cover.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), NAVY),
    ("TOPPADDING",(0,0),(-1,-1),20),("BOTTOMPADDING",(0,0),(-1,-1),6),
    ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
    ("ROUNDEDCORNERS",[6,6,6,6]),
]))
story.append(cover)
story.append(Spacer(1,6))

sub_row = Table([[
    Paragraph("Gurupriya", ParagraphStyle("n", fontSize=16, textColor=NAVY, fontName="Helvetica-Bold", leading=18, alignment=TA_CENTER)),
]], colWidths=[16*cm])
story.append(sub_row)
story.append(Paragraph("Female · 24 yrs · DOB: 17-Apr-2001 · Sagara, Shivamogga, Karnataka", sSub))
story.append(Paragraph("Analyst: Aruna Prasad · Nanocare, Jayanagar, Bengaluru", sSub))
story.append(Spacer(1, 8))

badges = Table([[
    badge_table(["Female, 24 yrs"], BLUE_L, BLUE),
    badge_table(["Left Brain 55%"], TEAL_L, TEAL),
    badge_table(["Dove Personality"], AMBER_L, AMBER),
    badge_table(["Kinesthetic 40%"], CORAL_L, CORAL_D),
]], colWidths=[3.9*cm]*4)
badges.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4)]))
story.append(badges)
story.append(Spacer(1,4))
story.append(HR(GRAY_L, 1))

# ── Section 1: Overview ──────────────────────────────────────────────────────
story += SectionTitle("1. Overview — Key Scores")
story.append(metric_cards([
    ("55%",  "Brain dominance", "Left brain",  BLUE),
    ("13.8%","Top intelligence","Linguistics",  NAVY),
    ("40%",  "Learning style",  "Kinesthetic",  AMBER),
    ("205",  "TRC",             "Total ridge count", TEAL),
]))
story.append(Spacer(1,6))

# ── Section 2: Brain Dominance ───────────────────────────────────────────────
story += SectionTitle("2. Brain Dominance")
left_brain = Table([
    [Paragraph("Left Brain — 55.12%", ParagraphStyle("bl", fontSize=10, textColor=BLUE, fontName="Helvetica-Bold", leading=13))],
    [Paragraph("• Analytical & logical thinking", sCard)],
    [Paragraph("• Language, grammar & writing", sCard)],
    [Paragraph("• Planning & organisation", sCard)],
    [Paragraph("• Convergent thinker", sCard)],
    [Paragraph("• Controls emotions well", sCard)],
    [Paragraph("• Strong in academics", sCard)],
], colWidths=[7.4*cm])
right_brain = Table([
    [Paragraph("Right Brain — 44.88%", ParagraphStyle("br", fontSize=10, textColor=TEAL, fontName="Helvetica-Bold", leading=13))],
    [Paragraph("• Creative & emotional brain", sCard)],
    [Paragraph("• Imagination & music", sCard)],
    [Paragraph("• Interpersonal skills", sCard)],
    [Paragraph("• Divergent thinker", sCard)],
    [Paragraph("• Full of feelings & creativity", sCard)],
    [Paragraph("• Team building", sCard)],
], colWidths=[7.4*cm])
brain_data = [[left_brain, right_brain]]
brain_tbl = Table(brain_data, colWidths=[8.0*cm, 8.0*cm])
brain_tbl.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(0,0), BLUE_L),
    ("BACKGROUND",(1,0),(1,0), TEAL_L),
    ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
    ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8),
    ("ROUNDEDCORNERS",[4,4,4,4]),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story.append(brain_tbl)

# ── Section 3: Multiple Intelligences ────────────────────────────────────────
story += SectionTitle("3. Multiple Intelligences")
mi_data = [
    ("Linguistics (Verbal)",  13.8, BLUE),
    ("Kinesthetic (Bodily)",  13.7, TEAL),
    ("Logical (Mathematical)",13.0, NAVY),
    ("Musical",               12.9, AMBER),
    ("Naturalistic",          12.7, GREEN_D),
    ("Intrapersonal",         12.4, PURPLE_D),
    ("Visual-Spatial",        11.6, CORAL_D),
    ("Interpersonal",          9.9, GRAY_M),
]
mi_block = Table([[
    [ProgressBar(lbl, pct, col, width=15.6*cm)] for lbl, pct, col in mi_data
]], colWidths=[16*cm])
mi_block.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), WHITE),
    ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
]))

prog_rows = []
for lbl, pct, col in mi_data:
    prog_rows.append([ProgressBar(lbl, pct, col, width=15.6*cm)])
prog_tbl = Table(prog_rows, colWidths=[16*cm])
prog_tbl.setStyle(TableStyle([
    ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),0),
]))
story.append(prog_tbl)
story.append(Spacer(1,4))
story.append(Paragraph("The top 4 intelligences (Linguistics, Kinesthetic, Logical, Musical) are the dominant areas. Interpersonal at 9.9% is the area needing most improvement.", sSmall))

# ── Section 4: Personality Type ──────────────────────────────────────────────
story += SectionTitle("4. Personality Type")
pers_tbl = Table([[
    Table([
        [Paragraph("PRIMARY — DOVE", ParagraphStyle("pp", fontSize=9, textColor=BLUE, fontName="Helvetica-Bold", leading=11))],
        [Paragraph("People-oriented, loyal, friendly, hardworking and a great team player. Peaceful and cooperative. Tends to avoid confrontation and risk-taking. Motivated by cooperation and sincere appreciation.", sCard)],
        [Spacer(1,4)],
        [Paragraph("Strengths:", ParagraphStyle("ps", fontSize=8, textColor=BLUE, fontName="Helvetica-Bold"))],
        [Paragraph("Team oriented · Kind-hearted · Adaptable · Gentle · Good listener · Easy going", sCard)],
    ], colWidths=[7.4*cm]),
    Table([
        [Paragraph("SECONDARY — EAGLE", ParagraphStyle("se", fontSize=9, textColor=AMBER, fontName="Helvetica-Bold", leading=11))],
        [Paragraph("Bold, dominant, decisive and stimulated by challenge. Goal-oriented natural achiever. Can be blunt or stubborn under pressure. Fast-paced and results-driven.", sCard)],
        [Spacer(1,4)],
        [Paragraph("Note:", ParagraphStyle("sn", fontSize=8, textColor=AMBER, fontName="Helvetica-Bold"))],
        [Paragraph("Eagle traits emerge under pressure or leadership situations. Conflict can arise when paired with other Eagles.", sCard)],
    ], colWidths=[7.4*cm]),
]], colWidths=[8.0*cm, 8.0*cm])
pers_tbl.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(0,0), BLUE_L),
    ("BACKGROUND",(1,0),(1,0), AMBER_L),
    ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
    ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8),
    ("ROUNDEDCORNERS",[4,4,4,4]),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story.append(pers_tbl)
story.append(Spacer(1,6))

cap_tbl = Table([[
    Paragraph("Doing capability: 48.1%", sCard),
    Paragraph("Planning capability: 51.9%", sCard),
    Paragraph("Acquiring style: 80% Self-Cognitive", sCard),
]], colWidths=[5.3*cm, 5.3*cm, 5.4*cm])
cap_tbl.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), GRAY_L),
    ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
    ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),4),
    ("ROUNDEDCORNERS",[4,4,4,4]),
]))
story.append(cap_tbl)

# ── Section 5: SWOT ───────────────────────────────────────────────────────────
story += SectionTitle("5. SWOT Analysis")
story += swot_grid(
    ["Highly adjusting nature","Team oriented","Kind-hearted & supportive","Good listener","Adaptable & interactive","Likes stability"],
    ["Needs a role model","Lack of individualism","Easily affected by environment","Too wide range of interests","Feels insecure towards challenges","Can be exploited"],
    ["Excels in human capital ventures","Conducive for business environments","Best in conflict management"],
    ["Caring too much for others","May lose opportunities","Non risk-taking attitude","Indecisive during crisis"],
)

# ── Section 6: 4 Quotients ────────────────────────────────────────────────────
story += SectionTitle("6. Four Quotients")
story.append(metric_cards([
    ("26.8%","IQ","Intelligence",  BLUE),
    ("22.3%","EQ","Emotional",     RED_D),
    ("26.4%","AQ","Adversity",     GREEN_D),
    ("24.5%","CQ","Creativity",    AMBER),
]))
story.append(Spacer(1,4))
story.append(Paragraph("EQ at 22.3% is the lowest quotient. Strengthening emotional intelligence will be key for personal and professional growth.", sSmall))

# ── Section 7: Learning Styles ────────────────────────────────────────────────
story += SectionTitle("7. Learning Styles")
learn_tbl = Table([[
    Table([
        [Paragraph("40%", ParagraphStyle("lv", fontSize=22, textColor=AMBER, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=24))],
        [Paragraph("Kinesthetic Learner", ParagraphStyle("ln", fontSize=9, textColor=AMBER, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=11))],
        [Paragraph("Learns by doing, hands-on activity and physical involvement.", ParagraphStyle("ld", fontSize=7.5, textColor=GRAY_D, alignment=TA_CENTER, leading=11))],
    ], colWidths=[4.8*cm]),
    Table([
        [Paragraph("33%", ParagraphStyle("lv2", fontSize=22, textColor=TEAL, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=24))],
        [Paragraph("Auditory Learner", ParagraphStyle("ln2", fontSize=9, textColor=TEAL, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=11))],
        [Paragraph("Learns by listening, discussion and verbal instructions.", ParagraphStyle("ld2", fontSize=7.5, textColor=GRAY_D, alignment=TA_CENTER, leading=11))],
    ], colWidths=[4.8*cm]),
    Table([
        [Paragraph("27%", ParagraphStyle("lv3", fontSize=22, textColor=BLUE, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=24))],
        [Paragraph("Visual Learner", ParagraphStyle("ln3", fontSize=9, textColor=BLUE, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=11))],
        [Paragraph("Learns by seeing diagrams, charts and demonstrations.", ParagraphStyle("ld3", fontSize=7.5, textColor=GRAY_D, alignment=TA_CENTER, leading=11))],
    ], colWidths=[4.8*cm]),
]], colWidths=[5.3*cm]*3)
learn_tbl.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(0,0), AMBER_L),
    ("BACKGROUND",(1,0),(1,0), TEAL_L),
    ("BACKGROUND",(2,0),(2,0), BLUE_L),
    ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
    ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
    ("ROUNDEDCORNERS",[4,4,4,4]),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story.append(learn_tbl)
story.append(Spacer(1,6))
tips = Table([[
    Paragraph("Study tips for Gurupriya:", ParagraphStyle("st", fontSize=8, textColor=GRAY_D, fontName="Helvetica-Bold", leading=11)),
    Paragraph("Study in 20-min intervals · use flashcards while walking · hands-on practice over reading · role-play exam scenarios · best test: short definitions & fill-ins · avoid: long essays", sCard),
]], colWidths=[3.5*cm, 12.5*cm])
tips.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), GRAY_L),
    ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
    ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
    ("ROUNDEDCORNERS",[4,4,4,4]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
]))
story.append(tips)

# ── Section 8: Brain Lobes ────────────────────────────────────────────────────
story += SectionTitle("8. Brain Lobe Activity")
lobe_data = [
    ("Parietal lobe — Senses, Touch, Language", 24.4, TEAL),
    ("Temporal lobe — Hearing, Memory, Emotion",20.5, BLUE),
    ("Frontal lobe — Emotions, Reasoning, Planning", 20.0, PURPLE_D),
    ("Pre-Frontal lobe — Execution & Personality", 18.5, CORAL_D),
    ("Occipital lobe — Vision & Object Recognition", 16.6, AMBER),
]
lobe_rows = []
for lbl, pct, col in lobe_data:
    lobe_rows.append([ProgressBar(lbl, pct, col, width=15.6*cm)])
lobe_tbl = Table(lobe_rows, colWidths=[16*cm])
lobe_tbl.setStyle(TableStyle([
    ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),0),
]))
story.append(lobe_tbl)

# ── Section 9: Career Recommendations ─────────────────────────────────────────
story += SectionTitle("9. Recommended Career Fields")
career_data = [
    ("Medical ★★★★",      "Doctor, Pharmacist, Surgeon,\nMedical Officer, Nutritionist"),
    ("Financial ★★★★",    "CA, Finance Officer, Tax Consultant,\nInvestment Banker, Business Analyst"),
    ("Life Sciences ★★★★","Biotechnology, Pathology Researcher,\nBotanist, Zoologist, Med Lab Technician"),
    ("Mass Media ★★★★",   "Reporter, Speaker, PR Officer,\nEditor, Script Writer, Advertising"),
    ("Agriculture ★★★★",  "Agricultural Engineer, Forest Officer,\nFood Analyst, Veterinary, Nursery Owner"),
    ("Sports ★★★★",       "Cricketer, Footballer, Swimmer,\nYoga Teacher, Gym Owner, Sports Coach"),
    ("Education ★★★",     "Professor, Career Counselor,\nLife Coach, School Teacher, Principal"),
    ("IT ★★★",            "Software Engineer, Web Developer,\nMultimedia Specialist, Network Engineer"),
]
career_rows = []
for i in range(0, len(career_data), 2):
    left = career_data[i]
    right = career_data[i+1] if i+1 < len(career_data) else ("","")
    def make_cell(title, roles):
        return Table([
            [Paragraph(title, ParagraphStyle("ct", fontSize=8, textColor=NAVY, fontName="Helvetica-Bold", leading=11))],
            [Paragraph(roles, ParagraphStyle("cr", fontSize=7.5, textColor=GRAY_D, leading=11))],
        ], colWidths=[7.4*cm])
    row_tbl = Table([[make_cell(*left), make_cell(*right)]], colWidths=[8.0*cm, 8.0*cm])
    row_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,0), BLUE_L),("BACKGROUND",(1,0),(1,0), GRAY_L),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("ROUNDEDCORNERS",[4,4,4,4]),("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    career_rows.append(row_tbl)
    career_rows.append(Spacer(1,4))
for cr in career_rows:
    story.append(cr)

# ── Section 10: Subjects & Activities ────────────────────────────────────────
story += SectionTitle("10. Recommended Subjects")
subj_hi  = ["Accounting","Visual Arts","Biology","Chemistry","Mathematics","Commerce","Finance","Law"]
subj_med = ["English","History","Sanskrit","French","Journalism","Economics","Computers"]

def tag_row(items, bg, fg):
    cells = []
    for item in items:
        cells.append(Paragraph(item, ParagraphStyle("tg", fontSize=7.5, textColor=fg, alignment=TA_CENTER, leading=10)))
    t = Table([cells], colWidths=[2.1*cm]*len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), bg),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("ROUNDEDCORNERS",[4,4,4,4]),
        ("GRID",(0,0),(-1,-1),0,WHITE),
    ]))
    return t

story.append(Paragraph("Highest suitability (score 11):", sSmall))
story.append(tag_row(subj_hi, BLUE_L, BLUE))
story.append(Spacer(1,4))
story.append(Paragraph("Good fit (score 9):", sSmall))
story.append(tag_row(subj_med, TEAL_L, TEAL))
story.append(Spacer(1,8))

story += SectionTitle("11. Recommended Activities & Hobbies")
act_hi  = ["Cycling","Trekking","Outdoor Games","Musical","Cookery","Calligraphy","Aerobics"]
act_med = ["Drawing/Painting","Dramatics","Debate","Dance","Diary Writing","Computers"]
story.append(Paragraph("Highest suitability (score 11):", sSmall))
story.append(tag_row(act_hi, AMBER_L, AMBER))
story.append(Spacer(1,4))
story.append(Paragraph("Good fit (score 9):", sSmall))
story.append(tag_row(act_med, CORAL_L, CORAL_D))
story.append(Spacer(1,8))

# ── Section 12: Development Suggestions ──────────────────────────────────────
story += SectionTitle("12. Key Development Suggestions")
story.append(two_col_card(
    "Build your strengths",
    [
        "Embrace team leadership in HR, planning or marketing",
        "Develop linguistic skills through debate and writing",
        "Pursue music or nature-related hobbies actively",
        "Use kinesthetic study methods — move while learning",
        "Leverage your planning capability (51.9%) in structured roles",
    ],
    "Work on challenges",
    [
        "Build assertiveness — practise saying no when needed",
        "Strengthen EQ through daily active listening exercises",
        "Find a mentor or role model for career direction",
        "Practise decision-making under pressure scenarios",
        "Avoid over-accommodating at the cost of your own goals",
    ],
))

# ── Footer ────────────────────────────────────────────────────────────────────
story.append(Spacer(1,14))
story.append(HR(GRAY_L, 0.5))
story.append(Paragraph(
    "Source: Kadamba Nanocare DMIT Report · Analyst: Aruna Prasad · Nanocare, 1st Floor, 10th Main Road, 4th Block, Jayanagar, Bengaluru 560011 · "
    "Disclaimer: Results are for reference only based on ongoing scientific research. Consult a certified analyst for interpretation.",
    ParagraphStyle("foot", fontSize=6.5, textColor=GRAY_M, alignment=TA_CENTER, leading=9)
))

# ── Build ─────────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    "/mnt/user-data/outputs/Gurupriya_DMIT_Report.pdf",
    pagesize=A4,
    leftMargin=1.8*cm, rightMargin=1.8*cm,
    topMargin=1.5*cm, bottomMargin=1.5*cm,
    title="DMIT Consolidated Report — Gurupriya",
    author="Kadamba Nanocare",
)
doc.build(story)
print("PDF created successfully.")