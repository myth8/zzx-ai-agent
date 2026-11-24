# 多设备 Git 远端配置

这个目录下的脚本用于把任意一台新设备的仓库配置成「**从 GitHub 拉取，同时推送到 GitHub + Gitee**」。

配一次即可，之后日常只需要 `git pull --rebase` 和 `git push`。

## 一、它解决什么问题

本仓库有两个远端：

| 平台 | 地址 | 角色 |
|---|---|---|
| GitHub | `git@github.com:myth8/zzx-ai-agent.git` | 主仓库，拉取与主推送 |
| Gitee | `git@gitee.com:crzzx/zzx-ai-agent.git` | 镜像，只推送 |

手工配置容易配成「拉取走 Gitee、推送走两个」，这样当另一台设备只推了 GitHub 时，本机会拉到旧代码，再推 GitHub 会被拒绝，而 Gitee 已经被改掉——两个仓库就此分叉。

脚本把顺序固定为 **GitHub 在前、Gitee 在后**：GitHub 一旦被拒，Gitee 还没动，问题立刻可见。

## 二、前置条件：SSH 密钥

双推意味着**同一把公钥要同时加到 GitHub 和 Gitee**。新设备上先做这一步。

### macOS / Linux / Windows Git Bash

```bash
ssh-keygen -t ed25519 -C "zhuzhuoxuan@sensetime.com"
cat ~/.ssh/id_ed25519.pub
```

把输出的整行分别粘贴到：

- GitHub → Settings → SSH and GPG keys → New SSH key
- Gitee → 设置 → SSH 公钥

然后验证两边都通：

```bash
ssh -T git@github.com     # 期望 Hi myth8! ...
ssh -T git@gitee.com      # 期望 Hi ... 认证成功
```

### Windows PowerShell

密钥路径是 `C:\Users\<用户名>\.ssh\`，不是 `~/.ssh`。

```powershell
ssh-keygen -t ed25519 -C "zhuzhuoxuan@sensetime.com"
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

验证命令同上。

> 若提示 `ssh` 或 `git` 不是可识别的命令，说明 Git for Windows 安装时没勾选
> "Git from the command line and also from 3rd-party software"，重新安装勾上即可。

## 三、执行脚本

先把仓库 clone 下来，再在**仓库根目录**执行对应平台的那一份。

### macOS / Linux

```bash
bash scripts/setup-remotes.sh
```

### Windows（PowerShell）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-remotes.ps1
```

必须带 `-ExecutionPolicy Bypass`，否则系统会拦截脚本执行。

### Windows（Git Bash）

```bash
bash scripts/setup-remotes.sh
```

两个脚本逻辑完全一致，Windows 上任选其一，装了 Git for Windows 就一定有 Git Bash。

## 四、怎么确认配好了

脚本最后会打印自检结果，期望长这样：

```
--- 远端配置 ---
origin  git@github.com:myth8/zzx-ai-agent.git (fetch)
origin  git@github.com:myth8/zzx-ai-agent.git (push)
origin  git@gitee.com:crzzx/zzx-ai-agent.git (push)
--- 推送预演 ---
Everything up-to-date
Everything up-to-date
```

三个要点：

1. **一行 fetch，两行 push** —— 说明拉取单源、推送双源。
2. **GitHub 那行在前** —— 顺序不能反，理由见第一节。
3. **两条 `Everything up-to-date`** —— 说明两个远端都连得上、认证通过。如果只出现一条或报 `Permission denied`，是密钥没加到对应平台。

## 五、脚本做了什么

按顺序五步，可重复执行（每次都会先清掉旧配置再重建）：

1. 删除 `github`、`gitee` 这两个历史遗留远端，清空 `origin` 上所有旧 `pushurl`
2. 把 `origin` 的拉取地址设为 GitHub
3. 追加两个 `pushurl`：GitHub 在前，Gitee 在后
4. `git fetch origin --prune`，并把 `develop` 的跟踪分支指到 `origin/develop`
5. 打印 `git remote -v` 和 `git push --dry-run` 做自检

## 六、日常命令

```bash
git pull --rebase     # 从 GitHub 拉取，rebase 保持历史线性
git push              # 一次推 GitHub + Gitee
```

嫌两条麻烦可以加个别名，`git sync` 一步到位：

```bash
git config --global alias.sync '!git pull --rebase && git push'
```

> Windows PowerShell 下同样可用：Git for Windows 自带 sh，`!` 开头的别名能正常执行。

## 七、常见问题

### 推送时报 `non-fast-forward` 被拒

说明远端有你本地没有的提交，通常是另一台设备推过。先拉再推：

```bash
git pull --rebase
git push
```

**不要用 `git push --force`**。双远端场景下一次 force 会冲掉另一台设备的提交。

### GitHub 推成功，但 Gitee 报 `non-fast-forward`

Gitee 上存在独立提交。确认 Gitee 没有别人在用的分支后，强制对齐镜像：

```bash
git push git@gitee.com:crzzx/zzx-ai-agent.git develop --force-with-lease
```

### 只想推 GitHub，不推 Gitee

`git push origin` 仍然会推两个。要推单个远端就直接给 URL：

```bash
git push git@github.com:myth8/zzx-ai-agent.git develop
```

### 报 `$'\r': command not found`

`.sh` 文件被以 CRLF 换行提交了。根目录 `.gitattributes` 已把 `*.sh` 锁为 LF，如果之前已污染过，修一次：

```bash
git add --renormalize .
git commit -m "chore: 统一换行符"
```

### Gitee 报 `Permission denied (publickey)`

公钥只加到了 GitHub。把同一份 `id_ed25519.pub` 也加到 Gitee 的 SSH 公钥设置里。

## 八、换新设备清单

- [ ] 安装 Git（Windows 用 Git for Windows，勾选加入 PATH）
- [ ] `ssh-keygen -t ed25519` 生成密钥
- [ ] 公钥加到 **GitHub**
- [ ] 公钥加到 **Gitee**
- [ ] `ssh -T git@github.com` / `ssh -T git@gitee.com` 都返回成功
- [ ] `git clone git@github.com:myth8/zzx-ai-agent.git`
- [ ] 仓库根目录执行 `scripts/setup-remotes.sh`（或 `.ps1`）
- [ ] 自检出现「一行 fetch + 两行 push + 两条 up-to-date」
