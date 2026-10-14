"""Plotly charts for the admin dashboard."""

import pandas as pd
import plotly.graph_objects as go

from core.models import STATUSES

# Dashboard style: one lime protagonist; statuses use the semantic tones
# (neutral / info / warning / lime) and always appear with a legend.
ACCENT = "#65a30d"
SERIES = [ACCENT]
STATUS_COLORS = dict(zip(STATUSES, ["#a3a59e", "#3b78c2", "#d9a03a", ACCENT]))


def _style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=24, t=8, b=8),
        barcornerradius=4,
        bargap=0.4,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(namelength=-1),
    )
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


def hours_by_employee(overview: pd.DataFrame) -> go.Figure:
    data = overview.sort_values("Hours")
    fig = go.Figure(
        go.Bar(
            x=data["Hours"],
            y=data["Employee"],
            orientation="h",
            marker_color=SERIES[0],
            text=[f"{h:g} h" for h in data["Hours"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:g} hours<extra></extra>",
        )
    )
    fig.update_xaxes(title="Hours logged")
    return _style(fig, 60 + 36 * len(data))


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
            marker=dict(color=STATUS_COLORS[status], line=dict(width=0)),
            hovertemplate=f"%{{y}} · {status}: %{{x}} tasks<extra></extra>",
        )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Tasks", dtick=1 if counts.values.sum() < 20 else None)
    return _style(fig, 90 + 36 * len(counts))


def monthly_trend(trend: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=trend["Month"],
            y=trend["Hours"],
            mode="lines+markers",
            line=dict(color=SERIES[0], width=2),
            marker=dict(size=8),
            hovertemplate="%{x}: %{y:g} hours<extra></extra>",
        )
    )
    fig.update_layout(hovermode="x")
    fig.update_yaxes(title="Team hours", rangemode="tozero")
    return _style(fig, 300)
