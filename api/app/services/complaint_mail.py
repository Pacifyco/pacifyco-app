"""Who's emailed as a complaint moves along (CLAUDE.md 6.12). Called after the change is committed.

Admins (`ADMIN_ALERT_EMAILS`) hear of new complaints, appeals and the person's messages, without details;
the Grievance Officer of escalations; the person of every reply and decision, with its words.
"""

from sqlalchemy.orm import Session

from app.models import AppealOutcome, Complaint, ComplaintType, Profile
from app.services import complaints
from app.services import email as email_service
from app.services.booking_mail import web_url
from app.services.email import EmailClient
from app.settings import Settings


def admin_url(settings: Settings, complaint: Complaint) -> str:
    return f"{web_url(settings).rstrip('/')}/admin/complaints/{complaint.id}"


def person_url(settings: Settings, person: Profile, complaint: Complaint) -> str:
    area = f"{web_url(settings).rstrip('/')}/{person.role.value}"
    return area if complaint.type == ComplaintType.suspension else f"{area}/help/{complaint.id}"


def tell_raised(db: Session, mailer: EmailClient, settings: Settings, complaint: Complaint) -> None:
    person = db.get(Profile, complaint.raised_by)
    for to in settings.admin_alert_emails:
        if complaint.type == ComplaintType.suspension:
            mailer.send(email_service.appeal_alert(to, person.role.value, admin_url(settings, complaint)))
        else:
            mailer.send(
                email_service.complaint_alert(
                    to, complaint.type.value, person.role.value, complaint.late, admin_url(settings, complaint)
                )
            )


def tell_person_wrote(mailer: EmailClient, settings: Settings, complaint: Complaint) -> None:
    for to in settings.admin_alert_emails:
        mailer.send(email_service.complaint_message_alert(to, admin_url(settings, complaint)))


def tell_admin_wrote(db: Session, mailer: EmailClient, settings: Settings, complaint: Complaint, body: str) -> None:
    person = db.get(Profile, complaint.raised_by)
    mailer.send(
        email_service.complaint_reply(person.email, person.full_name, body, person_url(settings, person, complaint))
    )


def tell_resolved(db: Session, mailer: EmailClient, settings: Settings, complaint: Complaint) -> None:
    person = db.get(Profile, complaint.raised_by)
    mailer.send(
        email_service.complaint_resolved(
            person.email, person.full_name, complaint.resolution or "", person_url(settings, person, complaint)
        )
    )


def tell_appeal_decided(
    db: Session, mailer: EmailClient, settings: Settings, complaint: Complaint, reinstated: bool
) -> None:
    person = db.get(Profile, complaint.raised_by)
    mailer.send(
        email_service.appeal_decided(
            person.email,
            person.full_name,
            complaint.appeal_outcome == AppealOutcome.upheld,
            reinstated,
            complaint.resolution or "",
            person_url(settings, person, complaint),
        )
    )


def tell_escalated(
    db: Session, mailer: EmailClient, settings: Settings, escalated: list[Complaint], overdue: bool
) -> None:
    """The people, each about theirs, and the Grievance Officer once for all of them."""
    if not escalated:
        return
    for complaint in escalated:
        person = db.get(Profile, complaint.raised_by)
        mailer.send(
            email_service.complaint_escalated(
                person.email, person.full_name, overdue, person_url(settings, person, complaint)
            )
        )
    for to in complaints.officer_emails(settings):
        mailer.send(email_service.escalation_alert(to, len(escalated), web_url(settings)))


def tell_officer_decided(db: Session, mailer: EmailClient, settings: Settings, complaint: Complaint) -> None:
    person = db.get(Profile, complaint.raised_by)
    mailer.send(
        email_service.officer_decision(
            person.email, person.full_name, complaint.officer_decision or "", person_url(settings, person, complaint)
        )
    )
