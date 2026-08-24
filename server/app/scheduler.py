"""The jobs that must run whether or not anybody is using the shop.

Three of them. Two were previously piggy-backing on user traffic:

  * releasing the stock of orders nobody paid for. It ran when someone
    placed an order or opened their order list, which means a quiet night
    left held stock held. The buyer who wanted that unit at 3am was told it
    was gone.
  * asking the gateway about payments we never got a webhook for. There was
    an endpoint, but nothing called it, so the safety net for a lost
    notification only worked if a human remembered to pull it.

Run in-process on an asyncio task rather than through APScheduler or an
external cron: no new dependency, it starts and stops with the app, and
there is no scheduler host in this project to put a cron on.

The honest limitation: with more than one worker every worker runs this,
so the polling is duplicated. It costs a query and nothing else — both jobs
are idempotent, and the order status guards them — but a real deployment
wants a leader lock or an external trigger rather than N copies.
"""

import asyncio
import logging

from app.config import settings
from app.db import SessionFactory

log = logging.getLogger("vmarket.scheduler")


async def _tick() -> None:
    """One pass of both jobs. Never raises: a failed pass must not end the
    loop, or the first blip would silently disable the safety nets."""
    from app.orders import store as orders

    try:
        async with SessionFactory() as session:
            released = await orders.release_expired(session)
            if released:
                log.info("released stock from %d expired order(s)", released)
    except Exception:  # noqa: BLE001 — keep the loop alive
        log.exception("release_expired failed")

    try:
        async with SessionFactory() as session:
            moved = await orders.advance_simulated_fulfilment(session)
            if moved:
                log.info("simulated courier moved %d shop order(s)", moved)
    except Exception:  # noqa: BLE001
        log.exception("advance_simulated_fulfilment failed")

    try:
        async with SessionFactory() as session:
            summary = await orders.reconcile_pending(session)
            if summary["recovered"]:
                log.warning(
                    "recovered %d payment(s) the webhook never delivered",
                    summary["recovered"],
                )
    except Exception:  # noqa: BLE001
        log.exception("reconcile_pending failed")


async def _loop() -> None:
    while True:
        await asyncio.sleep(settings.scheduler_interval_seconds)
        await _tick()


def start() -> asyncio.Task | None:
    """Start the background loop, unless it is switched off.

    Tests switch it off: they move the clock by monkeypatching the hold
    window, and a loop cancelling orders underneath them would make
    failures depend on timing.
    """
    if not settings.scheduler_enabled:
        log.info("scheduler disabled")
        return None
    log.info("scheduler every %ds", settings.scheduler_interval_seconds)
    return asyncio.create_task(_loop())


async def stop(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
