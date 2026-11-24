好，补进之前的完整总结里。以下是**从 0 开始的完整版**：

## 第一步：在 GitHub 建空仓库

- 仓库名和 Gitee 保持一致
- 不勾选 "Add README" / "Add .gitignore" / "Choose a license"
- 拿到地址，如 `git@github.com:myth8/zzx-ai-agent.git`

## 第二步：本地添加 GitHub remote

```bash
git remote add github git@github.com:myth8/zzx-ai-agent.git
git remote -v    # 确认
```

## 第三步：把 Gitee 已有的分支推上 GitHub

```bash
git push github master
git push github develop
```

（首次推 master 若被 GitHub 密钥保护拦截，按提示放行后重推。）

## 第四步：给 origin 配置双 push

```bash
# 先重置 push 为 Gitee
git remote set-url --push origin git@gitee.com:crzzx/zzx-ai-agent.git
# 再追加 GitHub
git remote set-url --add --push origin git@github.com:myth8/zzx-ai-agent.git
git remote -v
```

期望结果：

```
origin  git@gitee.com:crzzx/zzx-ai-agent.git (fetch)
origin  git@gitee.com:crzzx/zzx-ai-agent.git (push)
origin  git@github.com:myth8/zzx-ai-agent.git (push)
```

## 第五步：补一个独立 gitee remote（可选，方便单向操作）

```bash
git remote add gitee git@gitee.com:crzzx/zzx-ai-agent.git
```

- 只做双推 → 不用加
- 需要"从 GitHub 拉完只推 Gitee"这类单向操作 → 加

## 第六步：设置分支 upstream 为 origin（关键）

如果分支被绑到了 `github`，push 只会推 GitHub，不会双推。确认并修正：

```bash
git branch -vv
# 若显示 [github/develop]、[github/master]，改成 origin：
git branch --set-upstream-to=origin/develop develop
git branch --set-upstream-to=origin/master master
```

期望：

```
* develop xxx [origin/develop] ...
  master  xxx [origin/master] ...
```

## 第七步：设置 GitHub 默认分支

GitHub 仓库 → Settings → Branches → Default branch 设为 `master`。

## 第八步：设置默认 pull 策略（推荐）

避免 pull 报 "Need to specify how to reconcile"：

```bash
git config pull.rebase false
```

## 日常操作

**本地开发完推送两边（最常用）：**

```bash
git add .
git commit -m "xxx"
git push                    # 双推，成功即结束

# 如果 push 被拒（non-fast-forward），说明远程有你本地没有的提交：
git pull                    # 或 git pull --no-rebase origin develop
# 解决冲突（如果有）
git push                    # 再推
```

**只有你一个人推、网页没改过** → 直接 `git push` 基本不出问题。
**多人协作或网页可能改过** → 保险起见先 pull 再 push。

## 跨平台 merge 后同步

**Gitee merge → GitHub：**

```bash
git checkout 分支
git pull origin 分支
git push github 分支
```

**GitHub merge → Gitee：**

```bash
git checkout 分支
git pull github 分支
git push gitee 分支     # 需先加 gitee remote
```

## 速查表

| 场景 | 命令 |
|------|------|
| 本地开发完推送两边 | `git add . && git commit -m "..." && git push` |
| push 被拒后补救 | `git pull && git push` |
| Gitee merge → GitHub | `git checkout 分支 && git pull origin 分支 && git push github 分支` |
| GitHub merge → Gitee | `git checkout 分支 && git pull github 分支 && git push gitee 分支` |
| 双推 | `git push origin 分支` |
| 只推 Gitee | `git push gitee 分支` |
| 只推 GitHub | `git push github 分支` |

## 两个提醒

1. 同一分支别在两个平台各 merge 一次，会产生不同 hash 的 merge commit，导致历史分叉。merge 固定在一个平台做。
2. `git pull` 前确保工作区干净，有未提交改动先 `git stash` 或 commit。

**核心：`origin` 双推、`github`/`gitee` 单推、分支 upstream 绑 `origin`，日常就是 commit + push，被拒就 pull 再 push。**