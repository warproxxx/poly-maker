"""Tests for tweet_tracker.twitter_client module."""

import pytest
from unittest.mock import patch, MagicMock
from tweet_tracker.twitter_client import TwitterAPIClient, TwitterAPIError


def test_init_requires_api_key():
    """Should raise ValueError if api_key is empty."""
    with pytest.raises(ValueError, match="TWITTER_API_KEY"):
        TwitterAPIClient(api_key="")


def test_init_sets_headers():
    """Headers should include X-API-Key."""
    client = TwitterAPIClient(api_key="test_key_123")
    assert client.session.headers["X-API-Key"] == "test_key_123"


@patch("tweet_tracker.twitter_client.requests.Session")
def test_get_user_tweets_success(mock_session_cls):
    """Should return parsed JSON on success."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "tweets": [{"id": "1", "type": "tweet", "text": "hello"}],
        "has_next_page": False,
        "next_cursor": "",
        "status": "success",
    }
    mock_session.request.return_value = mock_resp

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session

    result = client.get_user_tweets(username="elonmusk")
    assert len(result["tweets"]) == 1
    assert result["tweets"][0]["id"] == "1"

    mock_session.request.assert_called_once_with(
        "GET",
        "https://api.twitterapi.io/twitter/user/last_tweets",
        params={"userName": "elonmusk"},
        timeout=30,
    )


@patch("tweet_tracker.twitter_client.requests.Session")
def test_get_user_tweets_with_cursor(mock_session_cls):
    """Should pass cursor parameter when provided."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"tweets": [], "has_next_page": False, "status": "success"}
    mock_session.request.return_value = mock_resp

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session

    client.get_user_tweets(username="elonmusk", cursor="abc123")

    call_params = mock_session.request.call_args[1]["params"]
    assert call_params["cursor"] == "abc123"


@patch("tweet_tracker.twitter_client.requests.Session")
def test_request_retries_on_failure(mock_session_cls):
    """Should retry on request exceptions with backoff."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session

    import requests as req
    mock_session.request.side_effect = req.ConnectionError("connection refused")

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session
    client.MAX_RETRIES = 2
    client.BACKOFF_BASE = 0.01  # fast backoff for test
    client.BASE_URL = "https://api.twitterapi.io"

    with pytest.raises(TwitterAPIError, match="retries exhausted"):
        client._request("GET", "/twitter/user/info")

    assert mock_session.request.call_count == 2


@patch("tweet_tracker.twitter_client.requests.Session")
def test_request_raises_on_api_error(mock_session_cls):
    """Should raise TwitterAPIError when API returns error status."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "error", "message": "Invalid API key"}
    mock_session.request.return_value = mock_resp

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session
    client.MAX_RETRIES = 1
    client.BACKOFF_BASE = 0.01
    client.BASE_URL = "https://api.twitterapi.io"

    with pytest.raises(TwitterAPIError, match="Invalid API key"):
        client._request("GET", "/twitter/user/info")


@patch("tweet_tracker.twitter_client.requests.Session")
def test_search_tweets(mock_session_cls):
    """Should call advanced_search endpoint with query."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"tweets": [], "status": "success"}
    mock_session.request.return_value = mock_resp

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session

    client.search_tweets("from:elonmusk since:2026-03-17")

    call_args = mock_session.request.call_args
    assert "/twitter/tweet/advanced_search" in call_args[0][1]
    assert call_args[1]["params"]["query"] == "from:elonmusk since:2026-03-17"


@patch("tweet_tracker.twitter_client.requests.Session")
def test_get_all_tweets_in_range_paginates(mock_session_cls):
    """Should paginate through all pages when has_next_page is True."""
    mock_session = MagicMock()

    page1 = MagicMock()
    page1.status_code = 200
    page1.json.return_value = {
        "tweets": [{"id": f"{i}"} for i in range(20)],
        "has_next_page": True,
        "next_cursor": "cursor2",
        "status": "success",
    }

    page2 = MagicMock()
    page2.status_code = 200
    page2.json.return_value = {
        "tweets": [{"id": f"{i}"} for i in range(20, 35)],
        "has_next_page": False,
        "next_cursor": "",
        "status": "success",
    }

    mock_session.request.side_effect = [page1, page2]

    client = TwitterAPIClient.__new__(TwitterAPIClient)
    client.session = mock_session
    client.MAX_RETRIES = 1
    client.BACKOFF_BASE = 0.01
    client.BASE_URL = "https://api.twitterapi.io"

    tweets = client.get_all_tweets_in_range("elonmusk", "2026-03-17", "2026-03-24")
    assert len(tweets) == 35
