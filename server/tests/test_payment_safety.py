"""The buyer must not lose money when the network does.

Losing connection mid-payment does not stop the payment: the gateway and
the bank finish it regardless. "Losing money" is therefore never *the money
didn't leave* — it is *the money left and the order never became PAID*.

Three defences, one per failure this system can actually suffer:

  the sweep must not cancel an order somebody is paying for   (prevention)
  a webhook that never arrives must still be noticed          (detection)
  money that cannot be applied must be recorded, not dropped  (recovery)
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.payments.security import compute_hash
from tests.conftest import USER_A_ID, USER_ADMIN_ID, USER_B_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)


@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield


ADDRESS = "12 Lê Lợi, Q1, HCM"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def token_for(base_url: str, vapp_user_id: str) -> str:
    async with httpx.AsyncClient() as client:
        issued = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": vapp_user_id, "scopes": "profile phone"},
        )
        session = await client.post(
            f"{base_url}/auth/session",
            json={"authCode": issued.json()["data"]["authCode"]},
        )
    return session.json()["token"]


async def order_for(base_url: str, stock: int = 5) -> tuple[str, dict, str]:
    """A shop, a product and one PENDING order. Returns (buyer, order, pid)."""
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop B", "description": "."},
        )
        product = (
            await client.post(
                f"{base_url}/products",
                headers=auth(seller),
                json={
                    "name": "Hàng thanh toán",
                    "description": ".",
                    "price": 100_000,
                    "stock": stock,
                },
            )
        ).json()
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [{"productId": product["id"], "qty": 1}],
                },
            )
        ).json()
    return buyer, order, product["id"]


# --- Prevention: the sweep leaves a payment in progress alone --------------


async def test_an_order_being_paid_is_not_swept_away(base_url, monkeypatch):
    """The scenario that costs real money: the buyer is at the bank's OTP
    screen when the stock hold lapses."""
    buyer, order, product_id = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        opened = await client.post(
            f"{base_url}/payments/session",
            headers=auth(buyer),
            json={"orderId": order["id"]},
        )

        # The plain hold runs out while they are still paying.
        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        listed = (
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        ).json()["items"][0]
        stock = (await client.get(f"{base_url}/products/{product_id}")).json()

        # The payment then lands, as it would have.
        amount = int(order["total"])
        ipn = await client.post(
            f"{base_url}/payments/ipn",
            json={
                "paymentId": opened.json()["paymentId"],
                "orderId": order["id"],
                "amount": amount,
                "status": "PAID",
                "secureHash": compute_hash(
                    settings.payment_ipn_secret, order["id"], amount, "PAID"
                ),
            },
        )
        final = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()

    assert opened.status_code == 200
    # Still alive, still holding its stock, and the grace shows in expiresAt.
    assert listed["status"] == "PENDING"
    assert stock["stock"] == 4
    assert ipn.status_code == 200
    assert final["status"] == "PAID"


async def test_an_abandoned_order_with_no_session_is_still_swept(
    base_url, monkeypatch
):
    """The grace applies to payments in progress, not to every order —
    otherwise nothing would ever release its stock again."""
    buyer, _, product_id = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        listed = (
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        ).json()["items"][0]
        stock = (await client.get(f"{base_url}/products/{product_id}")).json()

    assert listed["status"] == "CANCELLED"
    assert stock["stock"] == 5


async def test_a_session_cannot_be_opened_on_someone_elses_order(base_url):
    _, order, _ = await order_for(base_url)
    stranger = await token_for(base_url, USER_B_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/payments/session",
            headers=auth(stranger),
            json={"orderId": order["id"]},
        )

    assert response.status_code == 404  # not 403 — ids stay undiscoverable


# --- Detection: a webhook that never arrives ------------------------------


async def test_reconciliation_recovers_a_payment_whose_webhook_was_lost(
    base_url, monkeypatch
):
    """Confirm the payment at the gateway with the merchant's IPN endpoint
    pointed somewhere that swallows it — the money moves, the webhook never
    lands — then let reconciliation find it."""
    buyer, order, product_id = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        opened = (
            await client.post(
                f"{base_url}/payments/session",
                headers=auth(buyer),
                json={"orderId": order["id"]},
            )
        ).json()

        # Capture whatever the mock is configured with, so it can be put
        # back exactly. Restoring to this test's own base_url pointed the
        # shared mock at a port that dies with the test run, and every later
        # webhook — including the seed script's — went nowhere.
        original = (
            await client.post(
                f"{settings.vapp_base_url}/simulator/config", json={}
            )
        ).json()["data"]["merchant_ipn_url"]

        # Break the mock's delivery so the notification is lost in transit.
        # It stays broken for the whole test: the gateway retries with
        # backoff, and restoring the URL early just lets a retry win —
        # which is the gateway saving us, not reconciliation.
        await client.post(
            f"{settings.vapp_base_url}/simulator/config",
            json={"merchant_ipn_url": "http://127.0.0.1:9/nowhere"},
        )
        try:
            await client.post(
                f"{settings.vapp_base_url}/simulator/payment/"
                f"{opened['paymentId']}/confirm",
                json={},
            )

            during = (
                await client.get(
                    f"{base_url}/orders/{order['id']}", headers=auth(buyer)
                )
            ).json()

            # The merchant asks instead of waiting.
            summary = (
                await client.post(
                    f"{base_url}/payments/reconcile?older_than_seconds=0", json={}
                )
            ).json()
            after = (
                await client.get(
                    f"{base_url}/orders/{order['id']}", headers=auth(buyer)
                )
            ).json()
            stock = (
                await client.get(f"{base_url}/products/{product_id}")
            ).json()
        finally:
            # The mock is a shared process; leaving it pointed at nowhere
            # would silently break every later test.
            await client.post(
                f"{settings.vapp_base_url}/simulator/config",
                json={"merchant_ipn_url": original},
            )

    assert during["status"] == "PENDING"  # the webhook never came
    assert summary["recovered"] == 1
    assert after["status"] == "PAID"
    assert stock["stock"] == 4  # and the hold became a sale


async def test_reconciliation_leaves_an_unpaid_order_alone(base_url):
    """Asking the gateway about a session nobody completed must not
    invent a payment."""
    buyer, order, _ = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/payments/session",
            headers=auth(buyer),
            json={"orderId": order["id"]},
        )
        summary = (
            await client.post(
                f"{base_url}/payments/reconcile?older_than_seconds=0", json={}
            )
        ).json()
        after = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()

    assert summary["checked"] == 1
    assert summary["recovered"] == 0
    assert after["status"] == "PENDING"


# --- Recovery: money that cannot be applied -------------------------------


async def signed_ipn(order_id: str, amount: int, payment_id: str) -> dict:
    return {
        "paymentId": payment_id,
        "orderId": order_id,
        "amount": amount,
        "status": "PAID",
        "secureHash": compute_hash(
            settings.payment_ipn_secret, order_id, amount, "PAID"
        ),
    }


async def test_payment_for_a_cancelled_order_is_recorded_for_refund(
    base_url, monkeypatch
):
    buyer, order, _ = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        # The order is cancelled while the buyer is still paying.
        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        await client.get(f"{base_url}/orders", headers=auth(buyer))

        amount = int(order["total"])
        refused = await client.post(
            f"{base_url}/payments/ipn",
            json=await signed_ipn(order["id"], amount, "pay_late_1"),
        )
        # The gateway retries; the debt must not be recorded twice.
        await client.post(
            f"{base_url}/payments/ipn",
            json=await signed_ipn(order["id"], amount, "pay_late_1"),
        )
        operator = await token_for(base_url, USER_ADMIN_ID)
        open_items = (
            await client.get(
                f"{base_url}/payments/exceptions", headers=auth(operator)
            )
        ).json()["items"]

    assert refused.status_code == 409
    # Filtered by payment id: the mock retries earlier tests' webhooks in
    # the background, and their arrivals are noise here, not this test's
    # subject.
    ours = [e for e in open_items if e["gatewayPaymentId"] == "pay_late_1"]
    assert len(ours) == 1  # the retry did not queue a second debt
    entry = ours[0]
    assert entry["gatewayPaymentId"] == "pay_late_1"
    assert entry["orderId"] == order["id"]
    assert entry["amount"] == amount
    assert "hoàn tiền" in entry["reason"]


async def test_payment_for_an_unknown_order_is_recorded_too(base_url):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/payments/ipn",
            json=await signed_ipn("no-such-order", 250_000, "pay_ghost"),
        )
        operator = await token_for(base_url, USER_ADMIN_ID)
        open_items = (
            await client.get(
                f"{base_url}/payments/exceptions", headers=auth(operator)
            )
        ).json()["items"]

    assert response.status_code == 404
    ours = [e for e in open_items if e["gatewayPaymentId"] == "pay_ghost"]
    assert len(ours) == 1
    assert ours[0]["orderId"] == "no-such-order"


async def test_a_successful_payment_records_no_exception(base_url):
    buyer, order, _ = await order_for(base_url)

    async with httpx.AsyncClient() as client:
        amount = int(order["total"])
        ok = await client.post(
            f"{base_url}/payments/ipn",
            json=await signed_ipn(order["id"], amount, "pay_fine"),
        )
        operator = await token_for(base_url, USER_ADMIN_ID)
        open_items = (
            await client.get(
                f"{base_url}/payments/exceptions", headers=auth(operator)
            )
        ).json()["items"]

    assert ok.status_code == 200
    assert [e for e in open_items if e["gatewayPaymentId"] == "pay_fine"] == []


# --- Who may look at the money ---------------------------------------------


async def test_only_an_operator_can_read_the_refund_queue(base_url):
    """The list carries gateway payment ids and amounts across every shop,
    so it is not for buyers, not for sellers, and not for the internet."""
    buyer = await token_for(base_url, USER_A_ID)
    seller = await token_for(base_url, USER_B_ID)
    operator = await token_for(base_url, USER_ADMIN_ID)

    async with httpx.AsyncClient() as client:
        anonymous = await client.get(f"{base_url}/payments/exceptions")
        as_buyer = await client.get(
            f"{base_url}/payments/exceptions", headers=auth(buyer)
        )
        as_seller = await client.get(
            f"{base_url}/payments/exceptions", headers=auth(seller)
        )
        as_operator = await client.get(
            f"{base_url}/payments/exceptions", headers=auth(operator)
        )

    assert anonymous.status_code == 401
    assert as_buyer.status_code == 403
    assert as_seller.status_code == 403
    assert as_operator.status_code == 200


async def test_resolving_takes_a_debt_off_the_queue(base_url):
    operator = await token_for(base_url, USER_ADMIN_ID)

    async with httpx.AsyncClient() as client:
        # Money for an order that never existed: straight onto the queue.
        await client.post(
            f"{base_url}/payments/ipn",
            json=await signed_ipn("ghost-order", 500_000, "pay_to_refund"),
        )
        before = (
            await client.get(
                f"{base_url}/payments/exceptions", headers=auth(operator)
            )
        ).json()["items"]
        entry = next(
            e for e in before if e["gatewayPaymentId"] == "pay_to_refund"
        )

        resolved = await client.post(
            f"{base_url}/payments/exceptions/{entry['id']}/resolve",
            headers=auth(operator),
        )
        # Resolving twice is not an error — the operator may retry.
        again = await client.post(
            f"{base_url}/payments/exceptions/{entry['id']}/resolve",
            headers=auth(operator),
        )
        after = (
            await client.get(
                f"{base_url}/payments/exceptions", headers=auth(operator)
            )
        ).json()["items"]

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert again.status_code == 200
    assert [e for e in after if e["gatewayPaymentId"] == "pay_to_refund"] == []
