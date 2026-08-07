"""Slack provider — read-only and write clients, separate by construction."""

from studio.providers.slack.reader import SlackReadOnlyProvider
from studio.providers.slack.writer import SlackWriteProvider

__all__ = ["SlackReadOnlyProvider", "SlackWriteProvider"]
