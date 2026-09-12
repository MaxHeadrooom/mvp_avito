import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import order_service

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/establishments", response_model=list[schemas.EstablishmentOut])
def list_establishments(db: Session = Depends(get_db)) -> list[models.Establishment]:
    return db.scalars(
        select(models.Establishment)
        .where(models.Establishment.status == models.EstablishmentStatus.OPEN)
        .order_by(models.Establishment.name)
    ).all()


@router.get("/establishments/{establishment_id}/menu", response_model=schemas.MenuOut)
def get_menu(establishment_id: uuid.UUID, db: Session = Depends(get_db)) -> schemas.MenuOut:
    establishment = db.get(models.Establishment, establishment_id)
    if establishment is None:
        raise HTTPException(404, "establishment not found")
    categories = db.scalars(
        select(models.Category)
        .where(models.Category.establishment_id == establishment_id)
        .order_by(models.Category.name)
    ).all()
    products = db.scalars(
        select(models.Product)
        .where(models.Product.establishment_id == establishment_id)
        .order_by(models.Product.name)
    ).all()
    return schemas.MenuOut(establishment=establishment, categories=categories, products=products)


@router.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(
    payload: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> models.Order:
    try:
        order = order_service.create_order(db, payload)
    except order_service.OrderError as exc:
        raise HTTPException(409, str(exc)) from exc

    establishment = db.get(models.Establishment, order.establishment_id)
    assert establishment is not None  # guaranteed by the transaction above
    background_tasks.add_task(
        order_service.notify_establishment,
        establishment.callback_url,
        order.id,
        establishment.id,
    )
    return order


@router.get("/orders", response_model=list[schemas.OrderOut])
def list_orders_for_user(
    user_id: uuid.UUID = Query(),
    db: Session = Depends(get_db),
) -> list[models.Order]:
    return db.scalars(
        select(models.Order)
        .where(models.Order.user_id == user_id)
        .order_by(models.Order.created_at.desc())
    ).unique().all()


@router.get("/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> models.Order:
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    return order


@router.post("/orders/{order_id}/cancel", response_model=schemas.OrderOut)
def cancel_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> models.Order:
    order = _get_order_or_404(db, order_id, lock=True)
    try:
        return order_service.cancel_order(db, order)
    except order_service.OrderError as exc:
        raise HTTPException(409, str(exc)) from exc


def _get_order_or_404(db: Session, order_id: uuid.UUID, *, lock: bool) -> models.Order:
    statement = select(models.Order).where(models.Order.id == order_id)
    if lock:
        statement = statement.with_for_update()
    order = db.execute(statement).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "order not found")
    return order

