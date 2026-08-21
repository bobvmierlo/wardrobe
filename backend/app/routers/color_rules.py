"""Admin-editable colour-combination rules that drive outfit suggestions.

Everyone can read the rules (so the settings screen can explain the logic);
only admins can add or remove them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import ColorRule, User
from ..schemas import ColorLogic, ColorRuleIn, ColorRuleOut
from ..suggestions import BASE_COLORS, NEUTRALS

router = APIRouter(prefix="/api/color-rules", tags=["color-rules"])


def _canonical(color_a: str, color_b: str) -> tuple[str, str]:
    a, b = color_a.strip().lower(), color_b.strip().lower()
    return (a, b) if a <= b else (b, a)


def load_pairs(db: Session) -> tuple[set[frozenset[str]], set[frozenset[str]]]:
    """Return (good_pairs, bad_pairs) as sets of frozensets for the engine."""
    good: set[frozenset[str]] = set()
    bad: set[frozenset[str]] = set()
    for r in db.query(ColorRule).all():
        (good if r.verdict == "good" else bad).add(frozenset({r.color_a, r.color_b}))
    return good, bad


@router.get("", response_model=ColorLogic)
def list_rules(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rules = db.query(ColorRule).order_by(ColorRule.verdict, ColorRule.color_a, ColorRule.color_b).all()
    return ColorLogic(
        rules=[ColorRuleOut.model_validate(r) for r in rules],
        neutrals=NEUTRALS,
        colors=BASE_COLORS,
    )


@router.post("", response_model=ColorRuleOut, status_code=201)
def add_rule(
    body: ColorRuleIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a, b = _canonical(body.color_a, body.color_b)
    if a == b:
        raise HTTPException(status_code=400, detail="Kies twee verschillende kleuren")
    for color in (a, b):
        if color not in BASE_COLORS:
            raise HTTPException(status_code=400, detail=f"Onbekende kleur: {color}")
    if db.query(ColorRule).filter(
        ColorRule.color_a == a, ColorRule.color_b == b, ColorRule.verdict == body.verdict
    ).first():
        raise HTTPException(status_code=409, detail="Deze regel bestaat al")
    rule = ColorRule(color_a=a, color_b=b, verdict=body.verdict)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = db.get(ColorRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regel niet gevonden")
    db.delete(rule)
    db.commit()
