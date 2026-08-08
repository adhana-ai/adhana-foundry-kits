"""Write the 18 synthetic documents into data/corpus/ and the labelled spans into
data/labelled.jsonl. THE ONE DESIGN DECISION IN THIS FILE, AND WHY IT IS THE WHOLE INSTRUMENT.

docs-extract's build_corpus.py builds a document from a record's prose and its gold from the SAME
record's structured modules — two views of one source, kept apart so grading never writes the
answer into the question. This kit has no external record to split that way: every document here
is invented for the purpose, which is exactly why the label has to come from the SAME PLACE the
document text does, mechanically, rather than being retyped by hand into a second file.

⚠︎ THE LABEL IS NEVER RETYPED. Each entry below is one dict of named entities — a name, an SSN, an
address, and so on, each tagged with its category — and ONE template string with `{placeholders}`
for them. `document()` renders the template; `labels()` reads the same dict. There is no path by
which a document's text and its labelled spans can disagree, because they are never independently
authored: retyping the same value twice (or worse, copy-pasting it and drifting) is exactly the
failure `evals/check_labels.py` exists to catch in a kit that authors its gold by hand, and this
kit avoids the failure mode entirely by construction instead.

⚠︎ 18 DOCUMENT "KINDS", DELIBERATELY NO TWO ALIKE. A corpus that is 18 copies of one letter with
the names swapped measures how well a detector reads one house style. These vary structure (a
letter, an email with headers, a form with labelled fields, an invoice table, a report) and format
per category (an SSN written dashed in one document and run-together in another; a DOB as
04/12/1988 in one and "March 22, 1990" in the next) — see data/corpus/SOURCES.md for the coverage
table this was checked against before anything shipped.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")
LABELLED = os.path.join(HERE, "data", "labelled.jsonl")

# Each entry: id, a template with named {placeholders}, and the entities that fill them —
# {placeholder_name: (exact_text, CATEGORY)}. Order within `entities` is the order spans are
# written to labelled.jsonl; it has no bearing on where they land in the rendered document.
DOCS = [
    {
        "id": "hr-benefits-letter-01",
        "template": (
            "Dear {name},\n\n"
            "Your enrollment in the January benefits cycle is confirmed. Employee SSN {ssn}, "
            "DOB {dob}.\n\n"
            "Please verify your contact details on file: {email}, {phone}, {address}.\n\n"
            "Your relocation stipend will be applied to the card ending in {card} within 5 "
            "business days.\n\n"
            "— People Operations\n"
        ),
        "entities": {
            "name": ("Morgan Ellis", "NAME"),
            "ssn": ("219-08-4471", "SSN"),
            "dob": ("04/12/1988", "DOB"),
            "email": ("morgan.ellis@example-corp.com", "EMAIL"),
            "phone": ("(415) 555-0138", "PHONE"),
            "address": ("2200 Alder Court, Springfield, IL 62704", "ADDRESS"),
            "card": ("4485 9821 7734 0092", "CARD"),
        },
    },
    {
        "id": "hr-termination-letter-01",
        "template": (
            "NORTHGATE MANUFACTURING — HUMAN RESOURCES\n"
            "Notice of Separation\n\n"
            "This letter confirms the employment of {name} (SSN: {ssn}) ends effective the last "
            "business day of this month.\n\n"
            "Final correspondence will be mailed to {address}. A copy of this notice has also "
            "been sent to {email}.\n\n"
            "Questions about final pay should be directed to the HR hotline at {phone}.\n\n"
            "Sincerely,\nHuman Resources\n"
        ),
        "entities": {
            "name": ("Priya Nathan", "NAME"),
            "ssn": ("219084471", "SSN"),
            "address": ("48 Birchwood Lane, Unit 3B, Portland, OR 97205", "ADDRESS"),
            "email": ("priya.nathan@northgate-mail.com", "EMAIL"),
            "phone": ("212.555.0199", "PHONE"),
        },
    },
    {
        "id": "customer-support-email-01",
        "template": (
            "From: support@shipfast-orders.com\n"
            "To: {email}\n"
            "Subject: Re: Order #58213 — delayed shipment\n\n"
            "Hi {name},\n\n"
            "Thanks for reaching out. I can see order #58213 is still in transit to {address}. "
            "I've flagged it for expedited handling.\n\n"
            "If you don't see movement by Friday, call us directly at {phone} and reference this "
            "ticket.\n\n"
            "— ShipFast Customer Care\n"
        ),
        "entities": {
            "name": ("Devon Ruiz", "NAME"),
            "email": ("devon.ruiz84@webmailbox.net", "EMAIL"),
            "phone": ("415-555-0192", "PHONE"),
            "address": ("77 Harborview Drive, Apt 12, Tacoma, WA 98402", "ADDRESS"),
        },
    },
    {
        "id": "it-helpdesk-ticket-01",
        "template": (
            "IT HELPDESK — Identity Verification Ticket #7734\n\n"
            "Requestor: {name}\n"
            "Contact email on file: {email}\n"
            "Callback number: {phone}\n\n"
            "Verification question answered correctly (date of birth {dob}). Password reset "
            "authorized and a temporary credential has been issued.\n\n"
            "Ticket closed by: IT Service Desk\n"
        ),
        "entities": {
            "name": ("Alan Whitfield", "NAME"),
            "email": ("a.whitfield@corplink.io", "EMAIL"),
            "phone": ("(646) 555-0173", "PHONE"),
            "dob": ("07-19-1982", "DOB"),
        },
    },
    {
        "id": "medical-intake-note-01",
        "template": (
            "PATIENT INTAKE — New Patient Form\n\n"
            "Patient name: {name}\n"
            "Date of birth: {dob}\n"
            "Social Security Number: {ssn}\n"
            "Home address: {address}\n"
            "Best contact number: {phone}\n\n"
            "Chief complaint: recurring lower back pain, onset approximately three weeks ago. No "
            "known drug allergies reported at intake.\n"
        ),
        "entities": {
            "name": ("Carla Bennett", "NAME"),
            "dob": ("March 22, 1990", "DOB"),
            "ssn": ("588-21-0093", "SSN"),
            "address": ("910 Meadowlark Way, Boise, ID 83702", "ADDRESS"),
            "phone": ("208-555-0164", "PHONE"),
        },
    },
    {
        "id": "insurance-claim-correspondence-01",
        "template": (
            "MERIDIAN MUTUAL INSURANCE — Claim Correspondence\n"
            "Claim Reference: MC-88234\n\n"
            "Dear {name} (DOB {dob}),\n\n"
            "We have received your claim documentation. Our records show your Social Security "
            "Number as {ssn} and your address of record as {address}.\n\n"
            "Please confirm receipt by replying to {email} or calling our claims line at "
            "{phone}.\n\n"
            "Thank you,\nClaims Department\n"
        ),
        "entities": {
            "name": ("Yusuf Kader", "NAME"),
            "dob": ("12 Nov 1975", "DOB"),
            "ssn": ("402-91-3358", "SSN"),
            "address": ("14 Windermere Close, Hartford, CT 06103", "ADDRESS"),
            "email": ("yusuf.kader77@mailhub.co", "EMAIL"),
            "phone": ("+1 860-555-0121", "PHONE"),
        },
    },
    {
        "id": "invoice-01",
        "template": (
            "INVOICE #INV-20394\n"
            "Bill To: {name}\n"
            "{address}\n\n"
            "Description                          Amount\n"
            "Consulting services — March          $2,450.00\n"
            "Total Due                            $2,450.00\n\n"
            "Payment charged to card {card}. A receipt copy has been emailed to {email}.\n\n"
            "Thank you for your business.\n"
        ),
        "entities": {
            "name": ("Rosalind Ferro", "NAME"),
            "address": ("3390 Ashgrove Terrace, Nashville, TN 37211", "ADDRESS"),
            "card": ("4111-2233-4455-6677", "CARD"),
            "email": ("billing@ferro-consulting.com", "EMAIL"),
        },
    },
    {
        "id": "bank-statement-notice-01",
        "template": (
            "FIRST HARBOR BANK — Statement Notice\n\n"
            "Account Holder: {name}\n"
            "Mailing Address: {address}\n\n"
            "Your linked debit card ending pattern {card} was used for 4 transactions this cycle "
            "totaling $312.87.\n\n"
            "Questions? Call cardholder services at {phone}.\n"
        ),
        "entities": {
            "name": ("Trevor Okafor", "NAME"),
            "address": ("512 Copperfield Row, Denver, CO 80203", "ADDRESS"),
            "card": ("5500 0000 0000 0004", "CARD"),
            "phone": ("(303) 555-0146", "PHONE"),
        },
    },
    {
        "id": "apartment-lease-notice-01",
        "template": (
            "RIVERSTONE APARTMENTS — Lease Renewal Notice\n\n"
            "Tenant: {name} (DOB {dob})\n"
            "Unit Address: {address}\n\n"
            "Your current lease expires in 60 days. To renew, confirm via {email} or call the "
            "leasing office at {phone}.\n\n"
            "We look forward to another year.\n"
        ),
        "entities": {
            "name": ("Ingrid Solberg", "NAME"),
            "dob": ("1990-03-22", "DOB"),
            "address": ("88 Fenwick Row, Unit 4, Minneapolis, MN 55401", "ADDRESS"),
            "email": ("ingrid.solberg@leasehub.net", "EMAIL"),
            "phone": ("612-555-0187", "PHONE"),
        },
    },
    {
        "id": "gym-membership-form-01",
        "template": (
            "IRONPEAK FITNESS — Membership Application\n\n"
            "Full legal name: {name}\n"
            "DOB: {dob}\n"
            "Mobile: {phone}\n"
            "Email: {email}\n\n"
            "Membership tier selected: Gold (unlimited classes). Initiation fee waived through "
            "promotion code SPRING10.\n"
        ),
        "entities": {
            "name": ("Marcus Delaney", "NAME"),
            "dob": ("11/30/1995", "DOB"),
            "phone": ("917-555-0129", "PHONE"),
            "email": ("mdelaney95@fitmail.com", "EMAIL"),
        },
    },
    {
        "id": "school-enrollment-form-01",
        "template": (
            "WILLOWBROOK ELEMENTARY — New Student Enrollment\n\n"
            "Student name: {child_name}\n"
            "Date of birth: {dob}\n"
            "Parent/Guardian: {parent_name}\n"
            "Home address: {address}\n"
            "Contact phone: {phone}\n"
            "Contact email: {email}\n\n"
            "Enrollment accepted for the upcoming fall term pending immunization record "
            "submission.\n"
        ),
        "entities": {
            "child_name": ("Ezra Lindqvist", "NAME"),
            "dob": ("September 8, 2016", "DOB"),
            "parent_name": ("Helena Lindqvist", "NAME"),
            "address": ("27 Thistledown Ave, Ann Arbor, MI 48104", "ADDRESS"),
            "phone": ("734-555-0155", "PHONE"),
            "email": ("helena.lindqvist@parentmail.org", "EMAIL"),
        },
    },
    {
        "id": "subscription-cancellation-email-01",
        "template": (
            "From: accounts@streamplus.com\n"
            "To: {email}\n"
            "Subject: Your cancellation is confirmed\n\n"
            "Hi {name},\n\n"
            "Your StreamPlus subscription has been cancelled effective today. No further charges "
            "will be made to the card ending in {card}.\n\n"
            "If this was a mistake, call us at {phone} within 48 hours to reverse it.\n\n"
            "— StreamPlus Accounts Team\n"
        ),
        "entities": {
            "name": ("Bianca Torres", "NAME"),
            "email": ("bianca.torres@streammail.io", "EMAIL"),
            "card": ("4916 3820 7714 5502", "CARD"),
            "phone": ("702-555-0113", "PHONE"),
        },
    },
    {
        "id": "warranty-registration-01",
        "template": (
            "SUNVALE APPLIANCES — Warranty Registration\n\n"
            "Owner name: {name}\n"
            "Mailing address: {address}\n"
            "Email: {email}\n"
            "Phone: {phone}\n\n"
            "Product registered: SunVale Model SV-220 Refrigerator. Warranty period: 5 years "
            "parts and labor from date of registration.\n"
        ),
        "entities": {
            "name": ("Owen Kasprzak", "NAME"),
            "address": ("6601 Larkspur Blvd, San Antonio, TX 78201", "ADDRESS"),
            "email": ("owen.k@registermail.com", "EMAIL"),
            "phone": ("+1 210-555-0142", "PHONE"),
        },
    },
    {
        "id": "car-rental-agreement-01",
        "template": (
            "SUMMIT CAR RENTAL — Rental Agreement #RA-55291\n\n"
            "Renter: {name}\n"
            "DOB: {dob}\n"
            "Home address on file: {address}\n"
            "Phone: {phone}\n\n"
            "Security deposit authorized on card {card}. Vehicle: compact sedan, 3-day rental.\n\n"
            "Please inspect the vehicle before departure and report any damage immediately.\n"
        ),
        "entities": {
            "name": ("Fatima Zeidan", "NAME"),
            "dob": ("1982-01-09", "DOB"),
            "address": ("412 Cottonwood Drive, Salt Lake City, UT 84101", "ADDRESS"),
            "phone": ("801-555-0176", "PHONE"),
            "card": ("6011 0009 9013 9424", "CARD"),
        },
    },
    {
        "id": "mortgage-application-01",
        "template": (
            "CRESTLINE MORTGAGE — Loan Application Summary\n\n"
            "Applicant: {name}\n"
            "Social Security Number: {ssn}\n"
            "Date of birth: {dob}\n"
            "Current address: {address}\n"
            "Phone: {phone}\n"
            "Email: {email}\n\n"
            "Requested loan amount: $340,000 for a 30-year fixed mortgage. Application received "
            "and assigned to underwriting.\n"
        ),
        "entities": {
            "name": ("Gerald Huang", "NAME"),
            "ssn": ("441-62-8807", "SSN"),
            "dob": ("05/14/1979", "DOB"),
            "address": ("3050 Windmere Court, Raleigh, NC 27609", "ADDRESS"),
            "phone": ("919-555-0134", "PHONE"),
            "email": ("gerald.huang@homeloanmail.com", "EMAIL"),
        },
    },
    {
        "id": "jury-duty-notice-01",
        "template": (
            "COUNTY COURT — Jury Duty Summons\n\n"
            "Name: {name}\n"
            "DOB: {dob}\n"
            "Social Security Number (last verification only): {ssn}\n"
            "Address of record: {address}\n\n"
            "You are summoned to appear for jury service on the date indicated in the enclosed "
            "schedule. Failure to appear may result in a court order.\n"
        ),
        "entities": {
            "name": ("Nadia Volkov", "NAME"),
            "dob": ("02/27/1969", "DOB"),
            "ssn": ("356-40-2298", "SSN"),
            "address": ("154 Elmcourt Drive, Albany, NY 12203", "ADDRESS"),
        },
    },
    {
        "id": "background-check-report-01",
        "template": (
            "CLEARPATH SCREENING — Background Check Report\n\n"
            "Subject: {name}\n"
            "SSN {ssn}\n"
            "Date of birth: {dob}\n"
            "Last known address: {address}\n"
            "Phone on file: {phone}\n"
            "Email on file: {email}\n\n"
            "Result: No disqualifying records found in the counties searched. Report finalized "
            "and released to the requesting employer.\n"
        ),
        "entities": {
            "name": ("Terrence Boyle", "NAME"),
            "ssn": ("734519028", "SSN"),
            "dob": ("April 3, 1988", "DOB"),
            "address": ("790 Ridgeline Pass, Tulsa, OK 74103", "ADDRESS"),
            "phone": ("918-555-0159", "PHONE"),
            "email": ("t.boyle.verify@screeningmail.com", "EMAIL"),
        },
    },
    {
        "id": "utility-bill-01",
        "template": (
            "CAPITAL CITY UTILITIES — Monthly Statement\n\n"
            "Account Holder: {name}\n"
            "Service Address: {address}\n\n"
            "Current charges: $118.42. Autopay is enabled on card {card}.\n\n"
            "Manage your account online or update contact details: {email}, {phone}.\n\n"
            "Thank you for choosing Capital City Utilities.\n"
        ),
        "entities": {
            "name": ("Simone Achterberg", "NAME"),
            "address": ("22 Brambleton Way, Richmond, VA 23219", "ADDRESS"),
            "email": ("simone.achterberg@mailpoint.net", "EMAIL"),
            "phone": ("804-555-0188", "PHONE"),
            "card": ("3782 822463 10005", "CARD"),
        },
    },
]


def document(entry):
    """Render one document's text from its template and entities."""
    values = {k: v[0] for k, v in entry["entities"].items()}
    return entry["template"].format(**values)


def labels(entry):
    """The spans that document() put in the text — read from the SAME dict, never retyped."""
    return [{"text": v[0], "category": v[1]} for v in entry["entities"].values()]


def main():
    os.makedirs(CORPUS, exist_ok=True)
    with open(LABELLED, "w", encoding="utf-8") as lf:
        for entry in DOCS:
            text = document(entry)
            with open(os.path.join(CORPUS, "%s.txt" % entry["id"]), "w", encoding="utf-8") as f:
                f.write(text)
            lf.write(json.dumps({"doc": "%s.txt" % entry["id"], "spans": labels(entry)},
                                ensure_ascii=False) + "\n")
    n_spans = sum(len(e["entities"]) for e in DOCS)
    print("build_corpus: %d document(s), %d labelled span(s) -> %s, %s"
          % (len(DOCS), n_spans, os.path.relpath(CORPUS, HERE),
             os.path.relpath(LABELLED, HERE)))


if __name__ == "__main__":
    main()
