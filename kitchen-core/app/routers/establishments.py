import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import order_service

router = APIRouter(prefix="/establishments", tags=["establishments"])


@router.put("/{partner_id}", response_model=schemas.EstablishmentOut, status_code=201)
def upsert_establishment(
    response: Response,
    partner_id: str = Path(min_length=1, max_length=128),
    payload: schemas.EstablishmentUpsert = ...,  # FastAPI marks this as a request body.
    db: Session = Depends(get_db),
) -> models.Establishment:
    """Provision a whitelisted partner. Retrying the same request is safe."""
    establishment = db.scalar(
        select(models.Establishment).where(models.Establishment.partner_id == partner_id)
    )
    if establishment is None:
        establishment = models.Establishment(
            partner_id=partner_id,
            name=payload.name,
            description=payload.description,
            callback_url=str(payload.callback_url),
            status=payload.status,
        )
        db.add(establishment)
        response.status_code = status.HTTP_201_CREATED
    else:
        establishment.name = payload.name
        establishment.description = payload.description
        establishment.callback_url = str(payload.callback_url)
        establishment.status = payload.status
        response.status_code = status.HTTP_200_OK
    db.commit()
    db.refresh(establishment)
    return establishment


@router.patch("/{establishment_id}/status", response_model=schemas.EstablishmentOut)
def update_establishment_status(
    establishment_id: uuid.UUID,
    payload: schemas.EstablishmentStatusUpdate,
    db: Session = Depends(get_db),
) -> models.Establishment:
    establishment = _get_establishment_or_404(db, establishment_id, lock=True)
    establishment.status = payload.status
    db.commit()
    db.refresh(establishment)
    return establishment


@router.post(
    "/{establishment_id}/categories",
    response_model=schemas.CategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    establishment_id: uuid.UUID,
    payload: schemas.CategoryCreate,
    db: Session = Depends(get_db),
) -> models.Category:
    _get_establishment_or_404(db, establishment_id)
    category = models.Category(establishment_id=establishment_id, name=payload.name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "category with this name already exists") from exc
    db.refresh(category)
    return category


@router.post(
    "/{establishment_id}/products",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    establishment_id: uuid.UUID,
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
) -> models.Product:
    _get_establishment_or_404(db, establishment_id)
    _validate_category(db, establishment_id, payload.category_id)
    product = models.Product(establishment_id=establishment_id, **payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "product with this external_id already exists") from exc
    db.refresh(product)
    return product


@router.put(
    "/{establishment_id}/products/external/{external_id}",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def upsert_product(
    response: Response,
    establishment_id: uuid.UUID,
    external_id: str = Path(min_length=1, max_length=128),
    payload: schemas.ProductFields = ...,
    db: Session = Depends(get_db),
) -> models.Product:
    """Idempotent menu sync endpoint for a partner POS."""
    _get_establishment_or_404(db, establishment_id)
    _validate_category(db, establishment_id, payload.category_id)
    product = db.scalar(
        select(models.Product).where(
            models.Product.establishment_id == establishment_id,
            models.Product.external_id == external_id,
        )
    )
    if product is None:
        product = models.Product(
            establishment_id=establishment_id,
            external_id=external_id,
            **payload.model_dump(),
        )
        db.add(product)
        response.status_code = status.HTTP_201_CREATED
    else:
        for field, value in payload.model_dump().items():
            setattr(product, field, value)
        response.status_code = status.HTTP_200_OK
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{establishment_id}/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    establishment_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
) -> models.Product:
    _get_establishment_or_404(db, establishment_id)
    product = db.execute(
        select(models.Product)
        .where(
            models.Product.id == product_id,
            models.Product.establishment_id == establishment_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "product not found")
    values = payload.model_dump(exclude_unset=True)
    if "category_id" in values:
        _validate_category(db, establishment_id, values["category_id"])
    for field, value in values.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{establishment_id}/orders", response_model=list[schemas.OrderOut])
def list_orders(
    establishment_id: uuid.UUID,
    order_status: models.OrderStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[models.Order]:
    _get_establishment_or_404(db, establishment_id)
    statement = (
        select(models.Order)
        .where(models.Order.establishment_id == establishment_id)
        .order_by(models.Order.created_at)
    )
    if order_status is not None:
        statement = statement.where(models.Order.status == order_status)
    return db.scalars(statement).unique().all()


@router.post("/{establishment_id}/orders/{order_id}/decision", response_model=schemas.OrderOut)
def decide_order(
    establishment_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: schemas.OrderDecision,
    db: Session = Depends(get_db),
) -> models.Order:
    order = _get_order_or_404(db, establishment_id, order_id)
    try:
        return order_service.decide_order(db, order, payload.accept, payload.reason)
    except order_service.OrderError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{establishment_id}/orders/{order_id}/status", response_model=schemas.OrderOut)
def update_order_status(
    establishment_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
) -> models.Order:
    order = _get_order_or_404(db, establishment_id, order_id)
    try:
        return order_service.update_status(db, order, payload.status, payload.comment)
    except order_service.OrderError as exc:
        raise HTTPException(409, str(exc)) from exc


def _get_establishment_or_404(
    db: Session,
    establishment_id: uuid.UUID,
    *,
    lock: bool = False,
) -> models.Establishment:
    statement = select(models.Establishment).where(models.Establishment.id == establishment_id)
    if lock:
        statement = statement.with_for_update()
    establishment = db.execute(statement).scalar_one_or_none()
    if establishment is None:
        raise HTTPException(404, "establishment not found")
    return establishment


def _validate_category(
    db: Session,
    establishment_id: uuid.UUID,
    category_id: uuid.UUID | None,
) -> None:
    if category_id is None:
        return
    category = db.get(models.Category, category_id)
    if category is None or category.establishment_id != establishment_id:
        raise HTTPException(422, "category does not belong to this establishment")


def _get_order_or_404(
    db: Session,
    establishment_id: uuid.UUID,
    order_id: uuid.UUID,
) -> models.Order:
    order = db.execute(
        select(models.Order)
        .where(
            models.Order.id == order_id,
            models.Order.establishment_id == establishment_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "order not found")
    return order
