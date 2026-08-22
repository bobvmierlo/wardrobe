"""The audit trail: a durable record of who changed what.

Every action worth answering "wie heeft dit gedaan?" for goes through
:func:`record`. It writes one ``audit_logs`` row *and* one log line, so the
same event shows up in ``docker compose logs`` and in the in-app log screen.

Actions are named ``<onderwerp>.<handeling>`` (``item.create``,
``match.verdict``) so the log screen can group and filter them without knowing
every action up front.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .logging_setup import get_logger
from .models import AuditLog, User

log = get_logger("audit")

# Human-readable labels for the actions the app records, used by the log
# screen. Unknown actions simply fall back to their raw name.
ACTION_LABELS: dict[str, str] = {
    "auth.login": "Ingelogd",
    "auth.login_failed": "Mislukte login",
    "auth.password_change": "Wachtwoord gewijzigd",
    "user.create": "Account aangemaakt",
    "user.update": "Account gewijzigd",
    "user.delete": "Account verwijderd",
    "user.register": "Geregistreerd via uitnodiging",
    "item.create": "Kledingstuk toegevoegd",
    "item.update": "Kledingstuk gewijzigd",
    "item.duplicate": "Kledingstuk gedupliceerd",
    "item.delete": "Kledingstuk verwijderd",
    "match.verdict": "Combinatie beoordeeld",
    "match.undo": "Beoordeling ongedaan gemaakt",
    "match.skip": "Combinatie overgeslagen",
    "match.accept_suggestion": "Suggestie geaccepteerd",
    "member.invite": "Lid toegevoegd",
    "member.update": "Rol gewijzigd",
    "member.remove": "Toegang ingetrokken",
    "invitation.create": "Uitnodigingslink gemaakt",
    "invitation.accept": "Uitnodiging geaccepteerd",
    "invitation.revoke": "Uitnodigingslink ingetrokken",
    "category.create": "Categorie toegevoegd",
    "category.delete": "Categorie verwijderd",
    "size.create": "Maat toegevoegd",
    "size.delete": "Maat verwijderd",
    "color_rule.create": "Kleurregel toegevoegd",
    "color_rule.delete": "Kleurregel verwijderd",
}


def label_for(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def record(
    db: Session,
    action: str,
    detail: str,
    *,
    user: User | None = None,
    user_name: str | None = None,
    wardrobe_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    commit: bool = True,
) -> None:
    """Append one entry to the audit trail and to the application log.

    Pass ``user_name`` instead of ``user`` for actors without an account yet
    (a failed login, someone registering through an invitation link).

    Never raises: an audit write must not be able to fail the action it
    describes. A failure is logged, loudly, and the request continues.
    """
    actor = user.display_name if user else (user_name or "onbekend")
    entry = AuditLog(
        action=action,
        user_id=user.id if user else None,
        user_name=actor,
        wardrobe_id=wardrobe_id,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    try:
        db.add(entry)
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        log.exception("Auditregel kon niet worden opgeslagen: %s", action)
        return
    log.info("%s — %s (%s)", actor, detail, action)
