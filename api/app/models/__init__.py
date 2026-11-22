"""SQLAlchemy models. Import every model here so Alembic sees it (alembic/env.py uses Base.metadata)."""

from app.models.audit import AuditLog
from app.models.bookings import Booking, BookingChild, BookingHomeInfo, BookingStatus
from app.models.common import VerificationStatus
from app.models.consents import Consent, ConsentKind
from app.models.documents import Document, DocumentAccessLog, DocumentStatus, DocumentType
from app.models.earnings import EarningKind, EarningStatus, Payout, SitterEarning
from app.models.incidents import (
    Complaint,
    ComplaintStatus,
    ComplaintType,
    Incident,
    IncidentKind,
    IncidentStatus,
    IssueTopic,
)
from app.models.legal import AcceptanceMethod, LegalAcceptance, LegalDocument, LegalKind
from app.models.marketplace import DayOff, GeocodeCache, WeeklyHours
from app.models.messages import Message
from app.models.overtime import OvertimeCharge, OvertimeRequest, OvertimeRequestStatus
from app.models.parents import AuthorisedAdult, Child, EmergencyContact, Parent
from app.models.payments import Payment, PaymentKind, PaymentStatus
from app.models.profiles import Profile, ProfileStatus, Role, ServiceAreaPincode
from app.models.psych_tests import (
    PsychAnswer,
    PsychAttempt,
    PsychAttemptStatus,
    PsychQuestion,
    PsychQuestionKind,
    PsychTest,
)
from app.models.reports import BookingReport, ReportKind, ReportStatus
from app.models.sitters import (
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepName,
    PayoutMethod,
    Reference,
    Sitter,
    SitterLevel,
)
from app.models.strikes import Strike, StrikeReason

__all__ = [
    "Message",
    "Complaint",
    "ComplaintStatus",
    "ComplaintType",
    "Incident",
    "IncidentKind",
    "IncidentStatus",
    "IssueTopic",
    "BookingReport",
    "ReportKind",
    "ReportStatus",
    "Strike",
    "StrikeReason",
    "AcceptanceMethod",
    "AuditLog",
    "AuthorisedAdult",
    "Booking",
    "BookingChild",
    "BookingHomeInfo",
    "BookingStatus",
    "Child",
    "Consent",
    "ConsentKind",
    "DayOff",
    "Document",
    "DocumentAccessLog",
    "DocumentStatus",
    "DocumentType",
    "EmergencyContact",
    "GeocodeCache",
    "LegalAcceptance",
    "LegalDocument",
    "LegalKind",
    "OnboardingStatus",
    "OnboardingStep",
    "OnboardingStepName",
    "EarningKind",
    "EarningStatus",
    "OvertimeCharge",
    "Payout",
    "SitterEarning",
    "OvertimeRequest",
    "OvertimeRequestStatus",
    "Parent",
    "Payment",
    "PaymentKind",
    "PaymentStatus",
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
    "WeeklyHours",
]
