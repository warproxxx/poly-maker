"""Tweet counter that follows Polymarket settlement rules.

Counting rules (per Polymarket):
- Counted: original tweets, retweets, quote tweets
- NOT counted: replies (isReply=true)
"""

from datetime import datetime, timezone
from tweet_tracker.logger import logger
import tweet_tracker.tweet_state as tweet_state


class TweetCounter:
    def __init__(self, twitter_client, period_start: datetime, period_end: datetime):
        self.client = twitter_client
        self.period_start = period_start
        self.period_end = period_end
        self.counted_ids: set = set()

    @staticmethod
    def should_count(tweet: dict) -> bool:
        """Determine if a tweet should be counted per Polymarket rules.

        Counted: original tweets, retweets, quote tweets
        Not counted: replies
        """
        if tweet.get("isReply", False):
            return False

        tweet_type = tweet.get("type", "")
        return tweet_type in ("tweet", "retweet", "quote")

    def _is_in_period(self, tweet: dict) -> bool:
        """Check if tweet falls within the tracking period."""
        created_str = tweet.get("createdAt", "")
        if not created_str:
            return False

        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            # Try alternative timestamp formats
            try:
                # Twitter format: "Wed Mar 19 12:34:56 +0000 2026"
                created = datetime.strptime(created_str, "%a %b %d %H:%M:%S %z %Y")
            except (ValueError, TypeError):
                logger.warning(f"Cannot parse tweet date: {created_str}")
                return False

        return self.period_start <= created < self.period_end

    def process_tweets(self, tweets: list) -> int:
        """Process a batch of tweets. Returns count of new tweets added."""
        new_count = 0
        for tweet in tweets:
            tweet_id = tweet.get("id", "")
            if not tweet_id or tweet_id in self.counted_ids:
                continue

            if not self._is_in_period(tweet):
                continue

            if self.should_count(tweet):
                self.counted_ids.add(tweet_id)
                new_count += 1

        if new_count > 0:
            logger.info(
                f"Added {new_count} new tweets, total: {len(self.counted_ids)}"
            )

        return new_count

    def poll_and_update(self, username: str = "elonmusk") -> int:
        """Poll for new tweets and update count. Returns current total."""
        try:
            data = self.client.get_user_tweets(username=username)
            tweets = data.get("tweets", [])
            self.process_tweets(tweets)
        except Exception as e:
            logger.error(f"Poll failed: {e}", exc_info=True)

        # Sync to global state
        with tweet_state.lock:
            tweet_state.current_count = len(self.counted_ids)
            tweet_state.last_update_time = datetime.now(timezone.utc)

        return len(self.counted_ids)

    def full_sync(self, username: str = "elonmusk") -> int:
        """Do a full sync using date-range search. More accurate but uses more API credits."""
        since = self.period_start.strftime("%Y-%m-%d")
        until = self.period_end.strftime("%Y-%m-%d")

        try:
            all_tweets = self.client.get_all_tweets_in_range(
                username=username, since=since, until=until
            )
            self.process_tweets(all_tweets)
            logger.info(f"Full sync complete: {len(self.counted_ids)} tweets")
        except Exception as e:
            logger.error(f"Full sync failed: {e}", exc_info=True)

        with tweet_state.lock:
            tweet_state.current_count = len(self.counted_ids)
            tweet_state.last_update_time = datetime.now(timezone.utc)

        return len(self.counted_ids)

    def get_count(self) -> int:
        return len(self.counted_ids)
