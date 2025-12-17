# batch_test4.py
import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

from pdf2image import convert_from_path
from PIL import Image
import numpy as np
import cv2

from ocr_engines import ImagePreprocessor, TesseractEngine, PaddleOCREngine, HybridOCREngine, PADDLEOCR_AVAILABLE
from layout_analyzer import analyze_layout, load_anchors_from_yaml_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("batch_test4")

SUPPORTED_FORMATS = [".pdf", ".png", ".jpg", ".jpeg", ".tiff"]

def ocr_and_tokens_for_image(engine_name: str, image: Image.Image, page_index: int = 0) -> List[Dict]:
    logger.debug(f"ocr_and_tokens_for_image: engine={engine_name}, page_index={page_index}")
    if engine_name == "paddle" and PADDLEOCR_AVAILABLE:
        ocr = PaddleOCREngine()
    elif engine_name == "hybrid":
        ocr = HybridOCREngine()
    else:
        ocr = TesseractEngine()

    ocr_result = ocr.extract_text(image)
    word_boxes = getattr(ocr_result, "word_boxes", []) or []
    logger.debug(f"OCR returned raw word_boxes count: {len(word_boxes)}")

    # Use image size returned by OCRResult (processed image size) if available,
    # otherwise fall back to original PIL image size
    processed_size = getattr(ocr_result, "image_size", None)
    if processed_size:
        w, h = processed_size
        logger.debug(f"Using OCR-result image_size: {(w,h)}")
    else:
        w, h = image.size
        logger.debug(f"Using original PIL image size: {(w,h)}")

    tokens = []
    for wb in word_boxes:
        try:
            left = int(wb.get("left", wb.get("x", 0)))
            top = int(wb.get("top", wb.get("y", 0)))
            width = int(wb.get("width", wb.get("w", wb.get("width", 0))))
            height = int(wb.get("height", wb.get("h", wb.get("height", 0))))
            text = str(wb.get("text") or wb.get("text", "")).strip()
            conf = wb.get("confidence", wb.get("conf", wb.get("score", 0)))

            if width <= 0:
                width = 1
            if height <= 0:
                height = 1

            x0 = max(0.0, left / max(1, w))
            y0 = max(0.0, top / max(1, h))
            x1 = min(1.0, (left + width) / max(1, w))
            y1 = min(1.0, (top + height) / max(1, h))

            tokens.append({
                "text": text,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "confidence": float(conf) if conf is not None else 0.0,
                "page": page_index
            })
        except Exception:
            logger.exception("Błąd podczas parsowania word_box")
            continue

    logger.info(f"OCR zwrócił {len(tokens)} tokenów na stronie {page_index+1}")
    return tokens

def load_blocks_from_json(json_path: Path) -> List[Dict]:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # jeśli plik ma strukturę dict z kluczami per-page, próbujemy ekstraktować listę
        if isinstance(data, dict):
            # common case: dict with "blocks" or page keys
            if "blocks" in data and isinstance(data["blocks"], list):
                return data["blocks"]
            # flatten page keys
            blocks = []
            for v in data.values():
                if isinstance(v, list):
                    blocks.extend(v)
            if blocks:
                return blocks
        logger.warning(f"Nieoczekiwany format JSON: {json_path}")
        return []
    except Exception:
        logger.exception(f"Błąd wczytywania JSON {json_path}")
        return []
    
def estimate_bbox_offset(blocks: List[Dict], image_size: Tuple[int, int]) -> Tuple[int, int]:
    """
    Prosta heurystyka do oszacowania przesunięcia bbox względem obrazu.
    Porównuje minimalne x0,y0 bbox bloków z 0 i zwraca przesunięcie w px.
    Zakładamy, że bbox są znormalizowane (0..1) lub absolutne.
    """
    w, h = image_size
    try:
        min_x0 = min((b["bbox"][0] for b in blocks if b.get("bbox")), default=0)
        min_y0 = min((b["bbox"][1] for b in blocks if b.get("bbox")), default=0)
    except Exception:
        logger.exception("estimate_bbox_offset: błąd podczas obliczania min_x0/min_y0")
        return 0, 0

    offset_x = int(-min_x0 * w) if min_x0 > 0.05 else 0
    offset_y = int(-min_y0 * h) if min_y0 > 0.05 else 0

    logger.debug(f"estimate_bbox_offset -> min_x0={min_x0}, min_y0={min_y0}, offset_x={offset_x}, offset_y={offset_y}")
    return offset_x, offset_y
    
def draw_blocks_on_image(pil_image: Image.Image, blocks: List[Dict], out_path: Path,
                    draw_tokens: bool = False, alpha: float = 0.6):
    """
    Rysuje prostokąty na obrazie z automatyczną korektą przesunięcia bbox.
    """
    try:
        img = np.array(pil_image.convert("RGB"))[:, :, ::-1].copy()  # BGR for cv2
    except Exception:
        logger.exception("draw_blocks_on_image: błąd konwersji obrazu PIL->np")
        return
    h, w = img.shape[:2]

    offset_x, offset_y = estimate_bbox_offset(blocks, (w, h))
    logger.debug(f"Estimated bbox offset: x={offset_x}px, y={offset_y}px for image size {(w,h)}")

    color_map = {
        "table": (0, 128, 255),
        "column": (0, 255, 0),
        "anchor": (0, 0, 255),
        "free_text": (128, 128, 128),
        "cell_group": (255, 0, 255),
        "default": (0, 255, 255)
    }

    overlay = img.copy()

    for b in blocks:
        bbox = b.get("bbox")
        if not bbox:
            continue
        try:
            x0, y0, x1, y1 = bbox
            if x1 > 2.0 or y1 > 2.0:
                pt1 = (int(x0) + offset_x, int(y0) + offset_y)
                pt2 = (int(x1) + offset_x, int(y1) + offset_y)
            else:
                pt1 = (int(x0 * w) + offset_x, int(y0 * h) + offset_y)
                pt2 = (int(x1 * w) + offset_x, int(y1 * h) + offset_y)
        except Exception:
            try:
                pt1 = (int(bbox[0]) + offset_x, int(bbox[1]) + offset_y)
                pt2 = (int(bbox[2]) + offset_x, int(bbox[3]) + offset_y)
            except Exception:
                logger.debug("draw_blocks_on_image: niepoprawny bbox, pomijam")
                continue

        typ = b.get("type", "default")
        color = color_map.get(typ, color_map["default"])
        thickness = 2 if typ != "table" else 3

        cv2.rectangle(overlay, pt1, pt2, color, thickness)

        block_id = str(b.get("block_id", ""))[:12]
        label = f"{typ} {block_id}"
        txt_pos = (pt1[0] + 3, max(12, pt1[1] - 6))
        cv2.putText(overlay, label, txt_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        if draw_tokens and b.get("tokens"):
            for t in b.get("tokens", []):
                try:
                    tx0 = t.get("x0", 0)
                    ty0 = t.get("y0", 0)
                    tx1 = t.get("x1", 0)
                    ty1 = t.get("y1", 0)
                    # determine if coords are normalized (0..1) or absolute
                    if tx1 > 2.0 or ty1 > 2.0:
                        tpt1 = (int(tx0) + offset_x, int(ty0) + offset_y)
                        tpt2 = (int(tx1) + offset_x, int(ty1) + offset_y)
                    else:
                        tpt1 = (int(tx0 * w) + offset_x, int(ty0 * h) + offset_y)
                        tpt2 = (int(tx1 * w) + offset_x, int(ty1 * h) + offset_y)
                    cv2.rectangle(overlay, tpt1, tpt2, (200, 200, 200), 1)
                except Exception:
                    logger.debug("draw_blocks_on_image: błąd rysowania tokenu, pomijam")
                    continue

    try:
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
        cv2.imwrite(str(out_path), img)
        logger.info(f"Zapisano obraz z bbox (z korektą offsetu): {out_path}")
    except Exception:
        logger.exception(f"draw_blocks_on_image: nie udało się zapisać obrazu do {out_path}")

def draw_tokens_on_image(pil_image: Image.Image, tokens: List[Dict], out_path: Path, color=(0,255,0)):
    try:
        img = np.array(pil_image.convert("RGB"))[:, :, ::-1].copy()
    except Exception:
        logger.exception("draw_tokens_on_image: błąd konwersji obrazu PIL->np")
        return
    h, w = img.shape[:2]
    drawn = 0
    for t in tokens:
        try:
            tx0 = t.get("x0", 0)
            ty0 = t.get("y0", 0)
            tx1 = t.get("x1", 0)
            ty1 = t.get("y1", 0)
            if tx1 > 2.0 or ty1 > 2.0:
                p1 = (int(tx0), int(ty0))
                p2 = (int(tx1), int(ty1))
            else:
                p1 = (int(tx0 * w), int(ty0 * h))
                p2 = (int(tx1 * w), int(ty1 * h))
            cv2.rectangle(img, p1, p2, color, 1)
            drawn += 1
        except Exception:
            logger.debug("draw_tokens_on_image: błąd rysowania tokenu")
            continue
    try:
        cv2.imwrite(str(out_path), img)
        logger.info(f"Zapisano obraz z tokenami ({drawn}) : {out_path}")
    except Exception:
        logger.exception(f"draw_tokens_on_image: nie udało się zapisać obrazu do {out_path}")

def draw_pre_and_merged_layers(pil_image: Image.Image, pre_blocks: List[Dict], merged_blocks: List[Dict], out_path: Path, draw_tokens: bool = False):
    """
    Rysuje pre-merge cienko (kolor A) oraz merged grubo (kolor B) na jednym obrazie.
    Zapisuje wynik do out_path.
    """
    try:
        img = np.array(pil_image.convert("RGB"))[:, :, ::-1].copy()
    except Exception:
        logger.exception("draw_pre_and_merged_layers: błąd konwersji obrazu")
        return
    tmp1 = img.copy()
    # pre: cieńsze, kolor gray/blue
    if pre_blocks:
        draw_blocks_on_image(pil_image, pre_blocks, out_path.with_name(out_path.stem + "_pre_tmp.png"), draw_tokens=draw_tokens, alpha=0.35)
        # wczytaj tymczasowy i skopiuj
        tmp1 = cv2.imread(str(out_path.with_name(out_path.stem + "_pre_tmp.png")))
    # teraz narysuj merged na tmp1
    pil_tmp = Image.fromarray(tmp1[:, :, ::-1])
    draw_blocks_on_image(pil_tmp, merged_blocks, out_path, draw_tokens=draw_tokens, alpha=0.6)
    # sprzątanie pliku tymczasowego
    try:
        tmp_path = out_path.with_name(out_path.stem + "_pre_tmp.png")
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        logger.debug("Nie udało się usunąć pliku tymczasowego pre_tmp.png")

def merge_close_blocks_local(blocks: List[Dict], max_gap: float = 0.02) -> List[Dict]:
    # prosty merge blisko po typie i stronie (zachowuje strukturę JSON layout_analyzer)
    merged = []
    blocks = sorted(blocks, key=lambda b: (b.get("page", 0), b.get("bbox", (0,0,0,0))[1], b.get("bbox", (0,0,0,0))[0]))

    while blocks:
        base = blocks.pop(0)
        base_bbox = tuple(base.get("bbox", (0,0,0,0)))
        base_type = base.get("type", "default")
        to_merge = []

        for other in blocks[:]:
            if other.get("type") != base_type or other.get("page") != base.get("page"):
                continue
            ob = tuple(other.get("bbox", (0,0,0,0)))
            horizontal_close = abs(base_bbox[2] - ob[0]) < max_gap or abs(ob[2] - base_bbox[0]) < max_gap
            vertical_close = abs(base_bbox[3] - ob[1]) < max_gap or abs(ob[3] - base_bbox[1]) < max_gap
            if horizontal_close and vertical_close:
                to_merge.append(other)
                blocks.remove(other)

        all_tokens = base.get("tokens", [])[:]
        x0 = base_bbox[0]; y0 = base_bbox[1]; x1 = base_bbox[2]; y1 = base_bbox[3]

        for m in to_merge:
            mb = tuple(m.get("bbox", (0,0,0,0)))
            x0 = min(x0, mb[0]); y0 = min(y0, mb[1]); x1 = max(x1, mb[2]); y1 = max(y1, mb[3])
            all_tokens.extend(m.get("tokens", []))

        merged.append({
            "block_id": base.get("block_id"),
            "page": base.get("page", 0),
            "type": base_type,
            "bbox": (x0, y0, x1, y1),
            "tokens": all_tokens
        })

    return merged

def find_invoices(input_dir: Path, file_name: Optional[str] = None) -> List[Path]:
    if file_name:
        candidate = input_dir / file_name
        if candidate.exists():
            return [candidate]
        matches = list(input_dir.glob(f"*{file_name}*"))
        if matches:
            return [matches[0]]
        logger.warning(f"Nie znaleziono pliku: {file_name} w {input_dir}")
        return []
    invoices = []
    for ext in SUPPORTED_FORMATS:
        invoices.extend(input_dir.glob(f'*{ext}'))
        invoices.extend(input_dir.glob(f'*{ext.upper()}'))
    invoices = sorted(set(invoices))
    logger.info(f"Znaleziono {len(invoices)} plików faktur w {input_dir}")
    return invoices

def process_file(file_path: Path, output_dir: Path, engine: str, yaml_dir: Optional[str], anchors: Optional[List[str]], params: Optional[Dict], use_existing_json: bool = False, json_dir: Optional[Path] = None, draw_tokens: bool = False):
    logger.info(f"Przetwarzanie pliku: {file_path}")
    try:
        pages = convert_from_path(str(file_path), dpi=200)
        logger.debug(f"convert_from_path zwrócił {len(pages)} stron dla pliku {file_path.name}")
    except Exception:
        logger.exception("Błąd konwersji PDF")
        return

    for page_index, pil_img in enumerate(pages):
        logger.debug(f"process_file: przetwarzam stronę {page_index} (indeks) pliku {file_path.name}")
        # Najpierw spróbuj wczytać istniejące pliki JSON, jeśli flaga enabled
        json_pre = None
        json_merged = None
        # przewidywane nazwy plików wygenerowanych przez layout_analyzer
        name_pre = f"layout_pre_merge_summary_page{page_index}.json"
        name_merged = f"layout_merged_blocks_page{page_index}.json"
        # w JSONach nazwy mogą być page0 lub page1 — sprawdzimy obie możliwości
        candidates = []
        if json_dir:
            candidates.append(Path(json_dir))
        candidates.append(output_dir)
        candidates.append(Path("."))

        logger.debug(f"process_file: kandydaci na katalog JSON: {candidates}")

        found_pre = None
        found_merged = None
        if use_existing_json:
            for base in candidates:
                if not base:
                    continue
                p_pre = base / name_pre
                p_merged = base / name_merged
                # also try +1 variant
                p_pre_1 = base / f"layout_pre_merge_summary_page{page_index+1}.json"
                p_merged_1 = base / f"layout_merged_blocks_page{page_index+1}.json"
                # also try file stem prefixed variant: {stem}_page{n}_layout_blocks.json
                stem_pref = output_dir / f"{file_path.stem}_page{page_index+1}_layout_blocks.json"
                if p_pre.exists():
                    found_pre = p_pre
                elif p_pre_1.exists():
                    found_pre = p_pre_1
                if p_merged.exists():
                    found_merged = p_merged
                elif p_merged_1.exists():
                    found_merged = p_merged_1
                if stem_pref.exists() and not found_merged:
                    # stem_pref likely is merged blocks full file (one file per page)
                    found_merged = stem_pref
                # if found both - break
                if found_pre and found_merged:
                    break
            logger.debug(f"process_file: found_pre={found_pre}, found_merged={found_merged}")

        # jeśli mamy existing merged JSON -> rysujemy je; w przeciwnym wypadku generujemy nowe
        if (use_existing_json and found_merged) or (not use_existing_json):
            # if not forcing existing json, still we run OCR+analysis to produce blocks for saving
            tokens = ocr_and_tokens_for_image(engine, pil_img, page_index)
            logger.debug(f"process_file: otrzymano {len(tokens)} tokenów dla strony {page_index}")
            if not tokens:
                logger.warning(f"Brak tokenów OCR na stronie {page_index+1} pliku {file_path.name}")
                continue

            # jeśli wymuszono użycie istniejącego JSON i znaleziono go -> wczytaj i rysuj bez ponownej analizy
            if use_existing_json and found_merged:
                merged_blocks = load_blocks_from_json(found_merged)
                pre_blocks = load_blocks_from_json(found_pre) if found_pre else []
                # optionally merge nearby blocks to reduce over-segmentation (lokalny merge)
                merged_blocks = merge_close_blocks_local(merged_blocks, max_gap=0.02)
                out_png = output_dir / f"{file_path.stem}_page{page_index+1}_layout_blocks_fromjson.png"
                if pre_blocks:
                    draw_pre_and_merged_layers(pil_img, pre_blocks, merged_blocks, out_png, draw_tokens=draw_tokens)
                else:
                    draw_blocks_on_image(pil_img, merged_blocks, out_png, draw_tokens=draw_tokens)
                # optionally draw tokens separately if requested
                if draw_tokens:
                    try:
                        draw_tokens_on_image(pil_img, tokens, output_dir / f"{file_path.stem}_page{page_index+1}_tokens_fromjson.png")
                    except Exception:
                        logger.exception("Nie udało się narysować tokenów (z istniejącego JSON)")
                continue

            # otherwise (normal flow) run layout analyzer
            try:
                logger.debug("Uruchamiam analyze_layout")
                blocks = analyze_layout(tokens, anchor_files_or_list=anchors, anchor_yaml_dir=yaml_dir, use_yaml_anchors=bool(yaml_dir), use_table_detection=True, params=params)
                logger.debug(f"analyze_layout zwrócił {len(blocks)} bloków (przed merge)")
            except Exception:
                logger.exception("Błąd analyze_layout")
                blocks = []

            # Scal bloki blisko siebie
            try:
                blocks = merge_close_blocks_local(blocks, max_gap=0.02)
                logger.debug(f"Po merge_close_blocks_local: {len(blocks)} bloków")
            except Exception:
                logger.exception("Błąd merge_close_blocks_local")

            # Zapisz JSON wynikowy (merged)
            try:
                json_out = output_dir / f"{file_path.stem}_page{page_index+1}_layout_blocks.json"
                with open(json_out, "w", encoding="utf-8") as f:
                    json.dump(blocks, f, indent=2, ensure_ascii=False)
                logger.info(f"Zapisano JSON z blokami: {json_out}")
            except Exception:
                logger.exception("Nie udało się zapisać wynikowego JSON z blokami")

            # Spróbuj też zapisać w formacie kompatybilnym z layout_analyzer naming (merge file)
            out_merged_name = output_dir / f"layout_merged_blocks_page{page_index}.json"
            try:
                with open(out_merged_name, "w", encoding="utf-8") as f:
                    json.dump(blocks, f, indent=2, ensure_ascii=False, default=str)
            except Exception:
                logger.exception(f"Nie udało się zapisać pliku {out_merged_name}")

            # Narysuj bloky (z nowo wygenerowanego)
            try:
                img_out = output_dir / f"{file_path.stem}_page{page_index+1}_layout_blocks.png"
                draw_blocks_on_image(pil_img, blocks, img_out, draw_tokens=draw_tokens)
            except Exception:
                logger.exception("Nie udało się narysować bloków")

            # optionally draw tokens to separate PNG to help debug
            if draw_tokens:
                try:
                    draw_tokens_on_image(pil_img, tokens, output_dir / f"{file_path.stem}_page{page_index+1}_tokens.png")
                except Exception:
                    logger.exception("Nie udało się narysować tokenów (normal flow)")

        else:
            # przypadek gdy wybrano use_existing_json ale nie znaleziono plików -> log i pomiń
            logger.warning(f"Wybrano --use_existing_json, ale nie znaleziono plików JSON dla strony {page_index} (szukałem {name_merged} w {candidates}). Wykonuję normalną analizę.")
            # fallback: normalny przebieg powyżej (rekursywnie wywołaj funkcję bez use_existing flag)
            process_file(file_path, output_dir, engine, yaml_dir, anchors, params, use_existing_json=False, json_dir=json_dir, draw_tokens=draw_tokens)
            return

def main():
    parser = argparse.ArgumentParser(description="Batch test OCR + layout analyzer z wizualizacją bloków")
    parser.add_argument("--input", "-i", default="./faktury", help="Folder z fakturami")
    parser.add_argument("--output", "-o", default="./wyniki", help="Folder wynikowy")
    parser.add_argument("--file", "-f", help="Nazwa pojedynczego pliku PDF do przetworzenia")
    parser.add_argument("--engine", "-e", choices=["tesseract", "paddle", "hybrid"], default="tesseract", help="Silnik OCR")
    parser.add_argument("--yaml_dir", "-y", default="./templates/default", help="Folder z plikami YAML z anchors")
    parser.add_argument("--debug", action="store_true", help="Włącz debugowanie (logi)")
    parser.add_argument("--use_existing_json", action="store_true", help="Użyj istniejących plików JSON (pre/merged) do rysowania zamiast analizować layout ponownie")
    parser.add_argument("--json_dir", help="Katalog, w którym szukać istniejących plików JSON (jeśli różny od output)")
    parser.add_argument("--draw_tokens", action="store_true", help="Rysuj również prostokąty tokenów wewnątrz bloków (jeśli tokeny są obecne w JSON)")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    anchors = []
    if args.yaml_dir and os.path.isdir(args.yaml_dir):
        try:
            anchors = load_anchors_from_yaml_dir(args.yaml_dir)
            logger.info(f"Wczytano {len(anchors)} anchors z {args.yaml_dir}")
        except Exception:
            logger.exception("Nie udało się wczytać anchors z yaml_dir")
    else:
        logger.warning(f"Nie znaleziono folderu YAML: {args.yaml_dir}")

    params = {
        "eps_x": 0.04,
        "eps_y": 0.02,
        "min_samples_col": 3,
        "min_samples_row": 2,
        "min_table_rows": 2,
        "min_table_cols": 2,
        "anchor_margin_x": 0.1,
        "anchor_margin_y": 0.05,
        "debug": args.debug,
        "save_debug_json": True,
        "save_debug_dir": str(output_dir)
    }

    invoices = find_invoices(input_dir, args.file)
    if not invoices:
        logger.error("Brak plików do przetworzenia.")
        sys.exit(1)

    for invoice_path in invoices:
        process_file(invoice_path,
                    output_dir,
                    args.engine,
                    args.yaml_dir,
                    anchors,
                    params,
                    use_existing_json=args.use_existing_json,
                    json_dir=Path(args.json_dir) if args.json_dir else None,
                    draw_tokens=args.draw_tokens)

if __name__ == "__main__":
    main()