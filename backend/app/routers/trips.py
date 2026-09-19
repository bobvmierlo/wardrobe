"""Reistas: the outfits you are taking, and the packing list they imply.

The packing list is *derived* — every garment in every outfit taken along,
counted once — so editing an outfit can never leave a trip listing something
it no longer needs. Only the ticks ("packed") are stored.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..access import require_edit, require_view
from ..database import get_db
from ..deps import get_current_user
from ..models import Trip, TripOutfit, TripPacked, User
from ..outfit_store import get_outfit, serialize, wear_index
from ..schemas import (
    ItemOut,
    PackedIn,
    PackingEntry,
    TripDetail,
    TripIn,
    TripOut,
    TripOutfitIn,
)

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _get_trip(db: Session, trip_id: int) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Reis niet gevonden")
    return trip


def _packing(trip: Trip) -> list[PackingEntry]:
    """Every garment the trip's outfits need, each listed once."""
    ticked = {row.item_id for row in trip.packed}
    used: dict[int, int] = {}
    items: dict[int, object] = {}
    for link in trip.outfits:
        if link.outfit is None:
            continue
        for item in link.outfit.items:
            used[item.id] = used.get(item.id, 0) + 1
            items[item.id] = item
    entries = [
        PackingEntry(
            item=ItemOut.model_validate(items[item_id]),
            packed=item_id in ticked,
            used_in=count,
        )
        for item_id, count in used.items()
    ]
    # Most-needed first, then by name: the things several outfits depend on are
    # the ones you really must not forget.
    entries.sort(key=lambda e: (-e.used_in, e.item.name.lower()))
    return entries


def _summary(trip: Trip) -> TripOut:
    packing = _packing(trip)
    return TripOut(
        id=trip.id,
        name=trip.name,
        destination=trip.destination,
        starts_on=trip.starts_on,
        ends_on=trip.ends_on,
        notes=trip.notes,
        outfit_count=len(trip.outfits),
        item_count=len(packing),
        packed_count=sum(1 for e in packing if e.packed),
    )


def _detail(db: Session, trip: Trip, user_id: int) -> TripDetail:
    outfits = [link.outfit for link in trip.outfits if link.outfit is not None]
    wears = wear_index(db, user_id, [o.id for o in outfits])
    return TripDetail(
        **_summary(trip).model_dump(),
        outfits=[serialize(o, wears.get(o.id, [])) for o in outfits],
        packing=_packing(trip),
    )


@router.get("", response_model=list[TripOut])
def list_trips(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, wardrobe_id, user)
    trips = (
        db.query(Trip)
        .filter(Trip.wardrobe_id == wardrobe_id)
        .order_by(Trip.starts_on.is_(None), Trip.starts_on, Trip.created_at.desc())
        .all()
    )
    return [_summary(t) for t in trips]


@router.post("", response_model=TripDetail, status_code=201)
def create_trip(
    body: TripIn,
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_edit(db, wardrobe_id, user)
    trip = Trip(
        name=body.name.strip(),
        destination=(body.destination or "").strip() or None,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        notes=(body.notes or "").strip() or None,
        wardrobe_id=wardrobe_id,
        created_by_id=user.id,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    audit.record(
        db, "trip.create", f"Reis '{trip.name}' aangemaakt",
        user=user, wardrobe_id=wardrobe_id, entity_type="trip", entity_id=trip.id,
    )
    return _detail(db, trip, user.id)


@router.get("/{trip_id}", response_model=TripDetail)
def get_trip(
    trip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _get_trip(db, trip_id)
    require_view(db, trip.wardrobe_id, user)
    return _detail(db, trip, user.id)


@router.put("/{trip_id}", response_model=TripDetail)
def update_trip(
    trip_id: int,
    body: TripIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _get_trip(db, trip_id)
    require_edit(db, trip.wardrobe_id, user)
    trip.name = body.name.strip()
    trip.destination = (body.destination or "").strip() or None
    trip.starts_on = body.starts_on
    trip.ends_on = body.ends_on
    trip.notes = (body.notes or "").strip() or None
    db.commit()
    db.refresh(trip)
    return _detail(db, trip, user.id)


@router.delete("/{trip_id}", status_code=204)
def delete_trip(
    trip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _get_trip(db, trip_id)
    require_edit(db, trip.wardrobe_id, user)
    name, wardrobe_id = trip.name, trip.wardrobe_id
    db.delete(trip)
    db.commit()
    audit.record(
        db, "trip.delete", f"Reis '{name}' verwijderd",
        user=user, wardrobe_id=wardrobe_id, entity_type="trip", entity_id=trip_id,
    )


@router.post("/{trip_id}/outfits", response_model=TripDetail)
def add_outfit(
    trip_id: int,
    body: TripOutfitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _get_trip(db, trip_id)
    require_edit(db, trip.wardrobe_id, user)
    outfit = get_outfit(db, body.outfit_id)
    if outfit.wardrobe_id != trip.wardrobe_id:
        raise HTTPException(status_code=400, detail="Die outfit hoort bij een andere kast")
    if not any(link.outfit_id == outfit.id for link in trip.outfits):
        db.add(TripOutfit(trip_id=trip.id, outfit_id=outfit.id))
        db.commit()
        db.refresh(trip)
    return _detail(db, trip, user.id)


@router.delete("/{trip_id}/outfits/{outfit_id}", response_model=TripDetail)
def remove_outfit(
    trip_id: int,
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _get_trip(db, trip_id)
    require_edit(db, trip.wardrobe_id, user)
    db.query(TripOutfit).filter(
        TripOutfit.trip_id == trip.id, TripOutfit.outfit_id == outfit_id
    ).delete()
    db.commit()
    db.refresh(trip)
    return _detail(db, trip, user.id)


@router.post("/{trip_id}/packed", response_model=TripDetail)
def set_packed(
    trip_id: int,
    body: PackedIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tick a garment off the packing list, or untick it.

    Viewing rights are enough — packing a suitcase out of a shared kast is not
    a change to the kast.
    """
    trip = _get_trip(db, trip_id)
    require_view(db, trip.wardrobe_id, user)
    existing = (
        db.query(TripPacked)
        .filter(TripPacked.trip_id == trip.id, TripPacked.item_id == body.item_id)
        .first()
    )
    if body.packed and existing is None:
        db.add(TripPacked(trip_id=trip.id, item_id=body.item_id))
    elif not body.packed and existing is not None:
        db.delete(existing)
    db.commit()
    db.refresh(trip)
    return _detail(db, trip, user.id)
