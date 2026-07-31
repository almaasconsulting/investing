from __future__ import annotations

import html
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from investing.core.clustering import (
    cluster_distance_matrix,
    cluster_network_layout,
    cluster_relationship_summary,
)


COLORS = [
    "#38bdf8",
    "#a78bfa",
    "#34d399",
    "#fb7185",
    "#fbbf24",
    "#22d3ee",
    "#f472b6",
    "#a3e635",
]


def _figure_html(figure: go.Figure) -> str:
    return figure.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "responsive": True},
    )


def _format_frame(frame: pd.DataFrame, digits: int = 3) -> pd.DataFrame:
    result = frame.copy()
    numeric_columns = result.select_dtypes(include=[np.number]).columns
    result[numeric_columns] = result[numeric_columns].round(digits)
    return result


def _table(frame: pd.DataFrame, table_id: str = "") -> str:
    if frame.empty:
        return "<p class='muted'>No rows available.</p>"
    classes = "data-table"
    return _format_frame(frame).to_html(
        index=False,
        border=0,
        classes=classes,
        table_id=table_id or None,
        escape=True,
    )


def _cluster_sizes(clusters: pd.DataFrame) -> pd.DataFrame:
    return (
        clusters.groupby("cluster", as_index=False)
        .agg(stock_count=("symbol", "count"))
        .sort_values("cluster")
    )


def _size_chart(clusters: pd.DataFrame) -> go.Figure:
    sizes = _cluster_sizes(clusters)
    colors = [COLORS[(int(cluster) - 1) % len(COLORS)] for cluster in sizes["cluster"]]
    figure = go.Figure(
        go.Bar(
            x=[f"Cluster {value}" for value in sizes["cluster"]],
            y=sizes["stock_count"],
            marker_color=colors,
            text=sizes["stock_count"],
            textposition="outside",
            hovertemplate="%{x}<br>%{y} stocks<extra></extra>",
        )
    )
    figure.update_layout(
        title="Stocks per cluster",
        xaxis_title="",
        yaxis_title="Stock count",
        margin=dict(l=45, r=20, t=55, b=45),
    )
    return figure


def _trial_chart(trials: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for index, (linkage, group) in enumerate(trials.groupby("linkage")):
        figure.add_trace(
            go.Scatter(
                x=group["validation_silhouette"],
                y=group["full_silhouette"],
                mode="markers",
                name=str(linkage).title(),
                marker={
                    "size": 6 + group["cluster_count"].astype(float),
                    "color": group["fundamental_weight"],
                    "colorscale": "Viridis",
                    "showscale": index == 0,
                    "colorbar": {"title": "Fundamental<br>weight"},
                    "line": {"width": 1, "color": "#0f172a"},
                },
                customdata=np.column_stack(
                    [
                        group["cluster_count"],
                        group["performance_weight"],
                        group["largest_cluster_fraction"],
                        group["singleton_fraction"],
                        group["objective"],
                    ]
                ),
                hovertemplate=(
                    "Validation silhouette=%{x:.3f}<br>"
                    "Full silhouette=%{y:.3f}<br>"
                    "Clusters=%{customdata[0]:.0f}<br>"
                    "Performance parameter=%{customdata[1]:.0%}<br>"
                    "Largest cluster=%{customdata[2]:.0%}<br>"
                    "Singleton share=%{customdata[3]:.0%}<br>"
                    "Objective=%{customdata[4]:.3f}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title="Parameter-search results",
        xaxis_title="Validation-period silhouette",
        yaxis_title="Full-history silhouette",
        legend_title="Linkage",
        margin=dict(l=55, r=35, t=55, b=50),
    )
    return figure


def _network_chart(
    clusters: pd.DataFrame,
    distances: pd.DataFrame,
    dimensions: int,
) -> go.Figure:
    layout = cluster_network_layout(distances, dimensions=dimensions).set_index(
        "cluster"
    )
    members = {
        cluster: sorted(group["symbol"].astype(str).tolist())
        for cluster, group in clusters.groupby("cluster")
    }
    figure = go.Figure()
    axes = ["x", "y"] if dimensions == 2 else ["x", "y", "z"]
    for left, right in combinations(distances.index, 2):
        distance = distances.loc[left, right]
        if not np.isfinite(distance):
            continue
        coordinates = [
            [layout.loc[left, axis], layout.loc[right, axis]]
            for axis in axes
        ]
        common = {
            "mode": "lines",
            "line": {
                "color": "rgba(148,163,184,0.65)",
                "width": max(1.0, 5.0 - 2.5 * float(distance)),
            },
            "name": f"Cluster {left} ↔ {right}",
            "hovertext": (
                f"Cluster {left} ↔ Cluster {right}<br>"
                f"Exact distance: {float(distance):.3f}<br>"
                f"Blended similarity: {1.0 - float(distance):.3f}"
            ),
            "hoverinfo": "text",
            "showlegend": False,
        }
        if dimensions == 2:
            figure.add_trace(
                go.Scatter(x=coordinates[0], y=coordinates[1], **common)
            )
            midpoint_x = sum(coordinates[0]) / 2
            midpoint_y = sum(coordinates[1]) / 2
            figure.add_annotation(
                x=midpoint_x,
                y=midpoint_y,
                text=f"{float(distance):.2f}",
                showarrow=False,
                font={"size": 10, "color": "#64748b"},
                bgcolor="rgba(255,255,255,0.8)",
            )
        else:
            figure.add_trace(
                go.Scatter3d(
                    x=coordinates[0],
                    y=coordinates[1],
                    z=coordinates[2],
                    **common,
                )
            )

    node_rows = layout.reset_index()
    sizes = _cluster_sizes(clusters).set_index("cluster")["stock_count"]
    hover = [
        (
            f"<b>Cluster {cluster}</b><br>{sizes.loc[cluster]} stocks<br>"
            + ", ".join(members[cluster])
        )
        for cluster in node_rows["cluster"]
    ]
    marker = {
        "size": [18 + 2.5 * np.sqrt(sizes.loc[value]) for value in node_rows["cluster"]],
        "color": [
            COLORS[(int(value) - 1) % len(COLORS)]
            for value in node_rows["cluster"]
        ],
        "line": {"width": 2, "color": "#0f172a"},
        "opacity": 0.95,
    }
    text = [f"C{value}<br>{sizes.loc[value]} stocks" for value in node_rows["cluster"]]
    if dimensions == 2:
        figure.add_trace(
            go.Scatter(
                x=node_rows["x"],
                y=node_rows["y"],
                mode="markers+text",
                text=text,
                textposition="top center",
                hovertext=hover,
                hoverinfo="text",
                marker=marker,
                showlegend=False,
            )
        )
        figure.update_layout(
            xaxis={"visible": False},
            yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1},
        )
    else:
        figure.add_trace(
            go.Scatter3d(
                x=node_rows["x"],
                y=node_rows["y"],
                z=node_rows["z"],
                mode="markers+text",
                text=text,
                hovertext=hover,
                hoverinfo="text",
                marker=marker,
                showlegend=False,
            )
        )
        figure.update_layout(
            scene={
                "xaxis": {"visible": False},
                "yaxis": {"visible": False},
                "zaxis": {"visible": False},
                "aspectmode": "data",
            }
        )
    figure.update_layout(
        title=f"{dimensions}D cluster-distance network",
        margin=dict(l=15, r=15, t=55, b=15),
        height=620,
    )
    return figure


def generate_cluster_report(
    optimization: dict,
    metadata: pd.DataFrame,
    data_summary: dict[str, Any],
    settings: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Create an interactive HTML audit report for a clustering tuning run."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    best = optimization["best"]
    trials = optimization["trials"]
    clusters = optimization["clusters"]
    components = optimization["components"]
    similarity = components["similarity"]
    distances = cluster_distance_matrix(similarity, clusters)
    relationships = cluster_relationship_summary(
        similarity,
        clusters,
        metadata=metadata,
        return_correlation=components["return_correlation"],
        fundamental_similarity=components["fundamental_similarity"],
    )
    membership_columns = [
        column
        for column in ("cluster", "symbol", "name", "full_name", "country", "market")
        if column in clusters.columns or column in metadata.columns
    ]
    membership = clusters.merge(
        metadata[
            [
                column
                for column in membership_columns
                if column != "cluster" and column in metadata.columns
            ]
        ].drop_duplicates("symbol"),
        on="symbol",
        how="left",
    )
    membership = membership[
        [column for column in membership_columns if column in membership.columns]
    ].sort_values(["cluster", "symbol"])

    parameter_rows = pd.DataFrame(
        [
            ("Linkage method", best["linkage"]),
            ("Cluster count", int(best["cluster_count"])),
            ("Return co-movement weight", f"{best['co_movement_weight']:.0%}"),
            (
                "Realized performance weight",
                f"{best['realized_performance_weight']:.0%}",
            ),
            ("Fundamental weight", f"{best['fundamental_weight']:.0%}"),
            ("Training silhouette", f"{best['train_silhouette']:.3f}"),
            ("Validation silhouette", f"{best['validation_silhouette']:.3f}"),
            ("Full-history silhouette", f"{best['full_silhouette']:.3f}"),
            ("Largest cluster share", f"{best['largest_cluster_fraction']:.0%}"),
            ("Singleton cluster share", f"{best['singleton_fraction']:.0%}"),
        ],
        columns=["Parameter", "Selected value"],
    )
    process = pd.DataFrame(
        [
            (
                "1. Select stored data",
                f"{data_summary['eligible_stocks']} stocks with at least "
                f"{settings['min_observations']} observations",
            ),
            (
                "2. Split chronologically",
                f"{data_summary['training_dates']} training dates and "
                f"{data_summary['validation_dates']} validation dates",
            ),
            (
                "3. Build similarities",
                "Daily return co-movement, realized performance, and essential fundamentals",
            ),
            (
                "4. Search parameters",
                f"{len(trials)} combinations of weights, cluster counts, and linkage methods",
            ),
            (
                "5. Apply guardrails",
                "Prefer no singleton clusters and no cluster containing over 60% of stocks",
            ),
            (
                "6. Refit full history",
                "Apply the winning parameters to all selected stored dates",
            ),
        ],
        columns=["Step", "What happened"],
    )
    trial_columns = [
        "linkage",
        "cluster_count",
        "fundamental_weight",
        "performance_weight",
        "validation_silhouette",
        "full_silhouette",
        "largest_cluster_fraction",
        "singleton_fraction",
        "portfolio_usable",
        "objective",
    ]
    relation_columns = [
        "cluster",
        "stock_count",
        "dominant_sector",
        "dominant_country",
        "within_similarity",
        "nearest_cluster",
        "nearest_distance",
        "farthest_cluster",
        "farthest_distance",
        "interpretation",
    ]
    quality_note = (
        "Values near 1 indicate strong separation; values near 0 indicate overlapping "
        "groups. This run's validation silhouette is "
        f"{best['validation_silhouette']:.3f}, so treat clusters as a diversification "
        "map rather than a prediction or guarantee."
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Clustering Tuning Report</title>
  <script>{get_plotlyjs()}</script>
  <style>
    :root {{ --ink:#0f172a; --muted:#64748b; --line:#dbe4ee; --panel:#fff; --bg:#f3f7fb; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:15px/1.55 Inter,Segoe UI,Arial,sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:42px max(24px,6vw); color:white; background:linear-gradient(120deg,#0f172a,#164e63); }}
    header h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); }}
    header p {{ max-width:900px; margin:0; color:#d5edf5; }}
    main {{ max-width:1440px; margin:auto; padding:26px; }}
    section {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:22px; margin:0 0 22px; box-shadow:0 8px 25px rgba(15,23,42,.05); }}
    h2 {{ margin:0 0 8px; }} h3 {{ margin-top:22px; }}
    .muted,.note {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:20px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:18px; }}
    .metric {{ padding:16px; border-radius:12px; background:#eef7fb; border:1px solid #d6eaf2; }}
    .metric strong {{ display:block; font-size:24px; }} .metric span {{ color:var(--muted); }}
    .scroll {{ overflow:auto; max-height:620px; }}
    table.data-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    table.data-table th {{ position:sticky; top:0; background:#e9f0f6; z-index:1; }}
    table.data-table th,table.data-table td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    table.data-table tbody tr:hover {{ background:#f8fafc; }}
    .tabs {{ display:flex; gap:8px; margin:14px 0; }}
    .tabs button {{ border:1px solid var(--line); background:white; padding:9px 15px; border-radius:999px; cursor:pointer; }}
    .tabs button.active {{ color:white; background:#0e7490; border-color:#0e7490; }}
    .tab-panel {{ display:none; }} .tab-panel.active {{ display:block; }}
    code {{ background:#e7eef5; padding:2px 5px; border-radius:4px; }}
  </style>
</head>
<body>
<header>
  <h1>Stock clustering tuning report</h1>
  <p>Database-only audit of how the selected stocks were grouped. No market data was fetched during this run.</p>
</header>
<main>
  <section>
    <h2>Selected result</h2>
    <p class="note">{html.escape(quality_note)}</p>
    <div class="metric-grid">
      <div class="metric"><strong>{int(best['cluster_count'])}</strong><span>clusters</span></div>
      <div class="metric"><strong>{html.escape(str(best['linkage']).title())}</strong><span>linkage</span></div>
      <div class="metric"><strong>{best['validation_silhouette']:.3f}</strong><span>validation silhouette</span></div>
      <div class="metric"><strong>{best['largest_cluster_fraction']:.0%}</strong><span>largest cluster</span></div>
    </div>
    <div class="grid"><div>{_table(parameter_rows)}</div><div>{_figure_html(_size_chart(clusters))}</div></div>
  </section>

  <section>
    <h2>Cluster-distance diagrams</h2>
    <p class="note">Longer lines mean clusters are less similar. Shorter lines mean their combined return, performance, and fundamental profiles are more alike. Geometry is an MDS projection; use the edge label or table for the exact distance.</p>
    <div class="tabs"><button class="active" data-tab="network2d">2D</button><button data-tab="network3d">3D · drag to rotate</button></div>
    <div id="network2d" class="tab-panel active">{_figure_html(_network_chart(clusters, distances, 2))}</div>
    <div id="network3d" class="tab-panel">{_figure_html(_network_chart(clusters, distances, 3))}</div>
  </section>

  <section>
    <h2>How the result was produced</h2>
    {_table(process)}
    <div class="grid">
      <div>{_figure_html(_trial_chart(trials))}</div>
      <div><h3>Top parameter trials</h3><div class="scroll">{_table(trials[trial_columns].head(25))}</div></div>
    </div>
  </section>

  <section>
    <h2>Cluster relationships and interpretation</h2>
    <p class="note">Distance is <code>1 − blended similarity</code>. A short distance suggests similar behavior and characteristics; a long distance suggests limited similarity or opposing return movement. Distance is not a forecast and does not by itself imply lower investment risk.</p>
    <div class="scroll">{_table(relationships[relation_columns])}</div>
  </section>

  <section>
    <h2>Stock membership</h2>
    <p class="note">Use this table to choose candidates from several groups. Portfolio suitability still requires individual risk, valuation, liquidity, dividend, and news review.</p>
    <div class="scroll">{_table(membership, "membership-table")}</div>
  </section>
</main>
<script>
document.querySelectorAll('.tabs button').forEach(button => {{
  button.addEventListener('click', () => {{
    document.querySelectorAll('.tabs button').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    const panel = document.getElementById(button.dataset.tab);
    panel.classList.add('active');
    panel.querySelectorAll('.plotly-graph-div').forEach(plot => Plotly.Plots.resize(plot));
  }});
}});
</script>
</body>
</html>"""
    output.write_text(document, encoding="utf-8")
    return output
