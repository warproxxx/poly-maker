"""REST client for twitterapi.io — fetches Elon Musk tweets."""

import time
import requests
from tweet_tracker.logger import logger


class TwitterAPIError(Exception):
    """Raised when twitterapi.io returns an error."""


class TwitterAPIClient:
    BASE_URL = "https://api.twitterapi.io"
    MAX_RETRIES = 3
    BACKOFF_BASE = 2  # seconds

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("TWITTER_API_KEY is required")
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})

    def _request(self, method: str, path: str, params: dict = None) -> dict:
        """Make an HTTP request with retry + exponential backoff."""
        url = f"{self.BASE_URL}{path}"
        last_exc = None

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.session.request(method, url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "error":
                        raise TwitterAPIError(data.get("message", "Unknown API error"))
                    return data
                elif resp.status_code == 429:
                    wait = self.BACKOFF_BASE ** (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait}s (attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                else:
                    raise TwitterAPIError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
            except requests.RequestException as e:
                last_exc = e
                wait = self.BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    f"Request failed: {e}, retrying in {wait}s (attempt {attempt + 1})"
                )
                time.sleep(wait)

        raise TwitterAPIError(f"All {self.MAX_RETRIES} retries exhausted: {last_exc}")

    def get_user_tweets(
        self,
        username: str = "elonmusk",
        cursor: str = "",
        include_replies: bool = False,
    ) -> dict:
        """Fetch a user's recent tweets (up to 20 per page).

        Returns:
            {
                "tweets": [...],
                "has_next_page": bool,
                "next_cursor": str
            }
        """
        params = {"userName": username}
        if cursor:
            params["cursor"] = cursor
        if include_replies:
            params["includeReplies"] = "true"

        data = self._request("GET", "/twitter/user/last_tweets", params)
        logger.debug(f"Fetched {len(data.get('tweets', []))} tweets for @{username}")
        return data

    def search_tweets(self, query: str, query_type: str = "Latest", cursor: str = "") -> dict:
        """Advanced tweet search (e.g. 'from:elonmusk since:2026-03-17 until:2026-03-24').

        Returns same structure as get_user_tweets.
        """
        params = {"query": query, "queryType": query_type}
        if cursor:
            params["cursor"] = cursor

        data = self._request("GET", "/twitter/tweet/advanced_search", params)
        logger.debug(f"Search '{query}': {len(data.get('tweets', []))} results")
        return data

    def get_user_info(self, username: str = "elonmusk") -> dict:
        """Fetch user profile information."""
        return self._request("GET", "/twitter/user/info", {"userName": username})

    def get_all_tweets_in_range(
        self,
        username: str,
        since: str,
        until: str,
        include_replies: bool = False,
    ) -> list:
        """Fetch ALL tweets for a user in a date range using paginated search.

        Args:
            username: Twitter username (without @)
            since: Start date 'YYYY-MM-DD'
            until: End date 'YYYY-MM-DD' (exclusive)

        Returns:
            List of tweet objects
        """
        query = f"from:{username} since:{since} until:{until}"
        if not include_replies:
            query += " -filter:replies"

        all_tweets = []
        cursor = ""

        while True:
            data = self.search_tweets(query, cursor=cursor)
            tweets = data.get("tweets", [])
            if not tweets:
                break

            all_tweets.extend(tweets)
            logger.info(f"Fetched {len(all_tweets)} tweets so far for range {since} to {until}")

            if not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor", "")
            if not cursor:
                break

        return all_tweets
