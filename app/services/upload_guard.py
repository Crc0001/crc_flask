"""上传图片安全校验（双端共用，不依赖 cv2/torch/PIL）。

威胁模型：客户端可控的 MIME/扩展名不可信；图像炸弹（小体积、超解压尺寸）
会造成内存耗尽。本模块在**落盘之前**完成以下校验：

1. 单文件大小上限（MAX_IMAGE_BYTES，默认 20MB）；
2. 扩展名严格白名单（png/jpg/jpeg/bmp/webp），且必须与魔数一致；
3. 从文件头解析宽高（PNG/JPEG/BMP/VP8X-WebP），像素总量超限直接拒绝；
4. 返回**服务端生成**的安全文件名（`upload_<uuid12>.<可信扩展名>`），
   与用户提供的文件名完全解耦，杜绝 `.html/.svg` 落盘到 static 目录。

注意：这里只做结构校验；业务管线仍需自行做解码验证（cv2.imdecode）。
"""
import struct
import uuid

# 与 ai_detection.py / remote_api.py 的用法保持一致：只收 OpenCV 可解码的常见格式。
# 刻意排除 gif/tiff/heic/heif/jfif：OpenCV 无法可靠解码，且扩展名越多攻击面越大。
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}

# 单文件大小上限（字节）。整个请求的上限另由 Flask MAX_CONTENT_LENGTH 控制。
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# 解码后像素总量上限（宽 x 高），约 6400 万像素，防解压炸弹。
MAX_IMAGE_PIXELS = 64_000_000

# 扩展名 -> 魔数种类
_EXT_KIND = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "bmp": "bmp",
    "webp": "webp",
}

# (前缀, 种类)；webp 需额外校验 RIFF 四字节标记
_MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"BM", "bmp"),
    (b"RIFF", "webp"),
)

_KIND_SAFE_EXT = {"png": "png", "jpeg": "jpg", "bmp": "bmp", "webp": "webp"}


def _parse_dimensions(data):
    """从文件头解析 (width, height)；解析失败或格式不支持返回 None。

    只做头部读取，不做完整解码，避免解压炸弹在解析阶段就耗尽内存。
    """
    try:
        # PNG：IHDR 固定在偏移 16-24（大端 uint32 宽/高）
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            width, height = struct.unpack(">II", data[16:24])
            return width, height

        # JPEG：扫描 SOFn 标记段
        if data.startswith(b"\xff\xd8\xff"):
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in {
                    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0x0D, 0x0E, 0xCF,
                }:
                    height, width = struct.unpack(">HH", data[i + 5:i + 9])
                    return width, height
                # 填充字节
                if marker == 0xFF:
                    i += 1
                    continue
                length = struct.unpack(">H", data[i + 2:i + 4])[0]
                if length < 2:
                    break
                i += 2 + length
            return None

        # BMP：DIB 头宽高（偏移 18-26，有符号 int32）
        if data.startswith(b"BM") and len(data) >= 26:
            width, height = struct.unpack("<ii", data[18:26])
            return width, abs(height)

        # WebP：仅 VP8X 明文写尺寸；VP8/VP8L 解析成本高，返回 None 跳过像素校验
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
            if data[12:16] == b"VP8X":
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
                return width, height
            return None
    except (IndexError, struct.error):
        return None
    return None


def validate_image_upload(filename, data):
    """校验上传图片，返回 (ok: bool, message: str, safe_filename: str|None)。

    通过后 safe_filename 为服务端生成的 `upload_<uuid12>.<安全扩展名>`，
    与原文件名彻底无关；调用方用该名字落盘。
    """
    if not data:
        return False, "图片内容为空", None

    if len(data) > MAX_IMAGE_BYTES:
        return False, f"图片文件过大（单文件上限 {MAX_IMAGE_BYTES // (1024 * 1024)}MB）", None

    original = filename or ""
    ext = original.rsplit(".", 1)[1].lower() if "." in original else ""
    expected_kind = _EXT_KIND.get(ext)
    if not expected_kind:
        return False, "不支持的图片格式（仅支持 png/jpg/jpeg/bmp/webp）", None

    matched_kind = None
    for signature, kind in _MAGIC_SIGNATURES:
        if not data.startswith(signature):
            continue
        if kind == "webp" and data[8:12] != b"WEBP":
            continue
        matched_kind = kind
        break

    if matched_kind != expected_kind:
        return False, "文件内容与扩展名不符，已拒绝（可能不是有效图片）", None

    dimensions = _parse_dimensions(data)
    if dimensions is not None:
        width, height = dimensions
        if width <= 0 or height <= 0:
            return False, "图片尺寸无效", None
        if width * height > MAX_IMAGE_PIXELS:
            return False, "图片尺寸过大，已拒绝", None

    safe_ext = _KIND_SAFE_EXT[matched_kind]
    safe_filename = f"upload_{uuid.uuid4().hex[:12]}.{safe_ext}"
    return True, "", safe_filename
