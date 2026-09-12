from app.models import OrderStatus
from app.services.order_service import ALLOWED_TRANSITIONS


def test_order_state_machine_allows_only_documented_happy_path() -> None:
    assert ALLOWED_TRANSITIONS[OrderStatus.CREATED] == {
        OrderStatus.ACCEPTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    }
    assert ALLOWED_TRANSITIONS[OrderStatus.ACCEPTED] == {
        OrderStatus.PREPARING,
        OrderStatus.REJECTED,
    }
    assert ALLOWED_TRANSITIONS[OrderStatus.PREPARING] == {OrderStatus.READY}
    assert ALLOWED_TRANSITIONS[OrderStatus.READY] == {OrderStatus.COMPLETED}
    assert OrderStatus.COMPLETED not in ALLOWED_TRANSITIONS

