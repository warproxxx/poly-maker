"""Tests for tweet_tracker.tweet_counter module."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from tweet_tracker.tweet_counter import TweetCounter
import tweet_tracker.tweet_state as tweet_state


@pytest.fixture(autouse=True)
def reset_state():
    tweet_state.reset()
    yield
    tweet_state.reset()


@pytest.fixture
def counter():
    mock_client = MagicMock()
    start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
    return TweetCounter(mock_client, start, end)


def make_tweet(tweet_id, tweet_type="tweet", is_reply=False, created_at="2026-03-20T12:00:00Z"):
    return {
        "id": tweet_id,
        "type": tweet_type,
        "isReply": is_reply,
        "createdAt": created_at,
        "text": f"Tweet {tweet_id}",
    }


class TestShouldCount:
    def test_original_tweet_counted(self):
        assert TweetCounter.should_count(make_tweet("1", "tweet")) is True

    def test_retweet_counted(self):
        assert TweetCounter.should_count(make_tweet("2", "retweet")) is True

    def test_quote_tweet_counted(self):
        assert TweetCounter.should_count(make_tweet("3", "quote")) is True

    def test_reply_not_counted(self):
        assert TweetCounter.should_count(make_tweet("4", "tweet", is_reply=True)) is False

    def test_reply_type_with_flag(self):
        assert TweetCounter.should_count(make_tweet("5", "reply", is_reply=True)) is False

    def test_unknown_type_not_counted(self):
        assert TweetCounter.should_count(make_tweet("6", "unknown")) is False


class TestProcessTweets:
    def test_counts_valid_tweets(self, counter):
        tweets = [
            make_tweet("1", "tweet"),
            make_tweet("2", "retweet"),
            make_tweet("3", "quote"),
        ]
        added = counter.process_tweets(tweets)
        assert added == 3
        assert counter.get_count() == 3

    def test_skips_replies(self, counter):
        tweets = [
            make_tweet("1", "tweet"),
            make_tweet("2", "tweet", is_reply=True),
        ]
        added = counter.process_tweets(tweets)
        assert added == 1
        assert counter.get_count() == 1

    def test_deduplicates_tweets(self, counter):
        tweets = [make_tweet("1", "tweet")]
        counter.process_tweets(tweets)
        counter.process_tweets(tweets)  # duplicate
        assert counter.get_count() == 1

    def test_skips_tweets_outside_period(self, counter):
        tweets = [
            make_tweet("1", "tweet", created_at="2026-03-20T12:00:00Z"),  # in period
            make_tweet("2", "tweet", created_at="2026-03-15T12:00:00Z"),  # before
            make_tweet("3", "tweet", created_at="2026-03-25T12:00:00Z"),  # after
        ]
        added = counter.process_tweets(tweets)
        assert added == 1

    def test_empty_tweets_list(self, counter):
        assert counter.process_tweets([]) == 0
        assert counter.get_count() == 0

    def test_tweet_without_id_skipped(self, counter):
        tweets = [{"type": "tweet", "isReply": False, "createdAt": "2026-03-20T12:00:00Z"}]
        assert counter.process_tweets(tweets) == 0

    def test_handles_twitter_date_format(self, counter):
        """Should handle Twitter's native date format."""
        tweet = make_tweet("1", "tweet", created_at="Wed Mar 18 12:34:56 +0000 2026")
        assert counter.process_tweets([tweet]) == 1


class TestPollAndUpdate:
    def test_poll_updates_state(self, counter):
        counter.client.get_user_tweets.return_value = {
            "tweets": [
                make_tweet("1", "tweet"),
                make_tweet("2", "retweet"),
            ]
        }

        count = counter.poll_and_update()
        assert count == 2
        assert tweet_state.current_count == 2
        assert tweet_state.last_update_time is not None

    def test_poll_handles_api_error(self, counter):
        counter.client.get_user_tweets.side_effect = Exception("API down")
        count = counter.poll_and_update()
        assert count == 0  # graceful failure

    def test_poll_accumulates_over_time(self, counter):
        counter.client.get_user_tweets.return_value = {
            "tweets": [make_tweet("1", "tweet")]
        }
        counter.poll_and_update()

        counter.client.get_user_tweets.return_value = {
            "tweets": [
                make_tweet("1", "tweet"),  # duplicate
                make_tweet("2", "retweet"),  # new
            ]
        }
        count = counter.poll_and_update()
        assert count == 2  # total


class TestBoundaryConditions:
    def test_tweet_at_period_start(self, counter):
        tweet = make_tweet("1", "tweet", created_at="2026-03-17T00:00:00Z")
        assert counter.process_tweets([tweet]) == 1

    def test_tweet_at_period_end_exclusive(self, counter):
        tweet = make_tweet("1", "tweet", created_at="2026-03-24T00:00:00Z")
        assert counter.process_tweets([tweet]) == 0

    def test_tweet_one_second_before_end(self, counter):
        tweet = make_tweet("1", "tweet", created_at="2026-03-23T23:59:59Z")
        assert counter.process_tweets([tweet]) == 1
