import hmac
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    PaymentGatewayException,
    NotFoundException,
)
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.payment import PaymentTransaction, IdempotencyKey
from app.models.catalog import Product
from app.services.notification_service import notification_service

# Gateway SDKs
try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
except Exception:
    razorpay_client = None

try:
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY
except Exception:
    stripe = None


class PaymentService:

    @classmethod
    async def initialize_payment(cls, db: AsyncSession, order: Order) -> Dict[str, Any]:
        """
        Creates an upstream gateway order (Razorpay) or PaymentIntent (Stripe).
        """
        amount_in_paise = int(order.final_payable * 100)
        gateway = (order.payment_gateway or "RAZORPAY").upper()

        if gateway == "RAZORPAY":
            gateway_order_id = f"order_mock_{order.order_number}"
            if razorpay_client and settings.RAZORPAY_KEY_ID != "rzp_test_placeholder":
                try:
                    rzp_order = razorpay_client.order.create({
                        "amount": amount_in_paise,
                        "currency": "INR",
                        "receipt": order.order_number,
                        "notes": {"order_id": str(order.id)},
                    })
                    gateway_order_id = rzp_order.get("id")
                except Exception as e:
                    raise PaymentGatewayException(f"Failed to create Razorpay order: {str(e)}")

            order.gateway_order_id = gateway_order_id
            await db.commit()

            return {
                "order_id": order.id,
                "order_number": order.order_number,
                "amount": order.final_payable,
                "currency": "INR",
                "gateway": "RAZORPAY",
                "gateway_order_id": gateway_order_id,
                "gateway_public_key": settings.RAZORPAY_KEY_ID,
            }

        elif gateway == "STRIPE":
            gateway_order_id = f"pi_mock_{order.order_number}"
            if stripe and settings.STRIPE_SECRET_KEY != "sk_test_placeholder":
                try:
                    intent = stripe.PaymentIntent.create(
                        amount=amount_in_paise,
                        currency="inr",
                        metadata={"order_id": str(order.id), "order_number": order.order_number},
                    )
                    gateway_order_id = intent.id
                except Exception as e:
                    raise PaymentGatewayException(f"Failed to create Stripe PaymentIntent: {str(e)}")

            order.gateway_order_id = gateway_order_id
            await db.commit()

            return {
                "order_id": order.id,
                "order_number": order.order_number,
                "amount": order.final_payable,
                "currency": "INR",
                "gateway": "STRIPE",
                "gateway_order_id": gateway_order_id,
                "gateway_public_key": settings.STRIPE_PUBLISHABLE_KEY,
            }
        else:
            raise BadRequestException(f"Unsupported payment gateway '{gateway}'")

    # ------------------ IDEMPOTENCY KEY CHECK ------------------

    @classmethod
    async def check_or_create_idempotency_key(
        cls,
        db: AsyncSession,
        event_key: str,
        action: str,
    ) -> Tuple[bool, Optional[IdempotencyKey]]:
        """
        Guarantees webhook idempotency.
        Returns (already_processed: bool, idempotency_record).
        """
        query = select(IdempotencyKey).where(IdempotencyKey.key == event_key)
        record = (await db.execute(query)).scalar_one_or_none()

        if record and record.status == "COMPLETED":
            return True, record

        if not record:
            record = IdempotencyKey(
                key=event_key,
                action=action,
                status="PROCESSING",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        return False, record

    # ------------------ RAZORPAY WEBHOOK HANDLER ------------------

    @classmethod
    async def handle_razorpay_webhook(
        cls,
        db: AsyncSession,
        raw_body: bytes,
        signature: Optional[str],
    ) -> Dict[str, Any]:
        """
        Validates HMAC-SHA256 signature and applies payment updates idempotently.
        """
        if not signature:
            raise BadRequestException("Razorpay signature header missing")

        # Cryptographic HMAC SHA256 verification
        expected_sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if settings.RAZORPAY_WEBHOOK_SECRET != "rzp_webhook_secret_placeholder":
            if not hmac.compare_digest(expected_sig, signature):
                raise BadRequestException("Invalid webhook HMAC signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise BadRequestException("Invalid JSON body")

        event = payload.get("event")
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = entity.get("id")
        rzp_order_id = entity.get("order_id")
        event_id = payload.get("event_id") or f"{event}_{payment_id}"

        # Check idempotency
        already_processed, idem_record = await cls.check_or_create_idempotency_key(
            db,
            event_key=event_id,
            action="WEBHOOK_RAZORPAY",
        )
        if already_processed:
            return {"status": "success", "message": "Event already processed (Idempotent)"}

        # Find matching order
        query = select(Order).where(Order.gateway_order_id == rzp_order_id)
        order = (await db.execute(query)).scalar_one_or_none()

        if not order:
            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "ignored", "reason": "order_not_found"}
                await db.commit()
            return {"status": "ignored", "reason": "No matching order found"}

        if event == "payment.captured":
            order.payment_status = PaymentStatus.PAID
            order.order_status = OrderStatus.CONFIRMED

            transaction = PaymentTransaction(
                order_id=order.id,
                gateway="RAZORPAY",
                transaction_id=payment_id,
                amount=order.final_payable,
                currency="INR",
                status="SUCCESS",
                gateway_response=entity,
            )
            db.add(transaction)

            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "paid", "payment_id": payment_id}

            await db.commit()

            # Fire background receipt
            await notification_service.send_payment_receipt(
                email="customer@example.com",
                transaction_data={"transaction_id": payment_id, "amount": float(order.final_payable)},
            )

        elif event == "payment.failed":
            order.payment_status = PaymentStatus.FAILED
            order.order_status = OrderStatus.CANCELLED

            # Rollback inventory
            await cls._rollback_order_inventory(db, order)

            transaction = PaymentTransaction(
                order_id=order.id,
                gateway="RAZORPAY",
                transaction_id=payment_id or f"failed_{uuid.uuid4().hex[:8]}",
                amount=order.final_payable,
                currency="INR",
                status="FAILED",
                gateway_response=entity,
            )
            db.add(transaction)

            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "failed", "payment_id": payment_id}

            await db.commit()

        return {"status": "success", "event": event}

    # ------------------ STRIPE WEBHOOK HANDLER ------------------

    @classmethod
    async def handle_stripe_webhook(
        cls,
        db: AsyncSession,
        raw_body: bytes,
        sig_header: Optional[str],
    ) -> Dict[str, Any]:
        """
        Validates Stripe webhook cryptographic signature and processes idempotently.
        """
        if not sig_header:
            raise BadRequestException("Stripe-Signature header missing")

        event = None
        if stripe and settings.STRIPE_WEBHOOK_SECRET != "whsec_placeholder":
            try:
                event = stripe.Webhook.construct_event(
                    payload=raw_body,
                    sig_header=sig_header,
                    secret=settings.STRIPE_WEBHOOK_SECRET,
                )
            except Exception as e:
                raise BadRequestException(f"Invalid Stripe webhook signature: {str(e)}")
        else:
            try:
                event = json.loads(raw_body.decode("utf-8"))
            except Exception:
                raise BadRequestException("Invalid JSON payload")

        event_id = event.get("id")
        event_type = event.get("type")
        data_object = event.get("data", {}).get("object", {})

        already_processed, idem_record = await cls.check_or_create_idempotency_key(
            db,
            event_key=event_id,
            action="WEBHOOK_STRIPE",
        )
        if already_processed:
            return {"status": "success", "message": "Event already processed (Idempotent)"}

        payment_intent_id = data_object.get("id")
        query = select(Order).where(Order.gateway_order_id == payment_intent_id)
        order = (await db.execute(query)).scalar_one_or_none()

        if not order:
            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "ignored", "reason": "order_not_found"}
                await db.commit()
            return {"status": "ignored", "reason": "Order not found for PaymentIntent"}

        if event_type == "payment_intent.succeeded":
            order.payment_status = PaymentStatus.PAID
            order.order_status = OrderStatus.CONFIRMED

            tx = PaymentTransaction(
                order_id=order.id,
                gateway="STRIPE",
                transaction_id=payment_intent_id,
                amount=order.final_payable,
                currency="INR",
                status="SUCCESS",
                gateway_response=data_object,
            )
            db.add(tx)

            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "paid", "intent_id": payment_intent_id}

            await db.commit()

        elif event_type == "payment_intent.payment_failed":
            order.payment_status = PaymentStatus.FAILED
            order.order_status = OrderStatus.CANCELLED

            await cls._rollback_order_inventory(db, order)

            tx = PaymentTransaction(
                order_id=order.id,
                gateway="STRIPE",
                transaction_id=payment_intent_id,
                amount=order.final_payable,
                currency="INR",
                status="FAILED",
                gateway_response=data_object,
            )
            db.add(tx)

            if idem_record:
                idem_record.status = "COMPLETED"
                idem_record.response_payload = {"status": "failed", "intent_id": payment_intent_id}

            await db.commit()

        return {"status": "success", "event_type": event_type}

    @staticmethod
    async def _rollback_order_inventory(db: AsyncSession, order: Order) -> None:
        """
        Safely restores stock if an order payment fails or expires.
        """
        from app.models.order import OrderItem
        items = list((await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all())
        p_ids = sorted([item.product_id for item in items if item.product_id])
        if p_ids:
            query = select(Product).where(Product.id.in_(p_ids)).order_by(Product.id).with_for_update()
            products = {p.id: p for p in (await db.execute(query)).scalars().all()}
            for it in items:
                if it.product_id and it.product_id in products:
                    products[it.product_id].stock += it.quantity


payment_service = PaymentService()
