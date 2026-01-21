"""
Tests for Langfuse client caching functionality.
"""

import unittest
from unittest.mock import patch, MagicMock
from app.observability.tracing import (
    get_langfuse_client_for_user,
    get_callback_handler_for_user,
    cleanup_user_client,
    cleanup_all_clients,
    _user_langfuse_clients,
    _user_callback_handlers,
)


class TestLangfuseCaching(unittest.TestCase):
    """Test Langfuse client caching functionality."""

    def setUp(self):
        """Clear caches before each test."""
        _user_langfuse_clients.clear()
        _user_callback_handlers.clear()

    def tearDown(self):
        """Clean up after each test."""
        _user_langfuse_clients.clear()
        _user_callback_handlers.clear()

    @patch("app.observability.tracing.LANGFUSE_ENABLED", True)
    @patch("app.core.config.LANGFUSE_BASE_URL", "http://test.langfuse.com")
    def test_same_keys_return_same_client(self):
        """Test that same public_key returns the same cached client."""
        public_key = "test_public_key_123"
        secret_key = "test_secret_key_456"

        # Mock the Langfuse class
        with patch("app.observability.tracing.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client

            # First call should create new client
            client1 = get_langfuse_client_for_user(public_key, secret_key)
            self.assertEqual(client1, mock_client)
            self.assertEqual(mock_langfuse.call_count, 1)

            # Second call with same key should return cached client
            client2 = get_langfuse_client_for_user(public_key, secret_key)
            self.assertEqual(client1, client2)
            self.assertEqual(
                mock_langfuse.call_count, 1
            )  # Should not create new client

            # Verify client is cached
            self.assertIn(public_key, _user_langfuse_clients)
            self.assertEqual(_user_langfuse_clients[public_key], mock_client)

    @patch("app.observability.tracing.LANGFUSE_ENABLED", True)
    @patch("app.core.config.LANGFUSE_BASE_URL", "http://test.langfuse.com")
    def test_different_keys_return_different_clients(self):
        """Test that different public_keys return different clients."""
        key1 = ("test_public_key_1", "test_secret_key_1")
        key2 = ("test_public_key_2", "test_secret_key_2")

        # Mock the Langfuse class
        with patch("app.observability.tracing.Langfuse") as mock_langfuse:
            mock_client1 = MagicMock()
            mock_client2 = MagicMock()
            mock_langfuse.side_effect = [mock_client1, mock_client2]

            # First call
            client1 = get_langfuse_client_for_user(*key1)
            self.assertEqual(client1, mock_client1)

            # Second call with different key
            client2 = get_langfuse_client_for_user(*key2)
            self.assertEqual(client2, mock_client2)
            self.assertNotEqual(client1, client2)

            # Verify both clients are cached
            self.assertIn(key1[0], _user_langfuse_clients)
            self.assertIn(key2[0], _user_langfuse_clients)
            self.assertEqual(_user_langfuse_clients[key1[0]], mock_client1)
            self.assertEqual(_user_langfuse_clients[key2[0]], mock_client2)

    @patch("app.observability.tracing.LANGFUSE_ENABLED", True)
    @patch("app.core.config.LANGFUSE_BASE_URL", "http://test.langfuse.com")
    def test_callback_handler_caching(self):
        """Test that callback handlers are cached and reuse clients."""
        public_key = "test_public_key_123"
        secret_key = "test_secret_key_456"

        with (
            patch("app.observability.tracing.Langfuse") as mock_langfuse,
            patch("app.observability.tracing.CallbackHandler") as mock_callback_handler,
        ):
            mock_client = MagicMock()
            mock_handler = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_callback_handler.return_value = mock_handler

            # First call should create both client and handler
            handler1 = get_callback_handler_for_user(public_key, secret_key)
            self.assertEqual(handler1, mock_handler)
            self.assertEqual(mock_langfuse.call_count, 1)
            self.assertEqual(mock_callback_handler.call_count, 1)

            # Second call should reuse cached handler
            handler2 = get_callback_handler_for_user(public_key, secret_key)
            self.assertEqual(handler1, handler2)
            self.assertEqual(mock_langfuse.call_count, 1)  # Client not recreated
            self.assertEqual(
                mock_callback_handler.call_count, 1
            )  # Handler not recreated

    @patch("app.observability.tracing.LANGFUSE_ENABLED", True)
    def test_cleanup_user_client(self):
        """Test cleanup of specific user client."""
        public_key = "test_public_key_123"
        secret_key = "test_secret_key_456"

        with patch("app.observability.tracing.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client

            # Create and cache client
            client = get_langfuse_client_for_user(public_key, secret_key)
            self.assertIn(public_key, _user_langfuse_clients)

            # Cleanup should flush and shutdown client
            cleanup_user_client(public_key)

            # Verify cleanup calls were made
            mock_client.flush.assert_called_once()
            mock_client.shutdown.assert_called_once()

            # Verify client was removed from cache
            self.assertNotIn(public_key, _user_langfuse_clients)

    @patch("app.observability.tracing.LANGFUSE_ENABLED", True)
    def test_cleanup_all_clients(self):
        """Test cleanup of all cached clients."""
        # Setup multiple clients
        clients_data = [
            ("key1", "secret1"),
            ("key2", "secret2"),
        ]

        with patch("app.observability.tracing.Langfuse") as mock_langfuse:
            mock_clients = [MagicMock() for _ in clients_data]
            mock_langfuse.side_effect = mock_clients

            # Create clients
            for public_key, secret_key in clients_data:
                get_langfuse_client_for_user(public_key, secret_key)

            # Verify clients are cached
            self.assertEqual(len(_user_langfuse_clients), 2)

            # Cleanup all
            cleanup_all_clients()

            # Verify all clients were flushed and shutdown
            for mock_client in mock_clients:
                mock_client.flush.assert_called_once()
                mock_client.shutdown.assert_called_once()

            # Verify caches are empty
            self.assertEqual(len(_user_langfuse_clients), 0)
            self.assertEqual(len(_user_callback_handlers), 0)

    @patch("app.observability.tracing.LANGFUSE_ENABLED", False)
    def test_disabled_langfuse_returns_none(self):
        """Test that functions return None when LANGFUSE_ENABLED is False."""
        client = get_langfuse_client_for_user("key", "secret")
        handler = get_callback_handler_for_user("key", "secret")

        self.assertIsNone(client)
        self.assertIsNone(handler)

    def test_empty_keys_return_none(self):
        """Test that functions return None for empty/None keys."""
        test_cases = [
            (None, "secret"),
            ("", "secret"),
            ("key", None),
            ("key", ""),
        ]

        for public_key, secret_key in test_cases:
            with self.subTest(public_key=public_key, secret_key=secret_key):
                client = get_langfuse_client_for_user(public_key, secret_key)
                handler = get_callback_handler_for_user(public_key, secret_key)
                self.assertIsNone(client)
                self.assertIsNone(handler)


if __name__ == "__main__":
    unittest.main()
