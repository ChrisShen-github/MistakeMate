from __future__ import annotations

import os
import shutil
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
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


@app.post("/api/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
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
    except HTTPException:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件保存失败，请稍后重试。") from error

    return UploadResponse(id=batch_id, status="queued", file_count=len(file_records))
