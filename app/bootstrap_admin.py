"""Initialize the first admin locally, with no password in arguments or logs."""
from __future__ import annotations

import argparse
import getpass
import sys

from fastapi import HTTPException

from .auth import AUTH_DIR, create_initial_admin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在服务器本地创建首个管理员（已有管理员时拒绝）")
    parser.add_argument("--email", required=True, help="管理员登录邮箱")
    parser.add_argument("--language", choices=["zh", "en"], default="zh", help="Prompt language / 提示语言")
    args = parser.parse_args(argv)
    def message(zh: str, en: str) -> str:
        return en if args.language == "en" else zh
    if not sys.stdin.isatty():
        parser.error(message("请在交互终端运行，密码将隐藏输入（Docker 使用 exec -it）", "Run in an interactive terminal; password input is hidden (Docker: exec -it)"))
    password = getpass.getpass(message("管理员密码：", "Admin password: "))
    if password != getpass.getpass(message("再次输入密码：", "Confirm password: ")):
        parser.error(message("两次密码不一致，未创建账号", "Passwords do not match; no account created"))
    # Separate CLI invocations must serialize as well as ordinary in-process writes.
    # Public signup remains closed until this first admin exists.
    import fcntl
    AUTH_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (AUTH_DIR / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            admin = create_initial_admin(args.email, password)
        except HTTPException as error:
            detail = message(str(error.detail), "The email is registered or an admin already exists" if error.status_code == 409 else "Check the email address and password requirements")
            parser.exit(2, message(f"初始化失败：{detail}\n", f"Initialization failed: {detail}\n"))
    from .migrate import migrate_legacy_to_holding, inherit_legacy_if_eligible
    migrate_legacy_to_holding()
    inherit_legacy_if_eligible(admin)
    print(message("管理员已创建。请在网页使用该邮箱和密码登录。", "Admin created. Sign in on the website with this email and password."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
