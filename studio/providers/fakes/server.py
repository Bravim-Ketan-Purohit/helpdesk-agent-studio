"""Fake Slack + Jira provider server.

Implements the subset of Slack and Jira APIs that the system uses,
backed by in-memory state. No external accounts needed.

Usage: python -m studio.providers.fakes --port 7704
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

app = FastAPI(title="Fake Providers", description="Fake Slack + Jira for offline testing")

# --- In-memory state ---

slack_channels: dict[str, dict[str, Any]] = {
    "C001": {"id": "C001", "name": "helpdesk", "is_channel": True},
    "C002": {"id": "C002", "name": "engineering", "is_channel": True},
    "C003": {"id": "C003", "name": "general", "is_channel": True},
}

slack_messages: dict[str, list[dict[str, Any]]] = {
    "C001": [
        {
            "ts": "1700000001.000100",
            "user": "U001",
            "text": "My password isn't working, can someone help?",
            "channel": {"id": "C001", "name": "helpdesk"},
        },
        {
            "ts": "1700000002.000200",
            "user": "U002",
            "text": "I need a refund for order #12345",
            "channel": {"id": "C001", "name": "helpdesk"},
        },
    ],
}

slack_posted: list[dict[str, Any]] = []

jira_issues: dict[str, dict[str, Any]] = {
    "HELP-1": {
        "key": "HELP-1",
        "fields": {
            "summary": "Password reset request",
            "status": {"name": "Open", "id": "1"},
            "assignee": None,
            "priority": {"name": "Medium", "id": "3"},
            "description": "User cannot log in, requesting password reset.",
            "issuetype": {"name": "Task"},
            "project": {"key": "HELP"},
        },
    },
    "HELP-2": {
        "key": "HELP-2",
        "fields": {
            "summary": "Refund request - order #12345",
            "status": {"name": "Open", "id": "1"},
            "assignee": {"displayName": "Jane Chen"},
            "priority": {"name": "High", "id": "2"},
            "description": "Customer requesting refund of $45.00 for duplicate charge.",
            "issuetype": {"name": "Task"},
            "project": {"key": "HELP"},
        },
    },
    "HELP-3": {
        "key": "HELP-3",
        "fields": {
            "summary": "Escalation - critical outage report",
            "status": {"name": "In Progress", "id": "2"},
            "assignee": {"displayName": "Bob Smith"},
            "priority": {"name": "Critical", "id": "1"},
            "description": "Customer reports critical service outage. Needs immediate attention.",
            "issuetype": {"name": "Bug"},
            "project": {"key": "HELP"},
        },
    },
}

jira_transitions: dict[str, list[dict[str, Any]]] = {
    "HELP-1": [
        {"id": "21", "name": "In Progress"},
        {"id": "31", "name": "Done"},
        {"id": "41", "name": "Won't Do"},
    ],
    "HELP-2": [
        {"id": "21", "name": "In Progress"},
        {"id": "31", "name": "Done"},
    ],
    "HELP-3": [
        {"id": "31", "name": "Done"},
        {"id": "51", "name": "Escalated"},
    ],
}

jira_comments: dict[str, list[dict[str, Any]]] = {}

# Signing key for Slack signature verification testing
FAKE_SIGNING_SECRET = "fake_signing_secret_for_testing"


# --- Slack API endpoints ---


@app.get("/api/search.messages")
async def slack_search_messages(query: str, count: int = 20) -> dict[str, Any]:
    """Fake Slack search.messages."""
    results: list[dict[str, Any]] = []
    for channel_id, messages in slack_messages.items():
        for msg in messages:
            if query.lower() in msg.get("text", "").lower():
                results.append({
                    "text": msg["text"],
                    "ts": msg["ts"],
                    "user": msg["user"],
                    "channel": msg.get("channel", {"id": channel_id}),
                    "permalink": f"https://fake.slack.com/archives/{channel_id}/p{msg['ts'].replace('.', '')}",
                })
    return {"ok": True, "messages": {"matches": results[:count], "total": len(results)}}


@app.get("/api/conversations.history")
async def slack_conversations_history(channel: str, limit: int = 20) -> dict[str, Any]:
    """Fake Slack conversations.history."""
    messages = slack_messages.get(channel, [])
    return {"ok": True, "messages": messages[:limit]}


@app.get("/api/conversations.replies")
async def slack_conversations_replies(channel: str, ts: str) -> dict[str, Any]:
    """Fake Slack conversations.replies."""
    messages = slack_messages.get(channel, [])
    thread = [m for m in messages if m.get("ts") == ts or m.get("thread_ts") == ts]
    return {"ok": True, "messages": thread}


@app.get("/api/conversations.list")
async def slack_conversations_list(limit: int = 100) -> dict[str, Any]:
    """Fake Slack conversations.list."""
    return {"ok": True, "channels": list(slack_channels.values())[:limit]}


@app.post("/api/chat.postMessage")
async def slack_post_message(request: Request) -> dict[str, Any]:
    """Fake Slack chat.postMessage — records the post."""
    body = await request.json()
    channel = body.get("channel", "")
    text = body.get("text", "")
    thread_ts = body.get("thread_ts")

    msg = {
        "ts": f"{time.time():.6f}",
        "user": "BOT",
        "text": text,
        "channel": {"id": channel},
        "thread_ts": thread_ts,
    }

    if channel not in slack_messages:
        slack_messages[channel] = []
    slack_messages[channel].append(msg)
    slack_posted.append(msg)

    return {"ok": True, "ts": msg["ts"], "channel": channel, "message": msg}


# --- Jira API endpoints ---


@app.get("/rest/api/3/search")
async def jira_search(jql: str = "", maxResults: int = 20) -> dict[str, Any]:
    """Fake Jira search."""
    results = []
    query_lower = jql.lower()
    for key, issue in jira_issues.items():
        summary = issue["fields"].get("summary", "").lower()
        desc = issue["fields"].get("description", "").lower()
        if not jql or any(
            term in summary or term in desc
            for term in query_lower.replace('"', "").split()
            if term not in ("text", "~")
        ):
            results.append(issue)
    return {"issues": results[:maxResults], "total": len(results)}


@app.get("/rest/api/3/issue/{issue_key}")
async def jira_get_issue(issue_key: str) -> dict[str, Any]:
    """Fake Jira get issue."""
    issue = jira_issues.get(issue_key)
    if issue is None:
        return Response(status_code=404, content=json.dumps({"error": "Not found"}))
    return issue


@app.get("/rest/api/3/issue/{issue_key}/transitions")
async def jira_get_transitions(issue_key: str) -> dict[str, Any]:
    """Fake Jira get transitions."""
    transitions = jira_transitions.get(issue_key, [])
    return {"transitions": transitions}


@app.post("/rest/api/3/issue/{issue_key}/comment")
async def jira_add_comment(issue_key: str, request: Request) -> dict[str, Any]:
    """Fake Jira add comment — records the comment."""
    body = await request.json()
    comment_id = str(uuid.uuid4())

    comment = {
        "id": comment_id,
        "issue_key": issue_key,
        "body": body.get("body", {}),
        "created": datetime.now(timezone.utc).isoformat(),
        "author": {"displayName": "Helpdesk Bot"},
    }

    if issue_key not in jira_comments:
        jira_comments[issue_key] = []
    jira_comments[issue_key].append(comment)

    return comment


@app.post("/rest/api/3/issue/{issue_key}/transitions")
async def jira_do_transition(issue_key: str, request: Request) -> Response:
    """Fake Jira transition — updates the issue status."""
    body = await request.json()
    transition_id = body.get("transition", {}).get("id", "")

    issue = jira_issues.get(issue_key)
    if issue is None:
        return Response(status_code=404)

    # Find the transition name
    transitions = jira_transitions.get(issue_key, [])
    transition_name = "Unknown"
    for t in transitions:
        if t["id"] == transition_id:
            transition_name = t["name"]
            break

    # Update the issue status
    issue["fields"]["status"] = {"name": transition_name, "id": transition_id}

    return Response(status_code=204)


@app.get("/rest/api/3/project")
async def jira_list_projects() -> list[dict[str, Any]]:
    """Fake Jira list projects."""
    return [{"key": "HELP", "name": "Helpdesk", "id": "10001"}]


# --- Health and state endpoints ---


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "provider": "fakes"}


@app.get("/_state/slack/posted")
async def get_slack_posted() -> list[dict[str, Any]]:
    """Testing endpoint — get all posted Slack messages."""
    return slack_posted


@app.get("/_state/jira/comments/{issue_key}")
async def get_jira_comments(issue_key: str) -> list[dict[str, Any]]:
    """Testing endpoint — get all comments on an issue."""
    return jira_comments.get(issue_key, [])


@app.post("/_state/reset")
async def reset_state() -> dict[str, str]:
    """Reset all mutable state — for test isolation."""
    slack_posted.clear()
    jira_comments.clear()
    # Reset issue statuses
    for issue in jira_issues.values():
        if issue["key"] in ("HELP-1", "HELP-2"):
            issue["fields"]["status"] = {"name": "Open", "id": "1"}
    return {"status": "reset"}
