from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..access import require_edit, require_view
from ..database import get_db
from ..deps import get_current_user
from ..images import copy_photo, delete_files, save_upload, save_upload_from_url
from ..models import Brand, Item, User
from ..schemas import ItemOut

router = APIRouter(prefix="/api/items", tags=["items"])
# Brands are free text on garments rather than an admin-managed catalog, so
# every user can introduce a new one just by naming it on an item.
brands_router = APIRouter(prefix="/api/brands", tags=["brands"])


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


async def submitted_fields(request: Request) -> set[str]:
    """Names of the form fields this request actually contained.

    FastAPI substitutes a parameter's default for an *empty* form value, so
    ``Form(None)`` turns "" into ``None`` — making "cleared by the user" look
    exactly like "not submitted at all". Reading the raw form tells them apart:
    a field that is present but parsed as ``None`` was deliberately emptied.

    Async so Starlette can parse the body, but the endpoint itself stays sync
    (and keeps running in the threadpool) rather than blocking the event loop
    on its database calls.
    """
    form = await request.form()
    return set(form.keys())


def _brand(db: Session, name: str | None) -> Brand | None:
    """Resolve a typed brand name to its row, creating the brand on first use.

    The lookup and the unique constraint are both case-insensitive, so typing
    "NIKE" reuses an existing "Nike" instead of adding a second entry. Returns
    ``None`` for a blank name, which clears the garment's brand.

    Assign the result to ``Item.brand_ref`` rather than setting ``brand_id``:
    with the relationship loaded, SQLAlchemy reconciles from it on flush and
    would write the previous brand straight back.
    """
    clean = _clean(name)
    if clean is None:
        return None
    brand = db.query(Brand).filter(Brand.name == clean).first()
    if brand is None:
        try:
            # A savepoint keeps a lost race from rolling back the whole request.
            with db.begin_nested():
                brand = Brand(name=clean)
                db.add(brand)
        except IntegrityError:
            brand = db.query(Brand).filter(Brand.name == clean).first()
    return brand


@router.get("", response_model=list[ItemOut])
def list_items(
    wardrobe_id: int,
    category: str | None = None,
    q: str | None = None,
    favorites: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, wardrobe_id, user)
    query = db.query(Item).filter(Item.wardrobe_id == wardrobe_id)
    if category:
        query = query.filter(Item.category == category)
    if favorites:
        query = query.filter(Item.is_favorite.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.outerjoin(Brand, Item.brand_id == Brand.id).filter(
            or_(Item.name.ilike(like), Brand.name.ilike(like), Item.color.ilike(like))
        )
    return query.order_by(Item.created_at.desc()).all()


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_view(db, item.wardrobe_id, user)
    return item


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    wardrobe_id: int = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    brand: str | None = Form(None),
    color: str | None = Form(None),
    size: str | None = Form(None),
    season: str | None = Form(None),
    notes: str | None = Form(None),
    is_favorite: bool = Form(False),
    photo: UploadFile | None = File(None),
    photo_url: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_edit(db, wardrobe_id, user)
    photo_name = thumb_name = None
    if photo is not None and photo.filename:
        photo_name, thumb_name = save_upload(photo)
    elif _clean(photo_url):
        photo_name, thumb_name = save_upload_from_url(photo_url.strip())

    item = Item(
        name=name.strip(),
        category=category.strip(),
        brand_ref=_brand(db, brand),
        color=_clean(color),
        size=_clean(size),
        season=_clean(season),
        notes=_clean(notes),
        is_favorite=is_favorite,
        photo_filename=photo_name,
        thumb_filename=thumb_name,
        wardrobe_id=wardrobe_id,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/duplicate", response_model=ItemOut, status_code=201)
def duplicate_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a copy of an item, including its own copy of the photo."""
    src = db.get(Item, item_id)
    if not src:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_edit(db, src.wardrobe_id, user)

    photo_name, thumb_name = copy_photo(src.photo_filename, src.thumb_filename)
    item = Item(
        name=f"{src.name} (kopie)",
        category=src.category,
        brand_ref=src.brand_ref,
        color=src.color,
        size=src.size,
        season=src.season,
        notes=src.notes,
        is_favorite=src.is_favorite,
        photo_filename=photo_name,
        thumb_filename=thumb_name,
        wardrobe_id=src.wardrobe_id,
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
    photo_url: str | None = Form(None),
    submitted: set[str] = Depends(submitted_fields),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_edit(db, item.wardrobe_id, user)

    # Only touch fields the request actually sent; sending one empty clears it.
    # Name and category are required, so an empty value for those is ignored.
    if name is not None and name.strip():
        item.name = name.strip()
    if category is not None and category.strip():
        item.category = category.strip()
    if "brand" in submitted:
        item.brand_ref = _brand(db, brand)
    if "color" in submitted:
        item.color = _clean(color)
    if "size" in submitted:
        item.size = _clean(size)
    if "season" in submitted:
        item.season = _clean(season)
    if "notes" in submitted:
        item.notes = _clean(notes)
    if "is_favorite" in submitted:
        item.is_favorite = bool(is_favorite)

    if photo is not None and photo.filename:
        old = (item.photo_filename, item.thumb_filename)
        item.photo_filename, item.thumb_filename = save_upload(photo)
        delete_files(*old)
    elif _clean(photo_url):
        old = (item.photo_filename, item.thumb_filename)
        item.photo_filename, item.thumb_filename = save_upload_from_url(photo_url.strip())
        delete_files(*old)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_edit(db, item.wardrobe_id, user)
    delete_files(item.photo_filename, item.thumb_filename)
    db.delete(item)
    db.commit()


@brands_router.get("", response_model=list[str])
def list_brands(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every brand known to the app, for the item form's brand picker.

    Brands are shared across all wardrobes rather than scoped per kast, so a
    new user with an empty kast still gets a filled list to pick from.
    """
    return [name for (name,) in db.query(Brand.name).order_by(Brand.name).all()]
