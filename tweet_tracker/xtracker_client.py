"""xTracker client for cross-validating tweet counts.

xTracker (https://xtracker.polymarket.com) is Polymarket's official tweet
counting source. We use it as a secondary validation against our own counter.
"""

from typing import Optional

import requests
from tweet_tracker.logger import logger
from tweet_tracker.config import TWEET_CONFIG


class XTrackerError(Exception):
    """Raised when xTracker request fails."""


class XTrackerClient:
    BASE_URL = "https://xtracker.polymarket.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; PolyMaker/1.0)",
            "Accept": "application/json",
        })
        self._last_count = None

    def get_post_count(self, username: str = "elonmusk") -> Optional[dict]:
        """Fetch current post count from xTracker.

        Returns dict with count info or None on failure.
        The exact API structure depends on xTracker's endpoints.
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/user/{username}",
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.debug(f"xTracker response for @{username}: {data}")
                return data
            else:
                logger.warning(f"xTracker returned HTTP {resp.status_code}")
                return None
        except requests.RequestException as e:
            logger.warning(f"xTracker request failed: {e}")
            return None

    def validate_count(self, local_count: int, username: str = "elonmusk") -> bool:
        """Compare local count with xTracker. Returns True if within threshold."""
        data = self.get_post_count(username)
        if data is None:
            logger.warning("Cannot validate: xTracker unavailable")
            return True  # Don't block trading on validation failure

        xt_count = data.get("count", data.get("postCount", data.get("posts", 0)))
        if not isinstance(xt_count, (int, float)):
            logger.warning(f"xTracker returned non-numeric count: {xt_count}")
            return True

        xt_count = int(xt_count)
        diff = abs(local_count - xt_count)
        threshold = TWEET_CONFIG["xtracker_count_diff_alert"]

        if diff > threshold:
            logger.warning(
                f"Count mismatch: local={local_count} vs xTracker={xt_count}, "
                f"diff={diff} (threshold={threshold})"
            )
            return False

        logger.debug(f"Count validated: local={local_count}, xTracker={xt_count}")
        self._last_count = xt_count
        return True

    @property
    def last_count(self) -> Optional[int]:
        return self._last_count
