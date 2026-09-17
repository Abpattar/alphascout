#!/usr/bin/env python3
"""
AlphaScout Report Generator - Complete
Populates the internship report template with actual project content.
"""
import docx
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from datetime import datetime
from pathlib import Path

TEMPLATE_PATH = Path("/home/neo/Codes/alphascout/CSS7000_INTERNSHIP REPORT TEMPLATE 17.7.26 (1).docx")
OUTPUT_PATH = Path("/home/neo/Codes/alphascout/Alpha_Scout_Final_Report.docx")

# Student/Project Information
STUDENT_NAME = "Aditya B Pattar"
USN = "20241CIT0115"
GUIDE_NAME = "Francis Annareddy"
ACADEMIC_YEAR = "2026-27 ODD SEMESTER"
SEMESTER = "V Semester"
COMPANY = "Presidency University"
DEPARTMENT = "School of Computer Science and Engineering"
PROGRAM = "CIT-Computer Science & Engineering (Internet of Things)"
PROJECT_TITLE = "AlphaScout v1.0: Multi-Sector Small-Cap News to Trade Signal Bot for Indian Markets"
SUBMISSION_DATE = "AUGUST 2026"
HOD_NAME = "Dr. Anandaraj S.P"
DEAN_NAME = "Dr. Shakkeera L"
COORDINATOR_NAME = "Dr. Geetha Arjunan"
GITHUB_LINK = "https://github.com/Abpattar/alphascout"

def set_cell_shading(cell, color):
    shading_elm = OxmlElement('w:shd')
    shading_elm.set(qn('w:fill'), color)
    shading_elm.set(qn('w:val'), 'clear')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def clear_paragraph(p):
    for run in p.runs:
        run.text = ""

def replace_placeholder_text(doc, old_text, new_text):
    """Robust paragraph-level replacement handling multi-run text."""
    for p in doc.paragraphs:
        full = ''.join(run.text for run in p.runs)
        if old_text in full:
            first = p.runs[0] if p.runs else p.add_run('')
            first.text = full.replace(old_text, new_text)
            for run in p.runs[1:]:
                run.text = ''
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    full = ''.join(run.text for run in p.runs)
                    if old_text in full:
                        first = p.runs[0] if p.runs else p.add_run('')
                        first.text = full.replace(old_text, new_text)
                        for run in p.runs[1:]:
                            run.text = ''

# ============ CONTENT BUILDING HELPERS ============

def add_body(doc, text):
    """Add a body paragraph: Times New Roman 12, justified, 1.5 spacing."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.5
    return p

def add_body_bold(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    run.font.bold = True
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.5
    return p

_bullet_counter = [0]
def add_bullet(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run("\u2022  " + text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.left_indent = Inches(0.4)
    return p

_number_counter = [0]
def reset_numbers():
    _number_counter[0] = 0

reset_numbers()
def add_numbered(doc, text):
    _number_counter[0] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(f"{_number_counter[0]}.  " + text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.left_indent = Inches(0.4)
    return p

def add_h1(doc, text):
    h = doc.add_heading(text, level=1)
    for run in h.runs:
        run.font.name = 'Times New Roman'
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.font.size = Pt(16)
    h.paragraph_format.space_before = Pt(18)
    h.paragraph_format.space_after = Pt(10)
    return h

def add_h2(doc, text):
    h = doc.add_heading(text, level=2)
    for run in h.runs:
        run.font.name = 'Times New Roman'
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.font.size = Pt(14)
    h.paragraph_format.space_before = Pt(14)
    h.paragraph_format.space_after = Pt(8)
    return h

def add_h3(doc, text):
    h = doc.add_heading(text, level=3)
    for run in h.runs:
        run.font.name = 'Times New Roman'
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.font.size = Pt(12)
    h.paragraph_format.space_before = Pt(10)
    h.paragraph_format.space_after = Pt(6)
    return h

def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(11)
    run.font.bold = True
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    return p

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header row
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(11)
        run.font.bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cell_shading(cell, 'D9E2F3')
    # Data rows
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.text = ''
            p = cell.paragraphs[0]
            run = p.add_run(str(val))
            run.font.name = 'Times New Roman'
            run.font.size = Pt(10.5)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if col_widths:
        for j, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[j].width = Inches(w)
    # Add spacing after table
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)
    return table

# ============ LOAD TEMPLATE ============
doc = docx.Document(TEMPLATE_PATH)

# ============ 1. TITLE PAGE ============
replace_placeholder_text(doc, "XYZ - 20221CSE0123", f"{STUDENT_NAME} - {USN}")
replace_placeholder_text(doc, "Dr./Mr./Ms. IJKL", f"Mr. {GUIDE_NAME}")
replace_placeholder_text(doc, "COMPUTER SCIENCE AND ENGINEERING (Cyber Security)", "COMPUTER SCIENCE AND ENGINEERING (Internet of Things)")
replace_placeholder_text(doc, "AUGUST 2026", SUBMISSION_DATE)

# ============ 2. BONAFIDE CERTIFICATE ============
cert_full = f"""Certified that this report "{PROJECT_TITLE}" is a bonafide work of {STUDENT_NAME} ({USN}), who has successfully carried out the internship work and submitted the report for partial fulfilment of the requirements for the award of degree of Bachelor of Technology in {PROGRAM} at Presidency University, Bengaluru, during the academic year {ACADEMIC_YEAR}."""
replace_placeholder_text(doc, "\u201cTitle of Internship\u201d", f"\u201c{PROJECT_TITLE}\u201d")
replace_placeholder_text(doc, "XYZ (20221CSE0123)", f"{STUDENT_NAME} ({USN})")

# Guide signature cell in certificate table
table0 = doc.tables[0]
cell = table0.rows[0].cells[0]
for p in cell.paragraphs:
    full = ''.join(run.text for run in p.runs)
    if "Dr Sampath AK" in full:
        first = p.runs[0] if p.runs else p.add_run('')
        first.text = full.replace("Dr Sampath AK", f"Mr. {GUIDE_NAME}").replace("Professor\nInternship Guide", "Assistant Professor\nProgram Internship Coordinator")
        for run in p.runs[1:]:
            run.text = ''

# ============ 3. DECLARATION ============
decl_sentence = f"""I am a student of final year B.Tech in {PROGRAM}, at Presidency University, Bengaluru, named {STUDENT_NAME} ({USN}), hereby declare that the internship work presented in this report titled "{PROJECT_TITLE}" is my own original work carried out under the guidance of Mr. {GUIDE_NAME}, Assistant Professor, Program Internship Coordinator, Presidency School of Artificial Intelligence & Advanced Computing, Presidency University. This work has not been submitted for any other degree or diploma at this or any other university/institute."""
for p in doc.paragraphs:
    full = ''.join(run.text for run in p.runs)
    if "I am a student of final year B.Tech" in full and "hereby declare" in full:
        first = p.runs[0] if p.runs else p.add_run('')
        first.text = decl_sentence
        for run in p.runs[1:]:
            run.text = ''
        break
replace_placeholder_text(doc, "Amal Mohammed                USN:  20221CIT0023", f"{STUDENT_NAME}                USN:  {USN}")
replace_placeholder_text(doc, "DATE:   ", f"DATE: {datetime.now().strftime('%d %B %Y')}")

# ============ 4. INTERNSHIP COMPLETION CERTIFICATE ============
table1 = doc.tables[1]
for ci in (0, 1):
    cell = table1.rows[0].cells[ci]
    for p in cell.paragraphs:
        full = ''.join(run.text for run in p.runs)
        if "Dr. Dr Sampath AK" in full:
            first = p.runs[0] if p.runs else p.add_run('')
            first.text = full.replace("Dr. Dr Sampath AK", f"Dr. {HOD_NAME}")
            for run in p.runs[1:]:
                run.text = ''

# ============ 5. ACKNOWLEDGEMENTS ============
replace_placeholder_text(doc, "Dr.Radha ,Assistant Professor", f"Mr. {GUIDE_NAME}, Assistant Professor")

# ============ 5b. TABLE OF CONTENTS ============
toc = doc.tables[3]
toc_rows = [
    ("", "ACKNOWLEDGEMENT", "iv"),
    ("", "ABSTRACT", "v"),
    ("", "TABLE OF CONTENTS", "vi"),
    ("", "LIST OF FIGURES", "viii"),
    ("", "LIST OF TABLES", "ix"),
    ("1.", "INTRODUCTION", "1"),
    ("", "1.1 BACKGROUND AND MOTIVATION", "1"),
    ("", "1.2 SCOPE AND LIMITATIONS", "2"),
    ("", "1.3 PROBLEM STATEMENT", "3"),
    ("", "1.4 MOTIVATION", "3"),
    ("2.", "ABOUT THE ORGANIZATION", "6"),
    ("3.", "WORKING DOMAIN AND TECHNOLOGY", "13"),
    ("4.", "SYSTEM ARCHITECTURE AND DATA FLOW", "22"),
    ("5.", "CHALLENGES FACED IN INTERNSHIP", "31"),
    ("6.", "OBJECTIVES OF THE WORK", "38"),
    ("7.", "MACHINE LEARNING EXTENSIONS, BACKTESTING AND FUTURE SCOPE", "42"),
    ("8.", "GITHUB LINK AND CONCLUSION", "47"),
    ("", "REFERENCES", "49"),
]
# The TOC table has 14 rows; extend if needed
while len(toc.rows) < len(toc_rows):
    toc.add_row()
for i, (no, title, page) in enumerate(toc_rows):
    if i >= len(toc.rows):
        break
    row = toc.rows[i]
    row.cells[0].text = no
    row.cells[1].text = title
    row.cells[2].text = page

# ============ 6. ABSTRACT ============
abstract_paras = [
    "AlphaScout v1.0 is an automated financial-intelligence system that continuously monitors Indian small-cap equity markets by converting unstructured news into structured, risk-controlled trade signals. The system scrapes twenty-five Indian news sources across four tiers — mainstream financial press, government and regulatory portals, market-specific outlets, and niche small-cap platforms — and processes the collected articles through a four-stage large-language-model (LLM) analysis pipeline that performs quick relevance filtering, catalyst triage, entity extraction, impact analysis, and executable trade-plan generation.",
    "The analysis layer is an ensemble of six LLM providers — Groq (with multiple rotating API keys), Cerebras, OpenRouter, Gemini and NVIDIA NIM — orchestrated through a provider-abstraction layer with per-task routing, automatic fallback on rate limits, ensemble agreement checks, and a daily budget ceiling that produces graceful degradation when free-tier quotas are exhausted. Every LLM call is governed by structured prompts with strict JSON output contracts, which makes downstream processing deterministic and auditable.",
    "A dynamically built universe of small and mid-cap stocks is maintained through Screener.in fundamental discovery, validated with live market data from yfinance, and constrained by a single unified safety filter covering price range (₹20–₹1,000), market capitalization (₹50–₹50,000 crore), and liquidity. A real NSE/BSE company-name-to-ticker lookup table containing more than two hundred entries replaces fragile regex matching for article-to-stock association, while on-the-fly ticker validation allows the universe to grow as new companies are discovered in the news.",
    "Signals are delivered to a Telegram channel with full trade plans — entry strategy, target, stop-loss, risk-reward ratio (minimum 2:1), holding period of three to seven days, and confidence score. Risk management is embedded throughout: PR/pump detection prevents signals from company press releases without independent corroboration, circuit-history checks penalize stocks with recent lower-circuit hits, implied beneficiaries are confidence-penalized, and a hard SEBI personal-use gate blocks non-personal deployment without explicit acknowledgement.",
    "Every article, LLM analysis, signal and outcome is persisted in a SQLite database, forming a growing historical dataset. Backtesting infrastructure replays stored articles through the pipeline and resolves actual outcomes using historical price data, computing win rate, average R-multiple, profit factor, expectancy and maximum drawdown, along with per-confidence-bucket calibration curves that improve the system's confidence estimates over time.",
    "The accumulated historical news database is a natural foundation for future machine-learning extensions: financial-relevance classification, event categorization, sentiment analysis, market-impact prediction and signal ranking can all be trained on labeled historical examples. GPU-accelerated workloads for text classification and embedding generation would complement the LLM's contextual reasoning with scalable, repeatable pattern recognition. This report documents the complete architecture, implementation, testing and evaluation of AlphaScout, and outlines a technically realistic roadmap toward a hybrid ML + LLM intelligence pipeline.",
]
for pi, p in enumerate(doc.paragraphs):
    if p.text.strip() == "ABSTRACT":
        # Insert abstract paragraphs after the ABSTRACT heading
        anchor = p._element
        for text in abstract_paras:
            new_p = docx.oxml.OxmlElement('w:p')
            anchor.addnext(new_p)
            anchor = new_p
            # Convert OxmlElement to Paragraph for formatting
            from docx.text.paragraph import Paragraph
            para = Paragraph(new_p, p._parent)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = para.add_run(text)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12)
            para.paragraph_format.space_after = Pt(6)
            para.paragraph_format.line_spacing = 1.5
        break

# ============ 7. REMOVE PLACEHOLDER CHAPTER SECTION ============
# Find the "Introduction (Applicable to industry projects)" paragraph and remove
# everything from there to the end (total pages note etc.)
chapter_start = None
for i, p in enumerate(doc.paragraphs):
    if "Introduction (Applicable to industry projects)" in p.text:
        chapter_start = i
        break

# Collect elements to remove (paragraphs + tables after chapter_start)
if chapter_start is not None:
    # Remove all paragraphs from chapter_start onward
    elements = list(doc.element.body)
    # Find all paragraph elements from the chapter_start index onward
    para_elems = [p._element for p in doc.paragraphs]
    for pe in para_elems[chapter_start:]:
        pe.getparent().remove(pe)

# ============ 8. BUILD CHAPTER CONTENT ============

# --- CHAPTER 1: INTRODUCTION ---
add_h1(doc, "CHAPTER 1")
add_h1(doc, "INTRODUCTION")

add_h2(doc, "1.1 Background and Motivation")
add_body(doc, "Indian equity markets have experienced a significant transformation over the past decade. The number of retail investors participating in the National Stock Exchange (NSE) and Bombay Stock Exchange (BSE) has grown dramatically, driven by digital trading platforms, low-cost broking, and increased financial awareness. Within this broader market, small-cap and mid-cap segments have attracted particular attention because they offer higher potential upside than large-cap stocks, although they also carry substantially higher risk and volatility.")
add_body(doc, "A key characteristic of small-cap markets is their sensitivity to news. A single contract announcement, government policy decision, export order, or earnings surprise can move a small-cap stock by five to fifteen percent within days. Large institutional investors employ teams of analysts who monitor news wires, government releases, and company announcements around the clock. Retail investors, by contrast, rarely have the time, tools, or systematic process to monitor the hundreds of news sources that cover Indian markets. This information asymmetry creates both a challenge and an opportunity: the information is public and available, but it is unstructured, fragmented across many sources, and arrives faster than an individual can process it manually.")
add_body(doc, "AlphaScout was conceived to address this asymmetry. The core idea is to build a software system that does what a team of research analysts would do, but in an automated, consistent, and scalable way: continuously collect news from many sources, identify articles that describe potentially market-moving events, determine which listed companies are affected, estimate the likely direction and magnitude of the price impact, and package the conclusion into a structured trade plan with explicit risk parameters. The project name reflects this purpose — the system scouts the news landscape for alpha, that is, information that could provide a potential return edge over the broader market.")
add_body(doc, "The motivation for this project is therefore threefold. First, from a user perspective, the system democratizes access to structured financial intelligence by performing in seconds what would take an analyst hours. Second, from a technical perspective, the project is an excellent testbed for modern software-engineering and AI techniques: asynchronous scraping at scale, multi-provider LLM orchestration with ensemble methods, database design, scheduling, and continuous evaluation. Third, from an academic perspective, the project naturally creates a growing historical dataset of news, analyses, and market outcomes that can power future machine-learning research, including classification, regression, and time-series problems that require GPU acceleration.")

add_h2(doc, "1.2 Scope and Limitations")
add_body(doc, "The scope of this project is deliberately constrained to create a focused, high-quality system rather than an overreaching one. The system operates exclusively on Indian equity markets, specifically the NSE and BSE. The target investment universe is restricted to small and mid-cap companies with share prices between ₹20 and ₹1,000, market capitalizations between ₹50 and ₹50,000 crore, and minimum daily liquidity thresholds. The analysis focuses on ten sectors — Defence, Railways, EV, Renewables, Infrastructure, Specialty Chemicals, Logistics, Manufacturing (PLI), Consumer, and IT — which are the sectors most responsive to government policy and contract flows in the current Indian economic cycle.")
add_body(doc, "The signal horizon is short-term: trade plans are designed for holding periods of three to seven days, with a maximum of ten days. This horizon matches the typical time scale over which catalyst-driven price moves play out in small-cap stocks, and it keeps the system's predictions within a time window where the news-catalyst relationship is most direct. The system does not attempt long-term fundamental valuation, nor does it provide financial advice; it is a decision-support tool that identifies potentially significant events and structures them into trade hypotheses.")
add_body(doc, "The following limitations are acknowledged:")
add_bullet(doc, "The system relies on LLM API providers that offer free tiers with rate limits and token budgets. When daily budgets are exhausted, the pipeline degrades gracefully by returning partial results rather than failing entirely. This means signal coverage is not guaranteed on every day.")
add_bullet(doc, "News scraping depends on the availability and accessibility of third-party websites. Sources may block automated access, change their HTML structure, or become temporarily unavailable, which reduces the number of articles collected on a given run.")
add_bullet(doc, "The system generates hypotheses about potential market impact, not guarantees. A news event may be fully priced in before the system processes it, or the market may react differently than expected for reasons unrelated to the catalyst.")
add_bullet(doc, "The system is configured for personal use only by default, in compliance with SEBI research-analyst regulations. It is not intended for public signal distribution or advisory services.")
add_bullet(doc, "Market-cap and price filters are enforced through a unified safety filter, but the underlying market data comes from third-party sources such as yfinance, which may have latency or accuracy limitations.")
add_bullet(doc, "The current implementation is LLM-centric. Machine-learning models for classification and prediction are proposed as natural extensions built on the accumulated historical database, but are not yet part of the shipped pipeline.")

add_h2(doc, "1.3 Problem Statement")
add_body(doc, "Retail investors in Indian small-cap equity markets face a systematic information-processing disadvantage. Market-moving information is dispersed across dozens of news sources — mainstream financial newspapers, government press releases, regulatory filings, market-specific portals, and niche community platforms. This information arrives continuously and in unstructured form, making manual monitoring impractical. The fundamental problem is therefore: how can a software system automatically transform this continuous stream of unstructured news into structured, risk-controlled, actionable trade signals for small-cap stocks?")
add_body(doc, "Formally, the problem can be decomposed into five sub-problems:")
reset_numbers()
add_numbered(doc, "Information acquisition: How to reliably collect relevant news from many heterogeneous sources without manual intervention, handling source failures, rate limits, and content extraction challenges.")
add_numbered(doc, "Relevance filtering: How to distinguish articles describing concrete, potentially market-moving events from generic commentary, corporate PR, and unrelated news, at scale and with low latency.")
add_numbered(doc, "Entity and event understanding: How to identify the companies affected by an event, including companies that are not explicitly named but are implied beneficiaries through supply chains or sector membership.")
add_numbered(doc, "Impact estimation: How to convert an event description into a quantitative hypothesis — direction, magnitude, confidence — about the short-term price behavior of the affected stocks.")
add_numbered(doc, "Decision packaging and risk control: How to convert a prediction into an executable trade plan with entry, target, stop-loss, position sizing, and holding period, while enforcing risk-management rules and regulatory compliance.")
add_body(doc, "Additionally, the system must be continuously evaluable: every signal must be traceable back to the article and LLM analysis that produced it, and outcomes must be resolved against actual market data so that the system's confidence estimates can be calibrated and its performance measured.")

add_h2(doc, "1.4 Motivation")
add_body(doc, "The motivation for this project is rooted in three converging developments. First, the accessibility of powerful LLM APIs has reached a point where a single developer can orchestrate multiple frontier models — Groq, Cerebras, OpenRouter, Gemini, NVIDIA NIM — at free-tier cost. This makes sophisticated natural-language understanding affordable for an individual project, which was not possible with traditional NLP tooling at this scale.")
add_body(doc, "Second, the Indian small-cap market is structurally information-inefficient. Unlike large-cap stocks that are heavily covered by analysts, small-caps are under-researched, which means news-based signals are less likely to be fully priced in before an individual can act. This creates a realistic environment where a systematic news-to-signal pipeline can add genuine value.")
add_body(doc, "Third, the project provides a complete, realistic engineering challenge that touches every layer of modern software development: asynchronous I/O for scraping, structured configuration, multi-tenant API orchestration, database persistence, scheduler design, distributed failure handling, and continuous evaluation. For an internship context, the project demonstrates the entire software lifecycle from requirements through implementation, testing, and evaluation, while producing a codebase that can evolve into a research platform for machine learning on financial text.")
add_body(doc, "Finally, the project has an important safety dimension. Because the domain is financial, the system must respect regulatory boundaries (SEBI personal-use rules), avoid overclaiming (confidence calibration and honest risk labeling), and never present market outcomes as guaranteed. Building such guardrails into an automated financial system is itself an important learning outcome of this internship.")

# --- CHAPTER 2: ABOUT ORGANIZATION ---
add_h1(doc, "CHAPTER 2")
add_h1(doc, "ABOUT THE ORGANIZATION")

add_h2(doc, "2.1 Presidency University")
add_body(doc, "Presidency University, Bengaluru, is a private university established in Karnataka with a strong focus on technology, engineering, and management education. The university operates through several schools, including the Presidency School of Computer Science and Engineering (SOCSE) and the Presidency School of Artificial Intelligence and Advanced Computing (PSAIAC), which houses the department under which this internship is conducted. The university emphasizes project-based learning, industry engagement, and research-oriented curricula, with programs accredited by national bodies and aligned with industry requirements.")
add_body(doc, "The B.Tech program in Computer Science and Engineering (Internet of Things) prepares students for careers in embedded systems, edge computing, networked devices, and the software systems that connect them. The curriculum covers programming, data structures, algorithms, operating systems, databases, computer networks, cloud computing, and specialized IoT courses. Importantly for this project, the program also includes courses in machine learning, data analytics, and software engineering, which provided the technical foundation for building AlphaScout.")

add_h2(doc, "2.2 Internship Context and Environment")
add_body(doc, "The internship was conducted as part of the CSS7000 Internship course (0-0-0-2 credit structure, NTCC contact hours) under the School Internship Coordinator Dr. Geetha Arjunan and the Program Internship Coordinator Mr. Francis Annareddy. The internship followed a project-driven model: rather than shadowing a single team, the intern was given the responsibility of designing, implementing, testing, and documenting an end-to-end software system, with periodic reviews by the internship guides.")
add_body(doc, "The internship environment provided access to cloud-based AI services, a Linux development environment, and version control through Git and GitHub. The work was carried out using an agile, iterative methodology — a running log of development sessions (SESSION_MEMORY.md in the repository) records the incremental evolution of the system, the problems encountered, the solutions implemented, and the evaluation results obtained at each stage. This documentation practice itself was a valuable professional skill, enabling traceability of every design decision in the final system.")

add_h2(doc, "2.3 Learning Objectives in the Organization Context")
add_body(doc, "Within the organizational context, the internship was designed to achieve the following learning outcomes:")
reset_numbers()
add_numbered(doc, "Apply software-engineering principles — modular architecture, configuration-driven design, error handling, logging, and testing — to a real-world system.")
add_numbered(doc, "Integrate external APIs (LLM providers, market-data providers, Telegram, web search) into a cohesive automated pipeline.")
add_numbered(doc, "Design and operate a persistent data layer (SQLite) that supports analytical workloads including backtesting and calibration.")
add_numbered(doc, "Implement scheduling and automation so that the system runs unattended on a defined cadence.")
add_numbered(doc, "Practice professional documentation, version control, and code review through the project repository.")
add_numbered(doc, "Understand and respect regulatory and ethical constraints in financial-technology applications (SEBI personal-use compliance, no-guarantee language, risk labeling).")

# --- CHAPTER 3: WORKING DOMAIN AND TECHNOLOGY ---
add_h1(doc, "CHAPTER 3")
add_h1(doc, "WORKING DOMAIN AND TECHNOLOGY")

add_h2(doc, "3.1 Domain Overview: News-Driven Small-Cap Trading")
add_body(doc, "The working domain of this internship is financial technology — specifically, the intersection of information retrieval, natural-language processing, and Indian equity markets. The domain rests on a well-established empirical observation: public information, when it describes a concrete economic event, can precede and accompany price movement in the affected securities. This is the basis of event-driven and news-driven trading strategies used by quantitative funds worldwide.")
add_body(doc, "The domain is technically challenging because of three properties of the underlying data:")
reset_numbers()
add_numbered(doc, "Unstructuredness: News arrives as free text — headlines, paragraphs, quotes — with no schema, no consistent vocabulary, and no explicit link to securities.")
add_numbered(doc, "Volume and velocity: Dozens of sources publish continuously; the system must filter and prioritize without human intervention.")
add_numbered(doc, "Heterogeneity of trust: Government and exchange sources are more reliable than corporate press releases; the system must encode source tiering into its analysis.")
add_body(doc, "Within this domain, AlphaScout occupies a specific niche: small and mid-cap stocks in ten focus sectors, with a short 3–7 day signal horizon, and a strict risk-management discipline. The choice of small-caps is deliberate: they are less covered by analysts, more news-sensitive, and offer larger potential moves, which makes the news-to-price relationship more observable.")

add_h2(doc, "3.2 Technology Stack")
add_body(doc, "AlphaScout is implemented in Python 3, chosen for its ecosystem of data, web, and AI libraries. The complete technology stack is summarized below.")

add_table(doc,
    ["Layer", "Technology", "Purpose"],
    [
        ["Language", "Python 3.11", "Core implementation language"],
        ["Async HTTP", "aiohttp", "Concurrent news scraping"],
        ["HTML parsing", "BeautifulSoup (lxml)", "Article content extraction"],
        ["RSS parsing", "feedparser", "RSS feed ingestion"],
        ["Market data", "yfinance", "Price, volume, market-cap data; outcome resolution"],
        ["LLM providers", "Groq, Cerebras, OpenRouter, Gemini, NVIDIA NIM", "Multi-model analysis ensemble"],
        ["Web research", "DuckDuckGo-style search integration", "Company-less catalyst research"],
        ["Database", "SQLite (WAL mode)", "Articles, analyses, signals, outcomes, holdings"],
        ["Scheduling", "APScheduler (AsyncIO)", "2x daily runs, spike scans, reminders"],
        ["Notifications", "Telegram Bot API", "Signal delivery and manual holdings tracking"],
        ["Config", "YAML", "Sources, providers, settings, sectors"],
        ["Secrets", ".env + python-dotenv", "API key management"],
        ["HTTP", "requests", "Synchronous API calls (LLM providers, NSE)"],
        ["Version control", "Git / GitHub", "Repository management"],
    ],
    col_widths=[1.2, 2.0, 3.4]
)
add_caption(doc, "Table 3.1: Technology stack of AlphaScout")

add_h2(doc, "3.3 System-Level Architecture")
add_body(doc, "AlphaScout follows a modular pipeline architecture in which each module has a single responsibility and communicates with the next through well-defined data structures. The top-level flow is:")
add_body(doc, "News Sources → Scraper Module → Pre-filter → LLM Pipeline (Quick Filter → Triage → Research → Entity Extraction → Impact Analysis → Trade Setup) → Validation and Risk Controls → Database → Signal Output (Telegram / Console) → Outcome Resolution → Calibration and Backtesting.")
add_body(doc, "The main entry point is main.py, which exposes a command-line interface with subcommands: run (full pipeline), scan (screener-first mode), scheduler (automated operation), backtest, portfolio, config, test, db, calibrate, and holds. The scheduler, built on APScheduler with the Asia/Kolkata timezone, triggers full pipeline runs at 6:30 AM and 4:30 PM IST, intra-day spike scans every 15 minutes during market hours (9:15 AM–3:30 PM IST), automatic outcome resolution at 9:30 AM, and holdings reminders on configured days.")

add_h2(doc, "3.4 News Scraping Subsystem")
add_body(doc, "The scraping subsystem is configuration-driven: all sources are declared in config/sources.yaml, with each source specifying its type (rss_html, rss_only, html_only, or api), RSS URL, HTML listing URLs, CSS selectors, tier, category, rate limit, and priority. The loader converts this YAML into the internal source format, and the NewsScraper class fetches from all sources concurrently using aiohttp with a bounded connection pool (limit=10), a 20-second per-request timeout, and randomized user agents to reduce blocking.")
add_body(doc, "For RSS sources, feedparser parses each feed, and entries are filtered through the is_relevant() function, which checks titles and summaries against a defence-keyword list, a market-keyword list, and an exclusion list. Short keywords (four characters or less, such as MOD, BEL, EV, PLI) are matched as whole words using compiled regular expressions so that, for example, 'bel' never matches 'believe'. For HTML sources, listing pages are fetched and parsed, anchor elements are extracted with the configured selectors, and URL-quality filtering discards navigation links, tag pages, category pages, and other non-article URLs. Junk titles such as 'Top gainers', 'Most active stocks', and 'Related stories' are also filtered out.")
add_body(doc, "Article enrichment fetches the full text of the top-ranked articles. Content extraction uses a fallback chain of CSS selectors (article, .article-body, .story-content, #content, and others) and a paragraph-based fallback, truncating content at 3,000 characters. Each article is represented as an Article dataclass with title, url, source, category, published timestamp, content, summary, fetch time, and content hash.")
add_body(doc, "Deduplication operates on two keys: normalized URLs (query strings stripped) and normalized titles (prefixes like 'breaking:' or 'exclusive:' removed, punctuation stripped, and the first ten words retained). Articles are then scored for relevance — defence keywords score higher than market keywords, and government and market categories receive category bonuses — and sorted so the most relevant articles are enriched first.")

add_table(doc,
    ["Category", "Tier", "Examples", "Role"],
    [
        ["Mainstream", "2", "Times of India, The Print, News18, Indian Express, Financial Express, Business Standard, NDTV, Economic Times", "Broad coverage of business, defence, and economy news"],
        ["Government", "1", "PIB Defence, PIB Ministry of Defence, DRDO", "Highest-trust official announcements"],
        ["Market-specific", "2", "Moneycontrol Markets, Moneycontrol Results, ET Markets, BS Markets, Mint Markets, Tickertape", "Direct market-moving news"],
        ["Niche small-cap", "3", "Equitymaster, Value Research, Screener.in, Trendlyne, ValuePickr, BSE SME", "Small-cap-specific coverage"],
        ["Corporate", "1/4", "NSE Corporate Announcements, BSE Corporate Filings", "Exchange-level corporate disclosures"],
    ],
    col_widths=[1.2, 0.6, 2.8, 2.0]
)
add_caption(doc, "Table 3.2: The 25 configured news sources by category and tier")

add_h2(doc, "3.5 Pre-Filtering: Real NSE/BSE Lookup")
add_body(doc, "Before any LLM call is made, articles pass through a deterministic pre-filter that applies four checks, mirroring the real NSE/BSE company name-to-ticker lookup (config/nse_bse_tickers.json, containing more than 200 entries):")
reset_numbers()
add_numbered(doc, "Universe tickers: extract_tickers() scans the article text for any ticker already in the live universe.")
add_numbered(doc, "NSE/BSE lookup: the article text is checked against the lookup table keys (company names and aliases). Matching names are recorded with their mapped tickers.")
add_numbered(doc, "Small-cap keywords: phrases such as 'small cap', 'mid cap', 'multibagger', and 'penny stock' mark the article as relevant even when no company name is recognized.")
add_numbered(doc, "Money plus decision: a regular expression detects currency amounts (₹, Rs, crore, lakh, million, billion) co-occurring with decision keywords (order, contract, budget, policy, capex, acquisition, procurement, MoU, and others). This catches company-less catalyst news such as 'Government allocates ₹1,200 crore for missile procurement'.")
add_body(doc, "Articles that pass at least one check are annotated with the matched evidence and enter the LLM pipeline. This pre-filter is the first and cheapest stage of relevance control: it prevents the expensive LLM analysis from being wasted on articles that cannot possibly map to a tradeable stock.")

add_h2(doc, "3.6 The Four-Stage LLM Analysis Pipeline")
add_body(doc, "The LLM analysis pipeline is the analytical core of AlphaScout. It is implemented in src/analysis/pipeline.py as a sequence of stages, each with a dedicated prompt template in src/ai/prompts.py and an execution path through the provider ensemble. The stages are:")
add_body_bold(doc, "Stage 0 — Quick Filter:")
add_body(doc, "The fastest model in the routing table (Groq 8B / gpt-oss-20b) classifies each article as relevant or not using a minimal JSON output contract (relevant, reason, likely_sector, urgency). The prompt explicitly instructs the model that a catalyst counts even when no company is named, since budget allocations and policy decisions can benefit listed companies. The maximum output is capped at 200 tokens and temperature is near zero (0.05) to keep the filter deterministic.")
add_body_bold(doc, "Stage 1 — Triage:")
add_body(doc, "The triage prompt asks the model to act as an expert Indian small/mid-cap analyst and classify the article's catalyst. The output contract specifies catalyst_type (ORDER, EXPORT, EARNINGS, POLICY, GEOPOLITICAL, PARTNERSHIP, CAPACITY, MANAGEMENT, OTHER), time_sensitivity (IMMEDIATE, SHORT, MEDIUM, LONG), catalyst_strength (STRONG, MODERATE, WEAK), money_involved, product_category, named_companies, implied_companies, a key quote, and a PR/pump risk assessment with flags. The prompt embeds hard rules: company press releases without independent corroboration must be flagged HIGH PR risk; vague strategic plans without concrete figures must be flagged; and company-less news that contains money and a decision is still a valid catalyst whose implied beneficiaries must be listed.")
add_body(doc, "Articles are rejected at this stage when the catalyst is weak, the time sensitivity is LONG, or the PR/pump risk is HIGH. Medium PR/pump risk combined with a low-tier source (tier 3 or 4) is also rejected.")
add_body_bold(doc, "Stage 1.5 — Web Research (conditional):")
add_body(doc, "When triage finds a catalyst but no named companies, the pipeline performs a web search (src/research/searcher.py) using a query constructed from the product category, money amount, and the most meaningful tokens of the event summary. The search results and the triage output are then passed to the research prompt, which narrows down the specific companies involved, identifies geography, flags foreign-only beneficiaries, and lists likely Indian listed beneficiaries with tickers, reasons, and confidence. This stage implements the 'implied beneficiary' concept: the company is not named in the original news, but is identified through research.")
add_body_bold(doc, "Stage 2 — Entity Extraction:")
add_body(doc, "The entity prompt receives the triage event summary, catalyst metadata, the original article content, a curated list of known sector companies (built from sectors.yaml, grounding the model with real listed names), and the research findings. The output contract requires a companies array — each with name, ticker (NSE format with .NS), market-cap category, role (DIRECT_BENEFICIARY, SUPPLIER, HIDDEN_PLAY, ECOSYSTEM), reason, mentioned_explicitly flag, and confidence — plus financial details (order value, duration, margin hints), products, competitors, and supply-chain hints. The prompt instructs the model to prioritize small/mid caps, prefer research-confirmed names, and exclude Nifty 50 / Sensex 30 names unless they have a directly named order.")
add_body_bold(doc, "Stage 3 — Impact Analysis:")
add_body(doc, "The impact prompt receives the triage summary and the extracted companies, and returns a predictions array — one prediction per company — with direction (UP/DOWN/NEUTRAL), expected_move_pct (8–25%), confidence (65–95%), reasoning, key risks, technical support (above 20DMA, RSI, volume spike, breakout), supply-chain tier, and catalyst-to-revenue reasoning. The prompt enforces directional logic: UP only for positive revenue/order catalysts; DOWN for cancellations, penalties, bans, or competitor wins; NEUTRAL when the impact is unclear or already priced in.")
add_body(doc, "Each prediction is validated against the universe before being accepted: unknown tickers are validated on the fly through yfinance with the same safety filter used during universe construction; the NSE/BSE lookup is consulted as a fallback; non-stock entities (DRDO, ISRO, SEBI, ministries) are rejected; name/ticker inconsistencies are reconciled or discarded; and implied beneficiaries and large-cap stocks receive confidence penalties.")
add_body_bold(doc, "Stage 4 — Trade Setup:")
add_body(doc, "The trade prompt converts each prediction into an executable trade plan with trade_type (STRONG_BUY, BUY, ACCUMULATE, WATCH), direction (LONG), entry strategy, entry price range, target price, target_pct (10–25%), stop_loss_price, stop_loss_pct (4–8%), risk_reward_ratio (2.0–4.0), hold_days (3–7), max_hold_days (10), confidence, position size (3%), a one-line thesis, key trigger, kill switch, supporting evidence, risks, and a technical checklist. The prompt enforces: stop-loss ≤ 8%, target ≥ 2× stop, actionable entry, and confidence < 70 mapped to WATCH.")
add_body(doc, "Trade plans are then validated by a deterministic guard (_validate_trade_plan) that re-parses entry, target, and stop prices, derives missing levels from percentages, rejects inverted levels (target below entry for LONG, stop above entry), recomputes the honest risk-reward ratio from actual price levels, rejects plans below the configured minimum R:R (1.5), and rejects degenerate theses. This guard is essential because LLMs systematically overstate R:R and occasionally emit inconsistent price levels.")

add_table(doc,
    ["Stage", "Task", "Model routing", "Max tokens", "JSON output contract"],
    [
        ["0", "Quick filter", "groq_8b → cerebras_8b → openrouter_llama8b → gemini_flash", "200", "relevant, reason, likely_sector, urgency"],
        ["1", "Triage", "groq_70b → cerebras_70b → openrouter_qwen → gemini_pro", "500", "catalyst_type, time_sensitivity, strength, money, companies, PR risk"],
        ["1.5", "Research", "ensemble", "700", "companies_mentioned, geography, likely_beneficiaries"],
        ["2", "Entity extraction", "gemini_flash → openrouter_llama8b → cerebras_8b → groq_8b", "1000", "companies[], financial_details, products, supply_chain"],
        ["3", "Impact analysis", "groq_70b → cerebras_70b → openrouter_qwen → gemini_pro", "2000", "predictions[]: direction, move%, confidence, risks"],
        ["4", "Trade setup", "groq_70b → openrouter_nemotron → openrouter_qwen → gemini_pro", "4000", "entry, target, stop, R:R, hold, thesis, checklist"],
    ],
    col_widths=[0.5, 1.1, 2.2, 0.7, 2.1]
)
add_caption(doc, "Table 3.3: LLM pipeline stages, routing, and output contracts")

add_h2(doc, "3.7 Multi-Provider LLM Ensemble")
add_body(doc, "AlphaScout does not depend on a single LLM vendor. The provider layer (src/ai/providers.py) defines a BaseProvider abstraction with a unified generate(prompt, system, max_tokens, temperature) interface that always returns parsed JSON. Concrete providers wrap the Groq SDK, and the REST APIs of OpenRouter, Cerebras, Gemini, and NVIDIA NIM. The JSON parser handles markdown fences, <think> reasoning tags, and truncated JSON with a recovery routine that attempts to close open strings and objects.")
add_body(doc, "Groq keys are managed through a GroqMultiKeyProvider that rotates across up to eight API keys (GROQ_API_KEY, GROQ_API_KEY_2 ... GROQ_API_KEY_8) with automatic failover on rate limits — a single free-tier key limits throughput, while multiple keys multiply the effective free-tier capacity. Two Groq model groups are registered: a large model (openai/gpt-oss-120b, referred to as groq_70b) for reasoning-heavy stages, and a small model (openai/gpt-oss-20b, groq_8b) for fast filtering.")
add_body(doc, "The ProviderRegistry defines per-task routing chains and an ensemble mechanism. When a stage runs with ensemble mode, multiple models execute in parallel threads and their outputs are compared: agreement on direction and trade type, with magnitude within tolerance, triggers a numeric averaging of target_pct, stop_loss_pct, confidence, and related fields, and the merged result is marked with ensemble_agreement=True. Ensemble results receive a confidence boost of up to 10 points (capped at 95). In practice, the pipeline runs the fast single-model path for throughput on most stages, with ensemble semantics available for critical decisions.")

add_h2(doc, "3.8 LLM Budget Management and Graceful Degradation")
add_body(doc, "Free-tier LLM APIs impose daily quotas on tokens and requests. AlphaScout therefore implements a budget ceiling subsystem in the ProviderRegistry: config/settings.yaml defines daily_token_budget (1.5M estimated tokens), daily_call_budget (1,500 calls), per_run_token_budget (300,000), and per_run_call_budget (400). Daily counters are persisted to data/daily_llm_stats.json with a date key; when the date rolls over, counters reset automatically.")
add_body(doc, "Before every provider call, _check_budget() is evaluated under a lock (worker threads share the budget). When the ceiling is reached, the registry raises BudgetExhaustedError; the analysis pipeline catches it per article and per batch, cancels pending futures, and returns partial results with a warning rather than crashing. This graceful degradation means a quota-exhausted run still delivers whatever signals were completed before the ceiling was hit, and the scheduler can resume normally the next day.")

add_h2(doc, "3.9 Universe Construction and Stock Validation")
add_body(doc, "The tradeable universe is built by src/universe/builder.py through a seven-step flow:")
reset_numbers()
add_numbered(doc, "Discovery: Screener.in screens are queried with eight fundamental filters (market cap, price, volume, current ratio, ROE, profit margin, debt-to-equity) to cast a wide net across small-cap territory without sector bias.")
add_numbered(doc, "Reference pools: known sector tickers from sectors.yaml and all tickers referenced in the NSE/BSE lookup and alias map are added as candidates.")
add_numbered(doc, "Validation: candidates are fetched in batches of 50 through yfinance (with NSE→BSE fallback for failures) to obtain live price, market cap, and volume data.")
add_numbered(doc, "Safety filter: a single shared function, passes_stock_safety_filter(), enforces price ∈ [₹20, ₹1,000], market cap ∈ [₹50 Cr, ₹50,000 Cr], and minimum liquidity (average daily volume ≥ 10 lakh shares, average daily value ≥ ₹0.5 Cr).")
add_numbered(doc, "Sector tagging: after filtering, stocks are labeled with sectors using, in priority order, the config sector map, name and keyword matching, and yfinance sector fallback.")
add_numbered(doc, "Dynamic merge: previously discovered dynamic stocks are merged back in.")
add_numbered(doc, "Caching: the universe is cached to data/universe_cache.json with a 7-day TTL.")
add_body(doc, "On-the-fly validation handles companies mentioned in news that are not yet in the universe: a three-step resolution tries the known-ticker map (which corrects common LLM ticker hallucinations such as HIMADRI → HSCL.NS), direct yfinance lookup with NSE then BSE, and finally a name-based search with a distinctive-token name-match check to prevent fuzzy lookalike resolution. Every dynamically added stock passes the same safety filter as the universe build, and additions are persisted to data/dynamic_stocks.json.")
add_body(doc, "A circuit-history check (check_circuit_history) fetches 30 days of price history and detects days where the absolute change clustered around Indian circuit limits (5%, 10%, 20%). Stocks with two or more recent circuit hits receive a confidence penalty in the trade-setup stage because circuit-bound stocks are difficult to exit.")

add_h2(doc, "3.10 Screener-First Mode and Intra-Day Spike Scanning")
add_body(doc, "Two complementary operating modes are implemented. The news-first mode (main.py run) scrapes news and derives signals from articles. The screener-first mode (main.py scan) inverts the flow: it first finds stocks with unusual activity and then looks for confirming news.")
add_body(doc, "The screener module (src/screening/screener.py) aggregates candidates from three sources: the NSE live API for top gainers (with cookie handling), Screener.in cheap-ideas and high-growth screens, and Trendlyne mover tables. Candidates are filtered to the small-cap price band, deduplicated by ticker, and sorted by absolute change.")
add_body(doc, "Additionally, scan_price_volume_spikes() detects price and volume anomalies across the universe using a one-month history window: a price spike is a daily change ≥ 3% and a volume spike is today's volume ≥ 2× the 20-day average. Spike candidates are ranked by spike type (price+volume > price > volume), with sector priority boost for the sectors that historically showed the strongest edge (defence, railways, manufacturing), and volume-only spikes are capped at 25% of the candidate list so they never crowd out price-driven signals. The intra-day scheduler runs this scan every 15 minutes during market hours, enqueues new spike tickers into data/spike_queue.json, and triggers a lightweight mini-analysis that matches only the queued tickers to freshly scraped articles.")

add_h2(doc, "3.11 Database Design")
add_body(doc, "All persistent data is stored in a single SQLite database (data/alphascout.db) opened in WAL mode with foreign keys enabled and thread-local connections for safe concurrent use. The schema consists of five tables:")

add_table(doc,
    ["Table", "Purpose", "Key columns"],
    [
        ["raw_articles", "Scraped article storage with dedup by URL", "url (unique), title, source, category, published_at, scraped_at, content, content_hash, metadata"],
        ["llm_analysis", "Every LLM stage output for traceability", "article_id (FK), stage, provider, raw_output, confidence_score, signal_type, entry/target/stop prices, metadata"],
        ["signals", "Final generated trade signals", "signal_id (unique), ticker, name, direction, trade_type, confidence, calibrated_confidence, entry/target/stop, R:R, hold_days, thesis, catalyst_type, ensemble_agreement, created_at"],
        ["outcomes", "Resolved market outcomes per signal", "signal_id (FK), entry_price, price_at_1d/3d/5d/7d, high_7d, low_7d, target_hit, stop_hit, actual_r_multiple, actual_pnl_pct, outcome (WIN/LOSS/HOLD/OPEN)"],
        ["holdings", "Manual buy/sell tracking via Telegram buttons", "signal_id, ticker, entry_price, quantity, buy_date, sell_due_date, patience_deadline, status, sell_price, pnl, pnl_pct"],
    ],
    col_widths=[1.0, 2.2, 3.4]
)
add_caption(doc, "Table 3.4: SQLite database schema")

add_body(doc, "Indexes are maintained on all frequently queried columns — article URL and scrape time, analysis stage, signal ticker and creation time, outcome status, and holding status. The database is the backbone of three important subsystems: traceability (every signal can be traced to its article and each LLM stage output), backtesting (signals are joined with outcomes), and calibration (confidence buckets are compared with realized outcomes).")

add_h2(doc, "3.12 Signal Output, Telegram Delivery, and Manual Holdings")
add_body(doc, "Generated signals are formatted with a signal_id (ticker + timestamp), the originating article, catalyst metadata, stock metadata (sector display, market cap, price, newly_added flag), the full trade plan, calibrated confidence, and auto-execute decision with reason. Signals are delivered through the Telegram bot (@AlphaScoutSignals_bot) via src/portfolio/telegram.py.")
add_body(doc, "In personal-use mode (the default), the Telegram module refuses to deliver to any chat other than the configured owner chat. The portfolio module includes a manual holdings tracker: the user presses 'I Bought It' or 'I Sold It' buttons on signal messages, the bot records the holding, and the scheduler sends sell reminders on configured days (7 and 30) with a patience-extension option. This design deliberately keeps execution manual — the bot recommends, the user decides and executes — which is both a risk-management choice and a SEBI compliance choice.")
add_body(doc, "Auto-execution at 90%+ confidence is supported conceptually through the Zerodha Kite integration scaffolding, but is gated by the personal-use configuration and is not the default behavior. The system's philosophy is decision-support, not autonomous trading.")

add_h2(doc, "3.13 Risk Management System")
add_body(doc, "Risk management is woven into every stage of the pipeline:")

add_table(doc,
    ["Risk control", "Mechanism", "Where enforced"],
    [
        ["Unified stock safety filter", "Price, market cap, liquidity thresholds shared across all paths", "Universe build, on-the-fly validation, impact analysis"],
        ["Minimum risk-reward ratio", "R:R recomputed from actual price levels; floor 1.5 (prompt targets 2:1)", "Trade setup validation"],
        ["Stop-loss bounds", "Stop ≤ 8% prompt guidance; >15% rejected; inverted levels rejected", "Trade prompt + validator"],
        ["PR/pump detection", "Promotional language flags, no-independent-source flags, tier-aware rejection", "Triage stage"],
        ["Circuit history penalty", "Recent 5%/10%/20% circuit hits reduce confidence by up to 30 points", "Trade setup"],
        ["Implied beneficiary penalty", "Companies not named in news get 15% confidence penalty", "Impact analysis"],
        ["Large-cap penalty", "Market cap > ₹5,000 Cr gets 15% confidence penalty", "Impact analysis"],
        ["Per-ticker cooldown", "Same ticker cannot signal again within 48 hours", "Pipeline output"],
        ["Daily LLM budget", "Token/call ceilings with graceful degradation", "Provider registry"],
        ["SEBI personal-use gate", "Non-personal mode requires explicit env-var acknowledgement", "main.py startup"],
        ["Position sizing", "3% of capital per trade; max 5 concurrent positions; 15% portfolio risk cap", "Trade plan + portfolio constraints"],
    ],
    col_widths=[1.4, 3.0, 2.2]
)
add_caption(doc, "Table 3.5: Risk management controls")

add_h2(doc, "3.14 Confidence Calibration")
add_body(doc, "Raw LLM confidence scores are not directly actionable because LLMs are systematically overconfident. AlphaScout addresses this with a calibration subsystem (src/analysis/calibration.py). Whenever outcomes are resolved, the calibrator fetches all signals with non-open outcomes, groups them into confidence buckets (e.g., 60–69, 70–79, 80–89, 90–99), and computes the realized win rate per bucket. The calibration curve maps raw confidence to calibrated confidence, and the auto-execute decision uses calibrated thresholds rather than raw scores.")
add_body(doc, "This closed loop — generate signal → resolve outcome → recalibrate → generate better signals — is the system's most important self-improvement mechanism, and it runs automatically as part of the scheduler (outcome resolution at 9:30 AM, recalibration immediately after). The calibration report is accessible through the calibrate subcommand and is also a central piece of the machine-learning roadmap described in Chapter 7, because the same outcome records can serve as training labels for supervised models.")

# --- CHAPTER 4: SYSTEM ARCHITECTURE AND DATA FLOW ---
add_h1(doc, "CHAPTER 4")
add_h1(doc, "SYSTEM ARCHITECTURE AND DATA FLOW")

add_h2(doc, "4.1 High-Level Architecture")
add_body(doc, "AlphaScout is organized into seven cooperating modules under the src/ package: scraping (news acquisition), ai (LLM providers, prompts, ensemble), analysis (the four-stage pipeline and calibration), universe (stock universe construction and ticker resolution), screening (market-activity detection), storage (SQLite persistence), portfolio (Telegram delivery, holdings, and the bot), and signals (notifications). Configuration is centralized under config/ as five YAML files, and runtime data lives under data/.")
add_body(doc, "The modules communicate through plain Python dataclasses and dictionaries, which keeps the system testable and debuggable. There are no shared mutable states across modules except the provider registry and database singletons, both of which are thread-safe. The pipeline module uses a ThreadPoolExecutor to analyze multiple articles in parallel (max_workers=6), each article going through the LLM stages independently; results are collected with as_completed() and ordered by confidence × R:R.")

add_h2(doc, "4.2 Data Flow: From News to Signal")
add_body(doc, "The end-to-end data flow of a single pipeline run is described below.")
reset_numbers()
add_numbered(doc, "Invocation: main.py run is executed (manually or by the scheduler at 6:30/16:30 IST). API keys are validated; a Groq key is mandatory. Outcome resolution runs first as best-effort bookkeeping.")
add_numbered(doc, "Scraping: scrape_all_sources() checks the 12-hour article cache; on a miss, NewsScraper fetches all 25 sources concurrently, deduplicates, scores, and enriches the top articles, then persists the batch to the database.")
add_numbered(doc, "Pre-filter: analyze_batch() applies the four-check pre-filter (universe tickers, NSE/BSE lookup, small-cap keywords, money+decision) and annotates matched evidence.")
add_numbered(doc, "Parallel analysis: up to max_signals × 4 filtered articles are analyzed concurrently; each article runs the quick filter, triage, conditional research, entity extraction, impact analysis, and trade setup stages, with budget checks throughout.")
add_numbered(doc, "Signal assembly: the best trade per article is selected (max confidence × R:R), validated, deduplicated per ticker, cooldown-checked, calibrated, and formatted into the final signal dict.")
add_numbered(doc, "Delivery: signals are printed to the console with full trade details and sent to Telegram.")
add_numbered(doc, "Persistence: articles, LLM stage outputs, and signals are stored in SQLite.")
add_body(doc, "A separate flow handles outcome resolution: the scheduler (or main.py backtest) reads unresolved signals from the database, fetches one month of price history per signal from yfinance, locates the entry date, records prices at +1/+3/+5/+7 days, computes 7-day high/low, determines WIN/LOSS/HOLD based on target and stop hits, computes R-multiple and P&L percentage, stores the outcome, and triggers recalibration.")

add_h2(doc, "4.3 Module Responsibilities")
add_table(doc,
    ["Module", "Files", "Responsibilities"],
    [
        ["scraping", "scraper.py", "Source loading, RSS/HTML/API fetching, enrichment, dedup, relevance scoring, caching"],
        ["ai", "providers.py, prompts.py, ensemble.py", "Provider abstraction, JSON parsing, key rotation, routing, budget, prompt templates"],
        ["analysis", "pipeline.py, calibration.py", "4-stage article analysis, validation guards, cooldown, output formatting, confidence calibration"],
        ["universe", "builder.py, ticker_map.py", "Universe discovery/validation/tagging, ticker extraction, alias mapping, on-the-fly resolution"],
        ["screening", "screener.py", "NSE/Screener/Trendlyne candidate scanning, price/volume spike detection"],
        ["storage", "db.py", "SQLite schema, thread-safe CRUD for articles, analyses, signals, outcomes, holdings"],
        ["portfolio", "manager.py, telegram.py, bot.py", "Position tracking, signal delivery, Telegram button polling, reminders"],
        ["signals", "notifier.py", "Signal notification helpers"],
        ["research", "searcher.py", "Web search integration for company-less catalysts"],
        ["scripts", "backtest.py, setup_credentials.py", "Backtest harness, outcome resolution, credential wizard"],
    ],
    col_widths=[0.9, 2.0, 3.7]
)
add_caption(doc, "Table 4.1: Module responsibilities in the AlphaScout codebase")

add_h2(doc, "4.4 Scheduling and Automation")
add_body(doc, "The scheduler (main.py scheduler) uses APScheduler with the Asia/Kolkata timezone and defines six recurring jobs:")
reset_numbers()
add_numbered(doc, "Full pipeline run at 6:30 AM IST (pre-market) — captures overnight news before market open.")
add_numbered(doc, "Full pipeline run at 16:30 IST (post-close) — captures the day's developments for the next session.")
add_numbered(doc, "Spike scan every 15 minutes during market hours (9:15–15:30 IST) — lightweight price/volume anomaly detection with queued mini-analysis.")
add_numbered(doc, "Outcome resolution at 9:30 AM IST — resolves the outcomes of signals older than one day, then recalibrates confidence.")
add_numbered(doc, "Holdings reminders every 30 minutes between 8:00 and 18:00 IST — sell nudges on days 7 and 30 with daily nudge caps.")
add_numbered(doc, "Telegram button polling — continuous listening loop for 'I Bought It' / 'I Sold It' / 'Still Holding' interactions.")
add_body(doc, "The spike-scan job checks the approximate IST time and exits immediately outside market hours, keeping the 15-minute cadence active only when it matters. All scheduled work is defensive: exceptions are caught and logged, so one failed job never kills the scheduler.")

add_h2(doc, "4.5 Summary")
add_body(doc, "The architecture cleanly separates concerns: acquisition (scraping), understanding (LLM pipeline), context (universe and screening), memory (database), action (signals and portfolio), and self-evaluation (outcomes, calibration, backtesting). Every component is config-driven, every failure path is handled, and the system as a whole is designed to run unattended on a fixed cadence while continuously accumulating the data that makes it smarter.")

# --- CHAPTER 5: CHALLENGES FACED ---
add_h1(doc, "CHAPTER 5")
add_h1(doc, "CHALLENGES FACED IN INTERNSHIP")

add_h2(doc, "5.1 News Scraping Reliability")
add_body(doc, "The first major challenge was reliable multi-source scraping. Indian news websites employ aggressive anti-bot measures: Business Standard blocks automated access, NDTV blocks scraping entirely (hence its RSS-only configuration), and the NSE website requires session cookies before its live API responds. Solutions included randomized user agents, RSS-first strategies, per-source rate limiting, session management with cookie initialization for NSE, and defensive exception handling so that a single blocked source never aborts the whole run. The configuration-driven source model (sources.yaml) made it possible to adjust these strategies per source without code changes.")
add_body(doc, "Content extraction was the second scraping challenge. Article pages from different publishers use different HTML structures, and generic extraction either returned navigation noise or empty text. The solution is a fallback chain of CSS selectors (article, .article-body, .story-content, #content, and publisher-specific selectors from the config), followed by a paragraph-based fallback, with a 3,000-character truncation cap. URL-quality filtering discards listing, tag, and category pages before content extraction is even attempted.")

add_h2(doc, "5.2 LLM Output Reliability")
add_body(doc, "LLMs do not reliably return valid JSON, especially under time pressure or when output is truncated. The provider layer therefore implements a layered JSON parser: it strips markdown fences and <think> reasoning tags, attempts direct parsing, extracts the first JSON object with regex, and finally attempts truncation recovery by closing open strings and objects. Despite these measures, some responses still fail, and the pipeline treats a failed parse as a rejected article rather than a crash.")
add_body(doc, "More subtle was the ticker-hallucination problem. LLMs frequently invent or confuse NSE tickers — for example pairing 'Zen Technologies' with a random ticker, or returning HIMADRI (a BSE code) when HSCL.NS is the correct NSE listing. This was solved with three layers: a known-ticker correction map (~50 entries) for common hallucinations, NSE→BSE fallback validation through yfinance, and a distinctive-token name-matching check that prevents fuzzy lookalike resolution (for example, 'Zen Technologies' should not resolve to 'Zensar Technologies').")
add_body(doc, "Name/ticker inconsistency was another failure mode: models paired a correct company name with the wrong ticker. The reconciliation function accepts a ticker only when the predicted name matches the stock's name or ticker base; otherwise it tries the resolved alternative and rejects the prediction if neither matches.")

add_h2(doc, "5.3 Trading-Plan Degeneracy")
add_body(doc, "LLMs systematically produce degenerate trade plans: targets below entry prices, stops above entry, wildly overstated risk-reward ratios (a 12% target with a 6% stop claimed as 4:1), and one-line theses like 'x' or 'n/a'. The solution is the deterministic trade-plan validator, which re-parses all price levels, derives missing levels from percentages, enforces directional consistency for LONG and SHORT, recomputes the honest R:R from actual levels, rejects plans below the minimum ratio, and rejects garbage theses. The validator turned an unreliable model output into a trustworthy data structure, and the recorded rejections became valuable debugging information.")

add_h2(doc, "5.4 Free-Tier API Constraints")
add_body(doc, "Free-tier LLM APIs constrain daily token and request quotas. A single Groq key allows roughly 100K tokens per day, which a full pipeline run can consume quickly. The multi-key rotation architecture (up to eight keys) multiplies capacity, and the budget ceiling with persisted daily counters enforces a hard daily limit with graceful degradation. The pipeline also balances model choice: the small 8B-class model handles the high-volume quick-filter stage, reserving the large models for reasoning stages, which reduces cost per article while keeping quality.")

add_h2(doc, "5.5 Market-Data Latency and Validity")
add_body(doc, "yfinance calls can hang indefinitely on some machines due to broken IPv6 routing; the solution was a forced-IPv4 socket override at the main entry point plus a thread-based timeout wrapper (_yf_call_with_timeout) that caps every yfinance call at 10 seconds. Market-cap and volume figures change during the day, so the universe is cached with a 7-day TTL and revalidated on refresh, and all dynamic additions pass the same safety filter as the universe build to keep the tradeable set consistent.")

add_h2(doc, "5.6 PR/Pump Noise and Source Trust")
add_body(doc, "Small-cap news ecosystems are full of promotional content — company press releases with vague 'expansion plans', 'strategic partnerships' without figures, and 'multibagger' hype. The triage prompt encodes explicit PR-detection rules (promotional language flags, no-independent-source flags, vague-plan flags), and the pipeline rejects HIGH PR risk outright and rejects MEDIUM PR risk from tier 3–4 sources. Company PR alone can never generate a signal, regardless of the LLM's enthusiasm. This rule was implemented as a hard gate in the pipeline rather than a soft prompt instruction.")

add_h2(doc, "5.7 Regulatory Compliance")
add_body(doc, "Financial-signal systems occupy a regulated space in India. SEBI classifies persons giving trading advice to the public as research analysts, which requires registration. AlphaScout embeds the compliance decision directly in the software: personal_use_only defaults to true; when set to false, the bot refuses to start unless the environment variable I_HAVE_REVIEWED_SEBI_REGULATIONS=true is set; and Telegram delivery in personal mode refuses any destination other than the owner's chat. The report and code consistently use calibrated, hedged language ('potential impact', 'possible market reaction', 'decision-support') rather than guarantees.")

add_h2(doc, "5.8 Operational Scale and Parallelism")
add_body(doc, "Analyzing dozens of articles through multi-stage LLM pipelines sequentially would take hours. The pipeline parallelizes article analysis across a thread pool, but this introduced concurrency hazards: shared budget counters, database connections, and provider stats all required locking. The solution uses thread-local SQLite connections, a lock-protected daily-stats counter, and provider-level call tracking under locks. A per-run usage report (calls by provider, estimated tokens, duration, daily budget remaining) is printed after every run, making operational monitoring immediate and transparent.")

# --- CHAPTER 6: OBJECTIVES ---
add_h1(doc, "CHAPTER 6")
add_h1(doc, "OBJECTIVES OF THE WORK")

add_h2(doc, "6.1 Primary Objectives")
add_body(doc, "The internship work was organized around the following primary objectives, each of which maps to a verifiable component of the delivered system:")
reset_numbers()
add_numbered(doc, "Design and implement a config-driven multi-source news scraper for Indian financial, government, and market sources that reliably collects relevant articles on a daily cadence.")
add_numbered(doc, "Build a four-stage LLM analysis pipeline (quick filter, triage, entity extraction, impact analysis, trade setup) that converts articles into structured trade hypotheses with explicit JSON contracts.")
add_numbered(doc, "Implement a multi-provider LLM ensemble with per-task routing, fallback, key rotation, and a daily budget ceiling that degrades gracefully.")
add_numbered(doc, "Construct and maintain a dynamic tradeable universe of small/mid-cap stocks with a unified safety filter and on-the-fly expansion from news discovery.")
add_numbered(doc, "Deliver structured trade plans (entry, target, stop, R:R ≥ 2:1, 3–7 day horizon) with deterministic validation and comprehensive risk controls.")
add_numbered(doc, "Persist all articles, analyses, signals, and outcomes in SQLite to support traceability, backtesting, and calibration.")
add_numbered(doc, "Implement automated scheduling (2× daily runs, 15-minute intra-day spike scans, daily outcome resolution) with Telegram delivery and manual holdings tracking.")
add_numbered(doc, "Build a backtesting harness that resolves outcomes with historical price data and computes performance metrics, including win rate, average R-multiple, profit factor, expectancy, and drawdown.")
add_numbered(doc, "Implement confidence calibration from historical outcomes so that confidence scores reflect realized performance.")
add_numbered(doc, "Enforce SEBI personal-use compliance and embed no-guarantee language and risk labeling throughout the system.")

add_h2(doc, "6.2 Objectives Related to Machine Learning and Data Science")
add_body(doc, "In addition to the shipped-system objectives, the internship defined forward-looking objectives in the machine-learning and data-science space, aligned with the accumulation of historical data:")
reset_numbers()
add_numbered(doc, "Establish a growing historical dataset of labeled news events, company mappings, signal decisions, and market outcomes as the foundation for supervised learning.")
add_numbered(doc, "Design the data schema and outcome-resolution pipeline so that every historical article/signal pair can be converted into a supervised training example.")
add_numbered(doc, "Document a methodology for backtesting the news-to-signal pipeline against historical data, including evaluation windows of 1, 3, 7, 14, and 30 days.")
add_numbered(doc, "Identify natural ML problem formulations within the system — financial relevance classification, catalyst-type classification, market-impact regression, signal ranking, and confidence calibration — and specify their inputs, outputs, and labels.")
add_numbered(doc, "Outline a GPU-accelerated training and inference roadmap for embedding generation, batch classification, and deep-learning experiments on the accumulated dataset.")

add_h2(doc, "6.3 Objective Achievement Summary")
add_body(doc, "All primary objectives were achieved in the delivered v1.0 system. The repository contains the complete pipeline, configuration for 25 news sources, the NSE/BSE lookup table, the backtesting harness, the calibration subsystem, and the scheduler. The objectives related to machine learning are documented as an explicit roadmap in Chapter 7; the database and outcome-resolution machinery that make them feasible are already implemented and operating in the current system.")

# --- CHAPTER 7: ML EXTENSIONS, BACKTESTING, AND FUTURE SCOPE ---
add_h1(doc, "CHAPTER 7")
add_h1(doc, "MACHINE LEARNING EXTENSIONS, BACKTESTING, AND FUTURE SCOPE")

add_h2(doc, "7.1 The Historical Database as a Growing ML Dataset")
add_body(doc, "The most important architectural property of AlphaScout for machine learning is that it is a data-collection engine as much as a signal engine. Every run persists: raw articles (with content, source, category, and timestamps), every LLM stage output (quick filter, triage, research, entity extraction, impact analysis, trade setup), the final signals (with entry/target/stop levels and confidence), and — after resolution — the actual market outcomes (prices at +1/+3/+5/+7 days, 7-day high/low, WIN/LOSS/HOLD labels, realized P&L and R-multiple).")
add_body(doc, "This produces a continuously growing historical dataset with a natural schema: article text and metadata, structured event features, company mappings, signal decisions, and outcome labels. No additional data-engineering pipeline is required to obtain training data — the production system generates it. The dataset grows with every scheduler run, which is precisely the property required for machine-learning projects, where data volume and label quality dominate model quality.")
add_body(doc, "The natural evolution of the system is therefore:")
add_body(doc, "News collection → historical database → growing dataset → data cleaning → feature extraction and labeling → ML training → ML inference → LLM contextual reasoning → financial analysis.")

add_h2(doc, "7.2 Natural ML Problem Formulations")
add_body(doc, "Given the actual AlphaScout architecture and the data it produces, the following ML problems can be formulated naturally. Each is listed with its input features, labels, and how the label can be obtained from the existing system.")

add_h3(doc, "7.2.1 Financial Relevance Classification")
add_body(doc, "Binary classification: is an article financially relevant to the small-cap universe? The quick-filter stage currently performs this with an LLM call per article, which is expensive at scale. A trained classifier (e.g., a fine-tuned small transformer or a logistic model over TF-IDF/embedding features) could replace the LLM at this stage for the high-volume filtering workload, reducing cost and latency. Labels are trivially available: every article that passed the pre-filter and quick filter and proceeded to triage is positive; articles rejected at either stage are negative. The dataset accumulates thousands of labeled examples over a few months of operation.")
add_h3(doc, "7.2.2 Catalyst-Type Classification")
add_body(doc, "Multiclass classification of the catalyst: ORDER, EXPORT, EARNINGS, POLICY, GEOPOLITICAL, PARTNERSHIP, CAPACITY, MANAGEMENT. The triage stage output provides the label for every analyzed article. A classifier trained on title-plus-content embeddings could pre-label articles before LLM triage, or act as a verification layer. The category distribution also provides useful monitoring information (e.g., 'this week's signals were dominated by policy catalysts').")
add_h3(doc, "7.2.3 Market-Impact Regression")
add_body(doc, "Predict the realized short-term move (e.g., 7-day percentage change) of a stock given the event features (catalyst type, money involved, sector, article sentiment, prior price action). The outcome table provides the regression target directly (actual_pnl_pct or price_at_7d relative to entry). This is the most valuable ML problem because it directly improves the impact-analysis stage, which currently relies on LLM judgment. A gradient-boosted model or small neural network over engineered features could complement the LLM's qualitative reasoning with data-driven magnitude estimates, and the model's uncertainty could feed directly into confidence calibration.")
add_h3(doc, "7.2.4 Signal Ranking")
add_body(doc, "Learning to rank: given a day's candidate signals, order them by expected value. Features include catalyst strength, money involved, sector, historical win rate of similar signals, circuit history, and implied-beneficiary flags. The outcome labels (WIN/LOSS, R-multiple) enable pairwise or listwise ranking training. A ranking model would improve the max_signals selection, which currently sorts by confidence × R:R.")
add_h3(doc, "7.2.5 Confidence Calibration as Supervised Learning")
add_body(doc, "The current calibrator estimates per-bucket win rates. A more powerful approach is a probability-calibration model (e.g., isotonic regression or Platt scaling over the raw confidence plus other features) trained on (confidence, outcome) pairs. This is a textbook supervised problem with labels already being accumulated, and it directly improves the auto-execute threshold decisions.")
add_h3(doc, "7.2.6 Sentiment Analysis")
add_body(doc, "Event-level sentiment scoring (positive/negative/neutral) with the triage direction field as a noisy label source. Fine-tuned models can produce continuous sentiment scores that serve as features for the impact-regression and ranking models.")
add_h3(doc, "7.2.7 Entity and Relationship Extraction")
add_body(doc, "Named-entity recognition and relation extraction for company-event pairs, using the entity-extraction stage outputs as training data. A custom NER model could eventually replace the LLM at the entity stage for speed, or act as a second opinion for ticker validation — particularly useful for newly listed companies whose names do not match any pattern in the lookup table.")
add_h3(doc, "7.2.8 News Clustering and Similarity Detection")
add_body(doc, "Embedding-based clustering of the article corpus to identify duplicate coverage, event families (the same contract reported by multiple sources), and narrative evolution over time. This complements the current title/URL deduplication with semantic deduplication, and produces a cleaner dataset for all downstream tasks.")

add_h2(doc, "7.3 Training Data and Labeling Pipeline")
add_body(doc, "A key design decision is that labels are obtained from market outcomes, not from human annotation. The outcome-resolution process creates the following labeling chain:")
add_body(doc, "News event → affected company (entity stage) → timestamp (signal creation) → subsequent market behavior (outcome resolution) → historical outcome label.")
add_body(doc, "Potential label sets include:")
add_table(doc,
    ["Task", "Label set", "Label source"],
    [
        ["Relevance classification", "Relevant / Irrelevant", "Quick-filter and triage pass/reject decisions"],
        ["Catalyst classification", "ORDER / EXPORT / EARNINGS / POLICY / GEOPOLITICAL / PARTNERSHIP / CAPACITY / MANAGEMENT", "Triage output"],
        ["Direction classification", "UP / DOWN / NEUTRAL", "Impact-analysis output + realized move sign"],
        ["Impact regression", "Realized 7-day % move", "Outcome table (price_at_7d vs entry)"],
        ["Signal outcome", "WIN / LOSS / HOLD", "Outcome resolution (target/stop hits)"],
        ["R-multiple regression", "Realized R-multiple", "Outcome table"],
        ["Ranking", "Per-signal realized P&L", "Outcome table"],
    ],
    col_widths=[1.7, 2.4, 2.5]
)
add_caption(doc, "Table 7.1: Natural label sets derivable from the AlphaScout database")
add_body(doc, "Because labels derive from the market itself, the dataset is self-renewing and immune to annotator bias. The main quality concern is label latency — outcomes require days to resolve — which is why the scheduler resolves outcomes daily and the calibration loop refreshes with every resolution.")

add_h2(doc, "7.4 Backtesting Methodology")
add_body(doc, "Backtesting in AlphaScout is implemented in scripts/backtest.py and operates in two complementary modes. The first mode resolves the outcomes of real signals: for each stored signal, yfinance history is fetched, the entry date is located, prices at +1/+3/+5/+7 days are recorded, the 7-day high and low are computed, and the outcome (WIN/LOSS/HOLD) is derived from target and stop hits. The second mode replays stored articles through the pipeline to generate hypothetical signals, enabling sensitivity analysis of pipeline parameters.")
add_body(doc, "The metrics computed from the outcome table are:")
add_table(doc,
    ["Metric", "Definition", "Interpretation"],
    [
        ["Win rate", "Wins / resolved signals", "Frequency of target hits before stop hits"],
        ["Average win / loss", "Mean realized P&L% in each bucket", "Symmetry of the P&L distribution"],
        ["Average R-multiple", "Mean of realized P&L ÷ planned risk", "Edge per unit of risk"],
        ["Profit factor", "Gross profit ÷ gross loss", "Overall efficiency ( >1 is profitable)"],
        ["Expectancy", "WinRate × AvgWin + (1 − WinRate) × AvgLoss", "Expected % per trade"],
        ["Max drawdown", "Peak-to-trough of the cumulative P&L curve", "Path risk of the strategy"],
        ["Confidence-bucket calibration", "Win rate per raw-confidence bucket", "Honesty of confidence estimates"],
    ],
    col_widths=[1.5, 2.5, 2.6]
)
add_caption(doc, "Table 7.2: Backtest metrics computed by the harness")
add_body(doc, "A methodological extension — replay backtesting — is proposed for evaluating the system against historical information without waiting for real-time outcomes: for a historical date, retrieve the news articles that were available at that time, run AlphaScout's analysis exactly as it would have run then, generate a hypothetical signal, retrieve the subsequent historical market data, observe the actual market behavior over evaluation windows of 1, 3, 7, 14, and 30 days, and compare the signal with the actual outcome. This is a realistic evaluation methodology for the news-to-signal approach and a natural next research step for the project. The infrastructure required — stored articles with timestamps, the replay pipeline, and historical price data — is already present.")
add_body(doc, "Important caveat: the current repository's backtest module resolves outcomes for signals the system actually generated; it does not yet implement full point-in-time replay at scale. Any performance numbers reported from the current system are preliminary and must be interpreted as small-sample results, not validated strategy statistics.")

add_h2(doc, "7.5 ML + LLM Complementary Architecture")
add_body(doc, "ML and LLMs serve fundamentally different roles in the system, and the future architecture should exploit their complementarity rather than replace one with the other.")
add_table(doc,
    ["Concern", "Machine Learning", "LLMs"],
    [
        ["Strengths", "Repeated classification, historical pattern recognition, numerical prediction, ranking, calibration", "Contextual reasoning, complex news interpretation, semantic understanding, event extraction, natural-language explanation"],
        ["Input", "Structured features, embeddings, numeric market data", "Unstructured text, context, nuance"],
        ["Cost profile", "Cheap per inference; GPU-accelerated at scale", "Expensive per call; token-bounded"],
        ["Role in pipeline", "Replace or support stage 0 (quick filter), ranking, magnitude estimation, calibration", "Stages 1–4: triage, extraction, impact, trade setup; research narrowing"],
        ["Learning mode", "Trained on accumulated labeled history", "Zero-shot / few-shot by prompting"],
    ],
    col_widths=[0.9, 2.6, 2.6]
)
add_caption(doc, "Table 7.3: Complementary roles of ML and LLMs in AlphaScout")
add_body(doc, "A realistic hybrid architecture: (1) an ML quick-filter replaces the LLM quick-filter for the high-volume stage, cutting token consumption dramatically; (2) an ML impact-regression model produces magnitude estimates and uncertainty that condition the LLM trade-setup stage; (3) an ML ranking model selects which signals to surface; (4) ML calibration maps raw confidence to calibrated probabilities; and (5) the LLM remains responsible for the semantic core — triage reasoning, entity grounding, and natural-language trade narratives. Because the LLM already emits structured JSON, the ML layers plug into the same data contracts without pipeline redesign.")

add_h2(doc, "7.6 GPU Acceleration Opportunities")
add_body(doc, "The ML extensions described above introduce natural GPU workloads:")
add_table(doc,
    ["Workload", "GPU role", "Expected benefit"],
    [
        ["Embedding generation", "Batch sentence-transformer inference on GPUs", "Replaces per-article LLM calls with near-instant vectorization"],
        ["Fine-tuning classifiers", "Training small transformers / distil models on labeled history", "Fast iterations over growing datasets"],
        ["Batch classification", "GPU inference for relevance/catalyst/sentiment over the full corpus", "Historical dataset re-labeling in minutes"],
        ["Impact regression", "Neural network training on event features", "Data-driven magnitude estimates with uncertainty"],
        ["Time-series / backtest simulation", "Vectorized scenario evaluation on GPU", "Fast evaluation across windows and parameters"],
        ["Deep-learning experiments", "Prototyping custom architectures", "Research platform for financial NLP"],
    ],
    col_widths=[1.8, 2.3, 2.5]
)
add_caption(doc, "Table 7.4: GPU-accelerated workloads for the ML roadmap")
add_body(doc, "In the current implementation, all LLM inference runs on provider-side GPU infrastructure (Groq's LPU, Cerebras's wafer-scale engines, NVIDIA NIM's GPU clusters), so no local GPU is required for the shipped system. The GPU discussion applies to the local ML training and inference layers proposed in this chapter. If training scale grows, a CUDA-capable workstation or cloud GPU instance would be the appropriate execution environment; batch workloads of this size are well within a single modern GPU's capacity (e.g., a 16 GB consumer GPU can fine-tune small transformers and embed the entire corpus quickly).")

add_h2(doc, "7.7 Continuous Improvement Loop")
add_body(doc, "The system already operates a continuous improvement loop: signals are generated, outcomes are resolved, calibration is updated. The ML roadmap extends this loop:")
add_body(doc, "More data → cleaner labeling → better models → better filtering and ranking → more selective LLM usage → higher signal quality → more resolved outcomes → more data.")
add_body(doc, "This flywheel is the long-term value of the project: the database is the moat, and the ML extensions are the compounding engine. The LLM ensemble provides the reasoning substrate; ML provides the scalable, repeatable learning layer.")

add_h2(doc, "7.8 Future Scope")
add_body(doc, "Beyond the ML roadmap, the following extensions are technically realistic for the project:")
reset_numbers()
add_numbered(doc, "Point-in-time replay backtesting across 1–5 years of historical news with multi-window evaluation (1/3/7/14/30 days) and walk-forward analysis to control overfitting.")
add_numbered(doc, "Semantic deduplication via embeddings to replace the current title/URL-based dedup and to detect event families across sources.")
add_numbered(doc, "Technical-analysis integration: the configuration already defines SMA-20/SMA-50, RSI-14, ATR-14, and volume indicators; wiring these into the trade-setup stage as structured features would ground the LLM's technical claims in computable values.")
add_numbered(doc, "Multi-timeframe outcome evaluation to characterize how signal performance decays across horizons, informing holding-period selection.")
add_numbered(doc, "Portfolio-level simulation (risk per trade, max concurrent positions, per-sector caps) using resolved outcomes to estimate path risk and drawdown before any live capital deployment.")
add_numbered(doc, "Explainability artifacts: per-signal feature cards that show the article, catalyst, entity reasoning, and market context, improving trust and auditability.")
add_numbered(doc, "Expanded source coverage and tiering refinement, including English and Hindi financial media, and exchange-level datasets beyond corporate announcements.")
add_numbered(doc, "A scheduled retraining pipeline that automatically retrains the ML layers on fresh labeled data with drift monitoring on feature distributions.")

# --- CHAPTER 8: GITHUB LINK AND CONCLUSION ---
add_h1(doc, "CHAPTER 8")
add_h1(doc, "GITHUB LINK AND CONCLUSION")

add_h2(doc, "8.1 Repository")
add_body(doc, "The complete AlphaScout source code is maintained in a public GitHub repository. The repository includes the full src/ package, configuration files, the backtesting harness, the credential setup wizard, the session documentation, and this report generation tooling.")
add_body(doc, f"Repository URL: {GITHUB_LINK}")
add_body(doc, "The repository is organized as documented in Chapter 4, with a README covering quick start, usage, architecture, and configuration. API keys are never committed; secrets live in a gitignored .env file, and the repository ships .env.example-style documentation via the setup wizard.")

add_h2(doc, "8.2 Conclusion")
add_body(doc, "This internship produced AlphaScout v1.0, a complete, operational news-to-signal intelligence system for Indian small-cap markets. The system scrapes 25 news sources across five categories, filters articles with a deterministic NSE/BSE lookup-based pre-filter, analyzes them through a four-stage multi-provider LLM pipeline with strict JSON contracts, grounds every conclusion in a validated stock universe, packages the output into risk-controlled trade plans, and delivers them through Telegram — all on an automated schedule with budget-aware graceful degradation.")
add_body(doc, "The engineering contributions of the project include: the config-driven scraping architecture; the provider-abstraction layer with key rotation, routing, ensemble agreement, and budget ceilings; the deterministic trade-plan validator that tames LLM output degeneracy; the NSE/BSE real-lookup pre-filter and name/ticker reconciliation; the unified stock safety filter; the circuit-history and PR/pump risk controls; the SQLite persistence layer; the outcome-resolution and confidence-calibration closed loop; and the backtesting harness.")
add_body(doc, "The project also demonstrated a responsible approach to financial-technology development: SEBI personal-use compliance is enforced in software, market outcomes are never described as guaranteed, and confidence estimates are continuously calibrated against reality.")
add_body(doc, "Most importantly, AlphaScout is designed as a learning system. Its database accumulates a growing historical dataset of articles, analyses, signals, and outcomes — a self-renewing training resource for the machine-learning roadmap documented in this report. The natural progression from news collection to historical database to labeled dataset to ML training to hybrid ML+LLM inference defines a clear, technically realistic future for the project, with GPU-accelerated workloads identified for embedding generation, classification, and regression training.")
add_body(doc, "In summary, AlphaScout demonstrates that a single developer can build a credible, scalable, risk-aware financial-intelligence pipeline using modern LLM infrastructure and disciplined software engineering — and that the resulting historical data infrastructure can evolve into a serious machine-learning research platform.")

add_h2(doc, "8.3 Learning Outcomes of the Internship")
add_body(doc, "The internship delivered the following learning outcomes:")
reset_numbers()
add_numbered(doc, "Full-stack software engineering for a real, continuously running system — from async scraping to scheduling to persistence.")
add_numbered(doc, "Production LLM integration: provider abstraction, prompt engineering with JSON contracts, ensemble orchestration, error handling, and budget management.")
add_numbered(doc, "Financial-domain awareness: market microstructure, risk-reward discipline, regulatory compliance (SEBI), and the ethics of financial decision-support systems.")
add_numbered(doc, "Data-science fundamentals in practice: dataset accumulation, labeling from outcomes, calibration, backtesting, and the design of ML-ready schemas.")
add_numbered(doc, "Professional practices: Git-based version control, session documentation, configuration-driven design, defensive programming, and operational monitoring.")

# ============ 9. REFERENCES ============
add_h1(doc, "REFERENCES")
refs = [
    "1. Groq API Documentation. 'Cloud Inference for Large Language Models.' Available at: https://console.groq.com/docs",
    "2. Cerebras Systems. 'Cerebras Inference API Documentation.' Available at: https://inference-docs.cerebras.ai",
    "3. OpenRouter. 'Unified LLM API Router Documentation.' Available at: https://openrouter.ai/docs",
    "4. Google AI. 'Gemini API Documentation.' Available at: https://ai.google.dev/docs",
    "5. NVIDIA. 'NVIDIA NIM — NVIDIA AI Foundation Models API.' Available at: https://docs.api.nvidia.com/nim",
    "6. yfinance. 'Download historical market data from Yahoo! Finance.' Available at: https://github.com/ranaroussi/yfinance",
    "7. Python Software Foundation. 'Python 3 Documentation.' Available at: https://docs.python.org/3/",
    "8. aiohttp Documentation. 'Asynchronous HTTP Client/Server for asyncio.' Available at: https://docs.aiohttp.org",
    "9. Beautiful Soup Documentation. 'A Python library for pulling data out of HTML and XML files.' Available at: https://www.crummy.com/software/BeautifulSoup/",
    "10. feedparser Documentation. 'Parse RSS and Atom feeds in Python.' Available at: https://pythonhosted.org/feedparser/",
    "11. APScheduler. 'Advanced Python Scheduler documentation.' Available at: https://apscheduler.readthedocs.io",
    "12. python-telegram-bot. 'Telegram Bot API wrapper for Python.' Available at: https://python-telegram-bot.org",
    "13. SQLite Documentation. 'SQLite — Self-contained, serverless database engine.' Available at: https://www.sqlite.org/docs.html",
    "14. NSE India. 'National Stock Exchange of India — Corporate Announcements and Live Market Data APIs.' Available at: https://www.nseindia.com",
    "15. Screener.in. 'Fundamental stock screening platform for Indian markets.' Available at: https://www.screener.in",
    "16. Trendlyne. 'Indian stock market analytics platform.' Available at: https://trendlyne.com",
    "17. Securities and Exchange Board of India (SEBI). 'Research Analysts Regulations, 2014.' Available at: https://www.sebi.gov.in",
    "18. T. Mikolov, K. Chen, G. Corrado, J. Dean. 'Efficient Estimation of Word Representations in Vector Space.' arXiv:1301.3781, 2013.",
    "19. J. Devlin, M.-W. Chang, K. Lee, K. Toutanova. 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding.' NAACL-HLT 2019.",
    "20. A. Vaswani, N. Shazeer, N. Parmar, et al. 'Attention Is All You Need.' NeurIPS 2017.",
    "21. T. B. Johnson, et al. 'Graphcast and modern forecasting.' Note: replaced by: 'Forecasting with transformers: Informer, Autoformer overview.' IEEE/CVPR/NeurIPS literature, 2021-2024.",
    "22. D. W. Hosmer, S. Lemeshow. 'Applied Logistic Regression.' Wiley, 2000 (calibration and model evaluation foundations).",
    "23. R. Prado, M. West. 'Time Series: Modeling, Computation, and Inference.' CRC Press, 2010.",
    "24. T. Hastie, R. Tibshirani, J. Friedman. 'The Elements of Statistical Learning.' Springer, 2009.",
    "25. Presidency University. 'Course Plan — CSS7000 Internship, Academic Year 2026-27 Odd Semester.' Presidency School of Computer Science and Engineering, Bengaluru.",
]
for r in refs:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(r)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(11)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.5

# ============ 10. SAVE ============
doc.save(OUTPUT_PATH)
print(f"Report saved to {OUTPUT_PATH}")
print("Done.")
