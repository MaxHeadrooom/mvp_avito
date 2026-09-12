import uuid
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings


class OrderError(Exception):
    """A business-rule violation that the API renders as HTTP 409."""


ALLOWED_TRANSITIONS: dict[models.OrderStatus, set[models.OrderStatus]] = {
    models.OrderStatus.CREATED: {
        models.OrderStatus.ACCEPTED,
        models.OrderStatus.REJECTED,
        models.OrderStatus.CANCELLED,
    },
    models.OrderStatus.ACCEPTED: {
        models.OrderStatus.PREPARING,
        models.OrderStatus.REJECTED,
    },
    models.OrderStatus.PREPARING: {models.OrderStatus.READY},
    models.OrderStatus.READY: {models.OrderStatus.COMPLETED},
}


def create_order(db: Session, payload: schemas.OrderCreate) -> models.Order:
    product_ids = [item.product_id for item in payload.items]
    if len(product_ids) != len(set(product_ids)):
        raise OrderError("an order cannot contain the same product more than once")

    # The product rows are locked for the complete reserve-and-create operation.
    # This prevents two concurrent requests from overselling the last item.
    with db.begin():
        establishment = db.execute(
            select(models.Establishment)
            .where(models.Establishment.id == payload.establishment_id)
            .with_for_update()
        ).scalar_one_or_none()
        if establishment is None:
            raise OrderError("establishment not found")
        if establishment.status != models.EstablishmentStatus.OPEN:
            raise OrderError("establishment is closed")

        products = db.execute(
            select(models.Product)
            .where(models.Product.id.in_(product_ids))
            .with_for_update()
        ).scalars()
        products_by_id = {product.id: product for product in products}

        order = models.Order(
            user_id=payload.user_id,
            establishment_id=establishment.id,
            delivery_address=payload.delivery_address,
            comment=payload.comment,
            total_price=Decimal("0.00"),
            status=models.OrderStatus.CREATED,
        )
        for item in payload.items:
            product = products_by_id.get(item.product_id)
            if product is None or product.establishment_id != establishment.id:
                raise OrderError(f"product {item.product_id} not found in this establishment")
            if not product.is_available:
                raise OrderError(f"product '{product.name}' is not available")
            if product.stock is not None:
                if product.stock < item.quantity:
                    raise OrderError(f"not enough stock for '{product.name}'")
                product.stock -= item.quantity

            order.total_price += product.price * item.quantity
            order.items.append(
                models.OrderItem(
                    product_id=product.id,
                    quantity=item.quantity,
                    price_snapshot=product.price,
                )
            )

        order.status_history.append(
            models.OrderStatusHistory(
                status=models.OrderStatus.CREATED,
                comment="order placed by user",
            )
        )
        db.add(order)

    db.refresh(order)
    return order


def notify_establishment(
    callback_url: str,
    order_id: uuid.UUID,
    establishment_id: uuid.UUID,
) -> None:
    """Best-effort notification. The partner can recover orders through its pull API."""
    try:
        httpx.post(
            f"{callback_url.rstrip('/')}/notifications/orders",
            json={"order_id": str(order_id), "establishment_id": str(establishment_id)},
            timeout=settings.establishment_webhook_timeout,
        )
    except httpx.HTTPError:
        # The order is durable at this point. A production version would put an
        # event into an outbox and deliver it through a retrying broker.
        pass


def _restore_stock(db: Session, order: models.Order) -> None:
    product_ids = [item.product_id for item in order.items]
    products = db.execute(
        select(models.Product).where(models.Product.id.in_(product_ids)).with_for_update()
    ).scalars()
    products_by_id = {product.id: product for product in products}
    for item in order.items:
        product = products_by_id.get(item.product_id)
        if product is not None and product.stock is not None:
            product.stock += item.quantity


def decide_order(
    db: Session,
    order: models.Order,
    accept: bool,
    reason: str | None,
) -> models.Order:
    if order.status != models.OrderStatus.CREATED:
        raise OrderError(f"order in status '{order.status.value}' cannot be decided")

    if accept:
        order.status = models.OrderStatus.ACCEPTED
        comment = "accepted by establishment"
    else:
        if not reason:
            raise OrderError("reason is required to reject an order")
        order.status = models.OrderStatus.REJECTED
        order.rejection_reason = reason
        comment = reason
        _restore_stock(db, order)

    order.status_history.append(models.OrderStatusHistory(status=order.status, comment=comment))
    db.commit()
    db.refresh(order)
    return order


def update_status(
    db: Session,
    order: models.Order,
    new_status: models.OrderStatus,
    comment: str | None,
) -> models.Order:
    if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise OrderError(
            f"cannot move order from '{order.status.value}' to '{new_status.value}'"
        )

    if new_status == models.OrderStatus.REJECTED:
        if not comment:
            raise OrderError("reason is required to reject an order")
        _restore_stock(db, order)
    order.status = new_status
    order.rejection_reason = comment if new_status == models.OrderStatus.REJECTED else None
    order.status_history.append(models.OrderStatusHistory(status=new_status, comment=comment))
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order: models.Order) -> models.Order:
    if order.status != models.OrderStatus.CREATED:
        raise OrderError("only orders awaiting an establishment decision can be cancelled")
    order.status = models.OrderStatus.CANCELLED
    _restore_stock(db, order)
    order.status_history.append(
        models.OrderStatusHistory(
            status=models.OrderStatus.CANCELLED,
            comment="cancelled by user",
        )
    )
    db.commit()
    db.refresh(order)
    return order
