from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import shutil
import json
import math
import re
import tarfile
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from cryptography.fernet import Fernet, InvalidToken
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, inspect, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_FILES_PER_BATCH = 12
CHUNK_SIZE = 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".pdf"}
SESSION_COOKIE = "mistakemate_session"
SESSION_DAYS = 30
OCR_MODEL_BASE_URL = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
OCR_MODEL_PACKAGES = (
    ("PP-LCNet_x1_0_doc_ori", "文档方向校正"),
    ("UVDoc", "文档去扭曲"),
    ("PP-LCNet_x1_0_textline_ori", "文本行方向识别"),
    ("PP-OCRv6_medium_det", "文本检测"),
    ("PP-OCRv6_medium_rec", "中文文本识别"),
)

storage_root = Path(os.getenv("STORAGE_ROOT", "storage")).resolve()
ocr_model_root = Path(os.getenv("PADDLE_MODEL_HOME", str(Path.home() / ".paddlex"))).resolve()
ocr_official_models_root = ocr_model_root / "official_models"
database_url = os.getenv("DATABASE_URL", "sqlite:///storage/mistakemate.db")
engine_options: dict[str, object] = {"pool_pre_ping": True}
if database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AppSecurity(Base):
    __tablename__ = "app_security"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_secret: Mapped[str] = mapped_column(String(128))
    ai_config_secret: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
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
    ai_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    ai_text: Mapped[str] = mapped_column(Text, default="")
    ai_error_message: Mapped[str] = mapped_column(Text, default="")
    ai_model: Mapped[str] = mapped_column(String(128), default="")
    ai_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    settings: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AiProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(512), default="https://api.openai.com/v1")
    model: Mapped[str] = mapped_column(String(128), default="")
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UploadResponse(BaseModel):
    id: str
    status: str
    file_count: int
    batch_ids: list[str]


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
    ai_status: str
    ai_text: str
    ai_error_message: str
    ai_model: str
    ai_started_at: datetime | None
    ai_completed_at: datetime | None


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeResponse(BaseModel):
    status: str
    message: str


class AuthBootstrapResponse(BaseModel):
    has_users: bool


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AiConfigUpdateRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=512)
    model: str = Field(min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=512)
    clear_api_key: bool = False


class AiConfigResponse(BaseModel):
    base_url: str
    model: str
    api_key_configured: bool
    updated_at: datetime | None


class AiConnectionResponse(BaseModel):
    status: str
    message: str


class AiModelListRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=512)
    api_key: str = Field(default="", max_length=512)


class AiModelListResponse(BaseModel):
    models: list[str]


class OcrModelItemResponse(BaseModel):
    id: str
    name: str
    installed: bool
    size_bytes: int


class OcrModelStatusResponse(BaseModel):
    status: str
    message: str
    source: str
    current_model: str
    current_model_name: str
    completed_models: int
    total_models: int
    downloaded_bytes: int
    total_bytes: int | None
    speed_bytes_per_second: float
    models: list[OcrModelItemResponse]


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
ocr_model_download_lock = Lock()
ocr_model_download_cancel = Event()
ocr_model_download_state: dict[str, Any] = {
    "status": "not_installed",
    "message": "本地 OCR 模型尚未下载。",
    "current_model": "",
    "current_model_name": "",
    "completed_models": 0,
    "downloaded_bytes": 0,
    "total_bytes": None,
    "speed_bytes_per_second": 0.0,
}
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
        ai_status=run.ai_status,
        ai_text=run.ai_text,
        ai_error_message=run.ai_error_message,
        ai_model=run.ai_model,
        ai_started_at=run.ai_started_at,
        ai_completed_at=run.ai_completed_at,
    )


def to_user_response(user: AppUser) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, display_name=user.display_name)


def ensure_security_row(session: Any) -> AppSecurity:
    security = session.get(AppSecurity, 1)
    if security is None:
        security = AppSecurity(
            id=1,
            auth_secret=secrets.token_urlsafe(48),
            ai_config_secret=secrets.token_urlsafe(48),
        )
        session.add(security)
        session.flush()
    return security


def get_security_secret(field_name: str) -> str:
    with SessionLocal.begin() as session:
        security = ensure_security_row(session)
        return str(getattr(security, field_name))


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,64}", username):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名需为 3–64 位，可使用字母、数字、点、横线或下划线。",
        )
    return username


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, rounds, salt_value, digest_value = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_value)
        expected = base64.urlsafe_b64decode(digest_value)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session_token(user_id: str) -> str:
    expires_at = int(time.time()) + SESSION_DAYS * 24 * 60 * 60
    payload = base64.urlsafe_b64encode(f"{user_id}:{expires_at}".encode()).decode().rstrip("=")
    signature = hmac.new(get_security_secret("auth_secret").encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def parse_session_token(token: str) -> str | None:
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(get_security_secret("auth_secret").encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
        user_id, expires_at = decoded.rsplit(":", 1)
        return user_id if int(expires_at) >= int(time.time()) else None
    except (ValueError, UnicodeDecodeError):
        return None


def require_user(request: Request) -> AppUser:
    user_id = parse_session_token(request.cookies.get(SESSION_COOKIE, ""))
    if user_id:
        with SessionLocal() as session:
            user = session.get(AppUser, user_id)
            if user is not None:
                session.expunge(user)
                return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")


def set_session_cookie(response: Response, user_id: str, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id),
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def get_owned_batch(session: Any, batch_id: str, user_id: str) -> UploadBatch:
    batch = session.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id, UploadBatch.owner_id == user_id)
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这组错题。")
    return batch


def get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_security_secret("ai_config_secret").encode()).digest())
    return Fernet(key)


def fernet_from_secret(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt_api_key(api_key: str) -> str:
    return get_fernet().encrypt(api_key.encode()).decode() if api_key else ""


def decrypt_api_key(encrypted_api_key: str) -> str:
    try:
        return get_fernet().decrypt(encrypted_api_key.encode()).decode() if encrypted_api_key else ""
    except InvalidToken as error:
        # One release used this value before internal keys were stored in PostgreSQL.
        # Keep this small compatibility path so an existing configured key keeps working.
        try:
            return fernet_from_secret("mistakemate-local-ai-change-me").decrypt(encrypted_api_key.encode()).decode()
        except InvalidToken:
            raise RuntimeError("AI 密钥无法解密，请在设置页重新保存。") from error


def normalize_ai_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="接口地址需以 http:// 或 https:// 开头。")
    return base_url


def fetch_ai_models(base_url: str, api_key: str) -> list[str]:
    if not api_key:
        raise RuntimeError("请先输入 API 密钥，或先保存已有密钥。")
    request = UrlRequest(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"读取模型列表失败（{error.code}）：{detail or '请检查接口地址和密钥。'}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"无法连接 AI 服务：{error}") from error
    items = payload.get("data", []) if isinstance(payload, dict) else []
    models = sorted({str(item.get("id", "")).strip() for item in items if isinstance(item, dict) and item.get("id")})
    if not models:
        raise RuntimeError("服务没有返回可选模型。请检查接口是否兼容 OpenAI 的 /models 接口，或改用手动填写模型 ID。")
    return models


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


def ocr_model_directory(model_id: str) -> Path:
    return ocr_official_models_root / model_id


def is_ocr_model_installed(model_id: str) -> bool:
    model_dir = ocr_model_directory(model_id)
    return model_dir.is_dir() and (model_dir / "inference.yml").is_file()


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def ocr_models_ready() -> bool:
    return all(is_ocr_model_installed(model_id) for model_id, _ in OCR_MODEL_PACKAGES)


def update_ocr_download_state(**values: Any) -> None:
    with ocr_model_download_lock:
        ocr_model_download_state.update(values)


def get_ocr_model_status() -> OcrModelStatusResponse:
    models = [
        OcrModelItemResponse(
            id=model_id,
            name=model_name,
            installed=is_ocr_model_installed(model_id),
            size_bytes=directory_size(ocr_model_directory(model_id)),
        )
        for model_id, model_name in OCR_MODEL_PACKAGES
    ]
    with ocr_model_download_lock:
        state = dict(ocr_model_download_state)
    completed_models = sum(model.installed for model in models)
    if completed_models == len(models):
        status = "ready"
        message = "本地 OCR 模型已就绪。"
    else:
        status = state["status"]
        message = state["message"]
        if status == "ready":
            status = "not_installed"
    return OcrModelStatusResponse(
        status=status,
        message=message,
        source="百度 BOS（官方国内源）",
        current_model=state["current_model"],
        current_model_name=state["current_model_name"],
        completed_models=completed_models,
        total_models=len(models),
        downloaded_bytes=int(state["downloaded_bytes"]),
        total_bytes=state["total_bytes"],
        speed_bytes_per_second=float(state["speed_bytes_per_second"]),
        models=models,
    )


def safe_extract_model_archive(archive_path: Path, model_id: str) -> None:
    staging_root = ocr_model_root / ".mistakemate-model-download" / f"{model_id}-{uuid4().hex}"
    staging_root.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or member.issym() or member.islnk():
                    raise RuntimeError("模型压缩包包含不安全的文件路径。")
            archive.extractall(staging_root)
        entries = [entry for entry in staging_root.iterdir()]
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging_root
        if not (source / "inference.yml").is_file():
            raise RuntimeError("模型文件不完整，未找到 inference.yml。")
        target = ocr_model_directory(model_id)
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def download_ocr_model_archive(model_id: str, model_name: str, completed_models: int) -> None:
    download_root = ocr_model_root / ".mistakemate-model-download"
    download_root.mkdir(parents=True, exist_ok=True)
    archive_path = download_root / f"{model_id}.tar.part"
    url = f"{OCR_MODEL_BASE_URL}/{model_id}_infer.tar"
    existing_size = archive_path.stat().st_size if archive_path.exists() else 0
    request = UrlRequest(url, headers={"Range": f"bytes={existing_size}-"} if existing_size else {})
    started_at = time.monotonic()
    try:
        with urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            resumed = getattr(response, "status", response.getcode()) == 206 and existing_size > 0
            if not resumed:
                existing_size = 0
            total_bytes = existing_size + int(content_length) if content_length and content_length.isdigit() else None
            update_ocr_download_state(
                status="downloading",
                message=f"正在下载：{model_name}",
                current_model=model_id,
                current_model_name=model_name,
                completed_models=completed_models,
                downloaded_bytes=existing_size,
                total_bytes=total_bytes,
                speed_bytes_per_second=0.0,
            )
            with archive_path.open("ab" if resumed else "wb") as output:
                downloaded_bytes = existing_size
                while chunk := response.read(256 * 1024):
                    if ocr_model_download_cancel.is_set():
                        raise InterruptedError("已取消下载。下次下载会从当前进度继续。")
                    output.write(chunk)
                    downloaded_bytes += len(chunk)
                    elapsed = max(time.monotonic() - started_at, 0.1)
                    update_ocr_download_state(
                        downloaded_bytes=downloaded_bytes,
                        total_bytes=total_bytes,
                        speed_bytes_per_second=max(0.0, (downloaded_bytes - existing_size) / elapsed),
                    )
    except HTTPError as error:
        raise RuntimeError(f"下载 {model_name} 失败（{error.code}）。请检查网络后重试。") from error
    except URLError as error:
        raise RuntimeError(f"无法连接官方模型源：{error.reason}") from error
    update_ocr_download_state(status="extracting", message=f"正在校验并安装：{model_name}", speed_bytes_per_second=0.0)
    safe_extract_model_archive(archive_path, model_id)
    archive_path.unlink(missing_ok=True)


def download_ocr_models() -> None:
    global ocr_model
    try:
        ocr_model_download_cancel.clear()
        for index, (model_id, model_name) in enumerate(OCR_MODEL_PACKAGES):
            if ocr_model_download_cancel.is_set():
                raise InterruptedError("已取消下载。下次下载会从当前进度继续。")
            if is_ocr_model_installed(model_id):
                continue
            download_ocr_model_archive(model_id, model_name, index)
        ocr_model = None
        update_ocr_download_state(
            status="ready", message="本地 OCR 模型已下载完成，可以开始识别。", current_model="", current_model_name="",
            completed_models=len(OCR_MODEL_PACKAGES), downloaded_bytes=0, total_bytes=None, speed_bytes_per_second=0.0,
        )
    except InterruptedError as error:
        update_ocr_download_state(status="cancelled", message=str(error), speed_bytes_per_second=0.0)
    except Exception as error:
        update_ocr_download_state(status="failed", message=str(error)[:500], speed_bytes_per_second=0.0)


def get_ocr_model() -> Any:
    if not ocr_models_ready():
        raise RuntimeError("本地 OCR 模型尚未下载，请先在“OCR 模型”页面完成下载。")
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


def split_upload_batch_by_file(batch_id: str, user_id: str) -> list[str]:
    """Turn a legacy multi-file upload into one independent batch per file.

    Older MistakeMate versions combined all selected files into one OCR result.
    The files keep their IDs (and any selected crop regions) while being moved
    into new one-file batches, then OCR is run again for each individual image.
    """
    with SessionLocal() as session:
        batch = session.get(UploadBatch, batch_id)
        if batch is None or batch.owner_id != user_id:
            raise ValueError("未找到需要拆分的上传批次。")
        files = list(batch.files)
        if len(files) < 2:
            raise ValueError("这个上传批次只有一个文件，无需拆分。")
        if any(question.status == "confirmed" for question in batch.questions):
            raise ValueError("这组题目已有已确认内容，不能自动拆分。")
        batch_values = {
            "subject": batch.subject,
            "source": batch.source,
            "note": batch.note,
            "created_at": batch.created_at,
        }
        file_values = [(file.id, file.stored_name) for file in files]

    legacy_directory = storage_root / "uploads" / batch_id
    if not legacy_directory.is_dir():
        raise ValueError("原始文件目录不存在，无法拆分。")

    new_batch_ids = [str(uuid4()) for _ in file_values]
    moved_files: list[tuple[Path, Path]] = []
    try:
        for (_, stored_name), new_batch_id in zip(file_values, new_batch_ids, strict=True):
            source_path = legacy_directory / stored_name
            destination_directory = storage_root / "uploads" / new_batch_id
            destination_path = destination_directory / stored_name
            if not source_path.is_file():
                raise ValueError(f"缺少原始文件：{stored_name}")
            destination_directory.mkdir(parents=True, exist_ok=False)
            shutil.move(str(source_path), str(destination_path))
            moved_files.append((source_path, destination_path))

        with SessionLocal.begin() as session:
            legacy_batch = session.get(UploadBatch, batch_id)
            if legacy_batch is None or legacy_batch.owner_id != user_id:
                raise ValueError("上传批次已变化，请刷新后重试。")
            files_by_id = {file.id: file for file in legacy_batch.files}
            for (file_id, _), new_batch_id in zip(file_values, new_batch_ids, strict=True):
                file = files_by_id.get(file_id)
                if file is None:
                    raise ValueError("上传文件已变化，请刷新后重试。")
                new_batch = UploadBatch(
                    id=new_batch_id,
                    owner_id=user_id,
                    subject=batch_values["subject"],
                    source=batch_values["source"],
                    note=batch_values["note"],
                    status="queued",
                    created_at=batch_values["created_at"],
                    files=[file],
                )
                session.add(new_batch)
            session.flush()
            for new_batch_id in new_batch_ids:
                session.add(OcrRun(batch_id=new_batch_id))
            legacy_run = session.get(OcrRun, batch_id)
            if legacy_run is not None:
                session.delete(legacy_run)
            session.delete(legacy_batch)
        legacy_directory.rmdir()
    except Exception:
        for source_path, destination_path in reversed(moved_files):
            if destination_path.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination_path), str(source_path))
            try:
                destination_path.parent.rmdir()
            except OSError:
                pass
        raise

    return new_batch_ids


def call_ai_chat(config: AiProviderConfig, messages: list[dict[str, Any]], max_tokens: int = 5000) -> str:
    api_key = decrypt_api_key(config.encrypted_api_key)
    if not api_key:
        raise RuntimeError("尚未配置 AI API 密钥。")
    request_body = json.dumps(
        {"model": config.model, "messages": messages, "temperature": 0.1, "max_tokens": max_tokens},
        ensure_ascii=False,
    ).encode("utf-8")
    request = UrlRequest(
        f"{config.base_url.rstrip('/')}/chat/completions",
        data=request_body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"AI 服务返回 {error.code}：{detail}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"无法连接 AI 服务：{error}") from error
    try:
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        content = str(content).strip()
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("AI 服务返回格式不兼容 OpenAI Chat Completions。") from error
    if not content:
        raise RuntimeError("AI 没有返回可用文字。")
    return content


def build_ai_ocr_messages(batch_id: str, local_ocr_text: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "请复核这些试题图片，并结合下面的本地 OCR 初稿，输出完整、可编辑的题面文字。"
                "补全漏字，修正明显错字，保留题号、选项、小问、公式与换行。不要解题，不要添加答案，"
                "不要解释；看不清的内容标记为［无法确认］。\n\n本地 OCR 初稿：\n" + local_ocr_text[:16000]
            ),
        }
    ]
    with SessionLocal() as session:
        batch = session.get(UploadBatch, batch_id)
        files = [] if batch is None else list(batch.files)
        regions = {
            file.id: session.get(OcrRegion, file.id)
            for file in files
        }
    with tempfile.TemporaryDirectory(prefix="mistakemate-ai-ocr-") as temporary_path:
        temporary_directory = Path(temporary_path)
        image_count = 0
        for file in files:
            region = regions[file.id]
            crop_region = (region.x, region.y, region.width, region.height) if region else None
            source = storage_root / "uploads" / batch_id / file.stored_name
            for input_path in prepare_ocr_inputs(source, file.original_name, temporary_directory, crop_region):
                if image_count >= 8:
                    break
                from PIL import Image, ImageOps

                compressed_path = temporary_directory / f"ai-{image_count + 1}.jpg"
                with Image.open(input_path) as image:
                    prepared = ImageOps.exif_transpose(image).convert("RGB")
                    prepared.thumbnail((2600, 2600), Image.Resampling.LANCZOS)
                    prepared.save(compressed_path, "JPEG", quality=88, optimize=True)
                encoded = base64.b64encode(compressed_path.read_bytes()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"}})
                image_count += 1
            if image_count >= 8:
                break
    if image_count == 0:
        raise RuntimeError("没有可发送给 AI 的题目图片。")
    return [
        {"role": "system", "content": "你是谨慎的中文试题 OCR 复核助手，只按图片内容转写。"},
        {"role": "user", "content": content},
    ]


def run_ai_ocr_assist(batch_id: str, user_id: str) -> None:
    with SessionLocal.begin() as session:
        batch = session.get(UploadBatch, batch_id)
        run = session.get(OcrRun, batch_id)
        config = session.get(AiProviderConfig, user_id)
        if batch is None or batch.owner_id != user_id or run is None or config is None:
            return
        run.ai_status = "running"
        run.ai_error_message = ""
        run.ai_text = ""
        run.ai_model = config.model
        run.ai_started_at = datetime.now(timezone.utc)
        run.ai_completed_at = None
        local_ocr_text = run.text
        session.expunge(config)
    try:
        ai_text = call_ai_chat(config, build_ai_ocr_messages(batch_id, local_ocr_text))
        with SessionLocal.begin() as session:
            run = session.get(OcrRun, batch_id)
            if run is None:
                return
            run.ai_status = "completed"
            run.ai_text = ai_text
            run.ai_completed_at = datetime.now(timezone.utc)
    except Exception as error:
        with SessionLocal.begin() as session:
            run = session.get(OcrRun, batch_id)
            if run is None:
                return
            run.ai_status = "failed"
            run.ai_error_message = str(error)[:2000]
            run.ai_completed_at = datetime.now(timezone.utc)


def ensure_legacy_columns() -> None:
    schema = inspect(engine)
    migrations = {
        "upload_batches": [("owner_id", "VARCHAR(36)")],
        "print_templates": [("user_id", "VARCHAR(36)")],
        "ocr_runs": [
            ("ai_status", "VARCHAR(32) NOT NULL DEFAULT 'not_requested'"),
            ("ai_text", "TEXT NOT NULL DEFAULT ''"),
            ("ai_error_message", "TEXT NOT NULL DEFAULT ''"),
            ("ai_model", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("ai_started_at", "TIMESTAMP"),
            ("ai_completed_at", "TIMESTAMP"),
        ],
    }
    with engine.begin() as connection:
        for table_name, additions in migrations.items():
            existing = {column["name"] for column in schema.get_columns(table_name)}
            for column_name, definition in additions:
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_upload_batches_owner_id ON upload_batches (owner_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_print_templates_user_id ON print_templates (user_id)"))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    storage_root.mkdir(parents=True, exist_ok=True)
    for attempt in range(30):
        try:
            Base.metadata.create_all(engine)
            ensure_legacy_columns()
            break
        except OperationalError:
            if attempt == 29:
                raise
            time.sleep(1)
    with SessionLocal.begin() as session:
        ensure_security_row(session)
        completed_runs = session.execute(select(OcrRun).where(OcrRun.status == "completed")).scalars().all()
        for run in completed_runs:
            create_question_draft_if_missing(session, run.batch_id, run.text)
    yield
    engine.dispose()


app = FastAPI(title="MistakeMate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/bootstrap", response_model=AuthBootstrapResponse)
def auth_bootstrap() -> AuthBootstrapResponse:
    with SessionLocal() as session:
        return AuthBootstrapResponse(has_users=bool(session.scalar(select(func.count(AppUser.id)))))


@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest, response: Response, request: Request) -> UserResponse:
    username = normalize_username(payload.username)
    display_name = payload.display_name.strip()
    with SessionLocal.begin() as session:
        if session.scalar(select(AppUser).where(AppUser.username == username)) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="这个用户名已被使用。")
        first_user = not bool(session.scalar(select(func.count(AppUser.id))))
        user = AppUser(id=str(uuid4()), username=username, display_name=display_name, password_hash=hash_password(payload.password))
        session.add(user)
        session.flush()
        if first_user:
            session.execute(update(UploadBatch).where(UploadBatch.owner_id.is_(None)).values(owner_id=user.id))
            session.execute(update(PrintTemplate).where(PrintTemplate.user_id.is_(None)).values(user_id=user.id))
    set_session_cookie(response, user.id, request)
    return to_user_response(user)


@app.post("/api/auth/login", response_model=UserResponse)
def login_user(payload: LoginRequest, response: Response, request: Request) -> UserResponse:
    username = payload.username.strip().lower()
    with SessionLocal() as session:
        user = session.scalar(select(AppUser).where(AppUser.username == username))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码不正确。")
        session.expunge(user)
    set_session_cookie(response, user.id, request)
    return to_user_response(user)


@app.post("/api/auth/logout")
def logout_user(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@app.get("/api/auth/me", response_model=UserResponse)
def current_user(user: AppUser = Depends(require_user)) -> UserResponse:
    return to_user_response(user)


@app.put("/api/auth/profile", response_model=UserResponse)
def update_profile(payload: ProfileUpdateRequest, user: AppUser = Depends(require_user)) -> UserResponse:
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="显示名称不能为空。")
    with SessionLocal.begin() as session:
        saved_user = session.get(AppUser, user.id)
        if saved_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录。")
        saved_user.display_name = display_name
    user.display_name = display_name
    return to_user_response(user)


@app.put("/api/auth/password", response_model=PasswordChangeResponse)
def change_password(payload: PasswordChangeRequest, user: AppUser = Depends(require_user)) -> PasswordChangeResponse:
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="新密码不能与当前密码相同。")
    with SessionLocal.begin() as session:
        saved_user = session.get(AppUser, user.id)
        if saved_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录。")
        if not verify_password(payload.current_password, saved_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确。")
        saved_user.password_hash = hash_password(payload.new_password)
    return PasswordChangeResponse(status="ok", message="密码已修改，下次登录请使用新密码。")


@app.get("/api/settings/ai", response_model=AiConfigResponse)
def get_ai_config(user: AppUser = Depends(require_user)) -> AiConfigResponse:
    with SessionLocal() as session:
        config = session.get(AiProviderConfig, user.id)
        if config is None:
            return AiConfigResponse(base_url="https://api.openai.com/v1", model="", api_key_configured=False, updated_at=None)
        return AiConfigResponse(
            base_url=config.base_url,
            model=config.model,
            api_key_configured=bool(config.encrypted_api_key),
            updated_at=config.updated_at,
        )


@app.put("/api/settings/ai", response_model=AiConfigResponse)
def save_ai_config(payload: AiConfigUpdateRequest, user: AppUser = Depends(require_user)) -> AiConfigResponse:
    base_url = normalize_ai_base_url(payload.base_url)
    model = payload.model.strip()
    with SessionLocal.begin() as session:
        config = session.get(AiProviderConfig, user.id)
        if config is None:
            config = AiProviderConfig(user_id=user.id)
            session.add(config)
        config.base_url = base_url
        config.model = model
        if payload.clear_api_key:
            config.encrypted_api_key = ""
        elif payload.api_key.strip():
            config.encrypted_api_key = encrypt_api_key(payload.api_key.strip())
        config.updated_at = datetime.now(timezone.utc)
    return AiConfigResponse(
        base_url=config.base_url,
        model=config.model,
        api_key_configured=bool(config.encrypted_api_key),
        updated_at=config.updated_at,
    )


@app.post("/api/settings/ai/models", response_model=AiModelListResponse)
def list_ai_models(payload: AiModelListRequest, user: AppUser = Depends(require_user)) -> AiModelListResponse:
    base_url = normalize_ai_base_url(payload.base_url)
    api_key = payload.api_key.strip()
    if not api_key:
        with SessionLocal() as session:
            config = session.get(AiProviderConfig, user.id)
            if config is not None and config.encrypted_api_key:
                api_key = decrypt_api_key(config.encrypted_api_key)
    try:
        return AiModelListResponse(models=fetch_ai_models(base_url, api_key))
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@app.post("/api/settings/ai/test", response_model=AiConnectionResponse)
def test_ai_connection(user: AppUser = Depends(require_user)) -> AiConnectionResponse:
    with SessionLocal() as session:
        config = session.get(AiProviderConfig, user.id)
        if config is None or not config.model or not config.encrypted_api_key:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先保存完整的 AI 配置。")
        session.expunge(config)
    try:
        result = call_ai_chat(config, [{"role": "user", "content": "只回复：连接成功"}], max_tokens=20)
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    return AiConnectionResponse(status="ok", message=result[:100])


@app.get("/api/settings/ocr-models", response_model=OcrModelStatusResponse)
def get_ocr_models_status(user: AppUser = Depends(require_user)) -> OcrModelStatusResponse:
    return get_ocr_model_status()


@app.post("/api/settings/ocr-models/download", response_model=OcrModelStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def start_ocr_models_download(user: AppUser = Depends(require_user)) -> OcrModelStatusResponse:
    already_ready = False
    with ocr_model_download_lock:
        if ocr_model_download_state["status"] in {"downloading", "extracting"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OCR 模型正在下载，请稍候。")
        if ocr_models_ready():
            already_ready = True
        else:
            ocr_model_download_state.update(
                status="downloading", message="正在准备下载本地 OCR 模型。", current_model="", current_model_name="",
                completed_models=0, downloaded_bytes=0, total_bytes=None, speed_bytes_per_second=0.0,
            )
    if not already_ready:
        Thread(target=download_ocr_models, name="mistakemate-ocr-model-download", daemon=True).start()
    return get_ocr_model_status()


@app.post("/api/settings/ocr-models/cancel", response_model=OcrModelStatusResponse)
def cancel_ocr_models_download(user: AppUser = Depends(require_user)) -> OcrModelStatusResponse:
    with ocr_model_download_lock:
        if ocr_model_download_state["status"] not in {"downloading", "extracting"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有进行中的 OCR 模型下载。")
        ocr_model_download_cancel.set()
        ocr_model_download_state["message"] = "正在停止下载…"
    return get_ocr_model_status()


@app.get("/api/mistakes", response_model=list[MistakeBatchResponse])
def list_mistakes(subject: str | None = None, user: AppUser = Depends(require_user)) -> list[MistakeBatchResponse]:
    statement = (
        select(UploadBatch, func.count(UploadedFile.id).label("file_count"))
        .outerjoin(UploadedFile)
        .group_by(UploadBatch.id)
        .where(UploadBatch.owner_id == user.id)
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
def list_printable_questions(subject: str | None = None, user: AppUser = Depends(require_user)) -> list[PrintableQuestionResponse]:
    statement = (
        select(MistakeQuestion, UploadBatch)
        .join(UploadBatch, MistakeQuestion.batch_id == UploadBatch.id)
        .where(MistakeQuestion.status == "confirmed", UploadBatch.owner_id == user.id)
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
def list_print_templates(user: AppUser = Depends(require_user)) -> list[PrintTemplateResponse]:
    with SessionLocal() as session:
        templates = session.execute(
            select(PrintTemplate).where(PrintTemplate.user_id == user.id).order_by(PrintTemplate.updated_at.desc())
        ).scalars().all()
        return [to_print_template_response(template) for template in templates]


@app.post("/api/print/templates", response_model=PrintTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_print_template(payload: PrintTemplatePayload, user: AppUser = Depends(require_user)) -> PrintTemplateResponse:
    name, settings = normalize_print_template(payload)
    with SessionLocal.begin() as session:
        template = PrintTemplate(id=str(uuid4()), user_id=user.id, name=name, settings=settings)
        session.add(template)
    return to_print_template_response(template)


@app.put("/api/print/templates/{template_id}", response_model=PrintTemplateResponse)
def update_print_template(template_id: str, payload: PrintTemplatePayload, user: AppUser = Depends(require_user)) -> PrintTemplateResponse:
    name, settings = normalize_print_template(payload)
    with SessionLocal.begin() as session:
        template = session.get(PrintTemplate, template_id)
        if template is None or template.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这个打印模板。")
        template.name = name
        template.settings = settings
        template.updated_at = datetime.now(timezone.utc)
    return to_print_template_response(template)


@app.delete("/api/print/templates/{template_id}")
def delete_print_template(template_id: str, user: AppUser = Depends(require_user)) -> dict[str, str]:
    with SessionLocal.begin() as session:
        template = session.get(PrintTemplate, template_id)
        if template is None or template.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到这个打印模板。")
        session.delete(template)
    return {"status": "deleted"}


@app.get("/api/mistakes/{batch_id}", response_model=MistakeBatchDetailResponse)
def get_mistake_batch(batch_id: str, user: AppUser = Depends(require_user)) -> MistakeBatchDetailResponse:
    with SessionLocal() as session:
        batch = get_owned_batch(session, batch_id, user.id)
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
def get_uploaded_file(batch_id: str, file_id: str, user: AppUser = Depends(require_user)) -> FileResponse:
    with SessionLocal() as session:
        get_owned_batch(session, batch_id, user.id)
        file = session.get(UploadedFile, file_id)
        if file is None or file.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到原始文件。")
        path = storage_root / "uploads" / batch_id / file.stored_name

    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原始文件已不存在。")
    return FileResponse(path, media_type=file.content_type)


@app.post("/api/mistakes/{batch_id}/ocr", response_model=OcrRunResponse, status_code=status.HTTP_202_ACCEPTED)
def request_ocr(batch_id: str, background_tasks: BackgroundTasks, replace_question: bool = False, user: AppUser = Depends(require_user)) -> OcrRunResponse:
    if not ocr_models_ready():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="本地 OCR 模型尚未下载，请先在“OCR 模型”页面完成下载。")
    with SessionLocal.begin() as session:
        batch = get_owned_batch(session, batch_id, user.id)
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


@app.post("/api/mistakes/{batch_id}/ai-ocr", response_model=OcrRunResponse, status_code=status.HTTP_202_ACCEPTED)
def request_ai_ocr(batch_id: str, background_tasks: BackgroundTasks, user: AppUser = Depends(require_user)) -> OcrRunResponse:
    with SessionLocal.begin() as session:
        get_owned_batch(session, batch_id, user.id)
        run = session.get(OcrRun, batch_id)
        if run is None or run.status != "completed" or not run.text.strip():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先完成本地 OCR 识别。")
        config = session.get(AiProviderConfig, user.id)
        if config is None or not config.model or not config.encrypted_api_key:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先在 AI 设置中填写接口地址、模型和 API 密钥。")
        if run.ai_status in {"queued", "running"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI 正在复核，请稍后。")
        run.ai_status = "queued"
        run.ai_text = ""
        run.ai_error_message = ""
        run.ai_model = config.model
        run.ai_started_at = None
        run.ai_completed_at = None
    background_tasks.add_task(run_ai_ocr_assist, batch_id, user.id)
    return to_ocr_response(run)


@app.post("/api/mistakes/{batch_id}/ai-ocr/apply", response_model=MistakeBatchDetailResponse)
def apply_ai_ocr(batch_id: str, user: AppUser = Depends(require_user)) -> MistakeBatchDetailResponse:
    with SessionLocal.begin() as session:
        batch = get_owned_batch(session, batch_id, user.id)
        run = session.get(OcrRun, batch_id)
        if run is None or run.ai_status != "completed" or not run.ai_text.strip():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="还没有可采用的 AI 复核结果。")
        create_question_draft_if_missing(session, batch_id, run.ai_text, force_replace=True)
        batch.status = "review_ready"
    return get_mistake_batch(batch_id, user)


@app.put("/api/mistakes/{batch_id}/questions/{question_id}", response_model=MistakeQuestionResponse)
def update_mistake_question(batch_id: str, question_id: str, payload: QuestionUpdateRequest, user: AppUser = Depends(require_user)) -> MistakeQuestionResponse:
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
        get_owned_batch(session, batch_id, user.id)
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
def suggest_question_structure(batch_id: str, question_id: str, payload: StructureSuggestionRequest, user: AppUser = Depends(require_user)) -> StructureSuggestionResponse:
    with SessionLocal() as session:
        get_owned_batch(session, batch_id, user.id)
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
    user: AppUser = Depends(require_user),
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

    batch_ids: list[str] = []
    batch_directories: list[Path] = []
    upload_records: list[tuple[str, UploadedFile, OcrRegion | None]] = []

    try:
        for file_index, uploaded in enumerate(files):
            batch_id = str(uuid4())
            batch_directory = storage_root / "uploads" / batch_id
            batch_directory.mkdir(parents=True, exist_ok=False)
            batch_directories.append(batch_directory)
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
                batch_id=batch_id,
                original_name=original_name[:255],
                stored_name=stored_name,
                content_type=content_type,
                size=size,
            )
            region = parsed_crop_regions[file_index]
            region_record = None
            if region is not None:
                region_record = OcrRegion(
                    file_id=file_record.id,
                    x=region[0],
                    y=region[1],
                    width=region[2],
                    height=region[3],
                )
            batch_ids.append(batch_id)
            upload_records.append((batch_id, file_record, region_record))

        with SessionLocal.begin() as session:
            for batch_id, file_record, region_record in upload_records:
                batch = UploadBatch(
                    id=batch_id,
                    owner_id=user.id,
                    subject=subject.strip(),
                    source=source.strip(),
                    note=note.strip(),
                    status="queued",
                    files=[file_record],
                )
                session.add(batch)
            session.flush()
            for batch_id, _, region_record in upload_records:
                session.add(OcrRun(batch_id=batch_id))
                if region_record is not None:
                    session.add(region_record)
    except HTTPException:
        for batch_directory in batch_directories:
            shutil.rmtree(batch_directory, ignore_errors=True)
        raise
    except Exception as error:
        for batch_directory in batch_directories:
            shutil.rmtree(batch_directory, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件保存失败，请稍后重试。") from error

    for batch_id in batch_ids:
        background_tasks.add_task(run_ocr, batch_id)
    return UploadResponse(id=batch_ids[0], status="queued", file_count=len(upload_records), batch_ids=batch_ids)
