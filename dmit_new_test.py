from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)

W, H = A4

# ── Palette ────────────────────────────────────────────────────────────────
PSY_D  = colors.HexColor("#0C447C")
PSY_M  = colors.HexColor("#185FA5")
PSY_L  = colors.HexColor("#E6F1FB")
PSY_B  = colors.HexColor("#B5D4F4")

EMO_D  = colors.HexColor("#791F1F")
EMO_M  = colors.HexColor("#A32D2D")
EMO_L  = colors.HexColor("#FCEBEB")
EMO_B  = colors.HexColor("#F7C1C1")

SPI_D  = colors.HexColor("#27500A")
SPI_M  = colors.HexColor("#3B6D11")
SPI_L  = colors.HexColor("#EAF3DE")
SPI_B  = colors.HexColor("#C0DD97")

PHY_D  = colors.HexColor("#633806")
PHY_M  = colors.HexColor("#854F0B")
PHY_L  = colors.HexColor("#FAEEDA")
PHY_B  = colors.HexColor("#FAC775")

GRAY_L = colors.HexColor("#F5F5F3")
GRAY_M = colors.HexColor("#888780")
GRAY_D = colors.HexColor("#444441")
WHITE  = colors.white
BLACK  = colors.HexColor("#1A1A1A")
NAVY   = colors.HexColor("#1B3A6B")

CW = 16.8*cm   # content width

# ── Styles ─────────────────────────────────────────────────────────────────
def S(name, **kw): return ParagraphStyle(name, **kw)

sParamN = S("pN", fontName="Helvetica-Bold", fontSize=8.5, textColor=BLACK,   leading=12)
sParamD = S("pD", fontName="Helvetica",      fontSize=8,   textColor=GRAY_D,  leading=12)
sGrpLbl = S("gL", fontName="Helvetica-Bold", fontSize=8,   textColor=GRAY_M,  leading=11)
sSmall  = S("sm", fontName="Helvetica",       fontSize=7.5, textColor=GRAY_M,  leading=10, alignment=TA_CENTER)
sInsight= S("ins",fontName="Helvetica",       fontSize=8.5, textColor=GRAY_D,  leading=14)

# ── Reusable helpers ────────────────────────────────────────────────────────
def HR(c=GRAY_L, t=0.5):
    return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=4, spaceBefore=4)

def sp(h=4): return Spacer(1, h)

# ── Domain header (full-width coloured band) ───────────────────────────────
def domain_header(number, title, subtitle, hdr_bg, sub_color):
    num_style = S(f"dn{number}", fontName="Helvetica-Bold", fontSize=28,
                  textColor=colors.HexColor("#FFFFFF"), leading=32, alignment=TA_CENTER)
    ttl_style = S(f"dt{number}", fontName="Helvetica-Bold", fontSize=15,
                  textColor=WHITE, leading=18)
    sub_style = S(f"ds{number}", fontName="Helvetica", fontSize=9,
                  textColor=sub_color, leading=12)
    num_cell = Table([[Paragraph(number, num_style)]], colWidths=[1.6*cm])
    num_cell.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    txt_cell = Table([
        [Paragraph(title, ttl_style)],
        [Paragraph(subtitle, sub_style)],
    ], colWidths=[14.8*cm])
    txt_cell.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),2),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    hdr = Table([[num_cell, txt_cell]], colWidths=[1.8*cm, 15.0*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), hdr_bg),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),12), ("BOTTOMPADDING",(0,0),(-1,-1),12),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("ROUNDEDCORNERS",[6,6,0,0]),
    ]))
    return hdr

# ── Group header bar ────────────────────────────────────────────────────────
def grp_hdr(text, bg, fg):
    t = Table([[Paragraph(text.upper(), S(f"g_{text[:6]}",
               fontName="Helvetica-Bold", fontSize=7.5, textColor=fg, leading=10))]],
              colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), bg),
        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
    ]))
    return t

# ── Single parameter row ────────────────────────────────────────────────────
def param(name, desc, badge, badge_bg, badge_fg, dot_color, alt_bg):
    # dot
    dot = Table([[""]], colWidths=[0.28*cm], rowHeights=[0.28*cm])
    dot.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), dot_color),
        ("ROUNDEDCORNERS",[3,3,3,3]),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    # text
    avail = 13.4*cm if badge else 14.8*cm
    txt = Table([
        [Paragraph(name, sParamN)],
        [Paragraph(desc, sParamD)],
    ], colWidths=[avail])
    txt.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    cells = [dot, txt]
    cw    = [0.45*cm, avail + 0.5*cm]
    if badge:
        bdg = Table([[Paragraph(badge, S(f"b_{name[:6]}",
                     fontName="Helvetica-Bold", fontSize=7.5,
                     textColor=badge_fg, alignment=TA_CENTER, leading=10))]],
                    colWidths=[1.8*cm])
        bdg.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), badge_bg),
            ("ROUNDEDCORNERS",[4,4,4,4]),
            ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ]))
        cells.append(bdg)
        cw.append(1.9*cm)

    row = Table([cells], colWidths=cw)
    row.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    wrapper = Table([[row]], colWidths=[CW])
    wrapper.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), alt_bg),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8),
    ]))
    return wrapper

# ── Domain builder ──────────────────────────────────────────────────────────
def build_domain(number, title, subtitle, hdr_bg, sub_color,
                 grp_bg, grp_fg, dot_color, badge_bg, badge_fg, groups):
    """groups = list of (group_label, [(name, desc, badge), ...])"""
    items = [domain_header(number, title, subtitle, hdr_bg, sub_color)]

    # outer border wrapper using a large Table — we'll avoid this
    # Instead build individual rows inside a domain container table
    body_rows = []
    for g_idx, (g_label, params_list) in enumerate(groups):
        body_rows.append([grp_hdr(g_label, grp_bg, grp_fg)])
        body_rows.append([sp(2)])
        for i, (nm, desc, bdg) in enumerate(params_list):
            alt = GRAY_L if i % 2 == 0 else WHITE
            body_rows.append([param(nm, desc, bdg, badge_bg, badge_fg, dot_color, alt)])
        body_rows.append([sp(6)])

    body_tbl = Table(body_rows, colWidths=[CW])
    body_tbl.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))

    body_wrap = Table([[body_tbl]], colWidths=[CW])
    body_wrap.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("BOX",(0,0),(-1,-1), 0.5, grp_bg),
        ("ROUNDEDCORNERS",[0,0,6,6]),
    ]))

    items.append(body_wrap)
    return items


# ══════════════════════════════════════════════════════════════════════════
# STORY
# ══════════════════════════════════════════════════════════════════════════
story = []

# ── Cover header ──────────────────────────────────────────────────────────
cover = Table([
    [Paragraph("Four-Domain Analysis", S("ct", fontName="Helvetica-Bold",
               fontSize=22, textColor=WHITE, leading=26, alignment=TA_CENTER))],
    [Paragraph("Gurupriya  ·  DMIT Report  ·  Kadamba Nanocare",
               S("cs", fontName="Helvetica", fontSize=10,
                 textColor=colors.HexColor("#AABCCE"), leading=14, alignment=TA_CENTER))],
    [Paragraph("Psychological  ·  Emotional  ·  Spiritual  ·  Physical",
               S("cd", fontName="Helvetica", fontSize=9,
                 textColor=colors.HexColor("#AABCCE"), leading=12, alignment=TA_CENTER))],
], colWidths=[CW])
cover.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), NAVY),
    ("TOPPADDING",(0,0),(-1,-1),18),("BOTTOMPADDING",(0,0),(-1,-1),14),
    ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
    ("ROUNDEDCORNERS",[6,6,6,6]),
]))
story.append(cover)
story.append(sp(12))

# ── Quick summary bar ──────────────────────────────────────────────────────
def sum_cell(lbl, val, note, vc):
    t = Table([
        [Paragraph(lbl, S(f"sl{lbl}", fontName="Helvetica-Bold", fontSize=7,
                           textColor=GRAY_M, leading=9))],
        [Paragraph(val, S(f"sv{lbl}", fontName="Helvetica-Bold", fontSize=12,
                           textColor=vc, leading=15))],
        [Paragraph(note, S(f"sn{lbl}", fontName="Helvetica", fontSize=7.5,
                            textColor=GRAY_D, leading=11))],
    ], colWidths=[4.0*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), GRAY_L),
        ("ROUNDEDCORNERS",[4,4,4,4]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),6),
    ]))
    return t

srow = Table([[
    sum_cell("PSYCHOLOGICAL", "Strong",
             "IQ 26.8%  ·  Left brain 55%\nLinguistics top MI", PSY_M),
    sum_cell("EMOTIONAL", "Needs work",
             "EQ 22.3% lowest quotient\nInterpersonal only 9.9%", EMO_M),
    sum_cell("SPIRITUAL", "Moderate-strong",
             "AQ 26.4%  ·  Naturalistic 12.7%\nStrong values & resilience", SPI_M),
    sum_cell("PHYSICAL", "Strong",
             "Kinesthetic 13.7% top MI\nParietal lobe 24.39%", PHY_M),
]], colWidths=[4.25*cm]*4)
srow.setStyle(TableStyle([
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),5),
    ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
]))
story.append(srow)
story.append(sp(16))
story.append(HR(GRAY_M, 0.5))
story.append(sp(10))

# ══════════════════════════════════════════════════════════════════════════
# DOMAIN 1 — PSYCHOLOGICAL
# ══════════════════════════════════════════════════════════════════════════
story += build_domain(
    "1", "Psychological", "Cognition  ·  Reasoning  ·  Intelligence  ·  Learning",
    PSY_M, colors.HexColor("#AAC8E8"),
    PSY_L, PSY_D, PSY_M, PSY_L, PSY_D,
    [
        ("Brain & Intelligence", [
            ("Left brain dominance",
             "Analytical, logical, convergent thinker. Controls language, planning and organisation.", "55.12%"),
            ("Linguistics intelligence",
             "Highest multiple intelligence. Strong verbal memory, reading, writing, communication.", "13.8%"),
            ("Logical / mathematical intelligence",
             "Abstract reasoning, cause-effect thinking, pattern recognition and analytical processing.", "13.0%"),
            ("Visual-spatial intelligence",
             "Visualization, spatial judgment, 3D recognition and idea formation.", "11.6%"),
            ("Intrapersonal intelligence",
             "Self-awareness, understanding own strengths and weaknesses, high perfectionism.", "12.4%"),
            ("Intelligence quotient (IQ)",
             "Reasoning, observation, memory, imagination and problem-solving capacity.", "26.8%"),
        ]),
        ("Learning & Planning", [
            ("Auditory learning style",
             "Learns by listening; benefits from discussions, lectures and verbal instruction.", "33%"),
            ("Visual learning style",
             "Strong visual associations; benefits from charts, diagrams and demonstrations.", "27%"),
            ("Planning capability",
             "Concept-driven — thinks first then acts. Highly logical and cautious planner.", "51.9%"),
            ("Acquiring style — self-cognitive",
             "Independent, goal-oriented, target centric, self-starter, confident and inflexible.", "80%"),
        ]),
        ("Brain Lobes — Cognitive", [
            ("Frontal lobe",
             "Reasoning, planning, creativity, judgment and parts of speech. Key for academic performance.", "20.0%"),
            ("Pre-frontal lobe",
             "Execution, cognitive function and personality formation. Controls self-achievement.", "18.54%"),
        ]),
        ("Management Aptitude", [
            ("Analytical skills",
             "Strong logical analysis; well-suited for research and data-intensive roles.", "Score 9"),
            ("Decision-making abilities",
             "Good structured decision-making; tends to struggle when under sudden, unexpected pressure.", "Score 9"),
            ("Strategic planning",
             "Moderate long-horizon planning; benefits from methodical and structured frameworks.", "Score 7"),
            ("Critical observation",
             "Good perceptual and detail-spotting ability in structured environments.", "Score 7"),
            ("Creative approach",
             "Moderate creative thinking; best when creative tasks are grounded in logic.", "Score 7"),
        ]),
    ]
)

story.append(sp(14))

# ══════════════════════════════════════════════════════════════════════════
# DOMAIN 2 — EMOTIONAL
# ══════════════════════════════════════════════════════════════════════════
story += build_domain(
    "2", "Emotional", "Feelings  ·  Relationships  ·  Empathy  ·  Social dynamics",
    EMO_M, colors.HexColor("#F5AAAA"),
    EMO_L, EMO_D, EMO_M, EMO_L, EMO_D,
    [
        ("Emotional Intelligence", [
            ("Emotional quotient (EQ)",
             "Lowest of all four quotients. Covers managing emotions, interpersonal skills and connecting with self and others.", "22.3%"),
            ("Interpersonal intelligence",
             "Weakest multiple intelligence. Understanding others' moods, empathy, cooperation and team-based learning.", "9.9%"),
            ("Temporal lobe activity",
             "Covers hearing, memory, emotion, language and learning. Key centre for emotional processing.", "20.49%"),
            ("Emotions & feelings — neuron",
             "Right auditory neuron — sensitivity to music, voice, emotional processing and feelings.", "10.2%"),
        ]),
        ("Personality & Behaviour", [
            ("Dove personality — primary",
             "People-oriented, loyal, kind-hearted, good listener, great team player and naturally peaceful.", "Primary"),
            ("Eagle personality — secondary",
             "Goal-oriented, decisive and bold. Emerges under leadership situations or emotional pressure.", "Secondary"),
            ("Affective acquiring style",
             "Patient, supportive, calm, relationship-oriented; needs motivation and encouragement to act.", "10%"),
            ("Motivation source",
             "Motivated by cooperation, opportunities to help others and sincere appreciation from peers.", ""),
        ]),
        ("Emotional SWOT", [
            ("Emotional strengths",
             "Kind-hearted, gentle, good listener, highly supportive, interactive and naturally team-oriented.", ""),
            ("Emotional challenges",
             "Easily affected by environment, possessive-dependent, impulsive and indecisive during crises.", ""),
            ("Emotional threats",
             "Caring too much for others may lead to ignoring own needs, losing opportunities and non-risk-taking.", ""),
        ]),
        ("Social & Relationship", [
            ("Communication skill",
             "Highest management score overall — natural communicator and relationship builder.", "Score 11"),
            ("Teamwork",
             "Cooperative and collaborative; follows plans well as part of a team but not necessarily alone.", "Score 7"),
            ("RIASEC — social orientation",
             "Highest latent success score — conveying understanding of others and building personal relationships.", "23.55%"),
            ("Goals — group acceptance",
             "Motivated by cooperation, sincere appreciation and a strong sense of belonging.", ""),
            ("HR & marketing suitability",
             "Department scoring reflects high suitability for people-facing and collaborative roles.", "Score 9"),
        ]),
    ]
)

story.append(sp(14))

# ══════════════════════════════════════════════════════════════════════════
# DOMAIN 3 — SPIRITUAL
# ══════════════════════════════════════════════════════════════════════════
story += build_domain(
    "3", "Spiritual", "Values  ·  Purpose  ·  Inner self  ·  Nature connection",
    SPI_M, colors.HexColor("#A8D880"),
    SPI_L, SPI_D, SPI_M, SPI_L, SPI_D,
    [
        ("Nature & Observation Intelligence", [
            ("Naturalistic intelligence",
             "Keen observation of the natural world, affinity for flora and fauna, ability to classify living things.", "12.7%"),
            ("Nature love — neuron",
             "Visual identification, observation skills and deep nature awareness encoded in neural fingerprint patterns.", "WDL level"),
            ("Affinity to flora & fauna",
             "Right naturalistic neuron — spatial relations combined with profound affinity for the natural world.", "12.7%"),
            ("Naturalistic hobbies",
             "High interest in zoos, forests, aquariums; loves reading about animals, plants and astronomy.", ""),
        ]),
        ("Inner Self & Self-Reflection", [
            ("Intrapersonal intelligence",
             "Self-reflection, understanding life's purpose, strong values, high will-power and strong self-esteem.", "12.4%"),
            ("Motivation & emotional behaviour",
             "Deep inner motivation driven by values of loyalty, helping others and maintaining personal security.", ""),
            ("Core values",
             "Loyalty, helping others, security, stability, group acceptance and personal accomplishment.", ""),
            ("Initiative & judgement reasoning",
             "Inner planning tendency — ponders life's major questions and problems before taking action.", ""),
            ("Self-esteem",
             "High self-esteem; understands own value and is able to learn and grow from success and failure.", ""),
        ]),
        ("Resilience & Inner Strength", [
            ("Adversity quotient (AQ)",
             "Ability to face tough situations, handle challenges and maintain resilience under sustained pressure.", "26.4%"),
            ("Stability orientation",
             "Seeks controlled, predictable environments; finds inner peace and energy through routine and order.", ""),
            ("Conflict management",
             "Best at handling conflict management situations — a natural peacemaker and mediator by inclination.", ""),
            ("Introspective temperament",
             "Tends toward solitude for reflection; prefers quiet thinking over impulsive or reactive responses.", ""),
        ]),
        ("Meaning-Oriented Activities", [
            ("Trekking & outdoor activities",
             "Score 11 (highest) — nature immersion is a primary source of meaning, energy and restoration.", "Score 11"),
            ("Bird watching & gardening",
             "Strong affinity — directly connects the spiritual domain with naturalistic intelligence.", "Score 9"),
            ("Diary writing & journalling",
             "Self-reflection practice — recording thoughts, dreams, goals and processing emotional experiences.", "Score 9"),
            ("Career: counsellor / life coach",
             "Naturalistic and Intrapersonal alignment suggests deep suitability for meaning-driven human roles.", ""),
        ]),
    ]
)

story.append(sp(14))

# ══════════════════════════════════════════════════════════════════════════
# DOMAIN 4 — PHYSICAL
# ══════════════════════════════════════════════════════════════════════════
story += build_domain(
    "4", "Physical", "Body  ·  Movement  ·  Motor skills  ·  Sensory processing",
    PHY_M, colors.HexColor("#F5C880"),
    PHY_L, PHY_D, PHY_M, PHY_L, PHY_D,
    [
        ("Kinesthetic & Motor Intelligence", [
            ("Bodily-kinesthetic intelligence",
             "Top physical MI. Movement, hands-on activity, body memory and full muscle coordination.", "13.7%"),
            ("Kinesthetic learning — dominant",
             "Learns best through physical doing, touching, trial-and-error and practical hands-on experience.", "40%"),
            ("Gross motor skills",
             "Body movements, coordination, outdoor activities and sports. Highest tactile neuron score.", "12.7%"),
            ("Fine motor skills",
             "Action identification, hand control, precise finger skills and fine manual movements.", "11.7%"),
            ("Sensory integration",
             "Integration of physical senses for body awareness, balance and physical responsiveness.", "6.9%"),
        ]),
        ("Brain Lobes — Physical & Sensory", [
            ("Parietal lobe",
             "Highest brain lobe score. Governs senses, touch, pain, temperature and language functions.", "24.39%"),
            ("Occipital lobe",
             "Object recognition and vision — supports physical navigation and spatial awareness.", "16.59%"),
        ]),
        ("Physical Creative Expression", [
            ("Musical intelligence",
             "Rhythm, movement and pitch — bridges physical and creative expression through bodily awareness.", "12.9%"),
            ("Creativity quotient (CQ)",
             "Physical creativity; painting, dance and body-based artistic expression and performance.", "24.5%"),
            ("Energy level / drive",
             "High physical drive and stamina — sustained effort for demanding physical activities.", "Score 9"),
            ("Doing capability",
             "Object-driven model — determined, constructive, hands-on action taker and builder.", "48.1%"),
            ("Quality adherence",
             "High standards for physical tasks — meticulous in hands-on execution and craft.", "Score 9"),
        ]),
        ("Recommended Physical Activities", [
            ("Cycling · Trekking · Outdoor games · Aerobics",
             "All score 11 (highest possible) — perfectly aligned with physical domain strengths.", "Score 11"),
            ("Dance · Dramatics",
             "Physical body expression — connects bodily movement with emotional and musical intelligence.", "Score 9"),
            ("Calligraphy",
             "Fine motor expression — highest score; brings physical precision into artistic form.", "Score 11"),
            ("Career: Sports · Medical · Agriculture",
             "All 4-star feasibility — fields requiring physical skill, bodily intelligence and stamina.", ""),
        ]),
    ]
)

story.append(sp(16))
story.append(HR(GRAY_M, 0.5))
story.append(sp(8))

# ── Key Insight ────────────────────────────────────────────────────────────
insight_content = (
    "<b>Key insight across all four domains:</b>   Gurupriya is most naturally "
    "powerful in the <b>Psychological</b> and <b>Physical</b> domains — she thinks "
    "analytically and learns by doing. Her <b>Spiritual</b> domain is a quiet but "
    "solid strength, grounded in nature, inner values and resilience (AQ 26.4%). "
    "The <b>Emotional</b> domain is the clear gap — EQ at 22.3% (lowest quotient) "
    "and Interpersonal intelligence at just 9.9% (weakest MI) suggest that while "
    "she is naturally kind-hearted (Dove personality), she may struggle to manage "
    "complex interpersonal dynamics or emotionally charged situations. "
    "<b>Developing EQ is the single highest-leverage growth area across all four domains</b>, "
    "and will unlock the full potential of her strong Psychological and Physical foundations."
)
insight_box = Table([[Paragraph(insight_content, sInsight)]], colWidths=[CW])
insight_box.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1), GRAY_L),
    ("ROUNDEDCORNERS",[6,6,6,6]),
    ("TOPPADDING",(0,0),(-1,-1),12), ("BOTTOMPADDING",(0,0),(-1,-1),12),
    ("LEFTPADDING",(0,0),(-1,-1),16), ("RIGHTPADDING",(0,0),(-1,-1),16),
    ("LINEAFTER", (0,0),(0,-1), 4, NAVY),
]))
story.append(insight_box)
story.append(sp(12))

# ── Footer ─────────────────────────────────────────────────────────────────
story.append(HR(GRAY_L, 0.5))
story.append(Paragraph(
    "Source: Kadamba Nanocare DMIT Report  ·  Analyst: Aruna Prasad  ·  "
    "Nanocare, 1st Floor, 10th Main Road, 4th Block, Jayanagar, Bengaluru 560011  ·  "
    "Disclaimer: Results are for reference only based on ongoing scientific research. "
    "Consult a certified analyst for full interpretation.",
    S("foot", fontName="Helvetica", fontSize=6.5, textColor=GRAY_M,
      alignment=TA_CENTER, leading=9)
))

# ── Build ──────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    "Gurupriya_FourDomain_Analysis.pdf",
    pagesize=A4,
    leftMargin=1.6*cm, rightMargin=1.6*cm,
    topMargin=1.4*cm,  bottomMargin=1.4*cm,
    title="Four-Domain Analysis — Gurupriya",
    author="Kadamba Nanocare / DMIT",
)
doc.build(story)
print("PDF created successfully.")