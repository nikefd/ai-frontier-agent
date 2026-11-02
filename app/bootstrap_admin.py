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
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error("请在交互终端运行，密码将隐藏输入（Docker 使用 exec -it）")
    password = getpass.getpass("管理员密码：")
    if password != getpass.getpass("再次输入密码："):
        parser.error("两次密码不一致，未创建账号")
    # Separate CLI invocations must serialize as well as ordinary in-process writes.
    # Public signup remains closed until this first admin exists.
    import fcntl
    AUTH_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (AUTH_DIR / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            admin = create_initial_admin(args.email, password)
        except HTTPException as error:
            parser.exit(2, f"初始化失败：{error.detail}\n")
    from .migrate import migrate_legacy_to_holding, inherit_legacy_if_eligible
    migrate_legacy_to_holding()
    inherit_legacy_if_eligible(admin)
    print("管理员已创建。请在网页使用该邮箱和密码登录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
