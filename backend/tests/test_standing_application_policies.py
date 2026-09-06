from datetime import date

import pytest

from app.models.browser import ApplicationFormField, FieldType
from app.services.field_mapping_service import FieldMappingService
from app.services.policy_service import StandardApplicationPolicy, WorkAuthorizationService


def field(label, *, options=None, kind=FieldType.text, required=True):
    return ApplicationFormField(field_id=label, label=label, normalized_label="", field_type=kind, required=required, options=options or [])


@pytest.mark.parametrize(("label", "answer"), [
    ("First Name", "Alex"), ("Last Name", "Morgan"),
    ("Full Name", "Alex Morgan"), ("Preferred Name", "Alex"),
    ("Email", "alex.morgan@example.com"), ("Phone", "+1 (555) 010-0142"),
    ("Street Address", "100 Example Avenue"), ("City", "Metro City"),
    ("State", "EX"), ("ZIP Code", "00000"), ("Country", "United States"),
    ("Date of Birth", "01/01/1990"), ("Are you over 18?", "YES"),
])
def test_identity_contact_address_and_age(label, answer):
    mapped = FieldMappingService(date(2026, 9, 2)).map(field(label))
    assert mapped.mapped_answer == answer and mapped.write_allowed


def test_dob_date_control_and_required_middle_name_safeguard():
    mapper = FieldMappingService(date(2026, 9, 2))
    assert mapper.map(field("Date of Birth", kind=FieldType.date)).mapped_answer == "1990-01-01"
    assert mapper.map(field("Middle Name", required=False)).mapped_answer is None
    assert mapper.map(field("Middle Name")).requires_human_review


@pytest.mark.parametrize(("label", "answer"), [
    ("Are you legally authorized to work in the US?", "YES"),
    ("Will you require sponsorship at any point?", "YES"),
    ("Current immigration status", "Example Work Visa"), ("Current visa", "Example Work Visa"),
    ("Do you require an H-1B transfer?", "YES"), ("Do you require a new H-1B lottery?", "NO"),
    ("H-1B expiration date", "12/31/2030"), ("Are you a U.S. citizen?", "NO"),
    ("Are you a permanent resident / green-card holder?", "NO"),
])
def test_work_authorization_semantic_equivalents(label, answer):
    result = WorkAuthorizationService().assess(label)
    assert result.answer == answer and not result.requires_human_review


def test_dynamic_availability_notice_and_location_preferences():
    mapper = FieldMappingService(date(2026, 9, 2))
    assert mapper.map(field("When can you start?", kind=FieldType.date)).mapped_answer == "2026-09-16"
    assert mapper.map(field("Earliest start month")).mapped_answer == "September 2026"
    assert mapper.map(field("Notice period")).mapped_answer == "2 weeks"
    assert mapper.map(field("Preferred work location")).mapped_answer == "Remote US"
    for label, expected in (("Can you work from our SF office?", "YES"), ("Are you available for hybrid work?", "YES"), ("Can you work remotely in the US?", "YES"), ("Would you move for this job?", "NO"), ("Relocation assistance needed?", "NO")):
        assert mapper.map(field(label)).mapped_answer == expected


@pytest.mark.parametrize(("label", "options", "answer"), [
    ("Gender", ["Woman", "Man", "Decline"], "Man"),
    ("Race", ["Asian", "White", "Decline"], "Asian"),
    ("Are you Hispanic or Latino?", ["Yes", "Not Hispanic or Latino"], "Not Hispanic or Latino"),
    ("Pronouns", ["She/Her", "He/Him"], "He/Him"),
    ("Sexual orientation", ["Straight", "Decline"], "Straight"),
    ("Are you transgender?", ["Yes", "Not transgender"], "Not transgender"),
    ("Veteran classification", ["I am not a protected veteran", "Decline"], "I am not a protected veteran"),
    ("Do you identify as having a disability?", ["Yes", "No, I do not have a disability"], "No, I do not have a disability"),
])
def test_approved_demographics_are_selected_instead_of_declined(label, options, answer):
    mapped = FieldMappingService().map(field(label, options=options, kind=FieldType.select))
    assert mapped.mapped_answer == answer and mapped.write_allowed


def test_salary_policy_is_safe_and_range_aware():
    mapper = FieldMappingService()
    assert mapper.map(field("Minimum acceptable salary", kind=FieldType.number)).mapped_answer == "180000"
    assert mapper.map(field("Compensation expectation")).mapped_answer == "Open to discussing compensation within the posted range."
    assert mapper.map(field("Desired salary", kind=FieldType.number)).requires_human_review
    assert mapper.map(field("Desired salary", kind=FieldType.number), salary_min=180000, salary_max=350000).mapped_answer == "200000"
    assert mapper.map(field("Desired salary", kind=FieldType.number), salary_min=300000, salary_max=400000).mapped_answer == "300000"
    history = mapper.map(field("Current salary", options=["Prefer not to answer"], kind=FieldType.select))
    assert history.mapped_answer == "Prefer not to answer" and history.write_allowed


@pytest.mark.parametrize(("label", "answer"), [
    ("Are you willing to travel?", "Up to 100%"), ("Weekend availability", "NO"),
    ("Can we contact your current employer?", "YES"), ("Current employer", "Northstar Labs"),
    ("Do you consent to a drug test?", "YES"), ("Do you consent to a background check?", "YES"),
    ("Is a relative employed by company?", "NO"), ("Have you been a government employee?", "NO"),
    ("Are you subject to a non-compete?", "NO"), ("Have you been convicted of a crime?", "NO"),
    ("Do you have a conflict of interest?", "NO"), ("Do you currently have an export-control restriction?", "NO"),
    ("Are you currently bound by arbitration?", "NO"), ("Do you agree to the privacy policy?", "YES"),
])
def test_routine_schedule_employment_and_compliance(label, answer):
    mapped = FieldMappingService().map(field(label))
    assert mapped.mapped_answer == answer and mapped.write_allowed


def test_driver_license_details_export_and_new_arbitration_require_review():
    mapper = FieldMappingService()
    assert mapper.map(field("Do you have a valid driver's license?")).mapped_answer == "YES"
    for label in ("Driver's license number", "Are you a U.S. person under ITAR?", "Will an export license be required?", "Do you agree to this company's binding arbitration agreement?"):
        assert mapper.map(field(label)).requires_human_review


def test_truthfulness_and_signature_require_validated_context():
    policy = StandardApplicationPolicy()
    certification = policy.resolve("I certify that the information provided is true and accurate", certification_allowed=False)
    signature = policy.resolve("Electronic signature", certification_allowed=False)
    assert certification.requires_human_review and signature.requires_human_review
    assert policy.resolve("I certify that the information provided is true and accurate", certification_allowed=True).answer == "YES"
    assert policy.resolve("Electronic signature", certification_allowed=True).answer == "Alex Morgan"


def test_discovery_and_motivation_remain_semantically_mapped():
    mapper = FieldMappingService()
    assert mapper.map(field("How did you learn about this position?", options=["Google Search", "LinkedIn"])).mapped_answer == "LinkedIn"
    motivation = mapper.map(field("What kind of work excites you?"))
    assert motivation.write_allowed and "research and evaluation" in motivation.mapped_answer
