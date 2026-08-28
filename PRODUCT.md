# Verbatim

## What it is

Résumé screening for small businesses. An opening is advertised wherever the company already
advertises; applications are received through a link Verbatim hosts. Every résumé is parsed
deterministically, scored once against a rubric the company wrote, and presented to a person
with the exact sentences from the résumé that justify each score.

## The mechanism

**Every claim is a literal quote, verified against the source before anyone sees it.** The model
rates criteria and quotes the résumé; Python checks each quote appears verbatim in the extracted
text and computes the ranking number from the rubric weights. A quote that cannot be found flags
the evaluation for review rather than being shown as fact.

That is the difference from the category. Competing tools return a score. Verbatim returns the
score, the sentence it came from, and its position in the document.

## Users and jobs

**Primary: whoever screens at a small company.** Usually not a full-time recruiter — an office
manager, a founder, an operations lead who also does hiring. They face 200–800 applications per
opening, read the first fifty carefully and skim the rest, and know that is not a fair process.

Their job: reach a defensible shortlist without spending three days in a PDF viewer.

**Secondary: the applicant.** Sees only the company's opening and an application form. They
never see Verbatim's brand as the primary identity, never see the rubric, and never learn a
score. Their job: apply in under three minutes from a phone.

## What is true and must stay true

- **A person decides. Always.** The system scores and explains; it never rejects, never ranks
  someone out of consideration, and never sends anything without an explicit human approval.
  This is a legal requirement (GDPR art. 22) and the product's position, not a limitation.
- **Age, gender, nationality, origin, photo, marital and family status are not modelled** in the
  output schema and the evaluator is instructed not to infer them.
- **Hidden text is detected and shown, never obeyed.** Résumés that conceal instructions from
  human readers are surfaced to the reviewer with the concealed text as evidence, and scored on
  the visible text only.
- **Every human decision is recorded with its reason**, alongside the model's score, so the
  disagreement between the two is preserved.
- **Consent is explicit and timestamped**; résumés are deleted six months after an opening
  closes.

## Operating context

One company per deployment. The company's own name and colours own the public application page;
Verbatim signs it discreetly. The panel is Verbatim's.

Openings run for weeks. Evaluation is batched and can take up to a day, so the panel shows a
candidate's résumé, extracted text and integrity flags from the moment they apply, and adds the
score when it arrives. It never promises a time.

## Terminology

| Term | Meaning |
|---|---|
| Opening | A job being filled |
| Application | One candidate's submission to one opening |
| Rubric | Weighted criteria the company writes; weights sum to 100 |
| Evidence | A literal quote from the résumé backing a criterion score |
| Integrity | Whether a résumé hides text from human readers |
| Review flag | An objection from our verification, not a statement about the candidate |

## Platform

`web`. Desktop-first for the panel (a screening session is a desk task), mobile-first for the
public application page (people apply from phones).

## Stack

Decided before this document: Python 3.14 · FastAPI · PostgreSQL 16 · React 19 + Vite +
TypeScript. Sessions are `HttpOnly` cookies. No CSS framework in use yet — that choice is open.

## Accessibility

Not yet audited. Target: keyboard-operable panel and WCAG AA contrast, because a screening
session is a long reading task and the panel is used all day.

## Language

Interface copy in English. Code, comments and documentation in English (see `CLAUDE.md`).
Market is Spain and Latin America, so résumés arrive in Spanish and English and the extraction
and search must handle both.

## Brand commitments

- Name: **Verbatim**, chosen 2026-08-27.
- The public application page is branded as the hiring company, with a discreet Verbatim
  signature. Confirmed by the owner.
- No claim that the system decides, filters or rejects. It reads and evidences; people decide.
