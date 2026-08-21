"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole stub is ten times the input tokens of sending each field the section that could possibly
state it. THE BILL IS DRIVEN BY THE CONTEXT, NOT BY THE QUESTION.
"""

SECTION_HINTS = {
    "employee_name": ["Employee"],
    "employer_name": ["Employer"],
    "pay_frequency": ["Pay Frequency"],
    "pay_period_end": ["Pay Period End"],
    "ytd_base_pay": ["Year-to-Date Earnings"],
    "ytd_overtime_pay": ["Year-to-Date Earnings"],
    "overtime_periods_paid": ["Year-to-Date Earnings"],
    "overtime_periods_total": ["Year-to-Date Earnings"],
    "ytd_bonus_pay": ["Year-to-Date Earnings"],
    "bonus_recurring": ["Year-to-Date Earnings", "Bonus History"],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if s["name"] in want]
    return hit or list(secs)


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
