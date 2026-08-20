# -*- coding: utf-8 -*-
"""客户库每日自动备份：mysqldump -> C:\HwishAI\backups\，默认保留 30 天。

由 Windows 计划任务调用（06_install_backup_task.bat 注册，每日 02:30，pythonw 静默运行）。
手动运行：venv\Scripts\python.exe backup_db.py
环境变量覆盖（可选）：HWISHAI_BACKUP_DIR 备份目录；HWISHAI_BACKUP_DB 数据库名。
"""
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

# 定位 app 包：客户机安装在 C:\HwishAI；开发仓库里本脚本位于 deploy_client/
_SCRIPT_DIR = Path(__file__).resolve().parent
for _candidate in (_SCRIPT_DIR, _SCRIPT_DIR.parent, Path(r"C:\HwishAI")):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

BACKUP_DIR = Path(os.environ.get("HWISHAI_BACKUP_DIR") or r"C:\HwishAI\backups")
KEEP_DAYS = 30
LOG_FILE = BACKUP_DIR / "backup.log"


def find_mysqldump():
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe",
        r"C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return shutil.which("mysqldump")


def parse_db_uri():
    from app.config import Config

    uri = Config.SQLALCHEMY_DATABASE_URI
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = (parsed.path or "/").lstrip("/")
    return host, user, password, database


def log(message):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def cleanup_old():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=KEEP_DAYS)
    for item in BACKUP_DIR.glob("crc_ai_*.sql"):
        mtime = datetime.datetime.fromtimestamp(item.stat().st_mtime)
        if mtime < cutoff:
            item.unlink(missing_ok=True)
            log(f"清理过期备份: {item.name}")


def main():
    mysqldump = find_mysqldump()
    if not mysqldump:
        log("[FAIL] 未找到 mysqldump.exe（MySQL 未安装或未安装 Server 组件）")
        return 1
    try:
        host, user, password, database = parse_db_uri()
    except Exception as exc:
        log(f"[FAIL] 读取数据库配置失败: {exc}")
        return 1

    database = os.environ.get("HWISHAI_BACKUP_DB") or database

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = BACKUP_DIR / f"crc_ai_{ts}.sql"

    # 凭据经临时 defaults 文件传递（用完即删），避免 MYSQL_PWD 环境变量暴露
    cnf_path = None
    try:
        cnf_path = BACKUP_DIR / f".my_{ts}.cnf"
        with open(cnf_path, "w", encoding="utf-8") as cnf_file:
            cnf_file.write("[client]\n")
            cnf_file.write(f"user={user}\n")
            cnf_file.write(f"password={password}\n")
        os.chmod(cnf_path, 0o600)
        with open(out_path, "wb") as out_file:
            proc = subprocess.run(
                [mysqldump, f"--defaults-extra-file={cnf_path}",
                 "--single-transaction", "--routines", "--triggers",
                 "--default-character-set=utf8mb4", f"-h{host}", database],
                stdout=out_file,
                stderr=subprocess.PIPE,
            )
    finally:
        if cnf_path:
            try:
                cnf_path.unlink(missing_ok=True)
            except OSError:
                pass
    if proc.returncode != 0:
        out_path.unlink(missing_ok=True)
        log(f"[FAIL] mysqldump 失败: {proc.stderr.decode('utf-8', errors='replace')[:200]}")
        return 1

    size_kb = out_path.stat().st_size / 1024
    log(f"[OK] 备份完成: {out_path.name}（{size_kb:.0f} KB）")
    try:
        cleanup_old()
    except Exception as exc:
        log(f"[WARN] 清理过期备份失败: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
