# ALPHA SCOUT — MASTER PROJECT REPORT GENERATION INSTRUCTIONS

## ROLE

You are an expert technical researcher, software engineer, machine-learning engineer, AI/LLM engineer, and academic technical-report writer.

You are working inside the **Alpha Scout** project folder.

Your task is to:

1. Completely analyze and understand the Alpha Scout project.
2. Completely analyze the DOCX report template provided inside this folder.
3. Determine how the actual project maps to the template.
4. Identify any information that is missing and ask me for it.
5. Create a detailed academic project report based on Alpha Scout.
6. Edit the provided DOCX template rather than unnecessarily creating a new document.
7. Preserve the template's formatting and structure.
8. Produce a polished final report of **at least 40 meaningful pages**.
9. Naturally incorporate technically relevant Machine Learning, GPU, historical-data, dataset, and backtesting concepts wherever they make sense within the actual Alpha Scout architecture.
10. Validate the final DOCX before considering the task complete.

---

# 1. ABSOLUTE PRIORITY

The most important rule is:

> **Understand the actual Alpha Scout project first. Write the report second.**

Do not start writing the report immediately.

Do not start modifying the DOCX immediately.

Do not assume what Alpha Scout does.

Do not force Alpha Scout into a predetermined architecture.

Do not assume that it is a conventional stock-price prediction system.

Do not assume that it is primarily an ML project.

Do not assume that it is primarily an LLM project.

**Inspect the actual implementation and determine what it is.**

Your analysis of the source code, configuration, database, APIs, documentation, and other project files must be the primary source of truth.

---

# 2. PHASE 1 — COMPLETE ALPHA SCOUT DISCOVERY

Before modifying anything, recursively inspect the Alpha Scout folder.

Identify all relevant:

* Source-code files
* Frontend files
* Backend files
* API files
* Database/schema files
* Scraping code
* AI/LLM code
* Prompts
* Configuration
* Dependency files
* Environment examples
* Scripts
* Notebooks
* Documentation
* Images
* Screenshots
* Diagrams
* Tests
* Data files
* Model files
* Other technical assets

Ignore irrelevant generated directories such as dependency installations, caches, build output, etc., unless they contain information necessary for understanding the project.

Do not blindly read every generated dependency file.

Instead, focus on files that help establish how the actual application works.

---

# 3. UNDERSTAND THE COMPLETE EXECUTION FLOW

Do not merely summarize filenames.

Trace the actual system.

Determine:

* How the system starts
* How information enters the system
* How information is collected
* How information is processed
* How information moves between components
* Which APIs are called
* Which AI/LLM services are used
* What prompts are used
* How responses are processed
* What data is stored
* How the database is structured
* What outputs are generated
* How users interact with the system
* What happens from input to final output

Build a complete internal mental model of Alpha Scout.

You should be able to explain the entire pipeline from beginning to end before writing the report.

---

# 4. UNDERSTAND ALPHA SCOUT'S ACTUAL PURPOSE

The conceptual purpose of Alpha Scout is related to identifying potentially financially significant information from news and other real-world events.

The system is particularly interested in information involving things such as:

* Governments
* Government contracts
* Large financial agreements
* Companies
* Industries
* Defense
* Manufacturing
* Infrastructure
* Government spending
* Geopolitical events
* Wars/conflicts
* Large-scale production
* International developments
* Major investments
* Other events that could have meaningful economic or financial consequences

However:

**Do not simply assume this description is the implementation.**

Use the actual source code to determine exactly how Alpha Scout performs these functions.

---

# 5. NEWS SCRAPING AND INFORMATION COLLECTION

If Alpha Scout scrapes news websites, analyze exactly how this works.

Determine:

* Which websites/sources are used
* Which scraping technology is used
* How articles are retrieved
* How article content is extracted
* What metadata is extracted
* How headlines are handled
* How URLs are handled
* How timestamps/dates are handled
* How duplicate information is handled
* How scraped information is passed to later stages
* How frequently data is collected, if determinable

Document the actual implementation.

Do not invent scraping technologies or sources.

---

# 6. LLM/AI PROCESSING

If Alpha Scout uses LLMs or AI APIs, inspect them carefully.

Determine:

* Which models/APIs are used
* Where they are called
* What prompts they receive
* What inputs they receive
* What outputs they produce
* How the outputs are interpreted
* Whether there are multiple LLM stages
* How the stages interact
* How errors are handled
* How the results are stored or passed forward

If the system contains multiple AI stages, explain their distinct roles.

For example, if one stage filters irrelevant news and another evaluates financial significance, explain those as separate processing stages.

Do not merge distinct AI components into one generic "AI module."

---

# 7. FINANCIAL/ECONOMIC INTELLIGENCE

Understand how Alpha Scout identifies information that may matter financially.

For example, an event such as a major government contract may imply:

Government decision
↓
Company receives business opportunity
↓
Potential increase in business activity
↓
Potential change in investor expectations
↓
Potential market impact

This is an analytical hypothesis, not a guaranteed outcome.

The report must never claim that a particular event guarantees a stock-price increase.

Use academically appropriate language such as:

* Potential market impact
* Potential financial significance
* Market-relevant event
* Investment opportunity for further investigation
* Decision-support information
* Possible market reaction

---

# 8. GEOPOLITICAL INTELLIGENCE

If the actual system processes geopolitical or government-related news, explain how such events may have financial consequences.

Relevant examples may include:

* War
* Defense contracts
* Weapons production
* Government procurement
* Government spending
* Sanctions
* International agreements
* Strategic manufacturing
* Supply-chain disruptions
* Energy developments
* Major geopolitical decisions

Only include concepts relevant to the actual project.

---

# 9. DO NOT TURN ALPHA SCOUT INTO A GENERIC ML PROJECT

This is extremely important.

The report must remain centered on the **actual Alpha Scout architecture**.

Do not rewrite it as:

"Historical stock prices → ML model → stock prediction."

unless the actual implementation supports that.

If Alpha Scout is primarily an LLM-powered news intelligence system, document it as such.

ML should complement the project rather than replace its identity.

---

# 10. DOCX TEMPLATE ANALYSIS

Locate the DOCX template inside the Alpha Scout folder.

Before editing it, inspect the entire document.

Understand:

* Cover page
* Title page
* Certificate
* Declaration
* Acknowledgement
* Abstract
* Table of contents
* Chapters
* Sections
* Subsections
* Tables
* Figures
* Captions
* Headers
* Footers
* Page numbers
* Fonts
* Font sizes
* Margins
* Spacing
* Heading hierarchy
* Styles
* Placeholder text
* Institutional information
* Student information
* Guide information
* Department information
* Academic year
* Project/event information
* Any instructions contained in the template

Treat this template as the authoritative formatting specification.

---

# 11. DO NOT DESTROY THE TEMPLATE

The goal is to **populate and adapt the provided template**.

Do NOT redesign the report from scratch.

Preserve:

* Overall structure
* Layout
* Fonts
* Heading styles
* Margins
* Headers
* Footers
* Page numbering
* Table styles
* Figure styles
* Spacing
* Alignment
* Professional appearance

Do not change formatting merely because you prefer another style.

---

# 12. TEMPLATE PLACEHOLDERS

Find every placeholder in the template.

Examples may include:

* Student Name
* Roll Number
* USN
* College Name
* University
* Department
* Guide
* HOD
* Academic Year
* Team Members
* Project Title
* Event Name
* Address
* Submission Date

Determine which values can be obtained from the project.

For information that cannot be determined:

**DO NOT GUESS.**

Ask me.

---

# 13. ASK BEFORE MAKING IMPORTANT CHANGES

If required information is missing, stop and ask me.

If the template contains ambiguous information, ask me.

If a major structural formatting change appears necessary, ask me before making it.

Especially ask before:

* Changing the overall template structure
* Removing sections
* Adding major structural sections
* Changing margins
* Changing fonts globally
* Changing certificates/declarations
* Removing institutional content
* Reformatting the entire document

Do not silently make major formatting decisions.

---

# 14. REPORT CONTENT

Create a comprehensive academic technical report based on the actual project.

Where appropriate, cover:

* Introduction
* Background
* Problem statement
* Motivation
* Objectives
* Existing system
* Proposed system
* Literature survey
* Technologies used
* System requirements
* System architecture
* Data flow
* Module descriptions
* Web scraping
* Data processing
* AI/LLM architecture
* Financial intelligence
* Geopolitical intelligence
* Database
* APIs
* Implementation
* Testing
* Results
* Limitations
* Machine learning opportunities
* Dataset generation
* Historical analysis
* Backtesting
* GPU acceleration
* Future scope
* Conclusion
* References

The exact organization must follow the DOCX template.

Do not force all of these sections into the report if they are inappropriate.

---

# 15. SPECIAL REQUIREMENT — MACHINE LEARNING

The academic context of this project expects meaningful Machine Learning and GPU-related technical content.

Therefore, after understanding Alpha Scout, **actively identify every realistic opportunity where ML could naturally fit into the system.**

Do not use a predetermined ML structure.

You decide where ML belongs based on your understanding of the actual project.

Potential areas include:

* News classification
* Financial relevance classification
* Event classification
* Sentiment analysis
* Entity recognition
* Company/event relationship extraction
* News clustering
* Similarity detection
* Market-impact classification
* Signal ranking
* Anomaly detection
* Pattern recognition
* Historical-data analysis
* Time-series modeling
* Prediction
* Ranking
* Dataset creation
* Feature engineering
* Model evaluation
* Backtesting
* GPU acceleration
* Continuous dataset growth

These are examples, not mandatory items.

Think independently.

Ask yourself:

> "Given the actual Alpha Scout architecture and the data it produces, what useful ML problems could naturally be formulated?"

Include the most relevant answers in the report.

---

# 16. ML MUST FEEL NATURAL

Do not make the report look like:

"LLM project + random ML chapter added because college requires ML."

Instead, ML should appear as a natural extension of the system.

For example, if Alpha Scout continuously collects and stores news, explain that:

**The accumulated historical news database can become a growing dataset for future ML development.**

This creates a natural evolution:

News collection
↓
Historical database
↓
Growing dataset
↓
Data cleaning
↓
Feature extraction / labeling
↓
ML training
↓
ML inference
↓
LLM contextual reasoning
↓
Financial analysis

Use this concept wherever it fits naturally.

---

# 17. HISTORICAL DATASET CONCEPT

If Alpha Scout stores scraped/processed news in a database, discuss how that historical information can eventually be used as an ML dataset.

Potential applications include:

* Financial relevance classification
* Event classification
* Sentiment analysis
* Company/event classification
* Market-impact classification
* Signal ranking
* Pattern detection

Do not claim that the current system automatically trains a model from this data unless it actually does.

Instead, explain it as a technically realistic extension where appropriate.

---

# 18. ML TRAINING DATA

A potential future learning pipeline could be:

Historical news
+
Historical market behavior
↓
Structured training examples
↓
Feature extraction
↓
Labels
↓
ML model training
↓
Validation
↓
Testing
↓
Deployment
↓
New incoming news
↓
ML inference
↓
LLM analysis

The report may explain how this could allow Alpha Scout to improve as more historical data accumulates.

Do not claim that the model already does this unless the code proves it.

---

# 19. BACKTESTING

Think carefully about the role of **backtesting** in Alpha Scout.

Backtesting can be used to simulate what Alpha Scout would have done using historical information.

A possible methodology is:

Historical date
↓
Retrieve news available at that time
↓
Run Alpha Scout's analysis
↓
Identify potentially significant event
↓
Identify affected company/industry
↓
Generate a hypothetical signal
↓
Retrieve subsequent historical market data
↓
Observe actual market behavior
↓
Compare signal with actual outcome
↓
Evaluate performance

Potential evaluation windows may include:

* 1 day
* 3 days
* 7 days
* 14 days
* 30 days

Choose appropriate windows based on the project.

Do not invent backtesting results.

If backtesting exists in the code, document the actual implementation.

Otherwise describe it as a proposed evaluation methodology.

---

# 20. HISTORICAL FINANCIAL DATA

If appropriate, discuss how historical financial-market data could be combined with historical news.

Conceptually:

Historical news event
+
Affected company
+
Timestamp
+
Historical market data
↓
Training/evaluation dataset

This could allow the project to study whether particular categories of events historically corresponded with subsequent market movements.

Do not claim a particular financial-data provider is currently integrated unless the code confirms it.

If the project actually uses such a service, document it accurately.

---

# 21. DATA LABELING

Where relevant, discuss how historical outcomes could potentially be used to label ML training data.

For example:

News event
↓
Affected company
↓
Observe market behavior after event
↓
Determine historical outcome
↓
Create training label

Potential labels might include:

* Positive reaction
* Negative reaction
* Neutral reaction
* High-impact event
* Low-impact event
* Financially relevant
* Financially irrelevant

Choose appropriate labels based on Alpha Scout.

Do not fabricate actual labels or results.

---

# 22. ML + LLM COMPLEMENTARY ARCHITECTURE

Where technically appropriate, explain that ML and LLMs can serve different purposes.

Machine Learning can potentially handle:

* Repeated classification
* Historical pattern recognition
* Numerical analysis
* Structured prediction
* Ranking
* Scoring

LLMs can potentially handle:

* Contextual reasoning
* Complex news interpretation
* Semantic understanding
* Event extraction
* Financial significance analysis
* Natural-language explanation
* Unstructured information

The report should explain how both technologies could complement one another.

---

# 23. GPU COMPUTING

Identify where GPU acceleration could naturally contribute to the ML side of Alpha Scout.

Potential workloads include:

* Neural-network training
* Large-scale text classification
* Embedding generation
* Batch inference
* Deep-learning experiments
* Large historical datasets
* Model experimentation

If actual GPU usage is found, document it.

If not, discuss GPU utilization as a technically realistic ML extension.

Never invent GPU benchmark numbers.

---

# 24. HISTORICAL ML IMPLEMENTATION

Investigate whether previous ML work exists anywhere in the available repository/history.

Look for:

* Git commits
* Branches
* Tags
* Previous files
* Notebooks
* Training scripts
* Model files
* Dataset files
* Checkpoints
* Documentation
* Dependency changes

If genuine historical ML implementation can be verified, incorporate it into the report.

If it cannot be verified, do not invent specific historical details.

---

# 25. DO NOT FABRICATE RESULTS

Never invent:

* Accuracy
* Precision
* Recall
* F1-score
* RMSE
* MAE
* Dataset size
* Number of training samples
* Training epochs
* GPU utilization
* Training time
* Model parameters
* Backtesting results
* Profit percentages
* Return percentages
* Sharpe ratio
* Stock prediction accuracy

If a value exists in the actual project, use it.

Otherwise do not create one.

---

# 26. FINANCIAL CLAIMS

Alpha Scout concerns potentially actionable financial information.

Therefore, do not describe market outcomes as guaranteed.

Avoid statements such as:

"The system guarantees a 15% increase."

Instead use:

* Potential market impact
* Possible market reaction
* Potential investment opportunity
* Market-relevant signal
* Decision-support information
* Event that warrants further investigation

The report should remain technically and academically defensible.

---

# 27. 40+ PAGE REQUIREMENT

The final report must contain **at least 40 meaningful pages**.

Do not reach 40 pages through:

* Huge fonts
* Artificial spacing
* Empty pages
* Repeated paragraphs
* Repeated explanations
* Meaningless filler
* Destroying template formatting

Instead achieve the required length through genuine technical depth.

Expand naturally through:

* Detailed architecture explanations
* Module descriptions
* Algorithms
* Data flow
* AI/LLM methodology
* Database design
* Screenshots
* Tables
* Diagrams
* ML methodology
* Historical dataset methodology
* Backtesting methodology
* Testing
* Limitations
* Future architecture
* Technical discussion

---

# 28. SCREENSHOTS AND DIAGRAMS

Use actual project screenshots and diagrams when available.

Potential visuals include:

* System architecture
* Data flow
* Scraping pipeline
* AI/LLM pipeline
* Database structure
* UI
* Processing workflow
* ML extension architecture
* Backtesting workflow

Do not fabricate screenshots.

If a diagram can accurately be derived from the actual architecture, create one if appropriate.

---

# 29. ACADEMIC WRITING STYLE

The report must be:

* Formal
* Technical
* Academic
* Professional
* Clear
* Detailed
* Consistent

Avoid:

* Marketing hype
* Casual language
* Unsupported claims
* Excessive repetition
* Generic filler
* AI-sounding phrases
* Fake technical terminology

Write as if the actual project developers are documenting their system for academic evaluation.

---

# 30. REFERENCES

Use genuine references only.

References may include:

* Official technology documentation
* Relevant research papers
* Genuine APIs
* Genuine libraries
* Relevant ML/AI literature
* Financial-data documentation
* Web-scraping documentation
* Other sources actually relevant to Alpha Scout

Do not fabricate papers, authors, URLs, or citations.

---

# 31. PERSONAL INFORMATION RULE

Never invent:

* Student name
* Roll number
* USN
* College
* University
* Department
* Guide
* HOD
* Team members
* Address
* Academic year
* Submission date
* Event name

If missing, ask me.

---

# 32. DOCUMENT EDITING

Use an appropriate reliable DOCX editing method.

Prefer modifying the existing template directly.

Do not convert the template into plain text and rebuild it unless absolutely necessary.

Preserve formatting wherever possible.

---

# 33. FINAL VALIDATION

After generating the report:

1. Reopen/reinspect the generated DOCX.
2. Verify that the file is valid.
3. Verify that the document has at least 40 pages.
4. Verify the table of contents.
5. Verify page numbering.
6. Verify headers and footers.
7. Verify headings.
8. Verify tables.
9. Verify figures.
10. Verify captions.
11. Verify formatting.
12. Verify that placeholders have been replaced.
13. Verify that no accidental placeholders remain.
14. Verify that no major formatting corruption occurred.
15. Verify that the report accurately describes Alpha Scout.
16. Verify that ML content is naturally integrated.
17. Verify that LLM content is accurately described.
18. Verify that proposed ML functionality is not falsely presented as implemented.
19. Verify that no fabricated metrics exist.
20. Verify that no confidential credentials/secrets were inserted.

Fix legitimate issues discovered during validation.

---

# 34. EXACT WORKFLOW

Follow this sequence.

## PHASE 1 — DISCOVERY

Analyze the entire Alpha Scout folder.

Understand the project completely.

Do not edit the report yet.

---

## PHASE 2 — TEMPLATE ANALYSIS

Analyze the entire DOCX template.

Understand its structure and formatting.

Do not edit it yet.

---

## PHASE 3 — PROJECT/TEMPLATE MAPPING

Determine how the actual Alpha Scout project maps to the template.

Identify:

* What content belongs in each section
* What screenshots/diagrams belong where
* What technical information is available
* What information is missing

---

## PHASE 4 — ML OPPORTUNITY ANALYSIS

After understanding the project, independently identify:

* Where ML naturally fits
* What historical data can become useful
* What training opportunities exist
* What classification/prediction opportunities exist
* What backtesting methodology makes sense
* How GPU acceleration could be used
* How ML and LLMs could complement each other
* What future intelligent capabilities could naturally evolve from Alpha Scout

Do not force a predetermined ML architecture.

Use your own technical reasoning.

---

## PHASE 5 — QUESTIONS

If required personal, academic, or project information is missing, stop and ask me for it.

Ask all necessary questions together where possible.

Do not make final document changes that depend on missing information.

---

## PHASE 6 — REPORT GENERATION

After the required information is available:

* Populate the template
* Write the complete report
* Preserve formatting
* Integrate relevant ML content naturally
* Include appropriate LLM/AI content
* Include historical-data concepts
* Include backtesting methodology where appropriate
* Include GPU/ML discussion where appropriate
* Include actual project screenshots/diagrams
* Reach at least 40 meaningful pages

---

## PHASE 7 — VALIDATION

Reinspect the final DOCX.

Check content, formatting, page count, placeholders, tables, figures, headings, numbering, and overall consistency.

---

## PHASE 8 — FINAL OUTPUT

Save the completed report as a separate final DOCX file.

Do not overwrite the original template.

For example, if appropriate:

`Alpha_Scout_Final_Report.docx`

Keep the original template untouched.

Provide a final summary containing:

* Final report filename
* Page count
* Main sections created/filled
* ML-related sections incorporated
* Any assumptions made
* Any remaining information required from me

---

# 35. FINAL DECISION-MAKING PRINCIPLE

When deciding what to put into the report, use this priority order:

1. **Actual Alpha Scout implementation**
2. **Actual DOCX template requirements**
3. **Information explicitly provided by me**
4. **Verified historical project information**
5. **Technically realistic ML/AI extensions**
6. **Academic best practices**
7. **Your own assumptions**

Never let assumptions override actual evidence.

---

# 36. THE FINAL REPORT SHOULD TELL A COHERENT STORY

The final report should make the following progression understandable:

**Real-world information**

↓

**News/web scraping**

↓

**Collected information**

↓

**AI/LLM-based filtering and interpretation**

↓

**Financial/economic significance**

↓

**Potentially affected companies/industries**

↓

**Potential market relevance**

↓

**Historical data accumulation**

↓

**Potential ML dataset**

↓

**Potential ML classification/prediction**

↓

**Historical evaluation/backtesting**

↓

**Continuous improvement and future hybrid ML + LLM architecture**

This progression should only be used where it accurately reflects or reasonably extends the actual project.

The current Alpha Scout implementation must remain clearly identifiable.

Proposed ML capabilities must be distinguishable from currently implemented functionality.

---

# 37. MOST IMPORTANT FINAL INSTRUCTION

**DO NOT RUSH.**

The quality of the report depends on understanding the project before writing it.

First understand Alpha Scout.

Then understand the template.

Then determine what information is missing.

Then determine where ML naturally fits.

Then write the report.

Then validate the DOCX.

Do not start by blindly generating 40 pages.

Do not invent missing technical details.

Do not invent ML results.

Do not redesign the project.

Do not redesign the template unnecessarily.

Create the most technically detailed, academically appropriate, internally consistent, professional report possible from the actual Alpha Scout project and the provided template.



Please take note of the following instructions:
1.	The document should be in Times New Roman, font size 12.( only for content)
2.	Alignment to be followed .
Remaining format no changes (ex: Title , subtile



Additional info (Use if required)
School of Computer Science and Engineering 
COURSE PLAN  Academic Year 2026-27 ODD SEMESTER School/Department of Students School of Computer Science and Engineering 
Name of the Program(s) of Students CIT-Computer Science & Engineering (Internet of Things)
PRC Approval Ref. No. PU/AC-24.7/SOCSE04/CSE/2023-2027 
Semester/Year V / III 
Course Code & Name CSS7000 & Internship 
Credit Structure (L-T-P-C) 0-0-0-2 Contact Hours NTCC
Course In-Charge (IC) Dr. Geetha Arjunan Course Instructor(s) Internship Guides 
Course URL https://presidencyuniversity.linways.com  
