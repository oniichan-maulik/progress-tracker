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

.block-container { padding-top: 2rem; max-width: 1440px; }

/* Primary buttons: lime fill with dark ink, like the dashboard CTA. The theme's
   primaryColor is the darker olive, used for checkboxes, tabs and focus rings. */
[data-testid^="stBaseButton-primary"], [data-testid^="stBaseButton-primary"] * { color: var(--pt-accent-ink) !important; }
[data-testid^="stBaseButton-primary"] {
  background: var(--pt-accent) !important; font-weight: 600; border: 0; transition: filter 120ms;
}
[data-testid^="stBaseButton-primary"]:hover { filter: brightness(.94); }

/* Cards: white surface, hairline border, soft shadow. */
div[data-testid="stForm"], div[data-testid="stExpander"] details {
  background: var(--pt-surface); border-color: var(--pt-border); border-radius: 12px; box-shadow: var(--pt-shadow);
}

.pt-eyebrow {
  font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--pt-text-3);
}
.pt-header { padding: 2px 0 14px; margin-bottom: 14px; border-bottom: 1px solid var(--pt-border); }
.pt-header-title { font-size: 1.45rem; font-weight: 600; letter-spacing: -.015em; line-height: 1.3; margin-top: 4px; color: var(--pt-text); }
.pt-header-sub { color: var(--pt-text-2); margin-top: 2px; }

.pt-section { margin: 1.4rem 0 .5rem; padding-bottom: 6px; border-bottom: 1px solid var(--pt-border); }

.pt-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: .2rem 0 1rem; }
.pt-stat {
  display: flex; gap: 12px; align-items: flex-start; padding: 16px 18px; border-radius: 12px;
  background: var(--pt-surface); border: 1px solid var(--pt-border); box-shadow: var(--pt-shadow);
}
.pt-stat-icon { flex: none; width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; }
.pt-stat-value { font-size: 1.5rem; font-weight: 600; letter-spacing: -.015em; line-height: 1.25; font-variant-numeric: tabular-nums; color: var(--pt-text); }
.pt-stat-hint { font-size: .75rem; color: var(--pt-text-3); }

.pt-brand { display: flex; align-items: center; gap: 10px; padding: 2px 2px 12px; }
.pt-mark {
  width: 28px; height: 28px; flex: none; border-radius: 8px; display: grid; place-items: center;
  background: var(--pt-accent); color: var(--pt-accent-ink); font-weight: 600; font-size: .9rem;
}
.pt-brand-name { font-size: 1rem; font-weight: 600; letter-spacing: -.01em; }

.pt-user { display: flex; gap: 10px; align-items: center; padding: 10px 2px 12px; border-top: 1px solid var(--pt-border); }
.pt-avatar {
  flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
  font-size: .7rem; font-weight: 600; color: var(--pt-accent-text);
  background: var(--pt-accent-soft); border: 1px solid var(--pt-accent-text);
}
.pt-user-name { font-weight: 500; line-height: 1.25; }
.pt-user-meta { font-size: .72rem; color: var(--pt-text-3); }
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


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    top = f'<div class="pt-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<div class="pt-header-sub">{escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f'<div class="pt-header">{top}<div class="pt-header-title">{escape(title)}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


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


def sidebar_logo(org: str) -> None:
    """Lime mark + org name at the top of the sidebar, above the page navigation."""
    mark = escape(org.strip()[:1].upper() or "P")
    name = escape(org)
    width = 40 + int(len(org) * 8.6)
    square = (
        '<rect width="28" height="28" rx="8" fill="#a3e635"/>'
        f'<text x="14" y="19" text-anchor="middle" font-family="Geist, system-ui, sans-serif" font-size="14" '
        f'font-weight="600" fill="#172000">{mark}</text>'
    )
    wordmark = (
        f'<svg viewBox="0 0 {width} 28" width="{width}" height="28">'
        "<style>.n{fill:#161715}@media (prefers-color-scheme: dark){.n{fill:#f1f2ee}}</style>"
        f'{square}<text class="n" x="38" y="19" font-family="Geist, system-ui, sans-serif" font-size="15" '
        f'font-weight="600" letter-spacing="-0.15">{name}</text></svg>'
    )
    st.logo(wordmark, size="large", icon_image=f'<svg viewBox="0 0 28 28" width="28" height="28">{square}</svg>')


def brand(org: str) -> None:
    mark = escape(org.strip()[:1].upper() or "P")
    st.markdown(
        f'<div class="pt-brand"><span class="pt-mark">{mark}</span><span class="pt-brand-name">{escape(org)}</span></div>',
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
    if "Hours" in df:
        styler = styler.format({"Hours": lambda v: "" if pd.isna(v) else f"{v:.2f}"})
    return styler
