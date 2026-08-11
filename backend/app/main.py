from __future__ import annotations

import os
import shutil
import json
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, func, select
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


class MistakeBatchDetailResponse(MistakeBatchResponse):
    files: list[UploadedFileResponse]
    ocr: OcrRunResponse | None


ocr_model: Any | None = None
ocr_model_lock = Lock()


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


def prepare_ocr_inputs(source: Path, original_name: str, temporary_directory: Path) -> list[Path]:
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
        from PIL import Image

        register_heif_opener()
        target = temporary_directory / f"{source.stem}.png"
        Image.open(source).convert("RGB").save(target, "PNG")
        return [target]
    return [source]


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


def run_ocr(batch_id: str) -> None:
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
        files = [(file.id, file.original_name, file.stored_name) for file in batch.files]

    try:
        model = get_ocr_model()
        results: list[dict[str, Any]] = []
        text_lines: list[str] = []
        with tempfile.TemporaryDirectory(prefix="mistakemate-ocr-") as temporary_path:
            temporary_directory = Path(temporary_path)
            for _, original_name, stored_name in files:
                source = storage_root / "uploads" / batch_id / stored_name
                for input_path in prepare_ocr_inputs(source, original_name, temporary_directory):
                    for result in model.predict(str(input_path)):
                        payload = result_to_dict(result)
                        results.append(payload)
                        recognized = payload.get("res", payload).get("rec_texts", [])
                        text_lines.extend(str(line) for line in recognized if str(line).strip())

        with SessionLocal.begin() as session:
            batch = session.get(UploadBatch, batch_id)
            run = session.get(OcrRun, batch_id)
            if batch is None or run is None:
                return
            batch.status = "review_ready"
            run.status = "completed"
            run.text = "\n".join(text_lines)
            run.raw_result = json.dumps(results, ensure_ascii=False)
            run.completed_at = datetime.now(timezone.utc)
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
    yield
    engine.dispose()


app = FastAPI(title="MistakeMate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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


@app.get("/api/mistakes/{batch_id}", response_model=MistakeBatchDetailResponse)
def get_mistake_batch(batch_id: str) -> MistakeBatchDetailResponse:
    with SessionLocal() as session:
        batch = session.get(UploadBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这组错题。")
        files = list(batch.files)
        ocr = to_ocr_response(session.get(OcrRun, batch_id))

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
def request_ocr(batch_id: str, background_tasks: BackgroundTasks) -> OcrRunResponse:
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

    background_tasks.add_task(run_ocr, batch_id)
    return to_ocr_response(run)


@app.post("/api/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    background_tasks: BackgroundTasks,
    subject: str = Form(..., min_length=1, max_length=32),
    source: str = Form(..., min_length=1, max_length=32),
    note: str = Form("", max_length=2000),
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请至少上传一个文件。")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"一次最多上传 {MAX_FILES_PER_BATCH} 个文件。")

    batch_id = str(uuid4())
    batch_directory = storage_root / "uploads" / batch_id
    batch_directory.mkdir(parents=True, exist_ok=False)
    file_records: list[UploadedFile] = []

    try:
        for uploaded in files:
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
            file_records.append(
                UploadedFile(
                    id=str(uuid4()),
                    original_name=original_name[:255],
                    stored_name=stored_name,
                    content_type=content_type,
                    size=size,
                )
            )

        with SessionLocal.begin() as session:
            session.add(
                UploadBatch(
                    id=batch_id,
                    subject=subject.strip(),
                    source=source.strip(),
                    note=note.strip(),
                    status="queued",
                    files=file_records,
                )
            )
            session.add(OcrRun(batch_id=batch_id))
    except HTTPException:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件保存失败，请稍后重试。") from error

    background_tasks.add_task(run_ocr, batch_id)
    return UploadResponse(id=batch_id, status="queued", file_count=len(file_records))
