"""SQLAlchemy models. Import every model here so Alembic sees it (alembic/env.py uses Base.metadata)."""

from app.models.audit import AuditLog
from app.models.common import VerificationStatus
from app.models.consents import Consent, ConsentKind
from app.models.documents import Document, DocumentAccessLog, DocumentStatus, DocumentType
from app.models.legal import AcceptanceMethod, LegalAcceptance, LegalDocument, LegalKind
from app.models.parents import AuthorisedAdult, Child, EmergencyContact, Parent
from app.models.profiles import Profile, ProfileStatus, Role, ServiceAreaPincode
from app.models.psych_tests import (
    PsychAnswer,
    PsychAttempt,
    PsychAttemptStatus,
    PsychQuestion,
    PsychQuestionKind,
    PsychTest,
)
from app.models.sitters import (
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepName,
    PayoutMethod,
    Reference,
    Sitter,
    SitterLevel,
)

__all__ = [
    "AcceptanceMethod",
    "AuditLog",
    "AuthorisedAdult",
    "Child",
    "Consent",
    "ConsentKind",
    "Document",
    "DocumentAccessLog",
    "DocumentStatus",
    "DocumentType",
    "EmergencyContact",
    "LegalAcceptance",
    "LegalDocument",
    "LegalKind",
    "OnboardingStatus",
    "OnboardingStep",
    "OnboardingStepName",
    "Parent",
    "PayoutMethod",
    "Profile",
    "ProfileStatus",
    "PsychAnswer",
    "PsychAttempt",
    "PsychAttemptStatus",
    "PsychQuestion",
    "PsychQuestionKind",
    "PsychTest",
    "Reference",
    "Role",
    "ServiceAreaPincode",
    "Sitter",
    "SitterLevel",
    "VerificationStatus",
]
