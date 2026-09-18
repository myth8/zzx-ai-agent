"""公共输入边界和校验函数。数据库字段长度不能替代入口校验。"""
import re
import unicodedata


USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
NICKNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
INVITE_CODE_MAX_LENGTH = 256
SESSION_TITLE_MAX_LENGTH = 100
CHAT_MESSAGE_MAX_LENGTH = 4000
DOCUMENT_METADATA_MAX_FIELDS = 32
DOCUMENT_METADATA_MAX_KEY_LENGTH = 64
DOCUMENT_METADATA_MAX_VALUE_LENGTH = 1000
DOCUMENT_METADATA_MAX_ITEMS = 128
DOCUMENT_METADATA_MAX_DEPTH = 4
DOCUMENT_FRONT_MATTER_MAX_CHARS = 16 * 1024

ALLOWED_CHAT_TYPES = frozenset({"chain", "agent"})
ALLOWED_MARKDOWN_MIME_TYPES = frozenset({
    "text/markdown",
    "text/x-markdown",
    "text/plain",
    # 部分浏览器或系统无法识别 .md，会使用通用二进制类型；后续仍会执行
    # 扩展名、大小、UTF-8 和 Markdown 内容校验。
    "application/octet-stream",
})

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-\u4e00-\u9fff]+$")
_FORBIDDEN_SINGLE_LINE = re.compile(r"[\x00-\x1f\x7f]")
_FORBIDDEN_MULTILINE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputValidationError(ValueError):
    def __init__(self, code, message, field=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {"field": field} if field else None


def _string(value, field, *, strip=True):
    if not isinstance(value, str):
        raise InputValidationError("VALIDATION_ERROR", f"{field}格式无效", field)
    return value.strip() if strip else value


def validate_username(value):
    value = unicodedata.normalize("NFKC", _string(value, "username"))
    if not USERNAME_MIN_LENGTH <= len(value) <= USERNAME_MAX_LENGTH:
        raise InputValidationError(
            "USERNAME_LENGTH_INVALID",
            f"账号长度必须为 {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} 个字符",
            "username",
        )
    if not _USERNAME_PATTERN.fullmatch(value):
        raise InputValidationError(
            "USERNAME_FORMAT_INVALID",
            "账号只能包含中英文、数字、点、横线和下划线",
            "username",
        )
    return value


def validate_nickname(value):
    value = unicodedata.normalize("NFC", _string(value, "nickname"))
    if not value or len(value) > NICKNAME_MAX_LENGTH:
        raise InputValidationError(
            "NICKNAME_LENGTH_INVALID",
            f"昵称长度必须为 1-{NICKNAME_MAX_LENGTH} 个字符",
            "nickname",
        )
    if _FORBIDDEN_SINGLE_LINE.search(value):
        raise InputValidationError(
            "NICKNAME_FORMAT_INVALID", "昵称不能包含控制字符", "nickname"
        )
    return value


def validate_password(value, *, registration=False):
    # 密码不能 strip，否则用户输入的首尾空格会被静默改成另一份密码。
    value = _string(value, "password", strip=False)
    minimum = PASSWORD_MIN_LENGTH if registration else 1
    if not minimum <= len(value) <= PASSWORD_MAX_LENGTH:
        message = (
            f"密码长度必须为 {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 个字符"
            if registration else "账号或密码格式无效"
        )
        raise InputValidationError("PASSWORD_LENGTH_INVALID", message, "password")
    if "\x00" in value:
        raise InputValidationError(
            "PASSWORD_FORMAT_INVALID", "密码不能包含空字符", "password"
        )
    return value


def validate_invite_code(value, *, required=False):
    value = _string(value or "", "invite_code")
    if required and not value:
        raise InputValidationError(
            "AUTH_INVITE_REQUIRED", "请输入管理员邀请码", "invite_code"
        )
    if len(value) > INVITE_CODE_MAX_LENGTH or _FORBIDDEN_SINGLE_LINE.search(value):
        raise InputValidationError(
            "INVITE_CODE_INVALID", "管理员邀请码格式无效", "invite_code"
        )
    return value


def validate_session_title(value, *, default=None):
    if value is None and default is not None:
        return default
    value = unicodedata.normalize("NFC", _string(value, "title"))
    if not value or len(value) > SESSION_TITLE_MAX_LENGTH:
        raise InputValidationError(
            "SESSION_TITLE_LENGTH_INVALID",
            f"会话标题长度必须为 1-{SESSION_TITLE_MAX_LENGTH} 个字符",
            "title",
        )
    if _FORBIDDEN_SINGLE_LINE.search(value):
        raise InputValidationError(
            "SESSION_TITLE_FORMAT_INVALID", "会话标题不能包含控制字符", "title"
        )
    return value


def validate_chat_type(value):
    value = _string(value, "chat_type").lower()
    if value not in ALLOWED_CHAT_TYPES:
        raise InputValidationError(
            "CHAT_TYPE_INVALID", "会话类型无效", "chat_type"
        )
    return value


def validate_chat_message(value):
    value = _string(value, "message")
    if not value or len(value) > CHAT_MESSAGE_MAX_LENGTH:
        raise InputValidationError(
            "CHAT_MESSAGE_LENGTH_INVALID",
            f"聊天内容长度必须为 1-{CHAT_MESSAGE_MAX_LENGTH} 个字符",
            "message",
        )
    if _FORBIDDEN_MULTILINE.search(value):
        raise InputValidationError(
            "CHAT_MESSAGE_FORMAT_INVALID", "聊天内容包含不允许的控制字符", "message"
        )
    return value


def validate_markdown_mime_type(value):
    mime_type = str(value or "").split(";", 1)[0].strip().lower()
    if mime_type not in ALLOWED_MARKDOWN_MIME_TYPES:
        raise InputValidationError(
            "RAG_FILE_MIME_INVALID",
            "文件 MIME 类型无效，仅支持 Markdown 文本文件",
            "file",
        )
    return mime_type


def validate_document_metadata(metadata):
    """限制 Front Matter 的规模、层级、键和值，避免异常结构进入索引。"""
    if not isinstance(metadata, dict):
        raise InputValidationError(
            "RAG_METADATA_INVALID", "Markdown Front Matter 必须是键值对象", "metadata"
        )
    if len(metadata) > DOCUMENT_METADATA_MAX_FIELDS:
        raise InputValidationError(
            "RAG_METADATA_TOO_LARGE",
            f"文档元数据字段不能超过 {DOCUMENT_METADATA_MAX_FIELDS} 个",
            "metadata",
        )

    item_count = 0

    def visit(value, depth):
        nonlocal item_count
        item_count += 1
        if item_count > DOCUMENT_METADATA_MAX_ITEMS:
            raise InputValidationError(
                "RAG_METADATA_TOO_LARGE", "文档元数据项目过多", "metadata"
            )
        if depth > DOCUMENT_METADATA_MAX_DEPTH:
            raise InputValidationError(
                "RAG_METADATA_TOO_DEEP", "文档元数据嵌套层级过深", "metadata"
            )
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                if not key_text or len(key_text) > DOCUMENT_METADATA_MAX_KEY_LENGTH:
                    raise InputValidationError(
                        "RAG_METADATA_KEY_INVALID", "文档元数据字段名过长或为空", "metadata"
                    )
                if _FORBIDDEN_SINGLE_LINE.search(key_text):
                    raise InputValidationError(
                        "RAG_METADATA_KEY_INVALID", "文档元数据字段名包含控制字符", "metadata"
                    )
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, depth + 1)
        else:
            scalar = str(value if value is not None else "")
            if len(scalar) > DOCUMENT_METADATA_MAX_VALUE_LENGTH:
                raise InputValidationError(
                    "RAG_METADATA_VALUE_TOO_LONG", "文档元数据值过长", "metadata"
                )
            if _FORBIDDEN_MULTILINE.search(scalar):
                raise InputValidationError(
                    "RAG_METADATA_VALUE_INVALID",
                    "文档元数据值包含不允许的控制字符",
                    "metadata",
                )

    visit(metadata, 0)
    return metadata
