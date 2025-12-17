# ocr_engines.py
"""
FAKTURA BOT v5.0 - OCR Engines
====
Uniwersalne silniki OCR z obsługą Tesseract i PaddleOCR
"""

import os
import re
import numpy as np
from typing import Optional, List, Tuple, Dict
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import pytesseract
from dataclasses import dataclass
import logging

from config import CONFIG, TESSERACT_CMD  # ← DODANE: TESSERACT_CMD
from language_config import get_language_config

logger = logging.getLogger(__name__)

# ==== KONFIGURACJA TESSERACT ====
# Ustaw ścieżkę do Tesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
# ====

# Sprawdzenie dostępności PaddleOCR
PADDLEOCR_AVAILABLE = False
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logger.info("✅ PaddleOCR dostępny")
except ImportError:
    logger.info("⚠️ PaddleOCR niedostępny")

@dataclass
class OCRResult:
    """Wynik OCR z metadanymi"""
    text: str
    confidence: float
    language: str
    engine: str
    processing_time: float
    word_boxes: List[Dict]
    image_size: Tuple[int, int]  # (width, height) obrazu po preprocessingu

class ImagePreprocessor:
    """Preprocessing obrazów przed OCR"""
    
    @staticmethod
    def auto_rotate(image: Image.Image) -> Image.Image:
        """Automatyczna rotacja obrazu"""
        try:
            osd = pytesseract.image_to_osd(image)
            angle = int(re.search(r'Rotate: (\d+)', osd).group(1))
            
            if angle > 0:
                logger.info(f"Rotacja obrazu o {angle} stopni")
                return image.rotate(-angle, expand=True)
        except Exception as e:
            logger.warning(f"Nie można określić orientacji: {e}")
            
        return image
    
    @staticmethod
    def enhance_quality(image: Image.Image) -> Image.Image:
        """Poprawa jakości obrazu"""
        if image.mode != 'L':
            image = image.convert('L')
            
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.5)
        
        image = image.filter(ImageFilter.MedianFilter(size=3))
        
        return image
    
    @staticmethod
    def remove_shadows(image: Image.Image) -> Image.Image:
        """Usuwanie cieni ze skanów"""
        img_array = np.array(image)
        
        dilated = cv2.dilate(img_array, np.ones((7,7), np.uint8))
        bg = cv2.medianBlur(dilated, 21)
        
        diff = 255 - cv2.absdiff(img_array, bg)
        norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
        
        return Image.fromarray(norm)
    
    @staticmethod
    def deskew(image: Image.Image) -> Image.Image:
        """Prostowanie przekrzywionych skanów"""
        img_array = np.array(image.convert('L'))
        
        edges = cv2.Canny(img_array, 50, 150, apertureSize=3)
        
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        
        if lines is not None:
            angles = []
            for rho, theta in lines[:, 0]:
                angle = (theta * 180 / np.pi) - 90
                if -45 < angle < 45:
                    angles.append(angle)
                    
            if angles:
                median_angle = np.median(angles)
                if abs(median_angle) > 0.5:
                    logger.info(f"Korekcja przekrzywienia: {median_angle:.2f}°")
                    return image.rotate(median_angle, expand=True, fillcolor=255)
                    
        return image
    
    @staticmethod
    def detect_and_remove_watermark(image: Image.Image) -> Image.Image:
        """Usuwanie znaków wodnych"""
        img_array = np.array(image.convert('L'))
        
        _, mask = cv2.threshold(img_array, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.dilate(mask, np.ones((3,3), np.uint8), iterations=1)
        
        result = cv2.inpaint(img_array, mask, 3, cv2.INPAINT_TELEA)
        
        return Image.fromarray(result)
    
    @staticmethod
    def preprocess(image: Image.Image, settings: Dict = None) -> Image.Image:
        """Pełny preprocessing"""
        if settings is None:
            settings = {
                'auto_rotate': CONFIG.parsing.auto_rotation,
                'enhance': True,
                'deskew': True,
                'remove_shadows': False,
                'remove_watermarks': CONFIG.parsing.remove_watermarks
            }
            
        original_size = image.size
        
        if min(original_size) < 1000:
            scale = 2000 / min(original_size)
            new_size = (int(original_size[0] * scale), int(original_size[1] * scale))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            
        if settings.get('auto_rotate'):
            image = ImagePreprocessor.auto_rotate(image)
            
        if settings.get('enhance'):
            image = ImagePreprocessor.enhance_quality(image)
            
        if settings.get('deskew'):
            image = ImagePreprocessor.deskew(image)
            
        if settings.get('remove_shadows'):
            image = ImagePreprocessor.remove_shadows(image)
            
        if settings.get('remove_watermarks'):
            image = ImagePreprocessor.detect_and_remove_watermark(image)
            
        return image

class TesseractEngine:
    """Silnik OCR Tesseract"""
    
    def __init__(self, language: str = 'Polski'):
        self.lang_config = get_language_config(language)
        self.tesseract_lang = self.lang_config.tesseract_lang
        
    def extract_text(self, image: Image.Image) -> OCRResult:
        """Ekstrakcja tekstu z obrazu"""
        import time
        start_time = time.time()
        
        processed_image = ImagePreprocessor.preprocess(image)
        processed_size = processed_image.size
        
        custom_config = f'--oem {CONFIG.ocr.tesseract_oem} --psm {CONFIG.ocr.tesseract_psm}'
        
        text = pytesseract.image_to_string(
            processed_image, 
            lang=self.tesseract_lang,
            config=custom_config
        )
        
        word_data = pytesseract.image_to_data(
            processed_image,
            lang=self.tesseract_lang,
            output_type=pytesseract.Output.DICT
        )
        
        confidences = [int(c) for c in word_data['conf'] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        word_boxes = []
        for i in range(len(word_data['text'])):
            try:
                if int(word_data['conf'][i]) > 0:
                    word_boxes.append({
                        'text': word_data['text'][i],
                        'left': word_data['left'][i],
                        'top': word_data['top'][i],
                        'width': word_data['width'][i],
                        'height': word_data['height'][i],
                        'confidence': word_data['conf'][i]
                    })
            except Exception:
                continue
                
        processing_time = time.time() - start_time
        
        return OCRResult(
            text=text,
            confidence=avg_confidence / 100,
            language=self.lang_config.code,
            engine='tesseract',
            processing_time=processing_time,
            word_boxes=word_boxes,
            image_size=processed_size
        )
    
    def extract_with_regions(self, image: Image.Image, regions: List[Tuple[int, int, int, int]]) -> List[OCRResult]:
        """Ekstrakacja z określonych regionów"""
        results = []
        
        for x, y, w, h in regions:
            region_img = image.crop((x, y, x + w, y + h))
            result = self.extract_text(region_img)
            results.append(result)
            
        return results

class PaddleOCREngine:
    """Silnik PaddleOCR 3.3.2 - FINALNA WERSJA"""
    
    def __init__(self, language: str = 'Polski'):
        if not PADDLEOCR_AVAILABLE:
            raise ImportError("PaddleOCR nie jest dostępny")
            
        from paddleocr import PaddleOCR
        
        self.lang_config = get_language_config(language)
        
        # Mapowanie języków dla PaddleOCR 3.3.2
        lang_map = {
            'pol': 'pl',
            'deu': 'german', 
            'ron': 'ro',
            'eng': 'en'
        }
        
        paddle_lang = lang_map.get(self.lang_config.tesseract_lang, 'en')
        
        try:
            self.ocr = PaddleOCR(lang=paddle_lang)
            logger.info(f"✅ PaddleOCR 3.3.2 OK (język: {paddle_lang})")
        except Exception as e:
            logger.error(f"❌ Błąd PaddleOCR 3.3.2: {e}")
            raise
        
    def extract_text(self, image: Image.Image) -> OCRResult:
        """Ekstrakcja tekstu - PaddleOCR 3.3.2 FINALNA"""
        import time
        start_time = time.time()
        
        # preprocess and use processed image for prediction
        processed_image = ImagePreprocessor.preprocess(image)
        processed_size = processed_image.size
        # Upewnij się, że obraz jest w trybie RGB (3 kanały)
        if processed_image.mode != "RGB":
            processed_image = processed_image.convert("RGB")
        img_array = np.array(processed_image)
        
        try:
            # ==== WYWOŁANIE API 3.3.2 ====
            result = self.ocr.predict(img_array)
            # ====
            
            text_lines = []
            word_boxes = []
            confidences = []
            
            # ==== PARSOWANIE WYNIKU 3.3.2 ====
            if isinstance(result, list) and len(result) > 0:
                page_result = result[0]
                
                if isinstance(page_result, dict):
                    texts = page_result.get('rec_texts', [])
                    scores = page_result.get('rec_scores', [])
                    polys = page_result.get('rec_polys', [])
                    
                    logger.info(f"📊 PaddleOCR wykrył {len(texts)} elementów tekstowych")
                    
                    items = []
                    for idx in range(len(texts)):
                        text = texts[idx] if idx < len(texts) else ''
                        score = scores[idx] if idx < len(scores) else 0.0
                        poly = polys[idx] if idx < len(polys) else None
                        
                        if text.strip():
                            if poly is not None and len(poly) > 0:
                                try:
                                    y_coords = [point[1] for point in poly]
                                    x_coords = [point[0] for point in poly]
                                    y_center = sum(y_coords) / len(y_coords)
                                    x_center = sum(x_coords) / len(x_coords)
                                    
                                    items.append({
                                        'text': text,
                                        'score': score,
                                        'y': y_center,
                                        'x': x_center,
                                        'left': int(min(x_coords)),
                                        'top': int(min(y_coords)),
                                        'width': int(max(x_coords) - min(x_coords)),
                                        'height': int(max(y_coords) - min(y_coords))
                                    })
                                except Exception as e:
                                    logger.warning(f"⚠️ Błąd parsowania poly dla '{text}': {e}")
                                    items.append({
                                        'text': text,
                                        'score': score,
                                        'y': idx * 30,
                                        'x': 0,
                                        'left': 0,
                                        'top': idx * 30,
                                        'width': 100,
                                        'height': 20
                                    })
                            else:
                                items.append({
                                    'text': text,
                                    'score': score,
                                    'y': idx * 30,
                                    'x': 0,
                                    'left': 0,
                                    'top': idx * 30,
                                    'width': 100,
                                    'height': 20
                                })
                    
                    # SORTOWANIE: góra->dół, lewo->prawo
                    items.sort(key=lambda item: (int(item['y'] / 20), item['x']))
                    
                    # Wyciągnij posortowane dane
                    for item in items:
                        text_lines.append(item['text'])
                        confidences.append(item['score'])
                        
                        word_boxes.append({
                            'text': item['text'],
                            'left': item['left'],
                            'top': item['top'],
                            'width': item['width'],
                            'height': item['height'],
                            'confidence': item['score'] * 100
                        })
                    
                    logger.info(f"✅ PaddleOCR 3.3.2: {len(text_lines)} linii posortowanych")
                else:
                    logger.warning(f"⚠️ Nieoczekiwany typ page_result: {type(page_result)}")
            else:
                logger.warning(f"⚠️ Pusty lub nieprawidłowy wynik PaddleOCR")
            # ====
            
            full_text = '\n'.join(text_lines)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            processing_time = time.time() - start_time
            
            logger.info(f"⏱️ PaddleOCR czas: {processing_time:.2f}s, pewność: {avg_confidence:.1%}")
            
            return OCRResult(
                text=full_text,
                confidence=avg_confidence,
                language=self.lang_config.code,
                engine='paddleocr_3.3.2',
                processing_time=processing_time,
                word_boxes=word_boxes,
                image_size=processed_size
            )
            
        except Exception as e:
            logger.error(f"❌ Błąd PaddleOCR 3.3.2: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Zwróć pusty wynik zamiast crashować
            return OCRResult(
                text="",
                confidence=0.0,
                language=self.lang_config.code,
                engine='paddleocr_error',
                processing_time=time.time() - start_time,
                word_boxes=[],
                image_size=processed_size if 'processed_size' in locals() else image.size
            )
    
    def detect_tables(self, image: Image.Image) -> List[Dict]:
        """Detekcja tabel - placeholder"""
        return []

class HybridOCREngine:
    """Hybrydowy silnik łączący Tesseract i PaddleOCR"""
    
    def __init__(self, language: str = 'Polski'):
        self.language = language
        self.tesseract = TesseractEngine(language)
        self.paddle = None
        
        if PADDLEOCR_AVAILABLE:
            try:
                self.paddle = PaddleOCREngine(language)
            except Exception as e:
                logger.warning(f"Nie można zainicjować PaddleOCR: {e}")
                
    def extract_text(self, image: Image.Image, strategy: str = 'best') -> OCRResult:
        """
        Ekstrakcja z różnymi strategiami:
        - 'fast': tylko Tesseract
        - 'accurate': tylko PaddleOCR
        - 'best': porównaj oba i wybierz lepszy
        - 'merge': połącz wyniki obu
        """
        
        if strategy == 'fast' or not self.paddle:
            return self.tesseract.extract_text(image)
            
        elif strategy == 'accurate' and self.paddle:
            return self.paddle.extract_text(image)
            
        elif strategy == 'best' and self.paddle:
            tesseract_result = self.tesseract.extract_text(image)
            paddle_result = self.paddle.extract_text(image)
            
            if paddle_result.confidence > tesseract_result.confidence:
                return paddle_result
            else:
                return tesseract_result
                
        elif strategy == 'merge' and self.paddle:
            tesseract_result = self.tesseract.extract_text(image)
            paddle_result = self.paddle.extract_text(image)
            
            merged_text = self._merge_texts(
                tesseract_result.text, 
                paddle_result.text
            )
            
            avg_confidence = (tesseract_result.confidence + paddle_result.confidence) / 2
            
            all_boxes = tesseract_result.word_boxes + paddle_result.word_boxes
            
            image_size = getattr(tesseract_result, "image_size", None) or getattr(paddle_result, "image_size", (0, 0))
            
            return OCRResult(
                text=merged_text,
                confidence=avg_confidence,
                language=self.language,
                engine='hybrid',
                processing_time=tesseract_result.processing_time + paddle_result.processing_time,
                word_boxes=all_boxes,
                image_size=image_size
            )
            
        return self.tesseract.extract_text(image)
    
    def _merge_texts(self, text1: str, text2: str) -> str:
        """Inteligentne łączenie tekstów z dwóch OCR"""
        lines1 = text1.split('\n')
        lines2 = text2.split('\n')
        
        merged_lines = []
        
        max_lines = max(len(lines1), len(lines2))
        
        for i in range(max_lines):
            line1 = lines1[i] if i < len(lines1) else ''
            line2 = lines2[i] if i < len(lines2) else ''
            
            if len(line1) > len(line2):
                merged_lines.append(line1)
            elif len(line2) > len(line1):
                merged_lines.append(line2)
            else:
                alnum1 = sum(c.isalnum() for c in line1)
                alnum2 = sum(c.isalnum() for c in line2)
                
                if alnum1 >= alnum2:
                    merged_lines.append(line1)
                else:
                    merged_lines.append(line2)
                    
        return '\n'.join(merged_lines)