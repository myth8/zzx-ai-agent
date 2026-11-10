#!/usr/bin/env bash
# 配置双推远端：拉取与主推送指向 GitHub，Gitee 作为第二个推送目标。
# 适用于 macOS / Linux，以及 Windows 上的 Git Bash。
#
# 用法（在仓库根目录）：
#   bash scripts/setup-remotes.sh
#
# 可重复执行，每次都会先清掉旧配置再重建。
#
# 完整教程（前置的 SSH 密钥、自检标准、常见问题）见 scripts/README.md

set -e

GH="git@github.com:myth8/zzx-ai-agent.git"
GITEE="git@gitee.com:crzzx/zzx-ai-agent.git"

# 1. 清掉历史残留（首次在新设备执行时这些远端并不存在，失败属正常）
git remote remove github 2>/dev/null || true
git remote remove gitee  2>/dev/null || true
git config --unset-all remote.origin.pushurl 2>/dev/null || true

# 2. origin 的拉取与主推送都指向 GitHub
git remote set-url origin "$GH"

# 3. 追加 Gitee 作为第二个推送目标
#    顺序很关键：GitHub 在前，被拒时 Gitee 还没动，不会造成两库分叉
git remote set-url --add --push origin "$GH"
git remote set-url --add --push origin "$GITEE"

# 4. 对齐分支跟踪
git fetch origin --prune
git branch -u origin/develop develop

# 5. 自检：应看到 1 个 fetch + 2 个 push，且两次推送都 up-to-date
echo "--- 远端配置 ---"
git remote -v
echo "--- 推送预演 ---"
git push --dry-run
