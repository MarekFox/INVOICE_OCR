# layout_analyzer.py
"""
Layout Analyzer - wersja wykorzystująca scikit-learn (DBSCAN / Agglomerative) z fallbackem.
Wejście:
  tokens = [
    {"text": str, "x0": float, "y0": float, "x1": float, "y1": float, "conf": float (opt), "page": int},
    ...
  ]

Wyjście: lista bloków:
  {
    "block_id": str,
    "page": int,
    "type": "table"|"column"|"anchor"|"free_text",
    "bbox": (x0,y0,x1,y1),
    "tokens": [...],
    "rows": optional (dla tabela),
    "columns": optional (dla tabela)
  }
"""
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import math
import uuid
import os
import glob
import re

# optional deps
try:
    import numpy as np
except Exception as e:
    raise RuntimeError("layout_analyzer requires numpy. Install with: pip install numpy") from e

try:
    from sklearn.cluster import DBSCAN, AgglomerativeClustering
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except Exception:
    YAML_AVAILABLE = False

# --- Domyślne parametry (można nadpisać przez argumenty)
DEFAULTS = {
    "eps_x": 0.03,          # eps dla DBSCAN po X (normalizowany 0..1)
    "eps_y": 0.012,         # eps dla DBSCAN po Y
    "min_samples_col": 2,
    "min_samples_row": 1,
    "agg_n_clusters_cols": None,   # opcjonalne: jeśli chcesz wymusić liczbę kolumn
    "normalize": True,
    "anchor_margin_x": 0.12,
    "anchor_margin_y": 0.06,
    "min_table_rows": 2,
    "min_table_cols": 2,
    "debug": False
}

# ----------------- Helpers -----------------
def _new_block_id(page:int) -> str:
    return f"p{page}_b{uuid.uuid4().hex[:6]}"

def _centroid(tok:Dict) -> Tuple[float,float]:
    return ((tok["x0"] + tok["x1"]) / 2.0, (tok["y0"] + tok["y1"]) / 2.0)

def _bbox_from_tokens(tokens:List[Dict]) -> Tuple[float,float,float,float]:
    x0 = min(t["x0"] for t in tokens)
    y0 = min(t["y0"] for t in tokens)
    x1 = max(t["x1"] for t in tokens)
    y1 = max(t["y1"] for t in tokens)
    return (x0,y0,x1,y1)

def _normalize_tokens(tokens:List[Dict]) -> List[Dict]:
    # Normalizuj per page jeśli wartości współrzędnych > 1 (typowy PDF punktowy)
    pages = defaultdict(lambda: {"max_x": 0.0, "max_y": 0.0})
    for t in tokens:
        p = t.get("page", 0)
        pages[p]["max_x"] = max(pages[p]["max_x"], t["x1"])
        pages[p]["max_y"] = max(pages[p]["max_y"], t["y1"])
    out = []
    for t in tokens:
        p = t.get("page", 0)
        mx = pages[p]["max_x"] or 1.0
        my = pages[p]["max_y"] or 1.0
        nt = t.copy()
        if DEFAULTS["normalize"] and (mx > 1.0 or my > 1.0):
            nt["x0"] = nt["x0"] / mx
            nt["x1"] = nt["x1"] / mx
            nt["y0"] = nt["y0"] / my
            nt["y1"] = nt["y1"] / my
        out.append(nt)
    return out

# ----------------- Anchors loader -----------------
def load_anchors_from_yaml_dir(yaml_dir: str) -> List[str]:
    """
    Wczyta listy anchorów (keywords) z plików YAML w katalogu.
    Zwróci unikalną listę anchorów w formie lower-case strings.
    """
    anchors = set()
    if not YAML_AVAILABLE:
        # fallback: nic nie ładujemy
        return []
    # akceptujemy slashes/backslashes - normalize path
    yaml_dir = os.path.normpath(yaml_dir)
    if not os.path.isdir(yaml_dir):
        return []
    for path in glob.glob(os.path.join(yaml_dir, "*.yml")) + glob.glob(os.path.join(yaml_dir, "*.yaml")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # collect top-level keywords
        for key in ("keywords",):
            if key in data and isinstance(data[key], list):
                for k in data[key]:
                    anchors.add(str(k).lower())
        # collect table_start keywords
        li = data.get("line_items") or data.get("line_items", {})
        if isinstance(li, dict):
            ts = li.get("table_start") or {}
            if isinstance(ts, dict):
                kws = ts.get("keywords") or []
                for k in kws:
                    anchors.add(str(k).lower())
        # collect invoice_number line_keywords
        inv = data.get("invoice_number") or {}
        if isinstance(inv, dict):
            lks = inv.get("line_keywords") or []
            for k in lks:
                anchors.add(str(k).lower())
        # amounts total keywords
        amounts = data.get("amounts") or {}
        if isinstance(amounts, dict):
            tg = amounts.get("total_gross") or {}
            if isinstance(tg, dict):
                kws = tg.get("keywords") or []
                for k in kws:
                    anchors.add(str(k).lower())
    return sorted([a for a in anchors if isinstance(a, str)])

# ----------------- Clustering (sklearn / fallback) -----------------
def cluster_columns(tokens:List[Dict], eps:float = None, min_samples:int = None, agg_n_clusters:Optional[int]=None):
    """
    Zwraca listę grup (list of token lists) - grupowanie po X (kolumny)
    Używa DBSCAN po X jeśli sklearn dostępny, w przeciwnym razie prosty greedy clustering.
    """
    if eps is None: eps = DEFAULTS["eps_x"]
    if min_samples is None: min_samples = DEFAULTS["min_samples_col"]
    toks_sorted = sorted(tokens, key=lambda t: _centroid(t)[0])
    if SKLEARN_AVAILABLE:
        X = np.array([[_centroid(t)[0]] for t in toks_sorted])
        # DBSCAN na 1D
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
        labels = db.labels_
        groups = defaultdict(list)
        for t, lab in zip(toks_sorted, labels):
            groups[lab].append(t)
        # label -1 are noise; we still keep them as singletons if needed
        clusters = [groups[k] for k in sorted(groups.keys(), key=lambda x: (x==-1, x))]
        # If user provided agg_n_clusters, try Agglomerative
        if agg_n_clusters and agg_n_clusters > 0:
            try:
                ac = AgglomerativeClustering(n_clusters=agg_n_clusters).fit(X)
                alabels = ac.labels_
                groups2 = defaultdict(list)
                for t, lab in zip(toks_sorted, alabels):
                    groups2[lab].append(t)
                clusters = [groups2[k] for k in sorted(groups2.keys())]
            except Exception:
                pass
        return clusters
    else:
        # fallback: greedy cluster by gap
        clusters = []
        cur = []
        last_x = None
        for t in toks_sorted:
            cx = _centroid(t)[0]
            if last_x is None:
                cur = [t]; last_x = cx
            else:
                if abs(cx - last_x) <= eps:
                    cur.append(t)
                    # update last_x as running average to allow drift
                    last_x = (last_x * (len(cur)-1) + cx) / len(cur)
                else:
                    clusters.append(cur)
                    cur = [t]; last_x = cx
        if cur:
            clusters.append(cur)
        return clusters

def cluster_rows(tokens:List[Dict], eps:float = None, min_samples:int = None):
    """
    Grupowanie wierszy (po Y). DBSCAN na Y (1D) lub prosty greedy.
    """
    if eps is None: eps = DEFAULTS["eps_y"]
    if min_samples is None: min_samples = DEFAULTS["min_samples_row"]
    toks_sorted = sorted(tokens, key=lambda t: _centroid(t)[1])
    if SKLEARN_AVAILABLE:
        Y = np.array([[ _centroid(t)[1] ] for t in toks_sorted])
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(Y)
        labels = db.labels_
        groups = defaultdict(list)
        for t, lab in zip(toks_sorted, labels):
            groups[lab].append(t)
        rows = [groups[k] for k in sorted(groups.keys(), key=lambda x: (x==-1, x))]
        return rows
    else:
        rows = []
        cur = []
        last_y = None
        for t in toks_sorted:
            cy = _centroid(t)[1]
            if last_y is None:
                cur = [t]; last_y = cy
            else:
                if abs(cy - last_y) <= eps:
                    cur.append(t)
                    last_y = sum(_centroid(x)[1] for x in cur)/len(cur)
                else:
                    rows.append(cur)
                    cur = [t]; last_y = cy
        if cur:
            rows.append(cur)
        return rows

# ----------------- Anchor detection -----------------
def anchor_blocks(tokens:List[Dict], anchors:List[str], margin_x:float=None, margin_y:float=None):
    if margin_x is None: margin_x = DEFAULTS["anchor_margin_x"]
    if margin_y is None: margin_y = DEFAULTS["anchor_margin_y"]
    if not anchors:
        return []
    anchors_lower = [a.lower() for a in anchors if isinstance(a, str)]
    blocks = []
    for t in tokens:
        txt = (t.get("text","") or "").lower()
        # match exact anchor token or contains anchor phrase
        matched = any((txt == a) or (a in txt) or re.search(r'\b' + re.escape(a) + r'\b', txt) for a in anchors_lower)
        if matched:
            p = t.get("page", 0)
            x0 = max(0.0, t["x0"] - margin_x)
            y0 = max(0.0, t["y0"] - margin_y)
            x1 = min(1.0, t["x1"] + margin_x)
            y1 = min(1.0, t["y1"] + margin_y)
            contained = [k for k in tokens if k.get("page",0)==p and k["x0"] >= x0-1e-9 and k["x1"] <= x1+1e-9 and k["y0"] >= y0-1e-9 and k["y1"] <= y1+1e-9]
            blocks.append({
                "block_id": _new_block_id(p),
                "page": p,
                "type": "anchor",
                "bbox": (x0,y0,x1,y1),
                "tokens": contained
            })
    return blocks

# ----------------- Table detection -----------------
def detect_tables(tokens:List[Dict], eps_x:Optional[float]=None, eps_y:Optional[float]=None, min_rows:int=None, min_cols:int=None):
    if eps_x is None: eps_x = DEFAULTS["eps_x"]
    if eps_y is None: eps_y = DEFAULTS["eps_y"]
    if min_rows is None: min_rows = DEFAULTS["min_table_rows"]
    if min_cols is None: min_cols = DEFAULTS["min_table_cols"]
    tables = []
    by_page = defaultdict(list)
    for t in tokens:
        by_page[t.get("page",0)].append(t)
    for page, toks in by_page.items():
        if len(toks) < (min_rows * min_cols):
            continue
        rows = cluster_rows(toks, eps=eps_y)
        cols = cluster_columns(toks, eps=eps_x)
        # sanity checks
        if len(rows) >= min_rows and len(cols) >= min_cols:
            # build grid: for each row and col, intersection tokens
            grid = []
            for r in rows:
                row_cells = []
                for c in cols:
                    cell_tokens = [t for t in r if t in c]
                    row_cells.append(cell_tokens)
                grid.append(row_cells)
            bbox = _bbox_from_tokens(toks)
            tables.append({
                "block_id": _new_block_id(page),
                "page": page,
                "type": "table",
                "bbox": bbox,
                "tokens": toks,
                "rows": grid,
                "columns": [ _bbox_from_tokens(c) for c in cols ]
            })
    return tables

# ----------------- Main analyze function -----------------
def analyze_layout(tokens: List[Dict],
                   anchor_files_or_list: Optional[List[str]] = None,
                   anchor_yaml_dir: Optional[str] = None,
                   use_yaml_anchors: bool = True,
                   use_table_detection: bool = True,
                   params: Optional[Dict] = None,
                   lines: Optional[Dict[int, List[List[int]]]] = None) -> List[Dict]:
    """
    tokens - lista tokenów (dicty z x0,y0,x1,y1,text,page)
    anchor_files_or_list - opcjonalna lista anchorów (strings) lub None
    anchor_yaml_dir - jeśli podano i YAML dostępny, wczyta anchors z katalogu (np. "Invoice Bot/templates/default")
    lines - opcjonalny dict {page_number: [[x1,y1,x2,y2], ...]} z wykrytymi liniami (w pikselach)
    """
    # apply runtime params
    if params:
        for k, v in params.items():
            DEFAULTS[k] = v

    tokens_n = _normalize_tokens(tokens)

    # load anchors
    anchors = []
    if anchor_files_or_list:
        if isinstance(anchor_files_or_list, (list, tuple)):
            anchors.extend([str(x).lower() for x in anchor_files_or_list])
    if use_yaml_anchors and anchor_yaml_dir and YAML_AVAILABLE:
        anchors_from_yaml = load_anchors_from_yaml_dir(anchor_yaml_dir)
        anchors.extend(anchors_from_yaml)
    anchors = sorted(set(anchors))

    # anchor blocks
    anchor_bs = anchor_blocks(tokens_n, anchors) if anchors else []

    # table detection
    tables = detect_tables(tokens_n) if use_table_detection else []

    # column blocks (if not part of table)
    col_blocks = []
    by_page = defaultdict(list)
    for t in tokens_n:
        by_page[t["page"]].append(t)

    # Normalize lines coordinates to token coordinate space (0..1)
    lines_norm = {}
    if lines:
        page_max = defaultdict(lambda: {"mx": 1.0, "my": 1.0})
        for t in tokens_n:
            p = t.get("page", 0)
            page_max[p]["mx"] = max(page_max[p]["mx"], t.get("x1", page_max[p]["mx"]))
            page_max[p]["my"] = max(page_max[p]["my"], t.get("y1", page_max[p]["my"]))
        for p, llist in lines.items():
            norm_list = []
            mx = page_max.get(p, {}).get("mx", 1.0) or 1.0
            my = page_max.get(p, {}).get("my", 1.0) or 1.0
            for (x1, y1, x2, y2) in llist:
                nx1 = x1 / mx
                nx2 = x2 / mx
                ny1 = y1 / my
                ny2 = y2 / my
                norm_list.append([nx1, ny1, nx2, ny2])
            lines_norm[p] = norm_list

    for page, toks in by_page.items():
        page_lines = lines_norm.get(page, [])
        # Extract vertical lines (x1 ~ x2)
        vertical_x = sorted([(l[0] + l[2]) / 2.0 for l in page_lines if abs(l[0] - l[2]) < 0.02])
        if vertical_x:
            edges = [0.0] + vertical_x + [1.0]
            for e0, e1 in zip(edges[:-1], edges[1:]):
                bucket = [t for t in toks if (t['x0'] >= e0 - 1e-9 and t['x1'] <= e1 + 1e-9)]
                if bucket and len(bucket) >= 2:
                    bbox = _bbox_from_tokens(bucket)
                    col_blocks.append({
                        "block_id": _new_block_id(page),
                        "page": page,
                        "type": "column",
                        "bbox": bbox,
                        "tokens": bucket
                    })
            continue

        # fallback to existing cluster_columns if no vertical lines detected
        cols = cluster_columns(toks)
        for c in cols:
            if len(c) < 2:
                continue
            bbox = _bbox_from_tokens(c)
            col_blocks.append({
                "block_id": _new_block_id(page),
                "page": page,
                "type": "column",
                "bbox": bbox,
                "tokens": c
            })

    # merge blocks into final list and create free_text for unused tokens
    blocks = []
    blocks.extend(tables)
    blocks.extend(anchor_bs)
    blocks.extend(col_blocks)

    # mark tokens used
    used = set()
    for b in blocks:
        for t in b["tokens"]:
            used.add(id(t))

    # fallback free_text blocks per page
    for page, toks in by_page.items():
        unused = [t for t in toks if id(t) not in used]
        if unused:
            blocks.append({
                "block_id": _new_block_id(page),
                "page": page,
                "type": "free_text",
                "bbox": _bbox_from_tokens(unused),
                "tokens": unused
            })

    if DEFAULTS.get("debug"):
        print(f"[layout_analyzer] created {len(blocks)} blocks (tables={len(tables)}, anchors={len(anchor_bs)}, columns={len(col_blocks)})")

    return blocks

# ----------------- Utility for parser integration -----------------
def block_to_text(block:Dict, order:str="top_down_left_right") -> str:
    toks = block.get("tokens", [])
    if order == "top_down_left_right":
        toks = sorted(toks, key=lambda t: (_centroid(t)[1], _centroid(t)[0]))
    return " ".join((t.get("text","") or "").strip() for t in toks)

# ----------------- Simple CLI/test -----------------
if __name__ == "__main__":
    # Example tokens (normalizowane) - prosty test
    sample = [
        {"text":"Invoice","x0":0.05,"y0":0.05,"x1":0.2,"y1":0.07,"page":0},
        {"text":"Seller","x0":0.05,"y0":0.1,"x1":0.25,"y1":0.12,"page":0},
        {"text":"Item","x0":0.05,"y0":0.2,"x1":0.15,"y1":0.22,"page":0},
        {"text":"Qty","x0":0.3,"y0":0.2,"x1":0.35,"y1":0.22,"page":0},
        {"text":"Price","x0":0.5,"y0":0.2,"x1":0.6,"y1":0.22,"page":0},
        {"text":"Item A","x0":0.05,"y0":0.25,"x1":0.25,"y1":0.27,"page":0},
        {"text":"1","x0":0.3,"y0":0.25,"x1":0.32,"y1":0.27,"page":0},
        {"text":"100","x0":0.5,"y0":0.25,"x1":0.57,"y1":0.27,"page":0},
    ]
    # przykład: wczytaj anchors z katalogu (dostosuj ścieżkę)
    yaml_dir = os.path.join("Invoice Bot", "templates", "default")
    anchors = load_anchors_from_yaml_dir(yaml_dir) if YAML_AVAILABLE else []
    print("Loaded anchors:", anchors[:20])
    blocks = analyze_layout(sample, anchor_files_or_list=None, anchor_yaml_dir=yaml_dir, use_yaml_anchors=True)
    from pprint import pprint
    pprint(blocks)