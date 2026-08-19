"""Automatic document tagging based on filename keywords.

Assigns tags to documents when they are indexed, making filtering
in the Admin page easier.
"""

import re
from pathlib import Path

# Map of keyword patterns -> tags
TAG_RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"policy|policies|handbook"), ["hr", "policy"]),
    (re.compile(r"faq|question|answer"), ["hr", "faq"]),
    (re.compile(r"onboard|guide|getting.started"), ["hr", "onboarding"]),
    (re.compile(r"expense|reimburse|receipt|finance"), ["finance", "expense"]),
    (re.compile(r"manual|troubleshoot|fix|debug|support"), ["support", "manual"]),
    (re.compile(r"security|incident|breach"), ["security"]),
    (re.compile(r"remote|work.from.home|wfh"), ["policy", "remote"]),
    (re.compile(r"pto|vacation|leave|holiday"), ["hr", "benefits"]),
    (re.compile(r"401k|insurance|health|benefit"), ["hr", "benefits"]),
    (re.compile(r"password|vpn|wifi|network|it"), ["it"]),
    (re.compile(r"firmware|update|install|setup"), ["support", "technical"]),
]


def auto_tag(filename: str) -> list[str]:
    """Return tags for a document based on its filename."""
    name = filename.lower()
    tags: list[str] = []
    for pattern, tag_list in TAG_RULES:
        if pattern.search(name):
            for t in tag_list:
                if t not in tags:
                    tags.append(t)
    return tags
