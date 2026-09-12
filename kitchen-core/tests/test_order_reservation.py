import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.services import order_service


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        establishment = models.Establishment(
            partner_id="test-partner",
            name="Test kitchen",
            callback_url="http://example.test",
        )
        session.add(establishment)
        session.flush()
        product = models.Product(
            establishment_id=establishment.id,
            external_id="pizza",
            name="Pizza",
            price=Decimal("250.00"),
            stock=2,
        )
        session.add(product)
        session.commit()
        yield session


def test_cancelled_order_releases_reserved_stock(db: Session) -> None:
    establishment = db.scalar(select(models.Establishment))
    product = db.scalar(select(models.Product))
    assert establishment is not None
    assert product is not None
    # SQLAlchemy starts a read transaction for the fixture lookups. The service
    # owns the write transaction, just as it does when called by the HTTP route.
    db.commit()

    order = order_service.create_order(
        db,
        schemas.OrderCreate(
            user_id=uuid.uuid4(),
            establishment_id=establishment.id,
            delivery_address="Test street, 1",
            items=[schemas.OrderItemIn(product_id=product.id, quantity=2)],
        ),
    )
    db.refresh(product)
    assert product.stock == 0
    assert order.total_price == Decimal("500.00")

    order_service.cancel_order(db, order)
    db.refresh(product)
    assert product.stock == 2
    assert order.status == models.OrderStatus.CANCELLED
    assert [event.status for event in order.status_history] == [
        models.OrderStatus.CREATED,
        models.OrderStatus.CANCELLED,
    ]
