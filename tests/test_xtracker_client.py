"""Tests for tweet_tracker.xtracker_client module."""

from unittest.mock import patch, MagicMock
from tweet_tracker.xtracker_client import XTrackerClient


class TestValidateCount:
    @patch.object(XTrackerClient, "get_post_count")
    def test_within_threshold(self, mock_get):
        mock_get.return_value = {"count": 100}
        client = XTrackerClient()
        assert client.validate_count(102) is True
        assert client.last_count == 100

    @patch.object(XTrackerClient, "get_post_count")
    def test_exceeds_threshold(self, mock_get):
        mock_get.return_value = {"count": 100}
        client = XTrackerClient()
        assert client.validate_count(110) is False

    @patch.object(XTrackerClient, "get_post_count")
    def test_xtracker_unavailable(self, mock_get):
        mock_get.return_value = None
        client = XTrackerClient()
        # Should return True (don't block trading)
        assert client.validate_count(100) is True

    @patch.object(XTrackerClient, "get_post_count")
    def test_alternative_field_names(self, mock_get):
        """Should handle different response field names."""
        mock_get.return_value = {"postCount": 50}
        client = XTrackerClient()
        assert client.validate_count(52) is True
        assert client.last_count == 50

    @patch.object(XTrackerClient, "get_post_count")
    def test_non_numeric_count(self, mock_get):
        mock_get.return_value = {"count": "not_a_number"}
        client = XTrackerClient()
        assert client.validate_count(100) is True  # graceful fallback


class TestGetPostCount:
    @patch("tweet_tracker.xtracker_client.requests.Session")
    def test_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"count": 42}
        mock_session.get.return_value = mock_resp

        client = XTrackerClient()
        client.session = mock_session

        result = client.get_post_count("elonmusk")
        assert result == {"count": 42}

    @patch("tweet_tracker.xtracker_client.requests.Session")
    def test_http_error(self, mock_session_cls):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_session.get.return_value = mock_resp

        client = XTrackerClient()
        client.session = mock_session

        assert client.get_post_count("elonmusk") is None

    @patch("tweet_tracker.xtracker_client.requests.Session")
    def test_network_error(self, mock_session_cls):
        mock_session = MagicMock()
        import requests
        mock_session.get.side_effect = requests.ConnectionError("refused")

        client = XTrackerClient()
        client.session = mock_session

        assert client.get_post_count("elonmusk") is None
