"""Critical-event alerting via a generic webhook POST.

Fire-and-forget, deduped, and rate-limited so a flapping condition can't spam.
Works with any endpoint that accepts a JSON POST (Discord/Slack/Telegram-bridge/
ntfy). No-ops cleanly when no webhook is configured, so callers never branch.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import httpx

from polymaker.logging import get_logger

log = get_logger("alerts")


class Alerter:
    def __init__(self, webhook_url: str | None, *, min_interval_s: float = 30.0,
                 proxy: str | None = None) -> None:
        self._url = webhook_url
        self._min_interval = min_interval_s
        self._proxy = proxy
        self._last_sent: dict[str, float] = {}  # key -> ts (dedupe/rate-limit)

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def alert(self, key: str, message: str, *, critical: bool = False) -> None:
        """Queue an alert. `key` dedupes/rate-limits repeated conditions.

        Always logs (so nothing is lost even without a webhook); posts to the
        webhook at most once per `min_interval_s` per key (critical bypasses the
        limit). Safe to call from sync code — schedules the POST on the loop.
        """
        (log.critical if critical else log.warning)("alert", key=key, msg=message)
        if not self._url:
            return
        now = time.time()
        if not critical and now - self._last_sent.get(key, 0.0) < self._min_interval:
            return
        self._last_sent[key] = now
        with contextlib.suppress(RuntimeError):  # no running loop (off-loop call)
            asyncio.get_running_loop().create_task(self._post(key, message, critical))

    async def _post(self, key: str, message: str, critical: bool) -> None:
        text = f"{'🚨' if critical else '⚠️'} polymaker [{key}] {message}"
        try:
            kwargs: dict[str, object] = {"timeout": 10.0}
            if self._proxy:
                kwargs["proxy"] = self._proxy
            async with httpx.AsyncClient(**kwargs) as c:  # type: ignore[arg-type]
                # send both keys so Slack ("text") and Discord ("content") work
                await c.post(self._url, json={"text": text, "content": text})  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            log.warning("alert_post_failed", err=str(exc))
