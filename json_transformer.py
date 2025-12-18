import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

# --- Prototyp funkcji analizy layoutu i transformacji ---
def analyze_layout(ocr_data, debug=False):
    """
    Prosty prototyp analizy layoutu na podstawie OCR tokenów.
    ocr_data: dict - dane OCR i parsera w formacie JSON
    Zwraca przetworzony słownik z podziałem na kolumny/bloki.
    """
    # Tu powinna być Twoja logika klastrowania, grupowania itp.
    # Na razie zwracamy oryginalne dane z przykładową strukturą.
    if debug:
        print("[DEBUG] Analizuję layout dokumentu...")

    # Przykład: grupowanie tokenów po kolumnach (dummy)
    # W praktyce tu będzie clustering wg X, Y, anchorów itd.
    transformed = {
        "invoice": {
            "language": ocr_data.get("language", "pl"),
            "blocks": ocr_data.get("blocks", []),  # zakładamy, że parser zwraca bloki
            "raw_text": ocr_data.get("text", "")
        }
    }
    return transformed

# --- Funkcja do wywołania main2.py w celu wygenerowania JSON z PDF ---
def run_main2_for_pdf(pdf_path, engine, debug=False):
    """
    Wywołuje main2.py z odpowiednimi argumentami, aby wygenerować JSON z PDF.
    Zwraca ścieżkę do wygenerowanego pliku JSON lub None jeśli błąd.
    """
    # Zakładamy, że main2.py generuje JSON w folderze ./wyniki lub podobnym

    # env = os.environ.copy()
    # env["PYTHONIOENCODING"] = "utf-8"

    # result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    output_dir = Path("./wyniki")
    output_dir.mkdir(exist_ok=True)
    base_name = pdf_path.stem
    json_out_path = output_dir / f"{base_name}.json"

    if json_out_path.exists():
        if debug:
            print(f"[DEBUG] Plik JSON już istnieje: {json_out_path}")
        return json_out_path

    cmd = [
        sys.executable, "main2.py",
        "-i", str(pdf_path.parent),
        "-o", str(output_dir),
        "--engine", engine,
        "-f", pdf_path.name
    ]
    if debug:
        cmd.append("--debug")
        print(f"[DEBUG] Uruchamiam main2.py: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] main2.py zakończył się błędem:\n{result.stderr}")
        return None

    if not json_out_path.exists():
        print(f"[ERROR] Nie znaleziono wygenerowanego pliku JSON: {json_out_path}")
        return None

    return json_out_path

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
            pdf_files = list(input_path.glob("*.pdf"))
    else:
        print(f"[ERROR] Nie znaleziono ścieżki: {input_path}")
        sys.exit(1)

    for pdf_file in pdf_files:
        if not pdf_file.exists():
            print(f"[ERROR] Plik nie istnieje: {pdf_file}")
            continue

        if args.debug:
            print(f"[DEBUG] Przetwarzam plik: {pdf_file}")

        # Wywołaj main2.py, aby wygenerować JSON z OCR+parsera
        json_path = run_main2_for_pdf(pdf_file, args.engine, args.debug)
        if json_path is None:
            print(f"[ERROR] Nie udało się wygenerować JSON dla {pdf_file}")
            continue

        # Wczytaj JSON
        with open(json_path, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)

        # Analiza layoutu i transformacja
        transformed_data = analyze_layout(ocr_data, debug=args.debug)

        # Zapisz wynikowy JSON z sufiksem _out.json
        out_file = output_path / f"{pdf_file.stem}_out.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(transformed_data, f, ensure_ascii=False, indent=2)

        if args.debug:
            print(f"[DEBUG] Zapisano przetworzony JSON do: {out_file}")

        # Opcjonalnie: rysowanie tokenów (implementacja zależna od Twojego kodu)
        if args.draw_tokens:
            if args.debug:
                print("[DEBUG] Rysowanie tokenów - funkcja do zaimplementowania")

if __name__ == "__main__":
    main()