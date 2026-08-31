from app.services.identity_service import IdentityService
from app.services.policy_service import AnswerBankService, WorkAuthorizationService


def test_canonical_legal_and_preferred_identity():
    identity = IdentityService().get()
    assert identity.legal_first_name == "Srinikhil Reddy"
    assert identity.legal_last_name == "Parvath"
    assert identity.preferred_first_name == "Nick"
    assert identity.preferred_professional_name == "Nick Parvath"
    assert identity.display_name == "Nick Parvath"
    assert identity.legal_name == "Srinikhil Reddy Parvath"


def test_approved_application_name_mappings():
    service = IdentityService()
    assert service.map_form_field("Given Name").value == "Srinikhil Reddy"
    assert service.map_form_field("Surname").value == "Parvath"
    assert service.map_form_field("Preferred Name").value == "Nick"
    assert service.map_form_field("Professional Name").value == "Nick Parvath"
    assert service.map_form_field("Full Legal Name").value == "Srinikhil Reddy Parvath"


def test_middle_name_is_never_inferred_from_reddy():
    service = IdentityService()
    required = service.map_form_field("Middle Name", required=True)
    optional = service.map_form_field("Middle Name", required=False)
    assert required.value is None
    assert required.requires_human_review is True
    assert optional.value is None
    assert optional.requires_human_review is False
    assert "Reddy" not in (required.value or "")


def test_contact_and_portfolio_mappings():
    service = IdentityService()
    assert service.map_form_field("Email").value == "tonickred@gmail.com"
    assert service.map_form_field("Phone").value == "+1 (612) 447-3136"
    assert service.map_form_field("Portfolio URL").value == "https://nikhil-portfolio-ecru-eight.vercel.app/"
    assert service.map_form_field("LinkedIn URL").value == "https://www.linkedin.com/in/srinikhil-reddy-parvath-42aa46273/"


def test_answer_bank_identity_values_come_from_canonical_service():
    identity = IdentityService()
    answers = {answer.id: answer for answer in AnswerBankService().all()["approved_structured"]}
    assert answers["IDENTITY_LEGAL_FIRST_NAME"].answer == identity.map_form_field("Legal First Name").value
    assert answers["IDENTITY_EMAIL"].answer == identity.map_form_field("Email").value
    assert answers["IDENTITY_PORTFOLIO"].answer == identity.map_form_field("Portfolio URL").value


def test_work_authorization_policy_remains_exact():
    service = WorkAuthorizationService()
    expected = {
        "Are you legally authorized to work in the United States?": "YES",
        "Will you now or in the future require employment visa sponsorship?": "YES",
        "Are you currently in H-1B status?": "YES",
        "Would you require an H-1B change of employer / transfer?": "YES",
        "Do you require a new H-1B lottery / cap selection?": "NO",
    }
    for question, answer in expected.items():
        result = service.assess(question)
        assert result.answer == answer
        assert result.requires_human_review is False


def test_identity_mapping_endpoint(client):
    response = client.get("/profile/identity/map", params={"field_label": "Given Name"})
    assert response.status_code == 200
    assert response.json()["value"] == "Srinikhil Reddy"
