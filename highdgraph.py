#!/usr/bin/env python3
import argparse, os, sys
import pandas as pd
import numpy as np

# Optional imports loaded lazily so numeric-only runs don't require transformers
def _lazy_import_sentence_transformers():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer

from sklearn.preprocessing import StandardScaler
from sklearn.manifold import TSNE
import umap
import plotly.express as px

def infer_numeric_cols(df, exclude):
    cand = [c for c in df.columns if c not in exclude]
    num = [c for c in cand if pd.api.types.is_numeric_dtype(df[c])]
    return num

def join_text_cols(row, cols):
    parts = []
    for c in cols:
        v = row.get(c, "")
        if pd.isna(v): v = ""
        parts.append(str(v))
    return " | ".join(parts)

def build_matrix_from_text(df, text_cols, model_name):
    SentenceTransformer = _lazy_import_sentence_transformers()
    model = SentenceTransformer(model_name)
    texts = df.apply(lambda r: join_text_cols(r, text_cols), axis=1).tolist()
    X = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    return np.asarray(X), True  # is_text=True

def build_matrix_from_numeric(df, num_cols):
    X = df[num_cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    X = StandardScaler().fit_transform(X)
    return X, False  # is_text=False

def reduce_dim(X, method="umap", dims=2, is_text=True, n_neighbors=15, min_dist=0.1, perplexity=30):
    if method.lower() == "umap":
        metric = "cosine" if is_text else "euclidean"
        reducer = umap.UMAP(
            n_components=dims,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
            random_state=42
        )
        Z = reducer.fit_transform(X)
    elif method.lower() == "tsne":
        # sklearn TSNE uses euclidean; using normalized text embeddings works well
        Z = TSNE(
            n_components=dims,
            perplexity=perplexity,
            learning_rate="auto",
            init="random",
            random_state=42
        ).fit_transform(X)
    else:
        raise SystemExit(f"Unknown method: {method}")
    return Z

def make_plot(df, Z, dims, label_col=None, color_col=None, out="viz.html"):
    coords = pd.DataFrame(Z, columns=[f"dim{i+1}" for i in range(dims)], index=df.index)
    plot_df = pd.concat([coords, df], axis=1)

    hover_name = label_col if label_col and label_col in plot_df.columns else None
    color = color_col if color_col and color_col in plot_df.columns else None

    if dims == 3:
        fig = px.scatter_3d(
            plot_df, x="dim1", y="dim2", z="dim3",
            color=color, hover_name=hover_name, title="High-D → 3D projection"
        )
    else:
        # scattergl is faster for larger N
        fig = px.scatter(
            plot_df, x="dim1", y="dim2",
            color=color, hover_name=hover_name, title="High-D → 2D projection",
            render_mode="webgl"
        )
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False))
    fig.write_html(out, auto_open=True)
    print(f"[OK] Wrote interactive visualization → {out}")

def main():
    ap = argparse.ArgumentParser(
        description="Project high-dimensional data from a CSV to 2D/3D (UMAP/t-SNE) with interactive Plotly output."
    )
    ap.add_argument("--csv", required=True, help="Path to input CSV")
    ap.add_argument("--label-col", help="Column to use as the label/hover name")
    ap.add_argument("--color-col", help="Column to color points by (e.g., genre)")
    ap.add_argument("--text-cols", help="Comma-separated text columns to embed (e.g., title,description)")
    ap.add_argument("--num-cols", help="Comma-separated numeric feature columns (e.g., f1,f2,f3)")
    ap.add_argument("--model", default="all-MiniLM-L6-v2", help="SentenceTransformer model for text (default: all-MiniLM-L6-v2)")
    ap.add_argument("--method", choices=["umap","tsne"], default="umap", help="Dimensionality reduction method")
    ap.add_argument("--dims", type=int, choices=[2,3], default=2, help="Projection dimensionality (2 or 3)")
    ap.add_argument("--out", default="viz.html", help="Output HTML file")
    ap.add_argument("--neighbors", type=int, default=15, help="UMAP n_neighbors (local structure)")
    ap.add_argument("--min-dist", type=float, default=0.1, help="UMAP min_dist (cluster tightness)")
    ap.add_argument("--perplexity", type=float, default=30, help="t-SNE perplexity (roughly log of cluster size)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)

    # Resolve columns
    text_cols = [c.strip() for c in args.text_cols.split(",")] if args.text_cols else []
    num_cols  = [c.strip() for c in args.num_cols.split(",")] if args.num_cols else []

    # Build matrix X
    if text_cols:
        missing = [c for c in text_cols if c not in df.columns]
        if missing:
            raise SystemExit(f"--text-cols not found: {missing}")
        print(f"[info] Using TEXT columns for embeddings: {text_cols}")
        X, is_text = build_matrix_from_text(df, text_cols, args.model)

    elif num_cols:
        missing = [c for c in num_cols if c not in df.columns]
        if missing:
            raise SystemExit(f"--num-cols not found: {missing}")
        print(f"[info] Using NUMERIC feature columns: {num_cols}")
        X, is_text = build_matrix_from_numeric(df, num_cols)

    else:
        # Auto: prefer numeric features if available; else fall back to all object/text columns
        exclude = set([args.label_col, args.color_col]) if args.label_col or args.color_col else set()
        inferred_num = infer_numeric_cols(df, exclude)
        if len(inferred_num) >= 2:
            print(f"[auto] Using inferred NUMERIC columns: {inferred_num[:8]}{' ...' if len(inferred_num)>8 else ''}")
            X, is_text = build_matrix_from_numeric(df, inferred_num)
        else:
            cand_text = [c for c in df.columns if c not in exclude and df[c].dtype == object]
            if not cand_text:
                raise SystemExit("Could not infer text columns. Specify --text-cols or --num-cols.")
            print(f"[auto] Using TEXT columns: {cand_text[:4]}{' ...' if len(cand_text)>4 else ''}")
            X, is_text = build_matrix_from_text(df, cand_text, args.model)

    print(f"[info] Matrix shape: {X.shape} (is_text={is_text})")

    # Reduce
    Z = reduce_dim(
        X, method=args.method, dims=args.dims, is_text=is_text,
        n_neighbors=args.neighbors, min_dist=args.min_dist, perplexity=args.perplexity
    )

    # Plot
    make_plot(df, Z, args.dims, label_col=args.label_col, color_col=args.color_col, out=args.out)

if __name__ == "__main__":
    main()

