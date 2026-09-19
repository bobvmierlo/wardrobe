"""The week planner: which outfit on which day.

Personal, not shared. Two people who dress out of the same kast plan their own
weeks, so a plan is stored per user and nobody sees anybody else's.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..access import require_view
from ..database import get_db
from ..deps import get_current_user
from ..models import DayPlan, User
from ..outfit_store import get_outfit, serialize, wear_index
from ..preferences import daily_forecast_for, day_as_weather_out, get_preferences
from ..schemas import DayPlanOut, PlanIn, WeekOut

router = APIRouter(prefix="/api/planner", tags=["planner"])

DAYS = 7


def week_start(day: date) -> date:
    """The Monday of the week ``day`` falls in."""
    return day - timedelta(days=day.weekday())


@router.get("/week", response_model=WeekOut)
def week(
    wardrobe_id: int,
    start: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One week of plans, with the forecast for the days that have one."""
    require_view(db, wardrobe_id, user)
    try:
        anchor = date.fromisoformat(start) if start else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Ongeldige datum") from exc
    monday = week_start(anchor)
    days = [(monday + timedelta(days=i)).isoformat() for i in range(DAYS)]

    plans = {
        plan.day: plan
        for plan in db.query(DayPlan)
        .filter(
            DayPlan.user_id == user.id,
            DayPlan.wardrobe_id == wardrobe_id,
            DayPlan.day.in_(days),
        )
        .all()
    }
    wears = wear_index(
        db, user.id, [p.outfit_id for p in plans.values()]
    )
    # The forecast only reaches a week out, and only forwards: a plan for last
    # Tuesday gets no weather rather than a wrong one.
    outlook = {d.day: d for d in daily_forecast_for(get_preferences(db, user), DAYS)}

    out: list[DayPlanOut] = []
    for day in days:
        plan = plans.get(day)
        forecast = outlook.get(day)
        out.append(
            DayPlanOut(
                day=day,
                outfit=(
                    serialize(plan.outfit, wears.get(plan.outfit_id, []))
                    if plan is not None and plan.outfit is not None
                    else None
                ),
                weather=day_as_weather_out(forecast) if forecast else None,
            )
        )
    return WeekOut(start=monday.isoformat(), days=out)


@router.put("", response_model=DayPlanOut)
def set_day(
    body: PlanIn,
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Plan an outfit for a day, or clear it by sending no outfit.

    Viewing rights are enough: planning what *you* will wear out of a kast you
    were invited to changes nothing for anybody else.
    """
    require_view(db, wardrobe_id, user)
    existing = (
        db.query(DayPlan)
        .filter(DayPlan.user_id == user.id, DayPlan.day == body.day)
        .first()
    )

    if body.outfit_id is None:
        if existing is not None:
            db.delete(existing)
            db.commit()
        return DayPlanOut(day=body.day, outfit=None)

    outfit = get_outfit(db, body.outfit_id)
    if outfit.wardrobe_id != wardrobe_id:
        raise HTTPException(status_code=400, detail="Die outfit hoort bij een andere kast")
    require_view(db, outfit.wardrobe_id, user)

    if existing is None:
        existing = DayPlan(
            user_id=user.id, wardrobe_id=wardrobe_id, day=body.day, outfit_id=outfit.id
        )
        db.add(existing)
    else:
        existing.outfit_id = outfit.id
        existing.wardrobe_id = wardrobe_id
    db.commit()
    return DayPlanOut(
        day=body.day,
        outfit=serialize(outfit, wear_index(db, user.id, [outfit.id]).get(outfit.id, [])),
    )
