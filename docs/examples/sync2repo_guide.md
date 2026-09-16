懂了，从 0 开始，完整步骤：

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

## 第五步：补一个独立 gitee remote（方便单向操作）

```bash
git remote add gitee git@gitee.com:crzzx/zzx-ai-agent.git
```

## 第六步：设置 GitHub 默认分支

GitHub 仓库 → Settings → Branches → Default branch 设为 `master`。

## 后续日常操作

**本地 develop 开发完推送两边：**

```bash
git checkout develop
git pull origin develop
git add .
git commit -m "feat: xxx"
git push origin develop
```

**Gitee merge 后同步到 GitHub：**

```bash
git checkout master
git pull origin master
git push github master
```

**GitHub merge 后同步到 Gitee：**

```bash
git checkout master
git pull github master
git push gitee master
```

## 速查表

| 场景 | 命令 |
|------|------|
| 本地 develop 推送两边 | `git checkout develop && git pull origin develop && git add . && git commit -m "..." && git push origin develop` |
| Gitee merge → GitHub | `git checkout 分支 && git pull origin 分支 && git push github 分支` |
| GitHub merge → Gitee | `git checkout 分支 && git pull github 分支 && git push gitee 分支` |
| 双推 | `git push origin 分支` |
| 只推 Gitee | `git push gitee 分支` |
| 只推 GitHub | `git push github 分支` |

## 两个提醒

1. 同一分支别在两个平台各 merge 一次，会产生不同 hash 的 merge commit，导致历史分叉。merge 固定在一个平台做。
2. `git pull` 前确保工作区干净，有未提交改动先 `git stash` 或 commit。