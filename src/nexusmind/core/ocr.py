"""OCR 入库：图片与扫描版 PDF 的文字识别（本地 Tesseract，缺失时优雅降级）。

设计原则（与产品设计文档 P1-1 一致）：
- 引擎本地优先：调用本机 tesseract CLI，不上传任何数据。
- 引擎缺失时不抛错阻断入库：返回 available=False + 分平台安装指引，
  入库侧保存原件并标注 ocr=pending。
- PDF 渲染依赖可选的 PyMuPDF（pip install "nexusmind[ocr]"），缺失时同样降级。
"""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nexusmind.config import OCR_LANG

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

_INSTALL_HINTS = {
    "win32": "请安装 Tesseract OCR：https://github.com/UB-Mannheim/tesseract/wiki （安装时勾选中文语言包），并确认 tesseract.exe 在 PATH 中；或执行 pip install \"nexusmind[ocr]\" 补齐 PDF 渲染依赖。",
    "darwin": "请执行：brew install tesseract tesseract-lang；PDF 扫描件识别再执行 pip install \"nexusmind[ocr]\"。",
}
_DEFAULT_HINT = "请安装 Tesseract OCR 及中文语言包（如 Ubuntu：sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim）；PDF 扫描件识别再执行 pip install \"nexusmind[ocr]\"。"


def install_hint() -> str:
    return _INSTALL_HINTS.get(sys.platform, _DEFAULT_HINT)


def _tesseract_bin() -> Optional[str]:
    return shutil.which("tesseract")


def _tesseract_languages(binary: str) -> List[str]:
    try:
        proc = subprocess.run(
            [binary, "--list-langs"],
            capture_output=True, text=True, timeout=15,
        )
        langs = [line.strip() for line in proc.stdout.splitlines()[1:] if line.strip()]
        return langs
    except (OSError, subprocess.SubprocessError):
        return []


def _pdf_renderer_available() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_status() -> Dict[str, Any]:
    """返回 OCR 引擎可用性，供 UI 展示与入库降级决策。"""
    binary = _tesseract_bin()
    available = binary is not None
    version = None
    languages: List[str] = []
    if available:
        try:
            proc = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=15,
            )
            first = (proc.stdout or proc.stderr).splitlines()
            version = first[0].strip() if first else None
        except (OSError, subprocess.SubprocessError):
            version = None
        languages = _tesseract_languages(binary)
    return {
        "available": available,
        "engine": "tesseract" if available else None,
        "version": version,
        "languages": languages,
        "default_lang": OCR_LANG,
        "pdf_renderer": _pdf_renderer_available(),
        "install_hint": None if available else install_hint(),
    }


def _run_tesseract(image_path: Path, lang: str) -> Tuple[str, Optional[float]]:
    """对单张图片执行 OCR，返回 (文本, 平均置信度 0-1 或 None)。"""
    binary = _tesseract_bin()
    if not binary:
        raise RuntimeError("tesseract not available")
    text_proc = subprocess.run(
        [binary, str(image_path), "stdout", "--psm", "6", "-l", lang],
        capture_output=True, text=True, timeout=120,
    )
    if text_proc.returncode != 0:
        raise RuntimeError(f"tesseract failed: {text_proc.stderr.strip()[:200]}")
    text = text_proc.stdout.strip()

    confidence: Optional[float] = None
    try:
        tsv_proc = subprocess.run(
            [binary, str(image_path), "stdout", "--psm", "6", "-l", lang, "tsv"],
            capture_output=True, text=True, timeout=120,
        )
        if tsv_proc.returncode == 0:
            reader = csv.DictReader(io.StringIO(tsv_proc.stdout), delimiter="\t", quoting=csv.QUOTE_NONE)
            confs: List[float] = []
            for row in reader:
                try:
                    conf = float(row.get("conf", "-1"))
                except (TypeError, ValueError):
                    continue
                if conf >= 0:
                    confs.append(conf)
            if confs:
                confidence = round(sum(confs) / len(confs) / 100.0, 3)
    except (OSError, subprocess.SubprocessError):
        confidence = None
    return text, confidence


def ocr_image_bytes(data: bytes, suffix: str = ".png", *, lang: str = OCR_LANG) -> Dict[str, Any]:
    """识别图片字节，返回 {text, confidence, low_confidence}；引擎缺失抛 RuntimeError。"""
    if not _tesseract_bin():
        raise RuntimeError(install_hint())
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.TemporaryDirectory(prefix="nexusmind-ocr-") as tmp:
        image_path = Path(tmp) / f"page{suffix}"
        image_path.write_bytes(data)
        text, confidence = _run_tesseract(image_path, lang)
    return {
        "text": text,
        "confidence": confidence,
        "low_confidence": confidence is not None and confidence < 0.7,
        "engine": "tesseract",
        "lang": lang,
    }


def pdf_text_char_count(data: bytes) -> int:
    """统计 PDF 文本层总字符数，用于判断是否为扫描件。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    total = 0
    for page in reader.pages:
        total += len((page.extract_text() or "").strip())
    return total


def pdf_needs_ocr(data: bytes, *, min_chars: int = 50) -> bool:
    try:
        return pdf_text_char_count(data) < min_chars
    except Exception:
        return False


def ocr_pdf_bytes(data: bytes, *, lang: str = OCR_LANG, dpi: int = 200) -> Dict[str, Any]:
    """逐页渲染扫描版 PDF 并 OCR；缺 PyMuPDF 时抛 RuntimeError 并附安装指引。"""
    if not _tesseract_bin():
        raise RuntimeError(install_hint())
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "扫描版 PDF 识别需要 PyMuPDF 渲染页面：pip install \"nexusmind[ocr]\""
        ) from exc
    doc = fitz.open(stream=data, filetype="pdf")
    sections: List[str] = []
    confidences: List[float] = []
    with tempfile.TemporaryDirectory(prefix="nexusmind-ocr-pdf-") as tmp:
        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            image_path = Path(tmp) / f"page-{idx}.png"
            pix.save(str(image_path))
            text, confidence = _run_tesseract(image_path, lang)
            if confidence is not None:
                confidences.append(confidence)
            sections.append(f"## 第 {idx} 页\n\n{text}" if text else f"## 第 {idx} 页\n\n[未识别到文字]")
    avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else None
    return {
        "text": "\n\n".join(sections),
        "confidence": avg_conf,
        "low_confidence": avg_conf is not None and avg_conf < 0.7,
        "engine": "tesseract",
        "lang": lang,
        "pages": len(sections),
    }
