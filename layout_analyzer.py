# layout_analyzer.py
"""
Layout Analyzer - rozszerzona wersja z segmentacją po liniach i łączeniem bloków.

Wejście:
  tokens = [
    {"text": str, "x0": float, "y0": float, "x1": float, "y1": float, "confidence": float (opt), "page": int},
    ...
  ]

Opcjonalnie:
  lines = { page_index: [ [x1,y1,x2,y2], ... ] }  # współrzędne w tych samych jednostkach co tokeny (piksele lub normalizowane)

Wyjście: lista bloków zgodna z wcześniejszym API.
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
    "eps_x": 0.04,          # eps dla DBSCAN po X (normalizowany 0..1)
    "eps_y": 0.02,          # eps dla DBSCAN po Y
    "min_samples_col": 3,
    "min_samples_row": 2,
    "agg_n_clusters_cols": None,
    "normalize": True,
    "anchor_margin_x": 0.08,
    "anchor_margin_y": 0.03,
    "min_table_rows": 2,
    "min_table_cols": 2,
    "debug": False,
    "cell_min_tokens": 2,    # minimalna liczba tokenów żeby komórka była istotna
    "merge_iou_threshold": 0.02,  # IoU lub dystans progowy do łączenia bloków
    "max_anchor_vertical_expand_cells": 10
}

# ---- Helpers ----
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
        if DEFAULTS.get("normalize", True) and (mx > 1.0 or my > 1.0):
            nt["x0"] = nt["x0"] / mx
            nt["x1"] = nt["x1"] / mx
            nt["y0"] = nt["y0"] / my
            nt["y1"] = nt["y1"] / my
        out.append(nt)
    return out

# ---- Anchors loader (rozszerzony: czyta sekcję anchors jeśli jest) ----
def load_anchors_from_yaml_dir(yaml_dir: str) -> List[str]:
    anchors = set()
    if not YAML_AVAILABLE:
        return []
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
        # collect explicit anchors section
        if "anchors" in data and isinstance(data["anchors"], list):
            for a in data["anchors"]:
                anchors.add(str(a).lower())
        # fallback: existing keywords / line_items etc.
        for key in ("keywords",):
            if key in data and isinstance(data[key], list):
                for k in data[key]:
                    anchors.add(str(k).lower())
        li = data.get("line_items") or {}
        if isinstance(li, dict):
            ts = li.get("table_start") or {}
            if isinstance(ts, dict):
                kws = ts.get("keywords") or []
                for k in kws:
                    anchors.add(str(k).lower())
        inv = data.get("invoice_number") or {}
        if isinstance(inv, dict):
            lks = inv.get("line_keywords") or []
            for k in lks:
                anchors.add(str(k).lower())
        amounts = data.get("amounts") or {}
        if isinstance(amounts, dict):
            tg = amounts.get("total_gross") or {}
            if isinstance(tg, dict):
                kws = tg.get("keywords") or []
                for k in kws:
                    anchors.add(str(k).lower())
    return sorted([a for a in anchors if isinstance(a, str)])

# ---- Clustering (sklearn / fallback) ----
def cluster_columns(tokens:List[Dict], eps:float = None, min_samples:int = None, agg_n_clusters:Optional[int]=None):
    if eps is None: eps = DEFAULTS["eps_x"]
    if min_samples is None: min_samples = DEFAULTS["min_samples_col"]
    toks_sorted = sorted(tokens, key=lambda t: _centroid(t)[0])
    if SKLEARN_AVAILABLE:
        X = np.array([[_centroid(t)[0]] for t in toks_sorted])
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
        labels = db.labels_
        groups = defaultdict(list)
        for t, lab in zip(toks_sorted, labels):
            groups[lab].append(t)
        clusters = [groups[k] for k in sorted(groups.keys(), key=lambda x: (x==-1, x))]
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
                    last_x = (last_x * (len(cur)-1) + cx) / len(cur)
                else:
                    clusters.append(cur)
                    cur = [t]; last_x = cx
        if cur:
            clusters.append(cur)
        return clusters

def cluster_rows(tokens:List[Dict], eps:float = None, min_samples:int = None):
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

# ---- Anchor detection ----
def anchor_blocks(tokens:List[Dict], anchors:List[str], margin_x:float=None, margin_y:float=None):
    if margin_x is None: margin_x = DEFAULTS["anchor_margin_x"]
    if margin_y is None: margin_y = DEFAULTS["anchor_margin_y"]
    if not anchors:
        return []
    anchors_lower = [a.lower() for a in anchors if isinstance(a, str)]
    blocks = []
    for t in tokens:
        txt = (t.get("text","") or "").lower()
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

# ---- Table detection (bez zmian istotnych) ----
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
        if len(rows) >= min_rows and len(cols) >= min_cols:
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

# ---- Geometry helpers ----
def rect_iou(a:Tuple[float,float,float,float], b:Tuple[float,float,float,float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0); iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1); iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1-ix0)*(iy1-iy0)
    area_a = (ax1-ax0)*(ay1-ay0)
    area_b = (bx1-bx0)*(by1-by0)
    union = area_a + area_b - inter
    return inter/union if union>0 else 0.0

# ---- Grid-based segmentation using lines ----
def grid_cells_from_lines(tokens:List[Dict], lines_norm:List[List[float]], cell_min_tokens:int = None):
    """
    lines_norm: lista znormalizowanych linii dla strony: [[nx1,ny1,nx2,ny2], ...]
    Zwraca listę komórek: { 'ix','iy','bbox', 'tokens' }
    """
    if cell_min_tokens is None:
        cell_min_tokens = DEFAULTS["cell_min_tokens"]
    # zebranie linii pionowych i poziomych (środkowe współrzędne)
    vx = sorted([(l[0]+l[2])/2.0 for l in lines_norm if abs(l[0]-l[2]) < 0.02])
    hy = sorted([(l[1]+l[3])/2.0 for l in lines_norm if abs(l[1]-l[3]) < 0.02])
    x_edges = [0.0] + vx + [1.0]
    y_edges = [0.0] + hy + [1.0]
    cells = []
    for ix in range(len(x_edges)-1):
        e0 = x_edges[ix]; e1 = x_edges[ix+1]
        for iy in range(len(y_edges)-1):
            f0 = y_edges[iy]; f1 = y_edges[iy+1]
            # token is considered in cell if its centroid belongs to cell OR bbox overlaps > small threshold
            cell_toks = []
            for t in tokens:
                cx, cy = _centroid(t)
                if (cx >= e0 - 1e-9 and cx <= e1 + 1e-9 and cy >= f0 - 1e-9 and cy <= f1 + 1e-9):
                    cell_toks.append(t)
                else:
                    # fallback by bbox overlap: if token bbox overlap with cell bbox > 0.3 of token area -> include
                    tx0, ty0, tx1, ty1 = t["x0"], t["y0"], t["x1"], t["y1"]
                    overlap_x = max(0, min(tx1, e1) - max(tx0, e0))
                    overlap_y = max(0, min(ty1, f1) - max(ty0, f0))
                    if overlap_x > 0 and overlap_y > 0:
                        tok_area = (tx1 - tx0) * (ty1 - ty0)
                        if tok_area > 0 and (overlap_x * overlap_y) / tok_area >= 0.3:
                            cell_toks.append(t)
            if len(cell_toks) >= cell_min_tokens:
                bbox = (e0, f0, e1, f1)
                cells.append({"ix": ix, "iy": iy, "bbox": bbox, "tokens": cell_toks})
    return cells, x_edges, y_edges

# ---- Merge adjacent cells by connectivity (simple region growing) ----
def merge_adjacent_cells(cells:List[Dict], x_edges:List[float], y_edges:List[float]):
    # build lookup by grid index
    lookup = {}
    for c in cells:
        lookup[(c["ix"], c["iy"])] = c
    visited = set()
    merged = []
    for key, cell in lookup.items():
        if key in visited:
            continue
        stack = [key]; visited.add(key)
        group = []
        while stack:
            cur = stack.pop()
            group.append(lookup[cur])
            ix, iy = cur
            # neighbours: up/down/left/right
            for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                nb = (ix+dx, iy+dy)
                if nb in lookup and nb not in visited:
                    visited.add(nb); stack.append(nb)
        # merge group into single block
        toks = []
        xs = []; ys = []
        for g in group:
            toks.extend(g["tokens"])
            x0,y0,x1,y1 = g["bbox"]
            xs.append(x0); xs.append(x1)
            ys.append(y0); ys.append(y1)
        bbox = (min(xs), min(ys), max(xs), max(ys))
        merged.append({"block_id": _new_block_id(0), "page": 0, "type": "cell_group", "bbox": bbox, "tokens": toks})
    return merged

# ---- Merge blocks by overlap/proximity ----
def merge_close_blocks(blocks:List[Dict], merge_iou:float=None):
    if merge_iou is None:
        merge_iou = DEFAULTS["merge_iou_threshold"]
    if not blocks:
        return []
    blocks = sorted(blocks, key=lambda b: (b["page"], b["bbox"][1], b["bbox"][0]))
    merged = []
    used = [False]*len(blocks)
    for i,b in enumerate(blocks):
        if used[i]:
            continue
        bx = b["bbox"]
        toks = b.get("tokens", [])[:]
        used[i] = True
        for j in range(i+1, len(blocks)):
            if used[j]: continue
            if blocks[j]["page"] != b["page"]: continue
            iou = rect_iou(bx, blocks[j]["bbox"])
            if iou >= merge_iou:
                # merge
                bx = (min(bx[0], blocks[j]["bbox"][0]),
                    min(bx[1], blocks[j]["bbox"][1]),
                    max(bx[2], blocks[j]["bbox"][2]),
                    max(bx[3], blocks[j]["bbox"][3]))
                toks.extend(blocks[j].get("tokens", []))
                used[j] = True
        merged.append({"block_id": _new_block_id(b["page"]), "page": b["page"], "type": b.get("type","merged"), "bbox": bx, "tokens": toks})
    return merged

# ---- Main analyze function (rozszerzona) ----
def analyze_layout(tokens: List[Dict],
                   anchor_files_or_list: Optional[List[str]] = None,
                   anchor_yaml_dir: Optional[str] = None,
                   use_yaml_anchors: bool = True,
                   use_table_detection: bool = True,
                   params: Optional[Dict] = None,
                   lines: Optional[Dict[int, List[List[float]]]] = None) -> List[Dict]:
    """
    tokens - lista tokenów (dicty z x0,y0,x1,y1,text,page)
    lines - optional dict {page: [[x1,y1,x2,y2], ...]} with line coordinates (same units as tokens)
    params - optional dict:
        debug (bool)
        save_debug_json (bool)
        save_debug_dir (str)
        ... (może nadpisać DEFAULTS keys)
    """
    # apply runtime params (mutuje DEFAULTS as original; acceptable for quick runtime override)
    if params:
        for k, v in params.items():
            DEFAULTS[k] = v

    tokens_n = _normalize_tokens(tokens)

    # load anchors
    anchors = []
    if anchor_files_or_list:
        if isinstance(anchor_files_or_list, (list, tuple)):
            anchors.extend([str(x).lower() for x in anchor_files_or_list])
        else:
            anchors.append(str(anchor_files_or_list).lower())
    if use_yaml_anchors and anchor_yaml_dir and YAML_AVAILABLE:
        anchors_from_yaml = load_anchors_from_yaml_dir(anchor_yaml_dir)
        anchors.extend(anchors_from_yaml)
    anchors = sorted(set(anchors))

    # group tokens per page
    by_page = defaultdict(list)
    for t in tokens_n:
        by_page[t["page"]].append(t)

    all_blocks = []

    # detect tables first (they have priority)
    if use_table_detection:
        tables = detect_tables(tokens_n)
    else:
        tables = []

    # for each page, process lines -> grid -> cells -> anchor expansion
    for page, toks in by_page.items():
        page_tokens = toks
        page_lines = None
        if lines and page in lines:
            # normalize lines to 0..1 using per-page maxima
            page_max = {"mx":1.0,"my":1.0}
            for t in page_tokens:
                page_max["mx"] = max(page_max["mx"], t.get("x1", page_max["mx"]))
                page_max["my"] = max(page_max["my"], t.get("y1", page_max["my"]))
            norm_lines = []
            mx = page_max["mx"] or 1.0
            my = page_max["my"] or 1.0
            for (x1,y1,x2,y2) in lines.get(page, []):
                nx1 = x1 / mx; nx2 = x2 / mx; ny1 = y1 / my; ny2 = y2 / my
                norm_lines.append([nx1, ny1, nx2, ny2])
            page_lines = norm_lines

        # 1) If have lines -> build grid cells
        page_blocks = []
        if page_lines:
            cells, x_edges, y_edges = grid_cells_from_lines(page_tokens, page_lines, cell_min_tokens=DEFAULTS["cell_min_tokens"])
            # set real page ids for merged cells later
            for c in cells:
                c["page"] = page
            # merge adjacent cells (region growing)
            cell_groups = merge_adjacent_cells(cells, x_edges, y_edges)
            # set page ids and types
            for g in cell_groups:
                g["page"] = page
                g["type"] = "cell_group"
            page_blocks.extend(cell_groups)
        else:
            # fallback: cluster columns (existing behavior)
            cols = cluster_columns(page_tokens)
            for c in cols:
                if len(c) < 2:
                    continue
                bbox = _bbox_from_tokens(c)
                page_blocks.append({
                    "block_id": _new_block_id(page),
                    "page": page,
                    "type": "column",
                    "bbox": bbox,
                    "tokens": c
                })

        # 2) anchor detection in this page and expand anchor blocks along vertical grid
        anchor_bs = anchor_blocks(page_tokens, anchors) if anchors else []
        # expand anchors: try to attach neighboring cell_groups in same x-band (if grid exist)
        if page_lines and anchor_bs:
            # compute cols edges again
            vx = sorted([(l[0]+l[2])/2.0 for l in page_lines if abs(l[0]-l[2]) < 0.02])
            x_edges = [0.0] + vx + [1.0]
            # helper: find ix for center
            for a in anchor_bs:
                ax0, ay0, ax1, ay1 = a["bbox"]
                cx = (ax0+ax1)/2.0
                # determine column index
                ix = None
                for ii in range(len(x_edges)-1):
                    if cx >= x_edges[ii] - 1e-9 and cx <= x_edges[ii+1] + 1e-9:
                        ix = ii
                        break
                # collect all cell_groups in this ix
                selected = []
                for b in page_blocks:
                    bx0, by0, bx1, by1 = b["bbox"]
                    midx = (bx0 + bx1)/2.0
                    if ix is None:
                        # fallback: overlap heuristic
                        if not (bx1 < ax0 or bx0 > ax1):
                            selected.append(b)
                    else:
                        if midx >= x_edges[ix] - 1e-9 and midx <= x_edges[ix+1] + 1e-9:
                            selected.append(b)
                # now choose those selected which are vertically close to anchor
                sel_sorted = sorted(selected, key=lambda b: b["bbox"][1])
                # include contiguous ones that are near anchor vertical span (or until a major gap)
                merged_tokens = []
                anchor_y0 = ay0
                anchor_y1 = ay1
                for s in sel_sorted:
                    sb = s["bbox"]
                    # treat as contiguous if vertical overlap / adjacency
                    # include if bbox overlaps anchor vertical span or sits below/above but within some limit
                    if not (sb[3] < anchor_y0 - 0.05 or sb[1] > anchor_y1 + 0.05):
                        merged_tokens.extend(s.get("tokens", []))
                if merged_tokens:
                    # create expanded anchor block
                    all_tokens = a.get("tokens", []) + merged_tokens
                    bbox = _bbox_from_tokens(all_tokens)
                    page_blocks.append({
                        "block_id": _new_block_id(page),
                        "page": page,
                        "type": "anchor",
                        "bbox": bbox,
                        "tokens": all_tokens
                    })
                else:
                    # fallback: keep the small anchor block itself
                    page_blocks.append(a)
        else:
            # no grid or no anchors -> just keep anchor blocks
            page_blocks.extend(anchor_bs)

        # 3) add detected tables for this page (priority)
        page_tables = [t for t in tables if t["page"] == page]
        # mark tokens used by tables
        used_ids = set()
        for t in page_tables:
            for tok in t["tokens"]:
                used_ids.add(id(tok))

        # integrate page_blocks but try not to duplicate table tokens
        final_blocks = []
        # add tables first
        final_blocks.extend(page_tables)

        # filter page_blocks that do not only contain table tokens
        for b in page_blocks:
            toks_b = [tk for tk in b.get("tokens", []) if id(tk) not in used_ids]
            if not toks_b:
                continue
            b2 = b.copy()
            b2["tokens"] = toks_b
            final_blocks.append(b2)

        # --- DODATKOWY DEBUG: zapisz pre-merge i post-merge bloki jeśli ustawione ---
        _pre_merge_copy = [ { "block_id": b.get("block_id"), "page": b.get("page"), "type": b.get("type"), "bbox": b.get("bbox"), "tokens_count": len(b.get("tokens",[])) } for b in final_blocks ]

        # 4) merge close/small blocks to reduce over-segmentation
        merged = merge_close_blocks(final_blocks, merge_iou=DEFAULTS["merge_iou_threshold"])

        if params and params.get("save_debug_json"):
            try:
                import json, pathlib
                p = pathlib.Path(params.get("save_debug_dir", "." ))
                p.mkdir(parents=True, exist_ok=True)
                with open(p / f"layout_pre_merge_summary_page{page}.json", "w", encoding="utf-8") as f:
                    json.dump(_pre_merge_copy, f, ensure_ascii=False, indent=2)
                with open(p / f"layout_merged_blocks_page{page}.json", "w", encoding='utf-8') as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2, default=str)
            except Exception:
                # do not fail on debug save problems
                if DEFAULTS.get("debug"):
                    print("[layout_analyzer] failed to write debug json", repr(Exception))

        # assign correct page ids (if some helpers created page 0)
        for m in merged:
            m["page"] = page
        all_blocks.extend(merged)

    # mark tokens used across all_blocks and add free_text blocks for leftover tokens
    used = set()
    for b in all_blocks:
        for t in b.get("tokens", []):
            used.add(id(t))
    # leftover tokens per page
    for page, toks in by_page.items():
        unused = [t for t in toks if id(t) not in used]
        if unused:
            all_blocks.append({
                "block_id": _new_block_id(page),
                "page": page,
                "type": "free_text",
                "bbox": _bbox_from_tokens(unused),
                "tokens": unused
            })

    if DEFAULTS.get("debug"):
        print(f"[layout_analyzer] created {len(all_blocks)} blocks (pages={len(by_page)})")

    return all_blocks

# ---- Utility for parser integration ----
def block_to_text(block:Dict, order:str="top_down_left_right") -> str:
    toks = block.get("tokens", [])
    if order == "top_down_left_right":
        toks = sorted(toks, key=lambda t: (_centroid(t)[1], _centroid(t)[0]))
    return " ".join((t.get("text","") or "").strip() for t in toks)

# ---- CLI for quick test (unchanged but uses debug save) ----
if __name__ == "__main__":
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
    yaml_dir = os.path.join("Invoice Bot", "templates", "default")
    anchors = load_anchors_from_yaml_dir(yaml_dir) if YAML_AVAILABLE else []
    print("Loaded anchors:", anchors[:40])
    params = {"debug": True, "save_debug_json": True, "save_debug_dir": "debug_layout"}
    blocks = analyze_layout(sample, anchor_files_or_list=None, anchor_yaml_dir=yaml_dir, use_yaml_anchors=True, lines=None, params=params)
    from pprint import pprint
    pprint(blocks)