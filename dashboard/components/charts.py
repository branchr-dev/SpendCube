"""SpendCube reusable Plotly chart components."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(size=12),
    yaxis=dict(showgrid=False),
)


def _apply_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(**_LAYOUT)
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str = None) -> go.Figure:
    """Vertical bar chart."""
    fig = px.bar(df, x=x, y=y, title=title, color=color)
    return _apply_layout(fig)


def horizontal_bar(df: pd.DataFrame, x: str, y: str, title: str, max_rows: int = 20) -> go.Figure:
    """Horizontal bar chart, capped at max_rows."""
    data = df.nlargest(max_rows, x) if len(df) > max_rows else df
    fig = px.bar(data, x=x, y=y, title=title, orientation="h")
    fig.update_layout(**_LAYOUT, yaxis=dict(showgrid=False, autorange="reversed"))
    return fig


def treemap(df: pd.DataFrame, path: list, values: str, title: str) -> go.Figure:
    """Treemap chart."""
    fig = px.treemap(df, path=path, values=values, title=title)
    fig.update_layout(paper_bgcolor="white", font=dict(size=12))
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    """Line chart."""
    fig = px.line(df, x=x, y=y, title=title)
    return _apply_layout(fig)


def donut_chart(df: pd.DataFrame, names: str, values: str, title: str) -> go.Figure:
    """Donut (pie with hole) chart."""
    fig = px.pie(df, names=names, values=values, title=title, hole=0.4)
    fig.update_layout(paper_bgcolor="white", font=dict(size=12))
    return fig


def pareto_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    """Bar chart with cumulative % line on secondary y-axis (Pareto chart)."""
    data = df.copy().sort_values(y, ascending=False).reset_index(drop=True)
    total = data[y].sum()
    data["_cumulative_pct"] = data[y].cumsum() / total * 100 if total else 0.0

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=data[x], y=data[y], name=y, yaxis="y1")
    )
    fig.add_trace(
        go.Scatter(
            x=data[x],
            y=data["_cumulative_pct"],
            name="Cumulative %",
            yaxis="y2",
            mode="lines+markers",
        )
    )
    fig.update_layout(
        title=title,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        yaxis=dict(showgrid=False, title=y),
        yaxis2=dict(
            title="Cumulative %",
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False,
        ),
    )
    return fig


def heatmap(df: pd.DataFrame, x: str, y: str, values: str, title: str) -> go.Figure:
    """Heatmap with x on columns, y on rows, coloured by values."""
    pivot = df.pivot_table(index=y, columns=x, values=values, aggfunc="sum", fill_value=0)
    fig = px.imshow(
        pivot,
        title=title,
        color_continuous_scale="Blues",
        aspect="auto",
    )
    fig.update_layout(paper_bgcolor="white", font=dict(size=12))
    return fig
