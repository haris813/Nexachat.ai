# Demo walkthrough

Recommended length: 6–8 minutes. Use demo AI/search and mock WhatsApp for the safety demo; use configured live providers only when you want real current citations.

## Preparation

1. Start with a clean guest session or registered demo account.
2. Import `data/demo/contacts.csv`.
3. Keep `data/demo/sales.csv` ready for upload.
4. Confirm the activity rail is visible on a desktop-width browser.
5. If using live search, verify the provider key and current date before recording.

## Script

### 1. Product shell — 45 seconds

Show the three-pane layout, light/dark theme, new-task cards, chat search, model/persona selectors, activity rail, artifact library, contacts, analytics, and mobile-responsive intent.

Say: “Simple prompts stream like chat; research, files, and deliverables become visible plans with auditable tools.”

### 2. Plan-first research — 90 seconds

Prompt: “Research the five richest people in the world and create an Excel report with rank, net worth, source, and a comparison chart.”

Review the proposed steps before approving. Call out search progress, citations, retrieval time, workbook validation, and the download card. Open the workbook and show the styled Data table, freeze panes, filters, chart, Sources, and Metadata sheets.

If live search is disabled, demonstrate the refusal and explain that demo mode does not invent current rankings.

### 3. File analysis and presentation — 90 seconds

Upload `data/demo/sales.csv`. Show progress and the attached-file chip.

Prompt: “Analyze this file, calculate quarter-over-quarter growth, and create a concise executive presentation.”

Show extraction status, calculation/generation steps, the chart, and the downloadable 16:9 deck. Open it and inspect title, agenda, content, chart, and source slides.

### 4. Voice — 60 seconds

Record: “Summarize the sales risks and draft two actions for next quarter.”

Pause/resume, stop, preview the audio, transcribe it, edit one word, and insert the transcript into the composer. Optionally use text-to-speech on the answer.

### 5. Safe WhatsApp — 90 seconds

Open Contacts, import or select Rahul, then request: “Message Rahul on WhatsApp that I’ll be 20 minutes late.”

Show that the plan stops at a prepared action. In the confirmation dialog, point to recipient, masked phone, exact content, type, and `mock` mode. Demonstrate that Send is disabled until the checkbox is selected. Confirm in mock mode and show the audit status/provider id.

Say: “The model cannot bypass this screen; the backend provider also refuses rows without a confirmed timestamp.”

### 6. Engineering proof — 60 seconds

Show analytics, `/api/tools`, test results, CI workflow, migration, Docker Compose services, and the security document. Mention owner isolation, CSRF, SSRF protection, encrypted contacts, file-signature/ZIP defenses, and artifact reopening.

## Suggested screenshots

- Welcome workspace with prompt cards and activity rail
- Approved live-research plan in progress
- Excel workbook Data and Sources sheets
- Presentation overview with multiple slide thumbnails
- Voice transcript editor
- WhatsApp confirmation dialog in mock mode
- Analytics dashboard
- Green CI job summary

Never include API keys, full phone numbers, private file content, session cookies, or a real Meta send in portfolio screenshots.
