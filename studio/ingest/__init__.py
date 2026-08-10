"""Ingest module — Slack events, Jira webhooks, signature verification.

All inbound webhooks are verified before processing:
- Slack: X-Slack-Signature + timestamp window (prevents replay)
- Jira: webhook verification token

An unverified webhook endpoint on a project about trust boundaries is self-defeating.
"""
