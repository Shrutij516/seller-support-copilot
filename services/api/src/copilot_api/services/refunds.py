import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.models import CaseType, Order, OrderStatus, SupportCase

REFUND_WINDOW_DAYS = 30


class RefundError(Exception):
    """Base class for request_refund's typed domain errors."""


class OrderNotFound(RefundError):
    def __init__(self, order_id: uuid.UUID) -> None:
        super().__init__(f"order {order_id} not found")
        self.order_id = order_id


class AlreadyRequested(RefundError):
    def __init__(self, order_id: uuid.UUID) -> None:
        super().__init__(f"order {order_id} already has a refund request")
        self.order_id = order_id


class NotEligible(RefundError):
    def __init__(self, order_id: uuid.UUID, reason: str) -> None:
        super().__init__(f"order {order_id} is not eligible for refund: {reason}")
        self.order_id = order_id
        self.reason = reason


async def request_refund(
    session: AsyncSession, seller_id: uuid.UUID, order_id: uuid.UUID, reason: str
) -> SupportCase:
    """Move an order to refund_requested and open a case for it, atomically.

    Locks the order row (SELECT ... FOR UPDATE) so two concurrent requests for the same
    order serialize: the second sees the first's committed status change and is rejected,
    instead of both racing to insert a case.

    Doesn't assume it owns the session's transaction boundary: a session handed in mid
    request may already have autobegun one (e.g. from an earlier ownership lookup), and
    `session.begin()` raises if a transaction is already open. So this commits explicitly
    on success and rolls back explicitly on any failure, rather than using `session.begin()`
    as a context manager.
    """
    try:
        order = (
            await session.execute(select(Order).where(Order.id == order_id).with_for_update())
        ).scalar_one_or_none()

        # Don't distinguish "doesn't exist" from "not yours" in the error: neither should
        # leak whether an order id belongs to someone else.
        if order is None or order.seller_id != seller_id:
            raise OrderNotFound(order_id)
        if order.status == OrderStatus.REFUND_REQUESTED:
            raise AlreadyRequested(order_id)
        if order.status != OrderStatus.DELIVERED:
            raise NotEligible(order_id, reason=f"status is {order.status.value}, not delivered")
        if order.delivered_at is None or datetime.now(UTC) - order.delivered_at > timedelta(
            days=REFUND_WINDOW_DAYS
        ):
            raise NotEligible(
                order_id, reason=f"outside the {REFUND_WINDOW_DAYS}-day refund window"
            )

        order.status = OrderStatus.REFUND_REQUESTED
        # Flush now so the UPDATE lands inside this transaction before the case insert;
        # if the insert below fails, both roll back together.
        await session.flush()

        case = SupportCase(
            seller_id=seller_id,
            order_id=order_id,
            type=CaseType.REFUND_REQUEST,
            description=reason,
        )
        session.add(case)
        await session.flush()
    except Exception:
        await session.rollback()
        raise

    await session.commit()
    return case
