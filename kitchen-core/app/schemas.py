import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.models import EstablishmentStatus, OrderStatus


class EstablishmentUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    callback_url: AnyHttpUrl
    partner_api_key: str = Field(min_length=16, max_length=256)
    status: EstablishmentStatus = EstablishmentStatus.OPEN


class EstablishmentStatusUpdate(BaseModel):
    status: EstablishmentStatus


class EstablishmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner_id: str
    name: str
    description: str | None
    status: EstablishmentStatus


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProductFields(BaseModel):
    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    is_available: bool = True


class ProductCreate(ProductFields):
    external_id: str | None = Field(default=None, min_length=1, max_length=128)


class ProductUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    is_available: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    category_id: uuid.UUID | None
    name: str
    description: str | None
    price: Decimal
    stock: int | None
    is_available: bool


class MenuOut(BaseModel):
    establishment: EstablishmentOut
    categories: list[CategoryOut]
    products: list[ProductOut]


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, le=100)


class OrderCreate(BaseModel):
    user_id: uuid.UUID
    establishment_id: uuid.UUID
    delivery_address: str = Field(min_length=3, max_length=500)
    comment: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    quantity: int
    price_snapshot: Decimal


class OrderStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: OrderStatus
    changed_at: datetime
    comment: str | None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    establishment_id: uuid.UUID
    delivery_address: str
    comment: str | None
    total_price: Decimal
    status: OrderStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    status_history: list[OrderStatusHistoryOut]


class OrderDecision(BaseModel):
    accept: bool
    reason: str | None = Field(default=None, max_length=500)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    comment: str | None = Field(default=None, max_length=500)
