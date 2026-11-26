# Treasury Control Tower

A personal "finance department in a box". Every quarter it audits all my credit cards, savings accounts and investment funds, then shows the results on one dashboard. It answers the questions a company treasurer would ask:

- How much cash do I have, and how many months of expenses does it cover?
- How much do my credit cards really cost me in fees, insurance and interest, and are the rewards worth it?
- Is any money sitting idle when it could be earning more?
- Is too much money concentrated in one bank, beyond what deposit insurance protects?
- Did anything unusual happen that needs a follow-up?

> **Privacy:** this repository holds only the tools and the instructions. All real financial data (bank statements, spreadsheets, reports and account details) stays on my computer and is never uploaded.

## The problem it solves

With many cards, accounts and banks, things slip through the cracks: a missing statement, an unexpected fee, a quarter closed with numbers that don't add up. Doing it by hand takes hours and is easy to get wrong.

This project turns the review into a repeatable routine:

1. **Check first.** Before the audit starts, it confirms that every statement and export for the period is on hand. If something is missing, it stops and says exactly what is missing.
2. **Follow the steps in order.** The audit has fixed steps, and a step cannot run before the one it depends on is done.
3. **Cross-check everything.** Every time the numbers are updated, about 400 automatic checks confirm the totals match across sources.
4. **Keep a memory.** Issues found in past years are tracked separately from new ones, so an old problem is never forgotten and never counted twice.
5. **Report.** The dashboard and a quarterly PDF report come from the same numbers, so they always agree.

## How it works

```
Bank statements + expense app + shared-expenses app
                │
                ▼
     1. Completeness check  ──►  stop if anything is missing
                │
                ▼
     2. Audit spreadsheets  (the single source of truth: every decision is made here)
                │
                ▼
     3. Update script  ──►  reads the spreadsheets without changing them,
                │            cross-checks the totals, prepares the dashboard data
                ▼
     4. Dashboard (8 screens)  +  quarterly PDF reports  +  final quality check
```

The key rule: **decisions are made in one place only, the spreadsheets.** The scripts only read, add up and verify. The dashboard only displays. This keeps the numbers consistent and easy to trace back to the source.

## What the dashboard shows

| Screen | What it answers |
|---|---|
| Treasury | Cash position, months of coverage, card debt vs. available credit, total banking cost, return on cash, bank concentration |
| Summary | The quarter at a glance and what needs attention |
| Credit cards | Spending by card and category, fees and interest, rewards received |
| Banks and cash | Money in and out each month, balances, transfers between my own accounts |
| Products | Whether each card or account is worth keeping (cost vs. benefit) |
| Issues | Open, monitored and resolved findings |
| Timeline | Which quarters are audited and how past issues were followed up |
| Data quality | Results of all automatic checks |

## What it is built with

- **Excel spreadsheets:** where the audit work and all decisions live.
- **Python scripts:** small programs that check, cross-check and prepare the data. They use three free add-ons: one reads Excel files, one creates PDF reports, and one reads PDF bank statements.
- **A simple web page:** the dashboard opens with a double-click in any browser. No installation, no server and no internet connection needed. Charts are drawn with Chart.js, a free charting library included in the project.

## What's in this repository

| Folder or file | What it is |
|---|---|
| `index.html`, `css/`, `js/` | The dashboard |
| `scripts/` | The programs: completeness check, data update, PDF reports, quality checks, treasury inputs |
| `scripts/tests/` | Automatic tests for the completeness check |
| `examples/` | A sample product list with fake account numbers, to show the format |
| `docs/` | Dashboard guide and audit methodology (in Spanish) |
| `PROCEDIMIENTO_TRIMESTRAL.md` | Step-by-step quarterly procedure (in Spanish) |
| `ARQUITECTURA.md` | Design decisions for running the audit year after year (in Spanish) |

Not in the repository, kept only on my computer: the spreadsheets, bank statements, dashboard data, PDF reports, check results and the real list of accounts.

## How to run it

Requires Python 3.9 or newer.

```
pip install -r requirements.txt                                        # install the three add-ons
copy examples\audit_sources.example.json scripts\audit_sources.json   # then list your own products in it
python scripts/audit_pipeline.py preflight --period 2026Q4             # 1. is everything on hand?
python scripts/refresh_dashboard.py                                    # 3. update the dashboard data
```

Then open `index.html`. To close a full quarter in one go (update, PDF reports and final check), run `scripts\cierre_trimestral.bat 2026 4`.

Two practical notes:
- After editing a spreadsheet, open it in Excel and **save it** before updating. The update reads the values Excel calculated.
- Some banks send password-protected PDFs. The password is typed in for the session only and is never saved anywhere.

## The quarterly routine

1. **Every month:** statements arrive by email and are filed automatically. No audit yet.
2. **After each quarter:** export the expense and shared-expenses apps.
3. **Run the completeness check.** If it says GO, update the audit spreadsheets.
4. **Update the dashboard,** produce the PDF reports and run the final quality check.

## Testing

```
python scripts/tests/test_audit_pipeline.py
```

Runs 16 realistic situations: everything in place, a missing statement, a missing export, a locked PDF, a card replaced by another bank, a year-end audit, steps run out of order, and an old issue reappearing. The tests use made-up files only, never real data.

Before publishing any change:

```
python scripts/repo_safety_check.py
```

This scans everything about to be uploaded and blocks the upload if it finds spreadsheets, statements, reports, personal folder paths, emails, account numbers or large amounts.

## Privacy and security

- **Nothing is uploaded unless it is on an approved list.** Any new file is kept private by default.
- **Spreadsheets, statements, PDFs, images and data files are never uploaded.**
- **The scripts never change the spreadsheets** when updating the dashboard, and they confirm each file is unchanged afterwards.
- **No passwords are stored** anywhere in the project.
- **Accounts are identified only by their last 4 digits** (for example `*1234`).

## Status

- 2025 audited and frozen as the reference year. Q1–Q3 2026 closed. Q4 2026 is audited in January 2027.
- Completeness check, data update, dashboard, PDF reports and quality checks are all working.
- Treasury screen added in November 2026.
- Built around my own spreadsheets. Using it with different spreadsheets would need some adjustments to the settings, the product list and the card names.

## Next steps

- Currency exposure: what I actually get when income in US dollars is converted to pesos, compared with the official rate.
- A 13-week cash forecast.
- A demo version with fake data, so anyone can explore the dashboard.
- Automatic tests and privacy checks on every upload to GitHub.
