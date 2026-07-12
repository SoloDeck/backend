# Lead Qualification Framework

## Purpose

The Lead Qualification Framework provides a profession-independent methodology for evaluating client inquiries.

It works together with a profession-specific qualification guide to:

- Interpret the inquiry
- Identify missing information
- Generate clarification questions
- Assign a **HOT**, **WARM**, or **COLD** lead score

The framework evaluates inquiry quality only. It does not evaluate client credibility, payment reliability, commercial viability, or legal matters.

---

## Supported Professions

Current supported professions:

- Software Development
- UI/UX Design
- Graphic Design
- Digital Marketing
- Copywriting
- Photography & Videography

If the selected profession is unsupported, or the inquiry clearly belongs to another profession, return **Out of Scope**.

---

## Qualification Principles

- Evaluate only information provided by the client.
- Unknown information remains unknown.
- Use the profession-specific qualification guide for interpretation.
- Prefer clarification over unsupported assumptions.
- Report observations; do not make business decisions.

---

## Evaluation Dimensions

Each inquiry is evaluated across five dimensions.

| Dimension         | Score   |
|-------------------|--------:|
| Project Objective |     0–2 |
| Deliverables      |     0–2 |
| Budget            |     0–2 |
| Timeline          |     0–2 |
| Scope Consistency |     0–2 |

Maximum score: **10**

---

## Lead Score

| Total | Classification |
|------:|----------------|
|  8–10 | HOT            |
|   5–7 | WARM           |
|   0–4 | COLD           |

General interpretation:

- **HOT** — Proposal can generally be prepared with minimal clarification.
- **WARM** — Core project is understood but clarification is required.
- **COLD** — Insufficient information for proposal preparation.

---

## Qualification Process

```
Client Inquiry
        │
        ▼
Receive Selected Profession
        │
        ▼
Load Qualification Guide
        │
        ▼
Interpret Inquiry
        │
        ▼
Evaluate Five Dimensions
        │
        ▼
Calculate Lead Score
        │
        ▼
Generate Qualification Result
```

---

## Output

Every qualification result should include:

| Field                   | Required       |
|-------------------------|----------------|
| Project Type            | ✓              |
| Budget Signal           | ✓              |
| Timeline Signal         | ✓              |
| Urgency Signal          | ✓              |
| Positive Signals        | ✓              |
| Negative Signals        | ✓              |
| Lead Score              | ✓              |
| Reasoning               | ✓              |
| Suggested Actions       | ✓              |
| Clarification Questions | ✓              |
| Estimated Price Range   | When estimable |