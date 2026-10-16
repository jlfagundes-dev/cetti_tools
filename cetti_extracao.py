from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path


class ExtractionError(RuntimeError):
    pass


class ExtractionUnavailable(ExtractionError):
    pass


class OCRUnavailable(ExtractionError):
    pass


@dataclass(frozen=True)
class PageText:
    page: int
    text: str
    method: str
    confidence: float | None = None
    review_required: bool = False
    review_reason: str | None = None


@dataclass(frozen=True)
class ExtractionResult:
    path: Path
    pages: tuple[PageText, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text).strip()

    @property
    def has_text(self) -> bool:
        return bool(self.text)

    @property
    def review_required(self) -> bool:
        return any(page.review_required for page in self.pages)

    @property
    def review_reasons(self) -> tuple[str, ...]:
        return tuple(
            f"pagina {page.page}: {page.review_reason or 'revisao necessaria'}"
            for page in self.pages
            if page.review_required
        )

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(page.method for page in self.pages))


def _load_pymupdf():
    try:
        return importlib.import_module("pymupdf")
    except ImportError:
        try:
            return importlib.import_module("fitz")
        except ImportError as error:
            raise ExtractionUnavailable(
                "PyMuPDF nao esta instalado; instale pymupdf para extracao de PDFs."
            ) from error


def _render_page(page, fitz):
    try:
        image_module = importlib.import_module("PIL.Image")
    except ImportError as error:
        raise OCRUnavailable(
            "OCR local requer Pillow."
        ) from error
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = image_module.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    return image, pixmap.tobytes("png")


def _ocr_page_tesseract(page, fitz) -> tuple[str, float | None]:
    try:
        pytesseract = importlib.import_module("pytesseract")
    except ImportError as error:
        raise OCRUnavailable(
            "OCR Tesseract requer pytesseract e o executavel Tesseract."
        ) from error

    try:
        languages = set(pytesseract.get_languages(config=""))
        language = "por+eng" if {"por", "eng"}.issubset(languages) else "por" if "por" in languages else "eng"
        image, _ = _render_page(page, fitz)
        text = pytesseract.image_to_string(image, lang=language).strip()
        data = pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)
        confidences = [
            float(value)
            for value in data.get("conf", [])
            if str(value).strip() not in {"", "-1"}
        ]
        confidence = sum(confidences) / len(confidences) if confidences else None
        return text, confidence
    except Exception as error:
        raise OCRUnavailable(f"Falha no OCR local: {error}") from error


def _ocr_page_glm(page, fitz, ollama_client) -> str:
    _, image_bytes = _render_page(page, fitz)
    return ollama_client.ocr_image(image_bytes).strip()


def extract_pdf(
    path: Path | str,
    use_ocr: bool = True,
    ocr_backend: str = "auto",
    ollama_client=None,
    min_tesseract_confidence: float = 60.0,
) -> ExtractionResult:
    if ocr_backend not in {"auto", "tesseract", "glm-ocr"}:
        raise ValueError("ocr_backend deve ser auto, tesseract ou glm-ocr.")
    if not 0 <= min_tesseract_confidence <= 100:
        raise ValueError("min_tesseract_confidence deve estar entre 0 e 100.")
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    fitz = _load_pymupdf()
    pages: list[PageText] = []
    try:
        document = fitz.open(pdf_path)
    except Exception as error:
        raise ExtractionError(f"Nao foi possivel abrir o PDF: {pdf_path}") from error

    try:
        for page_number, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()
            method = "native"
            confidence = None
            review_required = False
            review_reason = None
            if not text and use_ocr:
                if ocr_backend == "glm-ocr" and ollama_client is None:
                    raise OCRUnavailable("ocr_backend=glm-ocr requer um cliente Ollama local.")
                try:
                    if ocr_backend != "glm-ocr":
                        text, confidence = _ocr_page_tesseract(page, fitz)
                        method = "tesseract"
                        if text and confidence is not None and confidence < min_tesseract_confidence:
                            review_required = True
                            review_reason = f"confianca Tesseract baixa ({confidence:.1f})"
                        if text and confidence is not None and confidence >= min_tesseract_confidence:
                            pass
                        elif ollama_client is not None and ocr_backend == "auto":
                            text = _ocr_page_glm(page, fitz, ollama_client)
                            method = "glm-ocr"
                            confidence = None
                            review_required = True
                            review_reason = "resultado produzido pelo fallback glm-ocr"
                    else:
                        text = _ocr_page_glm(page, fitz, ollama_client)
                        method = "glm-ocr"
                        review_required = True
                        review_reason = "resultado produzido pelo glm-ocr"
                except OCRUnavailable:
                    if ocr_backend == "auto" and ollama_client is not None:
                        text = _ocr_page_glm(page, fitz, ollama_client)
                        method = "glm-ocr"
                        review_required = True
                        review_reason = "Tesseract indisponivel; usado fallback glm-ocr"
                    else:
                        raise
                if not text:
                    method = f"{method}-empty"
                    review_required = True
                    review_reason = review_reason or "nenhum texto reconhecido"
            elif not text:
                method = "empty"
                review_required = True
                review_reason = "pagina sem texto nativo e OCR desativado"
            pages.append(PageText(page_number, text, method, confidence, review_required, review_reason))
    finally:
        document.close()
    return ExtractionResult(pdf_path, tuple(pages))
