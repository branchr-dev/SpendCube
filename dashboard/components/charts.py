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
    fig.update_layout(**{**_LAYOUT, "yaxis": dict(showgrid=False, autorange="reversed")})
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


def boxplot(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    """Box plot with one trace per unique value in df[x]."""
    fig = go.Figure()
    for val in df[x].unique():
        fig.add_trace(go.Box(
            y=df.loc[df[x] == val, y],
            name=str(val),
            boxpoints="outliers",
        ))
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        yaxis=dict(showgrid=False),
        showlegend=False,
        title=title,
    )
    return fig


def scatter_bubble(
    df: pd.DataFrame,
    x: str,
    y: str,
    size: str,
    color: str,
    label: str,
    title: str,
    hover_name: str = None,
) -> go.Figure:
    """Bubble scatter chart with sized, coloured markers and text labels."""
    fig = px.scatter(
        df,
        x=x,
        y=y,
        size=size,
        color=color,
        text=label,
        title=title,
        hover_name=hover_name or label,
        size_max=60,
    )
    fig.update_layout(paper_bgcolor="white", font=dict(size=12))
    fig.update_traces(textposition="top center")
    fig.update_traces(selector=dict(mode="markers+text"), textfont_size=9)
    return fig


def dumbbell(
    df: pd.DataFrame,
    label_col: str,
    left_col: str,
    right_col: str,
    left_name: str,
    right_name: str,
    title: str,
) -> go.Figure:
    """Dumbbell chart showing movement from left_col to right_col per label."""
    fig = go.Figure()
    for row in df.itertuples(index=False):
        fig.add_trace(go.Scatter(
            x=[getattr(row, left_col), getattr(row, right_col)],
            y=[getattr(row, label_col), getattr(row, label_col)],
            mode="lines",
            line=dict(color="#bdc3c7", width=1.5),
            showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=df[left_col],
        y=df[label_col],
        mode="markers",
        marker=dict(color="#e74c3c", size=10),
        name=left_name,
    ))
    fig.add_trace(go.Scatter(
        x=df[right_col],
        y=df[label_col],
        mode="markers",
        marker=dict(color="#2980b9", size=10),
        name=right_name,
    ))
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        yaxis=dict(showgrid=False, autorange="reversed"),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        title=title,
    )
    return fig
