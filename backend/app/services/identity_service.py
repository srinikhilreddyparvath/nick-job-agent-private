from app.models.identity import IdentityFieldMapping
from app.models.profile import CandidateProfile, Identity
from app.services.profile_service import load_profile


class IdentityService:
    """Canonical application identity access and approved form-field mapping."""

    def __init__(self, profile: CandidateProfile | None = None):
        self.profile = profile or load_profile()

    def get(self) -> Identity:
        return self.profile.identity

    def map_form_field(self, field_label: str, required: bool = True) -> IdentityFieldMapping:
        identity = self.get()
        normalized = " ".join(field_label.lower().strip().replace("_", " ").split())
        values = {
            "first name": identity.legal_first_name,
            "given name": identity.legal_first_name,
            "legal first name": identity.legal_first_name,
            "last name": identity.legal_last_name,
            "surname": identity.legal_last_name,
            "family name": identity.legal_last_name,
            "legal last name": identity.legal_last_name,
            "preferred first name": identity.preferred_first_name,
            "preferred name": identity.preferred_first_name,
            "professional name": identity.preferred_professional_name,
            "display name": identity.display_name,
            "full legal name": identity.legal_name,
            "legal name": identity.legal_name,
            "legal full name": identity.legal_name,
            "full name": identity.legal_name,
            "email": identity.email,
            "email address": identity.email,
            "phone": identity.phone,
            "phone number": identity.phone,
            "portfolio": str(identity.portfolio_url) if identity.portfolio_url else None,
            "portfolio url": str(identity.portfolio_url) if identity.portfolio_url else None,
            "linkedin": str(identity.linkedin_url) if identity.linkedin_url else None,
            "linkedin url": str(identity.linkedin_url) if identity.linkedin_url else None,
        }
        if normalized in {"middle name", "legal middle name"}:
            return IdentityFieldMapping(
                field_label=field_label,
                requires_human_review=required,
                reason=("A separately required middle-name field has no approved mapping" if required else "Optional middle-name field must be left blank"),
            )
        if normalized in values:
            value = values[normalized]
            return IdentityFieldMapping(
                field_label=field_label,
                value=value,
                requires_human_review=value is None,
                reason="Approved canonical identity mapping" if value is not None else "Canonical value is not configured",
            )
        return IdentityFieldMapping(field_label=field_label, requires_human_review=True, reason="No approved identity mapping")
