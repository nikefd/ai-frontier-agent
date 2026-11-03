# 数据备份与恢复

备份范围是完整 `AIF_DATA_DIR`：`ai-news/`、`auth/`、`users/`，包括收藏、实验笔记、覆盖证据、密码哈希、SQLite 对话及其 WAL。Redis 是抓取缓存，不是这些资料的主存储。

## 1. 取得一致副本

文件事务锁只在应用进程内有效，不能对正在运行的卷直接打包。先停止唯一应用进程，复制数据后立即重新启动；压缩和验证在副本上执行。操作会有短暂服务中断，应避开部署和长任务。下面在 Docker 主机执行，容器名按实际环境替换：

```bash
(
set -eu
umask 077
mkdir -p backups
mkdir backups/snapshot
container=ai-frontier-agent
# 复制失败时也重启；不要对整个 Compose down --volumes。
trap 'docker start "$container" >/dev/null' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker stop --time 30 "$container"
docker cp "$container":/data/. backups/snapshot/
docker start "$container"
trap - EXIT
)
```

确认容器恢复健康。副本放在仓库外的私有目录更合适；若使用上面的 `backups/`，已被 Git 与 Docker 上下文排除。不要在同一个 snapshot 目录反复覆盖复制，应每次新建目录。

## 2. 创建与验证

在源码目录执行（只依赖 Python 3.11+ 标准库），`--source` 指向刚才的离线副本，不能指向活动卷：

```bash
python3 -m app.backup create --offline-snapshot \
  --source backups/snapshot --archive backups/site.aif-backup.tar.gz
python3 -m app.backup verify --archive backups/site.aif-backup.tar.gz
python3 -m app.backup restore --archive backups/site.aif-backup.tar.gz \
  --destination backups/restored
```

归档包括 SHA-256/大小清单与空目录；校验 JSON 可解析、SQLite `quick_check`，SQLite 验证在另一个临时副本上进行，保留 WAL 且不改变备份字节。恢复拒绝已有目标目录、重复成员、未登记文件、路径穿越、链接与特殊文件；校验通过才创建恢复目标。摘要只输出文件计数，不输出账号或正文。SHA-256 检测损坏，不提供防恶意重签清单的数字签名。

备份为**未加密**的私有归档，创建权限 `0600`，恢复目录 `0700`、文件 `0600`。备份父目录也应 `0700`。包含认证与个人资料，不要公开上传、进入 Git、作为 CI 构建产物或放在网站静态目录。跨机器保存前使用可信的加密存储。

数据归档不包含 Compose/Coolify 环境变量或源码镜像。另行在私有备份目录保存部署配置、镜像标识和外部提供的 `AIF_SECRET_KEY`；它不在卷内时，单靠数据卷无法延续原签名会话。模型/SMTP/RSSHub 凭据也由部署配置管理，不能写入仓库。

## 3. 隔离演练

使用同一镜像，在独立目录/新卷恢复。关闭调度器、清空模型及 SMTP 配置，使用 `--network none`，不连接生产 RSSHub；通过容器内 localhost 检查 `/api/health`、公开文章、原管理员身份及各类用户资料读取。无需调用模型或重新抓取。

真实数据本来为空的类别应如实报告为空；通过合成测试单独覆盖收藏、实验、证据及 SQLite WAL 恢复。不要在生产卷植入测试记录。验收后清理演练容器和临时明文副本，保留私有归档和部署配置。

## 4. 真正恢复生产前

停止应用，先备份当前卷，恢复到新卷并完成上述检查。确认后再修改挂载并启动；不要用解压命令覆盖活动数据卷。本工具没有“覆盖生产”或“强制覆盖”选项。

同主机备份只能应对误删/坏数据，不能抵抗主机或磁盘损失。本次手动演练不等于已配置自动备份、保留周期或异地副本；这些需要另行确定存储位置和频率。

## 5. 首次演练记录（2026-11-03）

工具已通过 198 项全量测试及云端 CI。真实数据在独立目录完成备份、逐文件 SHA-256 对比、JSON/SQLite 校验和断网容器启动；身份、收藏、实验卡及对话读取验证通过。生产卷没有被恢复覆盖，演练容器与临时明文副本已清理，私有归档和独立部署配置保留在服务器。生产中没有覆盖基准记录，此类别由合成回归测试验证，不能据此声称恢复了真实基准证据。
