from __future__ import annotations

import os
import shutil
import json
import math
import re
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_FILES_PER_BATCH = 12
CHUNK_SIZE = 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".pdf"}

storage_root = Path(os.getenv("STORAGE_ROOT", "storage")).resolve()
database_url = os.getenv("DATABASE_URL", "sqlite:///storage/mistakemate.db")
engine_options: dict[str, object] = {"pool_pre_ping": True}
if database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    files: Mapped[list["UploadedFile"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    questions: Mapped[list["MistakeQuestion"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    batch: Mapped[UploadBatch] = relationship(back_populates="files")


class OcrRun(Base):
    __tablename__ = "ocr_runs"

    batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), primary_key=True)
    engine: Mapped[str] = mapped_column(String(64), default="PaddleOCR PP-OCRv6")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    text: Mapped[str] = mapped_column(Text, default="")
    raw_result: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OcrRegion(Base):
    __tablename__ = "ocr_regions"

    file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id"), primary_key=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)


class MistakeQuestion(Base):
    __tablename__ = "mistake_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    question_type: Mapped[str] = mapped_column(String(32), default="单选题")
    stem: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[str] = mapped_column(Text, default="[]")
    correct_answer: Mapped[str] = mapped_column(String(128), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    knowledge_points: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    error_type: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    batch: Mapped[UploadBatch] = relationship(back_populates="questions")
    parts: Mapped[list["QuestionPart"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class QuestionPart(Base):
    __tablename__ = "question_parts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("mistake_questions.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(32), default="")
    part_type: Mapped[str] = mapped_column(String(32), default="计算题")
    prompt: Mapped[str] = mapped_column(Text, default="")
    answers: Mapped[str] = mapped_column(Text, default="[]")
    solution: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[str] = mapped_column(Text, default="[]")
    answer_lines: Mapped[int] = mapped_column(Integer, default=3)
    knowledge_points: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    error_type: Mapped[str] = mapped_column(String(32), default="")
    question: Mapped[MistakeQuestion] = relationship(back_populates="parts")


class PrintTemplate(Base):
    __tablename__ = "print_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    settings: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UploadResponse(BaseModel):
    id: str
    status: str
    file_count: int


class MistakeBatchResponse(BaseModel):
    id: str
    subject: str
    source: str
    note: str
    status: str
    created_at: datetime
    file_count: int


class UploadedFileResponse(BaseModel):
    id: str
    original_name: str
    content_type: str
    size: int


class OcrRunResponse(BaseModel):
    engine: str
    status: str
    text: str
    error_message: str
    started_at: datetime | None
    completed_at: datetime | None


class QuestionOption(BaseModel):
    label: str
    text: str


class QuestionPartPayload(BaseModel):
    id: str = ""
    parent_id: str | None = None
    position: int = 1
    label: str = ""
    part_type: str = "计算题"
    prompt: str = ""
    answers: list[str] = Field(default_factory=list)
    solution: str = ""
    key_points: list[str] = Field(default_factory=list)
    answer_lines: int = 3
    knowledge_points: str = ""
    difficulty: int = 3
    error_type: str = ""


class MistakeQuestionResponse(BaseModel):
    id: str
    position: int
    question_type: str
    stem: str
    options: list[QuestionOption]
    correct_answer: str
    explanation: str
    knowledge_points: str
    difficulty: int
    error_type: str
    parts: list[QuestionPartPayload]
    status: str
    updated_at: datetime


class QuestionUpdateRequest(BaseModel):
    question_type: str
    stem: str
    options: list[QuestionOption]
    correct_answer: str = ""
    explanation: str = ""
    knowledge_points: str = ""
    difficulty: int = 3
    error_type: str = ""
    parts: list[QuestionPartPayload] = Field(default_factory=list)
    status: str = "draft"


class StructureSuggestionRequest(BaseModel):
    stem: str


class StructureSuggestionResponse(BaseModel):
    stem: str
    parts: list[QuestionPartPayload]


class MistakeBatchDetailResponse(MistakeBatchResponse):
    files: list[UploadedFileResponse]
    ocr: OcrRunResponse | None
    questions: list[MistakeQuestionResponse]


class PrintableQuestionResponse(MistakeQuestionResponse):
    batch_id: str
    subject: str
    source: str
    batch_created_at: datetime


class PrintTemplatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings: dict[str, Any]


class PrintTemplateResponse(PrintTemplatePayload):
    id: str
    created_at: datetime
    updated_at: datetime


ocr_model: Any | None = None
ocr_model_lock = Lock()
OPTION_LABEL_PATTERN = re.compile(r"^([A-H])(?:[.、．:：]\s*|\s+|$)(.*)$")
TOP_PART_PATTERN = re.compile(r"(?m)^\s*[（(](\d{1,2})[）)]\s*")
CIRCLED_PART_PATTERN = re.compile(r"(?m)^\s*([①②③④⑤⑥⑦⑧⑨⑩])\s*")
QUESTION_PART_TYPES = {"题组说明", "填空题", "计算题", "证明题", "简答题", "选择题", "判断题", "其他"}


def to_ocr_response(run: OcrRun | None) -> OcrRunResponse | None:
    if run is None:
        return None
    return OcrRunResponse(
        engine=run.engine,
        status=run.status,
        text=run.text,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def parse_string_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def to_question_part_payload(part: QuestionPart) -> QuestionPartPayload:
    return QuestionPartPayload(
        id=part.id,
        parent_id=part.parent_id,
        position=part.position,
        label=part.label,
        part_type=part.part_type,
        prompt=part.prompt,
        answers=parse_string_list(part.answers),
        solution=part.solution,
        key_points=parse_string_list(part.key_points),
        answer_lines=part.answer_lines,
        knowledge_points=part.knowledge_points,
        difficulty=part.difficulty,
        error_type=part.error_type,
    )


def to_question_response(question: MistakeQuestion) -> MistakeQuestionResponse:
    try:
        parsed_options = json.loads(question.options)
    except json.JSONDecodeError:
        parsed_options = []
    options = [QuestionOption(label=str(item.get("label", "")), text=str(item.get("text", ""))) for item in parsed_options if isinstance(item, dict)]
    return MistakeQuestionResponse(
        id=question.id,
        position=question.position,
        question_type=question.question_type,
        stem=question.stem,
        options=options,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        knowledge_points=question.knowledge_points,
        difficulty=question.difficulty,
        error_type=question.error_type,
        parts=[to_question_part_payload(part) for part in sorted(question.parts, key=lambda item: item.position)],
        status=question.status,
        updated_at=question.updated_at,
    )


def infer_part_type(prompt: str) -> str:
    if re.search(r"_{2,}|（\s*）|\(\s*\)|填空", prompt):
        return "填空题"
    if "证明" in prompt or ("说明" in prompt and "正确" in prompt):
        return "证明题"
    if any(marker in prompt for marker in ("计算", "求出", "求值", "解方程", "定值")):
        return "计算题"
    if "选择" in prompt:
        return "选择题"
    if "判断" in prompt:
        return "判断题"
    return "简答题"


def suggested_answer_count(prompt: str, part_type: str) -> int:
    if part_type != "填空题":
        return 1
    blanks = re.findall(r"_{2,}|（\s*）|\(\s*\)", prompt)
    return max(1, min(len(blanks), 12))


def suggested_answer_lines(part_type: str) -> int:
    return {"填空题": 1, "选择题": 1, "判断题": 1, "计算题": 4, "证明题": 6, "简答题": 4}.get(part_type, 3)


def build_structure_suggestion(stem: str) -> StructureSuggestionResponse:
    top_matches = list(TOP_PART_PATTERN.finditer(stem))
    if not top_matches:
        return StructureSuggestionResponse(stem=stem, parts=[])

    common_stem = stem[: top_matches[0].start()].strip()
    parts: list[QuestionPartPayload] = []
    position = 1
    for index, match in enumerate(top_matches):
        segment_end = top_matches[index + 1].start() if index + 1 < len(top_matches) else len(stem)
        segment = stem[match.end() : segment_end].strip()
        top_label = f"({match.group(1)})"
        child_matches = list(CIRCLED_PART_PATTERN.finditer(segment))
        if child_matches:
            group_id = str(uuid4())
            group_prompt = segment[: child_matches[0].start()].strip()
            parts.append(
                QuestionPartPayload(
                    id=group_id,
                    position=position,
                    label=top_label,
                    part_type="题组说明",
                    prompt=group_prompt,
                    answers=[],
                    answer_lines=0,
                )
            )
            position += 1
            for child_index, child_match in enumerate(child_matches):
                child_end = child_matches[child_index + 1].start() if child_index + 1 < len(child_matches) else len(segment)
                child_prompt = segment[child_match.end() : child_end].strip()
                part_type = infer_part_type(child_prompt)
                parts.append(
                    QuestionPartPayload(
                        id=str(uuid4()),
                        parent_id=group_id,
                        position=position,
                        label=child_match.group(1),
                        part_type=part_type,
                        prompt=child_prompt,
                        answers=[""] * suggested_answer_count(child_prompt, part_type),
                        answer_lines=suggested_answer_lines(part_type),
                    )
                )
                position += 1
        else:
            part_type = infer_part_type(segment)
            parts.append(
                QuestionPartPayload(
                    id=str(uuid4()),
                    position=position,
                    label=top_label,
                    part_type=part_type,
                    prompt=segment,
                    answers=[""] * suggested_answer_count(segment, part_type),
                    answer_lines=suggested_answer_lines(part_type),
                )
            )
            position += 1

    return StructureSuggestionResponse(stem=common_stem or stem, parts=parts)


def save_question_parts(session: Any, question: MistakeQuestion, payloads: list[QuestionPartPayload]) -> None:
    if len(payloads) > 30:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一道题最多添加 30 个小问或分组。")

    existing_by_id = {part.id: part for part in question.parts}
    payload_ids: set[str] = set()
    id_mapping: dict[str, str] = {}
    seen_ids: set[str] = set()
    seen_types: dict[str, str] = {}

    for index, payload in enumerate(payloads):
        payload_id = payload.id.strip()
        if not payload_id or payload_id in payload_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="小问编号数据无效，请重新拆分后再保存。")
        payload_ids.add(payload_id)
        id_mapping[payload_id] = payload_id if payload_id in existing_by_id else str(uuid4())

        if payload.part_type not in QUESTION_PART_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{payload.label or '小问'}的题型不正确。")
        if payload.parent_id is not None and payload.parent_id not in seen_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{payload.label or '小问'}的上级分组不正确。")
        if payload.parent_id is not None and seen_types.get(payload.parent_id) != "题组说明":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{payload.label or '小问'}只能放在题组说明下面。")
        if payload.parent_id is not None and payload.part_type == "题组说明":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="暂不支持三层以上的小问结构。")
        if not payload.label.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写每个小问的编号。")
        if not payload.prompt.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"请填写小问 {payload.label} 的内容。")
        if not 1 <= payload.difficulty <= 5:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"小问 {payload.label} 的难度应在 1 到 5 星之间。")
        if payload.part_type != "题组说明" and not 1 <= payload.answer_lines <= 12:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"小问 {payload.label} 的答题空间应为 1 到 12 行。")
        if len(payload.answers) > 12 or len(payload.key_points) > 12:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"小问 {payload.label} 的答案或关键步骤过多。")

        answers = [answer.strip()[:1000] for answer in payload.answers]
        solution = payload.solution.strip()[:12000]
        part_id = id_mapping[payload_id]
        part = existing_by_id.get(part_id)
        if part is None:
            part = QuestionPart(id=part_id, question_id=question.id)
            session.add(part)
        part.parent_id = id_mapping.get(payload.parent_id) if payload.parent_id else None
        part.position = index + 1
        part.label = payload.label.strip()[:32]
        part.part_type = payload.part_type
        part.prompt = payload.prompt.strip()[:12000]
        part.answers = json.dumps(answers, ensure_ascii=False)
        part.solution = solution
        part.key_points = json.dumps([point.strip()[:1000] for point in payload.key_points if point.strip()], ensure_ascii=False)
        part.answer_lines = 0 if payload.part_type == "题组说明" else payload.answer_lines
        part.knowledge_points = payload.knowledge_points.strip()[:1000]
        part.difficulty = payload.difficulty
        part.error_type = payload.error_type.strip()[:32]
        seen_ids.add(payload_id)
        seen_types[payload_id] = payload.part_type

    kept_ids = set(id_mapping.values())
    for part_id, part in existing_by_id.items():
        if part_id not in kept_ids:
            session.delete(part)


def first_non_empty(lines: list[str], start: int, limit: int = 8) -> str:
    for line in lines[start : start + limit]:
        match = OPTION_LABEL_PATTERN.match(line)
        if match:
            return match.group(1)
    return ""


def build_question_draft(ocr_text: str) -> MistakeQuestion:
    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    question_start = next((index for index, line in enumerate(lines) if re.search(r"[（(](?:单选|多选|判断)", line)), 0)
    marker_line = lines[question_start] if lines else ""
    type_match = re.search(r"[（(](单选题|多选题|判断题)[）)]", marker_line)
    question_type = type_match.group(1) if type_match else "其他"
    stem_opening = re.sub(r"^.*?[（(](?:单选题|多选题|判断题)[）)]\s*", "", marker_line)
    option_indexes = [index for index, line in enumerate(lines) if OPTION_LABEL_PATTERN.match(line)]
    first_option_index = next((index for index in option_indexes if index >= question_start), len(lines))
    stem_lines = ([stem_opening] if stem_opening else []) + lines[question_start + 1 : first_option_index]
    stem = "\n".join(line for line in stem_lines if line)

    stop_markers = ("正确答案", "你的答案", "全站正确率", "文本解析", "解析", "纠错", "收藏", "笔记", "草稿纸", "答题卡")
    answer_marker_index = next((index for index, line in enumerate(lines) if "正确答案" in line), -1)
    option_indexes = [index for index in option_indexes if index < answer_marker_index or answer_marker_index < 0]
    options: list[dict[str, str]] = []
    for position, option_index in enumerate(option_indexes):
        if option_index < first_option_index:
            continue
        label_match = OPTION_LABEL_PATTERN.match(lines[option_index])
        if label_match is None:
            continue
        label, first_text = label_match.groups()
        next_index = option_indexes[position + 1] if position + 1 < len(option_indexes) else len(lines)
        option_lines = [first_text] if first_text else []
        for line in lines[option_index + 1 : next_index]:
            if any(marker in line for marker in stop_markers):
                break
            option_lines.append(line)
        text = "\n".join(line for line in option_lines if line).strip()
        if text:
            options.append({"label": label, "text": text})

    correct_answer = first_non_empty(lines, answer_marker_index + 1) if answer_marker_index >= 0 else ""
    explanation_marker_index = next((index for index, line in enumerate(lines) if "文本解析" in line or line == "解析"), -1)
    explanation_lines: list[str] = []
    if explanation_marker_index >= 0:
        for line in lines[explanation_marker_index + 1 :]:
            if line in {"纠错", "收藏", "笔记", "草稿纸", "答题卡", "答案"}:
                continue
            explanation_lines.append(line)

    return MistakeQuestion(
        id=str(uuid4()),
        position=1,
        question_type=question_type,
        stem=stem or "请根据原图补充题干。",
        options=json.dumps(options, ensure_ascii=False),
        correct_answer=correct_answer,
        explanation="\n".join(explanation_lines),
        knowledge_points="",
        difficulty=3,
        error_type="",
        status="draft",
    )


def create_question_draft_if_missing(session: Any, batch_id: str, ocr_text: str, force_replace: bool = False) -> None:
    existing = session.execute(select(MistakeQuestion).where(MistakeQuestion.batch_id == batch_id).limit(1)).scalar_one_or_none()
    if existing is None and ocr_text.strip():
        question = build_question_draft(ocr_text)
        question.batch_id = batch_id
        session.add(question)
    elif (
        existing is not None
        and ocr_text.strip()
        and (
            force_replace
            or (
                existing.status == "draft"
                and not existing.knowledge_points
                and not existing.error_type
                and existing.updated_at <= existing.created_at + timedelta(seconds=2)
            )
        )
    ):
        refreshed = build_question_draft(ocr_text)
        existing.question_type = refreshed.question_type
        existing.stem = refreshed.stem
        existing.options = refreshed.options
        existing.correct_answer = refreshed.correct_answer
        existing.explanation = refreshed.explanation
        if force_replace:
            existing.status = "draft"
            for part in list(existing.parts):
                session.delete(part)
        existing.updated_at = datetime.now(timezone.utc)


def get_ocr_model() -> Any:
    global ocr_model
    with ocr_model_lock:
        if ocr_model is None:
            from paddleocr import PaddleOCR

            ocr_model = PaddleOCR(
                use_doc_orientation_classify=True,
                use_doc_unwarping=True,
                use_textline_orientation=True,
                enable_mkldnn=False,
                engine="paddle",
            )
    return ocr_model


def prepare_ocr_inputs(
    source: Path,
    original_name: str,
    temporary_directory: Path,
    crop_region: tuple[float, float, float, float] | None = None,
) -> list[Path]:
    extension = Path(original_name).suffix.lower()
    if extension == ".pdf":
        import fitz

        document = fitz.open(source)
        pages: list[Path] = []
        try:
            for index, page in enumerate(document):
                target = temporary_directory / f"{source.stem}-{index + 1}.png"
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(target)
                pages.append(target)
        finally:
            document.close()
        return pages
    if extension in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    if extension in {".heic", ".heif"} or crop_region is not None:
        from PIL import Image, ImageOps

        target = temporary_directory / f"{source.stem}-prepared.png"
        with Image.open(source) as image:
            prepared = ImageOps.exif_transpose(image).convert("RGB")
            if crop_region is not None:
                x, y, width, height = crop_region
                left = round(prepared.width * x)
                top = round(prepared.height * y)
                right = round(prepared.width * (x + width))
                bottom = round(prepared.height * (y + height))
                prepared = prepared.crop((left, top, right, bottom))
            prepared.save(target, "PNG")
        return [target]
    return [source]


def parse_crop_regions(value: str, file_count: int) -> list[tuple[float, float, float, float] | None]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="识别范围格式不正确。") from error
    if payload == []:
        return [None] * file_count
    if not isinstance(payload, list) or len(payload) != file_count:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="识别范围与文件数量不一致。")

    regions: list[tuple[float, float, float, float] | None] = []
    for region in payload:
        if region is None:
            regions.append(None)
            continue
        if not isinstance(region, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="识别范围格式不正确。")
        try:
            coordinates = tuple(float(region[key]) for key in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="识别范围缺少有效坐标。") from error
        x, y, width, height = coordinates
        if (
            not all(math.isfinite(coordinate) for coordinate in coordinates)
            or x < 0
            or y < 0
            or width < 0.03
            or height < 0.03
            or x + width > 1.0001
            or y + height > 1.0001
        ):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="识别范围超出图片边界或过小。")
        regions.append((x, y, width, height))
    return regions


def result_to_dict(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        return json.loads(payload)
    if isinstance(payload, dict):
        return payload
    if isinstance(result, dict):
        return result
    return json.loads(json.dumps(result, default=str))


def run_ocr(batch_id: str, replace_question: bool = False) -> None:
    with SessionLocal.begin() as session:
        batch = session.get(UploadBatch, batch_id)
        run = session.get(OcrRun, batch_id)
        if batch is None or run is None:
            return
        batch.status = "recognizing"
        run.status = "running"
        run.error_message = ""
        run.text = ""
        run.raw_result = ""
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        files = []
        for file in batch.files:
            region = session.get(OcrRegion, file.id)
            crop_region = (region.x, region.y, region.width, region.height) if region else None
            files.append((file.id, file.original_name, file.stored_name, crop_region))

    try:
        model = get_ocr_model()
        results: list[dict[str, Any]] = []
        text_lines: list[str] = []
        with tempfile.TemporaryDirectory(prefix="mistakemate-ocr-") as temporary_path:
            temporary_directory = Path(temporary_path)
            for _, original_name, stored_name, crop_region in files:
                source = storage_root / "uploads" / batch_id / stored_name
                for input_path in prepare_ocr_inputs(source, original_name, temporary_directory, crop_region):
                    for result in model.predict(str(input_path)):
                        payload = result_to_dict(result)
                        results.append(payload)
                        recognized = payload.get("res", payload).get("rec_texts", [])
                        text_lines.extend(str(line) for line in recognized if str(line).strip())

        recognized_text = "\n".join(text_lines).strip()
        if not recognized_text:
            raise RuntimeError("没有识别出可编辑文字，请调整裁剪范围或换一张更清晰的图片后重试。")

        with SessionLocal.begin() as session:
            batch = session.get(UploadBatch, batch_id)
            run = session.get(OcrRun, batch_id)
            if batch is None or run is None:
                return
            batch.status = "review_ready"
            run.status = "completed"
            run.text = recognized_text
            run.raw_result = json.dumps(results, ensure_ascii=False)
            run.completed_at = datetime.now(timezone.utc)
            create_question_draft_if_missing(session, batch_id, run.text, force_replace=replace_question)
    except Exception as error:
        with SessionLocal.begin() as session:
            batch = session.get(UploadBatch, batch_id)
            run = session.get(OcrRun, batch_id)
            if batch is None or run is None:
                return
            batch.status = "ocr_failed"
            run.status = "failed"
            run.error_message = str(error)[:2000]
            run.completed_at = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    storage_root.mkdir(parents=True, exist_ok=True)
    for attempt in range(30):
        try:
            Base.metadata.create_all(engine)
            break
        except OperationalError:
            if attempt == 29:
                raise
            time.sleep(1)
    with SessionLocal.begin() as session:
        completed_runs = session.execute(select(OcrRun).where(OcrRun.status == "completed")).scalars().all()
        for run in completed_runs:
            create_question_draft_if_missing(session, run.batch_id, run.text)
    yield
    engine.dispose()


app = FastAPI(title="MistakeMate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/mistakes", response_model=list[MistakeBatchResponse])
def list_mistakes(subject: str | None = None) -> list[MistakeBatchResponse]:
    statement = (
        select(UploadBatch, func.count(UploadedFile.id).label("file_count"))
        .outerjoin(UploadedFile)
        .group_by(UploadBatch.id)
        .order_by(UploadBatch.created_at.desc())
    )
    if subject:
        statement = statement.where(UploadBatch.subject == subject)

    with SessionLocal() as session:
        rows = session.execute(statement).all()
    return [
        MistakeBatchResponse(
            id=batch.id,
            subject=batch.subject,
            source=batch.source,
            note=batch.note,
            status=batch.status,
            created_at=batch.created_at,
            file_count=file_count,
        )
        for batch, file_count in rows
    ]


@app.get("/api/print/questions", response_model=list[PrintableQuestionResponse])
def list_printable_questions(subject: str | None = None) -> list[PrintableQuestionResponse]:
    statement = (
        select(MistakeQuestion, UploadBatch)
        .join(UploadBatch, MistakeQuestion.batch_id == UploadBatch.id)
        .where(MistakeQuestion.status == "confirmed")
        .order_by(UploadBatch.created_at.desc(), MistakeQuestion.position.asc())
    )
    if subject:
        statement = statement.where(UploadBatch.subject == subject)

    with SessionLocal() as session:
        rows = session.execute(statement).all()
        return [
            PrintableQuestionResponse(
                **to_question_response(question).model_dump(),
                batch_id=batch.id,
                subject=batch.subject,
                source=batch.source,
                batch_created_at=batch.created_at,
            )
            for question, batch in rows
        ]


def to_print_template_response(template: PrintTemplate) -> PrintTemplateResponse:
    try:
        settings = json.loads(template.settings)
    except (json.JSONDecodeError, TypeError):
        settings = {}
    return PrintTemplateResponse(
        id=template.id,
        name=template.name,
        settings=settings if isinstance(settings, dict) else {},
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def normalize_print_template(payload: PrintTemplatePayload) -> tuple[str, str]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="模板名称不能为空。")
    settings = json.dumps(payload.settings, ensure_ascii=False)
    if len(settings.encode("utf-8")) > 32 * 1024:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="模板设置内容过大。")
    return name, settings


@app.get("/api/print/templates", response_model=list[PrintTemplateResponse])
def list_print_templates() -> list[PrintTemplateResponse]:
    with SessionLocal() as session:
        templates = session.execute(select(PrintTemplate).order_by(PrintTemplate.updated_at.desc())).scalars().all()
        return [to_print_template_response(template) for template in templates]


@app.post("/api/print/templates", response_model=PrintTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_print_template(payload: PrintTemplatePayload) -> PrintTemplateResponse:
    name, settings = normalize_print_template(payload)
    with SessionLocal.begin() as session:
        template = PrintTemplate(id=str(uuid4()), name=name, settings=settings)
        session.add(template)
    return to_print_template_response(template)


@app.put("/api/print/templates/{template_id}", response_model=PrintTemplateResponse)
def update_print_template(template_id: str, payload: PrintTemplatePayload) -> PrintTemplateResponse:
    name, settings = normalize_print_template(payload)
    with SessionLocal.begin() as session:
        template = session.get(PrintTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这个打印模板。")
        template.name = name
        template.settings = settings
        template.updated_at = datetime.now(timezone.utc)
    return to_print_template_response(template)


@app.delete("/api/print/templates/{template_id}")
def delete_print_template(template_id: str) -> dict[str, str]:
    with SessionLocal.begin() as session:
        template = session.get(PrintTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这个打印模板。")
        session.delete(template)
    return {"status": "deleted"}


@app.get("/api/mistakes/{batch_id}", response_model=MistakeBatchDetailResponse)
def get_mistake_batch(batch_id: str) -> MistakeBatchDetailResponse:
    with SessionLocal() as session:
        batch = session.get(UploadBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这组错题。")
        files = list(batch.files)
        ocr = to_ocr_response(session.get(OcrRun, batch_id))
        questions = sorted(list(batch.questions), key=lambda question: question.position)
        question_responses = [to_question_response(question) for question in questions]

    return MistakeBatchDetailResponse(
        id=batch.id,
        subject=batch.subject,
        source=batch.source,
        note=batch.note,
        status=batch.status,
        created_at=batch.created_at,
        file_count=len(files),
        files=[
            UploadedFileResponse(
                id=file.id,
                original_name=file.original_name,
                content_type=file.content_type,
                size=file.size,
            )
            for file in files
        ],
        ocr=ocr,
        questions=question_responses,
    )


@app.get("/api/mistakes/{batch_id}/files/{file_id}")
def get_uploaded_file(batch_id: str, file_id: str) -> FileResponse:
    with SessionLocal() as session:
        file = session.get(UploadedFile, file_id)
        if file is None or file.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到原始文件。")
        path = storage_root / "uploads" / batch_id / file.stored_name

    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原始文件已不存在。")
    return FileResponse(path, media_type=file.content_type)


@app.post("/api/mistakes/{batch_id}/ocr", response_model=OcrRunResponse, status_code=status.HTTP_202_ACCEPTED)
def request_ocr(batch_id: str, background_tasks: BackgroundTasks, replace_question: bool = False) -> OcrRunResponse:
    with SessionLocal.begin() as session:
        batch = session.get(UploadBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这组错题。")
        run = session.get(OcrRun, batch_id)
        if run is None:
            run = OcrRun(batch_id=batch_id)
            session.add(run)
        batch.status = "queued"
        run.status = "queued"
        run.error_message = ""
        run.text = ""
        run.raw_result = ""
        run.started_at = None
        run.completed_at = None

    background_tasks.add_task(run_ocr, batch_id, replace_question)
    return to_ocr_response(run)


@app.put("/api/mistakes/{batch_id}/questions/{question_id}", response_model=MistakeQuestionResponse)
def update_mistake_question(batch_id: str, question_id: str, payload: QuestionUpdateRequest) -> MistakeQuestionResponse:
    if payload.question_type not in {"单选题", "多选题", "判断题", "填空题", "计算题", "证明题", "综合题", "简答题", "其他"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="题型不正确。")
    if payload.status not in {"draft", "confirmed"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="确认状态不正确。")
    if not payload.stem.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请补充题干后再保存。")
    if not 1 <= payload.difficulty <= 5:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="难度应在 1 到 5 星之间。")
    if len(payload.options) > 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="选项不能超过 8 个。")

    normalized_options: list[dict[str, str]] = []
    for option in payload.options:
        label = option.label.strip()[:8]
        text = option.text.strip()[:4000]
        if not label or not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="每个选项都需要编号和内容。")
        normalized_options.append({"label": label, "text": text})

    with SessionLocal.begin() as session:
        question = session.get(MistakeQuestion, question_id)
        if question is None or question.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这道题。")
        question.question_type = payload.question_type
        question.stem = payload.stem.strip()[:12000]
        question.options = json.dumps(normalized_options, ensure_ascii=False)
        question.correct_answer = payload.correct_answer.strip()[:128]
        question.explanation = payload.explanation.strip()[:12000]
        question.knowledge_points = payload.knowledge_points.strip()[:1000]
        question.difficulty = payload.difficulty
        question.error_type = payload.error_type.strip()[:32]
        save_question_parts(session, question, payload.parts)
        question.status = payload.status
        question.updated_at = datetime.now(timezone.utc)
        batch = session.get(UploadBatch, batch_id)
        if batch is not None:
            session.flush()
            question_statuses = session.scalars(
                select(MistakeQuestion.status).where(MistakeQuestion.batch_id == batch_id)
            ).all()
            batch.status = "confirmed" if question_statuses and all(value == "confirmed" for value in question_statuses) else "review_ready"

    with SessionLocal() as session:
        saved_question = session.get(MistakeQuestion, question_id)
        if saved_question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这道题。")
        return to_question_response(saved_question)


@app.post("/api/mistakes/{batch_id}/questions/{question_id}/structure-suggestion", response_model=StructureSuggestionResponse)
def suggest_question_structure(batch_id: str, question_id: str, payload: StructureSuggestionRequest) -> StructureSuggestionResponse:
    with SessionLocal() as session:
        question = session.get(MistakeQuestion, question_id)
        if question is None or question.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这道题。")
    if not payload.stem.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请先补充题干，再识别小问。")
    suggestion = build_structure_suggestion(payload.stem.strip()[:12000])
    if not suggestion.parts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="没有识别到 (1)、(2) 等小问编号，可以手动添加小问。")
    return suggestion


@app.post("/api/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    background_tasks: BackgroundTasks,
    subject: str = Form(..., min_length=1, max_length=32),
    source: str = Form(..., min_length=1, max_length=32),
    note: str = Form("", max_length=2000),
    crop_regions: str = Form("[]"),
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请至少上传一个文件。")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"一次最多上传 {MAX_FILES_PER_BATCH} 个文件。")
    parsed_crop_regions = parse_crop_regions(crop_regions, len(files))

    batch_id = str(uuid4())
    batch_directory = storage_root / "uploads" / batch_id
    batch_directory.mkdir(parents=True, exist_ok=False)
    file_records: list[UploadedFile] = []
    region_records: list[OcrRegion] = []

    try:
        for file_index, uploaded in enumerate(files):
            original_name = uploaded.filename or "untitled"
            extension = Path(original_name).suffix.lower()
            content_type = uploaded.content_type or "application/octet-stream"
            content_type_is_unknown = content_type == "application/octet-stream"
            if extension not in ALLOWED_EXTENSIONS or (content_type not in ALLOWED_CONTENT_TYPES and not content_type_is_unknown):
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"不支持文件：{original_name}")

            stored_name = f"{uuid4()}{extension}"
            destination = batch_directory / stored_name
            size = 0
            with destination.open("wb") as target:
                while chunk := await uploaded.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"文件超过 20 MB：{original_name}")
                    target.write(chunk)
            await uploaded.close()
            file_record = UploadedFile(
                id=str(uuid4()),
                original_name=original_name[:255],
                stored_name=stored_name,
                content_type=content_type,
                size=size,
            )
            file_records.append(file_record)
            region = parsed_crop_regions[file_index]
            if region is not None:
                region_records.append(
                    OcrRegion(
                        file_id=file_record.id,
                        x=region[0],
                        y=region[1],
                        width=region[2],
                        height=region[3],
                    )
                )

        with SessionLocal.begin() as session:
            batch = UploadBatch(
                id=batch_id,
                subject=subject.strip(),
                source=source.strip(),
                note=note.strip(),
                status="queued",
                files=file_records,
            )
            session.add(batch)
            session.flush()
            session.add(OcrRun(batch_id=batch_id))
            session.add_all(region_records)
    except HTTPException:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件保存失败，请稍后重试。") from error

    background_tasks.add_task(run_ocr, batch_id)
    return UploadResponse(id=batch_id, status="queued", file_count=len(file_records))
