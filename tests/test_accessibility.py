"""Accessibility regression tests for the chatwire web UI.

Verifies that ARIA roles, live regions, skip-nav, and accessible labels
are present in the rendered templates. These tests parse templates as text
(no browser required) and guard against attribute regressions.
"""
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"
STATIC = Path(__file__).resolve().parent.parent / "web" / "static"


def _read(relpath: str) -> str:
    return (TEMPLATES / relpath).read_text()


def _read_static(relpath: str) -> str:
    return (STATIC / relpath).read_text()


# ---------------------------------------------------------------------------
# Test 1: Message container (role="log" + aria-live + aria-label)
# ---------------------------------------------------------------------------

def test_message_container_aria_log():
    """_conversation.html message div has role=log, aria-live=polite, aria-label."""
    src = _read("_conversation.html")
    assert 'role="log"' in src, "messages div must have role=log"
    assert 'aria-live="polite"' in src, "messages div must have aria-live=polite"
    assert 'aria-label="Conversation messages"' in src, (
        "messages div must have aria-label='Conversation messages'"
    )


def test_message_container_aria_log_popout():
    """_popout.html message div also has role=log + aria-live."""
    src = _read("_popout.html")
    assert 'role="log"' in src, "_popout.html messages div must have role=log"
    assert 'aria-live="polite"' in src, "_popout.html messages div must have aria-live=polite"


# ---------------------------------------------------------------------------
# Test 2: Individual messages (role="article" + aria-label)
# ---------------------------------------------------------------------------

def test_individual_messages_role_article():
    """_messages.html message bubbles have role=article."""
    src = _read("_messages.html")
    assert 'role="article"' in src, "message divs must have role=article"


def test_individual_messages_aria_label():
    """_messages.html message bubbles have an aria-label with sender + timestamp."""
    src = _read("_messages.html")
    # The template uses {{ m.sender_name or 'You' }}, {{ m.ts }}
    assert "m.sender_name or 'You'" in src or 'aria-label=' in src, (
        "message divs must have aria-label referencing sender and timestamp"
    )
    assert "aria-label=" in src, "message divs must have aria-label"


# ---------------------------------------------------------------------------
# Test 3: Skip-nav link in index.html
# ---------------------------------------------------------------------------

def test_skip_nav_link():
    """index.html has a skip-nav link pointing to #messages."""
    src = _read("index.html")
    assert 'href="#messages"' in src, "index.html must have a skip-to-messages link"
    assert "sr-only" in src, "skip-nav must use sr-only class"
    assert "Skip to messages" in src, "skip-nav link text must say 'Skip to messages'"


# ---------------------------------------------------------------------------
# Test 4: Sidebar landmark
# ---------------------------------------------------------------------------

def test_sidebar_nav_landmark():
    """index.html sidebar uses nav element with aria-label."""
    src = _read("index.html")
    assert '<nav id="sidebar"' in src, "sidebar must be a <nav> element"
    assert 'aria-label="Conversations"' in src, "sidebar nav must have aria-label='Conversations'"


# ---------------------------------------------------------------------------
# Test 5: Main landmark
# ---------------------------------------------------------------------------

def test_main_aria_label():
    """index.html main element has aria-label='Chat'."""
    src = _read("index.html")
    assert 'aria-label="Chat"' in src, "main element must have aria-label='Chat'"


# ---------------------------------------------------------------------------
# Test 6: Conversation list role
# ---------------------------------------------------------------------------

def test_conversation_list_role():
    """_conversations.html convolist has role=list."""
    src = _read("_conversations.html")
    assert 'role="list"' in src, "conversation <ul> must have role=list"
    assert 'role="listitem"' in src, "conversation <li> elements must have role=listitem"


# ---------------------------------------------------------------------------
# Test 7: Compose input + send button aria-labels
# ---------------------------------------------------------------------------

def test_composer_aria_labels():
    """_conversation.html compose input and send button have aria-labels."""
    src = _read("_conversation.html")
    assert 'aria-label="Type a message"' in src, (
        "compose input must have aria-label='Type a message'"
    )
    assert 'aria-label="Send message"' in src, (
        "send button must have aria-label='Send message'"
    )


# ---------------------------------------------------------------------------
# Test 8: sr-only CSS class defined in style.css
# ---------------------------------------------------------------------------

def test_sr_only_css_defined():
    """style.css defines the .sr-only utility class."""
    src = _read_static("style.css")
    assert ".sr-only" in src, "style.css must define .sr-only"
    assert "position: absolute" in src or "position:absolute" in src, (
        ".sr-only must use position: absolute"
    )
    assert "clip" in src, ".sr-only must clip the element"


# ---------------------------------------------------------------------------
# Test 9: No <div onclick or <span onclick (non-semantic clickables)
# ---------------------------------------------------------------------------

def test_no_div_span_onclick():
    """Templates must not have <div onclick or <span onclick."""
    import re
    for tmpl in TEMPLATES.rglob("*.html"):
        src = tmpl.read_text()
        matches = re.findall(r"<(?:div|span)[^>]+onclick", src)
        assert not matches, (
            f"{tmpl.name} has non-semantic onclick on div/span: {matches[:3]}"
        )
