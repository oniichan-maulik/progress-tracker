"""Custom visual components styled after the Citral AI dashboard.

Surfaces, borders and text tones come from CSS variables that switch with the
viewer's light/dark preference. Table cell colors are translucent so they read
on both backgrounds.
"""

from html import escape

import pandas as pd
import streamlit as st

from core.models import APPROVED, CHANGES_REQUESTED, COMPLETED, DRAFT, IN_PROGRESS, NOT_STARTED, SUBMITTED, UNDER_REVIEW

# Tones mirror the dashboard's semantic colors: (cell background, cell text).
_NEUTRAL = ("rgba(139,141,135,.16)", "#7a7c76")
_INFO = ("rgba(29,95,168,.14)", "#3b78c2")
_WARNING = ("rgba(217,140,20,.16)", "#b7791f")
_SUCCESS = ("rgba(47,125,50,.15)", "#3d8b40")
_ERROR = ("rgba(179,38,30,.14)", "#c0453d")

PILL_STYLES = {
    NOT_STARTED: _NEUTRAL,
    IN_PROGRESS: _INFO,
    UNDER_REVIEW: _WARNING,
    COMPLETED: _SUCCESS,
    DRAFT: _NEUTRAL,
    SUBMITTED: _INFO,
    APPROVED: _SUCCESS,
    CHANGES_REQUESTED: _ERROR,
    "Active": _SUCCESS,
    "Inactive": _NEUTRAL,
}

# Line icons (24px grid, stroked) in the dashboard's style.
ICONS = {
    "tasks": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2M9 12h6M9 16h6"/>',
    "done": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "users": '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0114 0M16 4a4 4 0 010 8M22 21a7 7 0 00-4-6.3"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>',
    "pause": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
}
_TONE_VARS = {
    "lime": ("var(--pt-accent-soft)", "var(--pt-accent-text)"),
    "blue": ("var(--pt-info-bg)", "var(--pt-info)"),
    "green": ("var(--pt-success-bg)", "var(--pt-success)"),
    "amber": ("var(--pt-warning-bg)", "var(--pt-warning)"),
    "red": ("var(--pt-error-bg)", "var(--pt-error)"),
    "neutral": ("var(--pt-surface-2)", "var(--pt-text-2)"),
}

_CSS = """
<style>
:root {
  --pt-surface:#ffffff; --pt-surface-2:#f0f0ec; --pt-border:#e3e3de; --pt-border-strong:#cfcfc8;
  --pt-text:#161715; --pt-text-2:#585a55; --pt-text-3:#8b8d87;
  --pt-accent:#a3e635; --pt-accent-ink:#172000; --pt-accent-text:#4d7c0f; --pt-accent-soft:#eef9d6;
  --pt-success:#2f7d32; --pt-success-bg:#e6f4e7; --pt-warning:#9a5b00; --pt-warning-bg:#fdf1dc;
  --pt-error:#b3261e; --pt-error-bg:#fbe7e6; --pt-info:#1d5fa8; --pt-info-bg:#e5eefb;
  --pt-shadow:0 1px 2px rgba(20,22,16,.05);
}
@media (prefers-color-scheme: dark) {
  :root {
    --pt-surface:#151815; --pt-surface-2:#1c201c; --pt-border:#262b26; --pt-border-strong:#353b35;
    --pt-text:#f1f2ee; --pt-text-2:#a9ada5; --pt-text-3:#727770;
    --pt-accent-text:#bef264; --pt-accent-soft:#1d2a0b;
    --pt-success:#7ed684; --pt-success-bg:#16301a; --pt-warning:#f5b95a; --pt-warning-bg:#3a2a0d;
    --pt-error:#f28b82; --pt-error-bg:#3d1a17; --pt-info:#8ab8f2; --pt-info-bg:#152741;
    --pt-shadow:0 1px 2px rgba(0,0,0,.3);
  }
}

/* ---- App chrome ---- */
.block-container { padding: 1.6rem 2.2rem 4rem; max-width: 1360px; }
[data-testid="stAppDeployButton"], [data-testid="stToolbar"], [data-testid="stMainMenu"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebarHeader"] { display: none; }
[data-testid="stSidebarUserContent"] { padding-top: 1.1rem; }

/* Sidebar: brand on top, navigation, account block pinned to the bottom. */
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { min-height: calc(100vh - 2.6rem); }
[data-testid="stLayoutWrapper"]:has(> .st-key-sidebar_account) { margin-top: auto; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { border-radius: 8px; padding: 6px 10px; }
/* Streamlit gives markdown a -1rem bottom margin to cancel its default 1rem gap; with the
   tighter sidebar gap that pulled labels into the next item, so spacing is explicit here. */
[data-testid="stSidebarUserContent"] [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { margin: 0; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 2px; }
[data-testid="stSidebarUserContent"] .st-key-sidebar_account { gap: 10px; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: var(--pt-surface-2); }
.pt-nav-label { margin: 0; padding: 16px 6px 6px; }

/* Primary buttons: lime fill with dark ink, like the dashboard CTA. The theme's
   primaryColor is the darker olive, used for checkboxes, tabs and focus rings. */
[data-testid^="stBaseButton-primary"], [data-testid^="stBaseButton-primary"] * { color: var(--pt-accent-ink) !important; }
[data-testid^="stBaseButton-primary"] {
  background: var(--pt-accent) !important; font-weight: 600; border: 0; transition: filter 120ms;
}
[data-testid^="stBaseButton-primary"]:hover { filter: brightness(.94); }

/* Cards: keyed containers named card_* get a white surface, hairline border, soft shadow. */
[class*="st-key-card_"] {
  background: var(--pt-surface); border: 1px solid var(--pt-border) !important; border-radius: 12px;
  box-shadow: var(--pt-shadow); padding: 18px 20px !important;
}
div[data-testid="stExpander"] details { background: var(--pt-surface); border-color: var(--pt-border); border-radius: 10px; }
[class*="st-key-card_"] div[data-testid="stExpander"] details { background: transparent; }
div[data-testid="stForm"] { border-color: var(--pt-border); border-radius: 10px; }

.pt-eyebrow {
  font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--pt-text-3);
}
.pt-header { padding: 2px 0 0; }
.pt-header-title { font-size: 1.5rem; font-weight: 600; letter-spacing: -.02em; line-height: 1.3; margin-top: 4px; color: var(--pt-text); }
.pt-header-sub { color: var(--pt-text-2); margin-top: 2px; }
.pt-rule { height: 1px; background: var(--pt-border); margin: 4px 0 18px; }

.pt-card-title { font-size: .98rem; font-weight: 600; letter-spacing: -.01em; color: var(--pt-text); line-height: 1.35; }
.pt-card-sub { font-size: .8rem; color: var(--pt-text-3); margin-top: 1px; }
[data-testid="stElementContainer"]:has(> div > div > .pt-card-title),
[data-testid="stElementContainer"]:has(.pt-card-title) { margin-bottom: 6px; }
.pt-section { margin: 1.4rem 0 .5rem; padding-bottom: 6px; border-bottom: 1px solid var(--pt-border); }

.pt-attention {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 14px; margin-bottom: 16px;
  border: 1px solid var(--pt-warning); border-radius: 10px; background: var(--pt-warning-bg); color: var(--pt-text);
}
.pt-attention-icon {
  width: 26px; height: 26px; flex: none; border-radius: 7px; display: grid; place-items: center;
  background: var(--pt-surface); color: var(--pt-warning);
}
.pt-attention b { font-weight: 600; }
.pt-attention .pt-sep { color: var(--pt-text-3); }

.pt-pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px;
  font-size: .74rem; font-weight: 600; white-space: nowrap;
}
.pt-pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.pt-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 0 0 16px; }
.pt-stat {
  display: flex; gap: 12px; align-items: flex-start; padding: 16px 18px; border-radius: 12px;
  background: var(--pt-surface); border: 1px solid var(--pt-border); box-shadow: var(--pt-shadow);
}
.pt-stat-icon { flex: none; width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; }
.pt-stat-value { font-size: 1.5rem; font-weight: 600; letter-spacing: -.015em; line-height: 1.25; font-variant-numeric: tabular-nums; color: var(--pt-text); }
.pt-stat-hint { font-size: .75rem; color: var(--pt-text-3); }

.pt-brand { display: flex; align-items: center; gap: 10px; padding: 0 4px 10px; }
.pt-mark {
  width: 30px; height: 30px; flex: none; border-radius: 8px; display: grid; place-items: center;
  background: var(--pt-accent); color: var(--pt-accent-ink); font-weight: 700; font-size: .92rem;
}
.pt-brand-name { font-size: 1rem; font-weight: 600; letter-spacing: -.01em; line-height: 1.2; overflow-wrap: anywhere; }
.pt-brand-sub { font-size: .7rem; color: var(--pt-text-3); }

.pt-user { display: flex; gap: 10px; align-items: center; padding: 12px 4px 4px; border-top: 1px solid var(--pt-border); }
.pt-avatar {
  flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
  font-size: .7rem; font-weight: 600; color: var(--pt-accent-text);
  background: var(--pt-accent-soft); border: 1px solid var(--pt-accent-text);
}
.pt-user-name { font-weight: 500; line-height: 1.25; }
.pt-user-meta { font-size: .72rem; color: var(--pt-text-3); }

.pt-login { margin-top: 8vh; }

.pt-field { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--pt-border); }
.pt-field:last-child { border-bottom: 0; }

/* Destructive actions: red outline trigger, solid red confirm (keyed buttons). */
.st-key-open_delete_user button { color: var(--pt-error) !important; border-color: var(--pt-error) !important; }
.st-key-open_delete_user button:hover { background: var(--pt-error-bg) !important; }
.st-key-confirm_delete_user button { background: #b3261e !important; border-color: #b3261e !important; }
.st-key-confirm_delete_user button, .st-key-confirm_delete_user button * { color: #ffffff !important; }
.st-key-confirm_delete_user button:disabled { opacity: .45; }
.pt-danger { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--pt-border); }
</style>
"""


def inject_css() -> None:
    st.html(_CSS)


def hide_sidebar() -> None:
    """Remove the sidebar and its expand button entirely (used on sign-in and setup)."""
    st.html(
        "<style>"
        '[data-testid="stSidebar"], [data-testid="stExpandSidebarButton"], '
        '[data-testid="stSidebarCollapseButton"] { display: none !important; }'
        "</style>"
    )


def page_header(title: str, subtitle: str = "", eyebrow: str = "", controls: int = 0, ratio: float = 2.6):
    """Title block on the left; returns `controls` columns on the right for filters/actions."""
    top = f'<div class="pt-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<div class="pt-header-sub">{escape(subtitle)}</div>' if subtitle else ""
    html = f'<div class="pt-header">{top}<div class="pt-header-title">{escape(title)}</div>{sub}</div>'
    if not controls:
        st.markdown(html, unsafe_allow_html=True)
        header_rule()
        return []
    cols = st.columns([ratio] + [1] * controls, vertical_alignment="bottom")
    cols[0].markdown(html, unsafe_allow_html=True)
    return cols[1:]


def header_rule() -> None:
    st.markdown('<div class="pt-rule"></div>', unsafe_allow_html=True)


def card(name: str):
    """A white card section; `name` must be unique on the page."""
    return st.container(border=True, key=f"card_{name}")


def card_title(title: str, subtitle: str = "") -> None:
    sub = f'<div class="pt-card-sub">{escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="pt-card-title">{escape(title)}</div>{sub}', unsafe_allow_html=True)


def attention(items: list[str]) -> None:
    """Amber strip listing things that need action, e.g. reports awaiting review."""
    if not items:
        return
    icon = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
        'stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5h.01"/></svg>'
    )
    body = ' <span class="pt-sep">·</span> '.join(escape(i) for i in items)
    st.markdown(
        f'<div class="pt-attention"><span class="pt-attention-icon">{icon}</span>'
        f'<span><b>Needs attention</b> <span class="pt-sep">·</span> {body}</span></div>',
        unsafe_allow_html=True,
    )


def status_pill(text: str, state: str | None = None) -> str:
    bg, fg = PILL_STYLES.get(state or text, _NEUTRAL)
    return f'<span class="pt-pill" style="background:{bg};color:{fg}">{escape(text)}</span>'


def nav_label(text: str) -> None:
    st.markdown(f'<div class="pt-eyebrow pt-nav-label">{escape(text)}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="pt-section pt-eyebrow">{escape(title)}</div>', unsafe_allow_html=True)


def _icon(name: str, color: str, size: int = 16) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, "")}</svg>'
    )


def stat_cards(cards: list[dict]) -> None:
    """cards: [{label, value, icon (ICONS key), tone (lime|blue|green|amber|red|neutral), hint?}]"""
    items = []
    for c in cards:
        bg, fg = _TONE_VARS.get(c.get("tone", "neutral"), _TONE_VARS["neutral"])
        hint = f'<div class="pt-stat-hint">{escape(c["hint"])}</div>' if c.get("hint") else ""
        items.append(
            f'<div class="pt-stat"><div class="pt-stat-icon" style="background:{bg}">{_icon(c["icon"], fg)}</div>'
            f'<div><div class="pt-eyebrow">{escape(c["label"])}</div>'
            f'<div class="pt-stat-value">{escape(str(c["value"]))}</div>{hint}</div></div>'
        )
    st.markdown(f'<div class="pt-stats">{"".join(items)}</div>', unsafe_allow_html=True)


def user_card(full_name: str, username: str, role: str) -> None:
    initials = "".join(p[0] for p in full_name.split()[:2]).upper() or "?"
    st.markdown(
        f'<div class="pt-user"><div class="pt-avatar">{escape(initials)}</div>'
        f'<div><div class="pt-user-name">{escape(full_name)}</div>'
        f'<div class="pt-user-meta">{escape(role.title())} · @{escape(username)}</div></div></div>',
        unsafe_allow_html=True,
    )


def brand(org: str, subtitle: str = "Progress reports") -> None:
    mark = escape(org.strip()[:1].upper() or "P")
    st.markdown(
        f'<div class="pt-brand"><span class="pt-mark">{mark}</span>'
        f'<span><div class="pt-brand-name">{escape(org)}</div><div class="pt-brand-sub">{escape(subtitle)}</div></span></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- table styling


def _cell(value) -> str:
    colors = PILL_STYLES.get(value) if isinstance(value, str) else None
    if not colors:
        return ""
    bg, fg = colors
    return f"background-color: {bg}; color: {fg}; font-weight: 600"


def style_table(df: pd.DataFrame):
    """Color status / review / account cells and flag overdue dates in a read-only table."""
    styler = df.style
    pill_cols = [c for c in ("Status", "Review") if c in df]
    if pill_cols:
        styler = styler.map(_cell, subset=pill_cols)
    overdue_cols = [c for c in ("Due Date", "Due", "Overdue") if c in df]
    if overdue_cols:
        styler = styler.map(
            lambda v: f"color: {_ERROR[1]}; font-weight: 600" if isinstance(v, str) and "overdue" in v.lower() else "",
            subset=overdue_cols,
        )
    return styler
