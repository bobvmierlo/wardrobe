"""Admin-managed lists: clothing categories and sizes.

Both are simple ordered name lists that everyone can read but only admins
can change, so the mobile UI can offer a real dropdown instead of free text.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Category, Item, SizeOption, User
from ..schemas import CategoryOut, LabelIn, NameIn, SizeOut

categories_router = APIRouter(prefix="/api/categories", tags=["categories"])
sizes_router = APIRouter(prefix="/api/sizes", tags=["sizes"])


# ---- Categories ----
@categories_router.get("", response_model=list[CategoryOut])
def list_categories(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Category).order_by(Category.position, Category.name).all()


@categories_router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    body: NameIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if db.query(Category).filter(Category.name == name).first():
        raise HTTPException(status_code=409, detail="Categorie bestaat al")
    last = db.query(Category).order_by(Category.position.desc()).first()
    cat = Category(name=name, position=(last.position + 1) if last else 0)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    audit.record(
        db, "category.create", f"Categorie '{cat.name}' toegevoegd",
        user=admin, entity_type="category", entity_id=cat.id,
    )
    return cat


@categories_router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categorie niet gevonden")
    in_use = db.query(Item).filter(Item.category == cat.name).count()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Categorie is nog in gebruik door {in_use} kledingstuk(ken)",
        )
    name = cat.name
    db.delete(cat)
    db.commit()
    audit.record(
        db, "category.delete", f"Categorie '{name}' verwijderd",
        user=admin, entity_type="category", entity_id=category_id,
    )


# ---- Sizes ----
@sizes_router.get("", response_model=list[SizeOut])
def list_sizes(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(SizeOption).order_by(SizeOption.position, SizeOption.label).all()


@sizes_router.post("", response_model=SizeOut, status_code=201)
def create_size(
    body: LabelIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    label = body.label.strip()
    if db.query(SizeOption).filter(SizeOption.label == label, SizeOption.kind == body.kind).first():
        raise HTTPException(status_code=409, detail="Maat bestaat al")
    last = db.query(SizeOption).order_by(SizeOption.position.desc()).first()
    size = SizeOption(
        label=label,
        kind=body.kind,
        position=(last.position + 1) if last else 0,
    )
    db.add(size)
    db.commit()
    db.refresh(size)
    audit.record(
        db, "size.create", f"Maat '{size.label}' ({size.kind}) toegevoegd",
        user=admin, entity_type="size", entity_id=size.id,
    )
    return size


@sizes_router.delete("/{size_id}", status_code=204)
def delete_size(
    size_id: int,
    force: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    size = db.get(SizeOption, size_id)
    if not size:
        raise HTTPException(status_code=404, detail="Maat niet gevonden")
    # Warn (but allow, once confirmed) when the size is still assigned to items.
    # The items keep their size label as free text, so this is not destructive.
    in_use = db.query(Item).filter(Item.size == size.label).count()
    if in_use and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Maat '{size.label}' is nog in gebruik door {in_use} kledingstuk(ken)",
        )
    label = size.label
    db.delete(size)
    db.commit()
    audit.record(
        db,
        "size.delete",
        f"Maat '{label}' verwijderd" + (f" (nog in gebruik door {in_use} stuk(ken))" if in_use else ""),
        user=admin, entity_type="size", entity_id=size_id,
    )
