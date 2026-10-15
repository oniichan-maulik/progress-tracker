"""Plotly charts for the admin dashboard.

Styled to sit inside the white cards: transparent backgrounds, Geist type,
recessive grid, no mode bar. Heights scale with the number of rows but never
drop below a readable minimum, so labels can't collide with few employees.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.models import STATUSES

# Dashboard style: one lime protagonist; statuses use the semantic tones
# (neutral / info / warning / lime) and always appear with a legend.
ACCENT = "#65a30d"
SERIES = [ACCENT]
STATUS_COLORS = dict(zip(STATUSES, ["#a3a59e", "#3b78c2", "#d9a03a", ACCENT]))

_INK = "#8b8d87"  # mid-grey that reads on both light and dark surfaces
_GRID = "rgba(139,141,135,0.18)"
CONFIG = {"displayModeBar": False, "responsive": True}


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config=CONFIG, theme=None)


def _style(fig: go.Figure, height: int, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=12, t=36 if legend else 8, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Geist, Inter, system-ui, sans-serif", size=12, color=_INK),
        barcornerradius=4,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", title=None, font=dict(size=12)),
        hoverlabel=dict(namelength=-1, font=dict(family="Geist, Inter, sans-serif")),
    )
    fig.update_xaxes(gridcolor=_GRID, zeroline=False, automargin=True, tickfont=dict(color=_INK))
    fig.update_yaxes(gridcolor=_GRID, zeroline=False, automargin=True, tickfont=dict(color=_INK))
    return fig


def _bar_height(rows: int, legend: bool = False) -> int:
    return max(200, 70 + 46 * rows) + (30 if legend else 0)


def hours_by_employee(overview: pd.DataFrame) -> go.Figure:
    data = overview.sort_values("Hours")
    top = float(data["Hours"].max() or 0)
    fig = go.Figure(
        go.Bar(
            x=data["Hours"],
            y=data["Employee"],
            orientation="h",
            marker_color=SERIES[0],
            width=0.55,
            text=[f"{h:g} h" for h in data["Hours"]],
            textposition="outside",
            textfont=dict(color=_INK),
            cliponaxis=False,
            hovertemplate="%{y}: %{x:g} hours<extra></extra>",
        )
    )
    # Leave room on the right for the "12.5 h" labels.
    fig.update_xaxes(range=[0, max(top * 1.18, 1)], ticksuffix=" h")
    fig.update_yaxes(showgrid=False, ticklabelstandoff=10)
    return _style(fig, _bar_height(len(data)))


def status_breakdown(df: pd.DataFrame, employees: list[str]) -> go.Figure:
    counts = df.groupby(["Employee", "Status"]).size().unstack(fill_value=0).reindex(employees, fill_value=0)
    fig = go.Figure()
    for status in STATUSES:
        values = counts[status] if status in counts else [0] * len(counts)
        fig.add_bar(
            name=status,
            x=values,
            y=counts.index,
            orientation="h",
            width=0.55,
            marker=dict(color=STATUS_COLORS[status], line=dict(width=0)),
            hovertemplate=f"%{{y}} · {status}: %{{x}} tasks<extra></extra>",
        )
    fig.update_layout(barmode="stack", legend_traceorder="normal")
    fig.update_xaxes(dtick=1 if counts.values.sum() < 20 else None)
    fig.update_yaxes(showgrid=False, ticklabelstandoff=10)
    return _style(fig, _bar_height(len(counts), legend=True), legend=True)


def monthly_trend(trend: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=trend["Month"],
            y=trend["Hours"],
            mode="lines+markers",
            line=dict(color=SERIES[0], width=2),
            marker=dict(size=8, color=SERIES[0], line=dict(width=2, color="#ffffff")),
            fill="tozeroy",
            fillcolor="rgba(101,163,13,0.10)",
            hovertemplate="%{x}: %{y:g} hours<extra></extra>",
        )
    )
    fig.update_layout(hovermode="x")
    # Pad the category axis so the first point and the "0 h" label don't collide.
    fig.update_xaxes(showgrid=False, type="category", range=[-0.35, len(trend) - 0.65])
    fig.update_yaxes(rangemode="tozero", ticksuffix=" h", ticklabelstandoff=8)
    return _style(fig, 260)
