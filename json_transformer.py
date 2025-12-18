#!/usr/bin/env python3
"""
json_transformer.py - prototyp transformera OCR -> JSON z analizą layoutu

Użycie (przykład):
    python json_transformer.py -i "./faktury" -o "./wyniki" --engine paddle --debug

Opis:
- Jeśli nie znajdzie JSONa wygenerowanego dla pliku PDF, spróbuje uruchomić main2.py,
  by go wygenerować (ustawiając PYTHONIOENCODING=utf-8).
- Przyjmuje JSON w formacie listy bloków (tak jak main2.py zapisuje `all_blocks`)
  lub słownika zawierającego klucz "blocks".
- Zapisuje wynik transformacji do katalogu wyjściowego jako "<stem>_out.json".
"""
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- Prototyp funkcji analizy layoutu i transformacji ---
def detect_language_from_blocks(blocks: List[Dict[str, Any]]) -> str:
    """Prosta heurystyka wykrywania języka na podstawie często występujących słów."""
    text = " ".join(b.get("text", "") for b in blocks if isinstance(b.get("text", ""), str)).lower()
    # sprawdź proste tokeny
    if any(w in text for w in ["faktura", "nip", "sprzedawca", "nabywca"]):
        return "pl"
    if any(w in text for w in ["rechnung", "ust-id", "ustid", "nehmer", "lieferant"]):
        return "de"
    if any(w in text for w in ["invoice", "vat", "supplier", "buyer"]):
        return "en"
    if any(w in text for w in ["factura", "cui", "furnizor", "cumparator"]):
        return "ro"
    # fallback
    return "pl"

def analyze_layout(ocr_input: Any, debug: bool = False) -> Dict[str, Any]:
    """
    Analiza layoutu i transformacja danych OCR -> ujednolicony JSON.
    Przyjmuje:
      - listę bloków (List[Dict])  <- format zapisywany przez main2.py (all_blocks)
      - lub słownik zawierający "blocks": List[Dict]
    Zwraca słownik z kluczami: invoice -> { language, blocks, raw_text }
    """
    if debug:
        print("[DEBUG] analyze_layout: wejście typu:", type(ocr_input))

    # Normalizacja: uzyskaj listę bloków
    if isinstance(ocr_input, list):
        blocks = ocr_input
    elif isinstance(ocr_input, dict):
        # jeśli dict zawiera "blocks" użyj ich, inaczej spróbuj zebrać listy z wartości
        if "blocks" in ocr_input and isinstance(ocr_input["blocks"], list):
            blocks = ocr_input["blocks"]
        else:
            # zbierz wszystkie listy w dict -> flatten (prosty heurystyczny try)
            found = []
            for v in ocr_input.values():
                if isinstance(v, list):
                    found.extend(v)
            blocks = found
    else:
        # nieznany format
        blocks = []

    if debug:
        print(f"[DEBUG] analyze_layout: liczba bloków = {len(blocks)}")
        if len(blocks) > 0:
            sample_texts = [b.get("text", "") for b in blocks[:3]]
            print(f"[DEBUG] analyze_layout: przykładowe teksty bloków: {sample_texts}")

    # jeśli brak bloków - zwróć pustą strukture
    if not blocks:
        return {
            "invoice": {
                "language": "pl",
                "blocks": [],
                "raw_text": ""
            }
        }

    # wykryj język prostą heurystyką
    language = detect_language_from_blocks(blocks)

    # stwórz raw_text jako połączenie tekstów bloków (można rozszerzyć)
    raw_text = " ".join((b.get("text") or "").strip() for b in blocks if isinstance(b.get("text", ""), str))

    transformed = {
        "invoice": {
            "language": language,
            "blocks": blocks,
            "raw_text": raw_text
        }
    }

    return transformed

# --- Funkcja do wywołania main2.py w celu wygenerowania JSON z PDF ---
def run_main2_for_pdf(pdf_path: Path, engine: str, debug: bool = False, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Wywołuje main2.py z odpowiednimi argumentami, aby wygenerować JSON z PDF.
    Zwraca ścieżkę do wygenerowanego pliku JSON lub None jeśli błąd.
    """
    # domyślny output_dir jeżeli nie podano
    if output_dir is None:
        output_dir = Path("./wyniki")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = pdf_path.stem
    json_out_path = output_dir / f"{base_name}.json"

    # jeśli już istnieje plik - zwróć go
    if json_out_path.exists():
        if debug:
            print(f"[DEBUG] Plik JSON już istnieje: {json_out_path}")
        return json_out_path

    # zlokalizuj main2.py - najpierw w tym samym katalogu co ten skrypt, potem w CWD
    candidate_main2 = Path(__file__).parent / "main2.py"
    if candidate_main2.exists():
        main2_script = str(candidate_main2)
    else:
        main2_script = "main2.py"  # polegamy na PATH/CWD

    cmd = [
        sys.executable, main2_script,
        "-i", str(pdf_path.parent),
        "-o", str(output_dir),
        "--engine", engine,
        "-f", pdf_path.name
    ]
    if debug:
        cmd.append("--debug")
        print(f"[DEBUG] Uruchamiam main2.py: {' '.join(cmd)}")

    env = os.environ.copy()
    # wymuś unicode w subprocessie
    env["PYTHONIOENCODING"] = "utf-8"
    # zachowaj locale/chcp jeśli trzeba (opcjonalnie)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] main2.py przekroczył limit czasu dla pliku {pdf_path.name}")
        return None
    except Exception as e:
        print(f"[ERROR] Błąd uruchamiania main2.py: {e}")
        return None

    if result.returncode != 0:
        # wypisz stderr + stdout dla diagnostyki
        print(f"[ERROR] main2.py zakończył się błędem (code={result.returncode}):")
        if result.stdout:
            print("STDOUT:")
            print(result.stdout.strip())
        if result.stderr:
            print("STDERR:")
            print(result.stderr.strip())
        return None

    # spróbuj zlokalizować wygenerowany JSON w kilku miejscach
    candidates = [
        json_out_path,
        Path.cwd() / f"{base_name}.json",
        Path.cwd() / "wyniki" / f"{base_name}.json",
        output_dir / f"{base_name}.json"
    ]
    for cand in candidates:
        if cand and cand.exists():
            if debug:
                print(f"[DEBUG] Znaleziono wygenerowany JSON: {cand}")
            return cand

    # jeśli nic nie znaleziono
    if debug:
        print("[DEBUG] Nie znaleziono pliku JSON po uruchomieniu main2.py - sprawdź logi main2.py")
    return None

# --- Główna funkcja CLI ---
def main():
    parser = argparse.ArgumentParser(description="JSON Transformer for Invoice OCR")
    parser.add_argument("-i", "--input", required=True, help="Folder lub plik PDF do przetworzenia")
    parser.add_argument("-o", "--output", required=True, help="Folder wyjściowy na pliki JSON")
    parser.add_argument("--engine", choices=["paddle", "tesseract"], default="paddle", help="Silnik OCR")
    parser.add_argument("--debug", action="store_true", help="Tryb debugowania")
    parser.add_argument("-f", "--file", help="Nazwa pliku PDF do przetworzenia (jeśli -i to folder)")
    parser.add_argument("--draw_tokens", action="store_true", help="Rysuj tokeny (opcjonalne)")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Obsługa pojedynczego pliku PDF lub folderu
    if input_path.is_file():
        pdf_files = [input_path]
    elif input_path.is_dir():
        if args.file:
            pdf_files = [input_path / args.file]
        else:
            pdf_files = sorted(input_path.glob("*.pdf"))
    else:
        print(f"[ERROR] Nie znaleziono ścieżki: {input_path}")
        sys.exit(1)

    for pdf_file in pdf_files:
        if not pdf_file.exists():
            print(f"[ERROR] Plik nie istnieje: {pdf_file}")
            continue

        if args.debug:
            print(f"[DEBUG] Przetwarzam plik: {pdf_file}")

        # Wywołaj main2.py, aby wygenerować JSON z OCR+parsera (jeśli nie ma)
        json_path = run_main2_for_pdf(pdf_file, args.engine, debug=args.debug, output_dir=output_path)
        if json_path is None:
            print(f"[ERROR] Nie udało się wygenerować JSON dla {pdf_file}")
            continue

        # Wczytaj JSON (może to być lista bloków lub struktura)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Nie można wczytać JSON {json_path}: {e}")
            continue

        # Debug: pokaż typ i rozmiar wczytanych danych
        if args.debug:
            print(f"[DEBUG] Wczytany JSON: typ={type(ocr_data)}")
            if isinstance(ocr_data, list):
                print(f"[DEBUG] Lista bloków: {len(ocr_data)} elementów")
            elif isinstance(ocr_data, dict):
                keys = list(ocr_data.keys())
                print(f"[DEBUG] Dict keys: {keys}")

        # Analiza layoutu i transformacja (analyze_layout obsługuje listę i dict)
        try:
            transformed_data = analyze_layout(ocr_data, debug=args.debug)
        except Exception as e:
            print(f"[ERROR] Błąd analyze_layout dla {json_path}: {e}")
            continue

        # Zapisz wynikowy JSON z sufiksem _out.json (zgodnie z życzeniem)
        out_file = output_path / f"{pdf_file.stem}_out.json"
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(transformed_data, f, ensure_ascii=False, indent=2)
            if args.debug:
                print(f"[DEBUG] Zapisano przetworzony JSON do: {out_file}")
        except Exception as e:
            print(f"[ERROR] Nie udało się zapisać przetworzonego JSON do {out_file}: {e}")
            continue

        # Opcjonalnie: rysowanie tokenów (miejsce na implementację)
        if args.draw_tokens:
            if args.debug:
                print("[DEBUG] Rysowanie tokenów - funkcja do zaimplementowania")

if __name__ == "__main__":
    main()