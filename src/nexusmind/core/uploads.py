from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from docx import Document
from pypdf import PdfReader

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.ocr import ocr_image_bytes, ocr_pdf_bytes, pdf_needs_ocr

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp"}
IMAGE_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _safe_name(filename: str) -> str:
    name = Path(filename).name.strip()
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    safe_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    return (safe_stem or "upload") + suffix


def _unique_rel_path(folder: str, filename: str, vault_root: Path) -> str:
    base = f"{folder.rstrip('/')}/{filename}"
    if not (vault_root / base).exists():
        return base
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"{folder.rstrip('/')}/{stem}-{stamp}{suffix}"
    seq = 2
    while (vault_root / candidate).exists():
        candidate = f"{folder.rstrip('/')}/{stem}-{stamp}-{seq}{suffix}"
        seq += 1
    return candidate
def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages: List[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append(f"## 第 {idx} 页\n\n{text}" if text else f"## 第 {idx} 页\n\n[未提取到可搜索文本]")
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    blocks: List[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            blocks.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                blocks.append("| " + " | ".join(cells) + " |")
    return "\n\n".join(blocks)


def _extract_text(filename: str, data: bytes) -> Tuple[str, str, Dict[str, Any]]:
    """提取可编译文本；图片/扫描 PDF 走 OCR，引擎缺失时返回占位说明与 pending 标记。"""
    ext = Path(filename).suffix.lower()
    if ext == ".md":
        return data.decode("utf-8-sig", errors="replace"), "markdown", {}
    if ext == ".txt":
        return data.decode("utf-8-sig", errors="replace"), "text", {}
    if ext == ".docx":
        return _extract_docx(data), "docx", {}
    if ext == ".pdf":
        text = _extract_pdf(data)
        if not pdf_needs_ocr(data):
            return text, "pdf", {}
        # 扫描版 PDF：尝试 OCR，失败则保留原占位并标注 ocr: needed。
        try:
            result = ocr_pdf_bytes(data)
        except RuntimeError as exc:
            return text, "pdf", {"ocr": "needed", "ocr_note": str(exc)}
        meta: Dict[str, Any] = {"ocr": True, "ocr_engine": result["engine"]}
        if result.get("confidence") is not None:
            meta["ocr_confidence"] = result["confidence"]
        body = result["text"]
        if result.get("low_confidence"):
            body += "\n\n> ⚠️ OCR 平均置信度较低，请对识别结果人工校对。"
        return body, "pdf", meta
    if ext in IMAGE_UPLOAD_EXTENSIONS:
        try:
            result = ocr_image_bytes(data, ext)
        except RuntimeError as exc:
            placeholder = (
                "[图片原件已保存，但 OCR 引擎当前不可用，未能提取文字]\n\n"
                f"安装指引：{exc}"
            )
            return placeholder, "image", {"ocr": "pending"}
        meta = {"ocr": True, "ocr_engine": result["engine"]}
        if result.get("confidence") is not None:
            meta["ocr_confidence"] = result["confidence"]
        body = result["text"] or "[未识别到文字]"
        if result.get("low_confidence"):
            body += "\n\n> ⚠️ OCR 平均置信度较低，请对识别结果人工校对。"
        return body, "image", meta
    raise ValueError(f"Unsupported file type: {ext or '[none]'}")
def ingest_uploaded_file(
    filename: str,
    data: bytes,
    *,
    author: str = "Unknown",
    source_url: str | None = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """保存原始文件并生成可编译 Markdown，二者都不覆盖已有内容。"""
    safe_name = _safe_name(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported file types: .md, .txt, .pdf, .docx, .png, .jpg, .jpeg, .webp")
    if not data:
        raise ValueError("Uploaded file is empty")

    raw_rel = _unique_rel_path("60-References/Files", safe_name, vault_root)
    raw_path = vault_root / raw_rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(data)

    extracted, kind, ocr_meta = _extract_text(safe_name, data)
    title = Path(safe_name).stem
    note_filename = title + ".md"
    note_rel = _unique_rel_path("60-References/Articles", note_filename, vault_root)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_link = raw_rel.replace("\\", "/")
    clean_author = (author or "Unknown").replace('"', "'")
    clean_url = (source_url or "").replace('"', "'")
    extra_fm = ""
    for key, value in ocr_meta.items():
        if isinstance(value, bool):
            extra_fm += f"{key}: {str(value).lower()}\n"
        elif isinstance(value, (int, float)):
            extra_fm += f"{key}: {value}\n"
        else:
            extra_fm += f'{key}: "{str(value).replace(chr(34), chr(39))}"\n'
    markdown = f"""---
title: "{title.replace('"', "'")}"
author: "{clean_author}"
url: "{clean_url}"
ingested_at: "{timestamp}"
source_file: "{source_link}"
source_type: "{kind}"
{extra_fm}tags:
  - "#raw-reference"
  - "#uploaded"
---

# {title}

> 原始文件：[[{source_link}]]

{extracted.strip()}
"""
    result = patch_note(
        note_rel,
        markdown,
        if_match="NEW",
        actor="upload",
        privileged=True,
        vault_root=vault_root,
    )
    return {
        "status": "ingested_successfully",
        "filename": safe_name,
        "original_path": raw_rel,
        "markdown_path": note_rel,
        "version": result["version"],
        "source_type": kind,
        "bytes": len(data),
        "ocr": ocr_meta or None,
    }


def ingest_uploaded_files(
    files: Iterable[Tuple[str, bytes]],
    *,
    author: str = "Unknown",
    source_url: str | None = None,
    vault_root: Path = VAULT_ROOT,
) -> List[Dict[str, Any]]:
    return [
        ingest_uploaded_file(
            filename,
            data,
            author=author,
            source_url=source_url,
            vault_root=vault_root,
        )
        for filename, data in files
    ]
