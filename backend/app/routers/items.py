from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..images import delete_files, save_upload
from ..models import Item, User
from ..schemas import ItemOut

router = APIRouter(prefix="/api/items", tags=["items"])


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


@router.get("", response_model=list[ItemOut])
def list_items(
    category: str | None = None,
    q: str | None = None,
    favorites: bool = False,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Item)
    if category:
        query = query.filter(Item.category == category)
    if favorites:
        query = query.filter(Item.is_favorite.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(Item.name.ilike(like), Item.brand.ilike(like), Item.color.ilike(like))
        )
    return query.order_by(Item.created_at.desc()).all()


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    return item


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    name: str = Form(...),
    category: str = Form(...),
    brand: str | None = Form(None),
    color: str | None = Form(None),
    size: str | None = Form(None),
    season: str | None = Form(None),
    notes: str | None = Form(None),
    is_favorite: bool = Form(False),
    photo: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_name = thumb_name = None
    if photo is not None and photo.filename:
        photo_name, thumb_name = save_upload(photo)

    item = Item(
        name=name.strip(),
        category=category.strip(),
        brand=_clean(brand),
        color=_clean(color),
        size=_clean(size),
        season=_clean(season),
        notes=_clean(notes),
        is_favorite=is_favorite,
        photo_filename=photo_name,
        thumb_filename=thumb_name,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    name: str | None = Form(None),
    category: str | None = Form(None),
    brand: str | None = Form(None),
    color: str | None = Form(None),
    size: str | None = Form(None),
    season: str | None = Form(None),
    notes: str | None = Form(None),
    is_favorite: bool | None = Form(None),
    photo: UploadFile | None = File(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")

    if name is not None:
        item.name = name.strip()
    if category is not None:
        item.category = category.strip()
    if brand is not None:
        item.brand = _clean(brand)
    if color is not None:
        item.color = _clean(color)
    if size is not None:
        item.size = _clean(size)
    if season is not None:
        item.season = _clean(season)
    if notes is not None:
        item.notes = _clean(notes)
    if is_favorite is not None:
        item.is_favorite = is_favorite

    if photo is not None and photo.filename:
        old = (item.photo_filename, item.thumb_filename)
        item.photo_filename, item.thumb_filename = save_upload(photo)
        delete_files(*old)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    delete_files(item.photo_filename, item.thumb_filename)
    db.delete(item)
    db.commit()
