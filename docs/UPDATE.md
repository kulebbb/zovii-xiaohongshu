# 更新指导

## 自动检查（默认开启，无需配置）

skill **每次运行的第一步**会比较本地版本与 GitHub 最新版本（`scripts/check_update.py`）：

| 结果 | 行为 |
|---|---|
| 有新版本 | AI 提示你有新版，**经你同意后**才执行更新；拒绝则继续使用当前版本 |
| 已是最新 | 静默继续 |
| 网络不通 | 仅 stderr 一行警告，**绝不阻塞任务** |

## 手动更新

### 通过 skills CLI 安装的用户（方式一/二）

```bash
npx skills update zovii-xiaohongshu        # 只更新本 skill
npx skills update                          # 交互式更新所有已装 skill
```

也可以对 AI 说：「帮我更新 zovii-xiaohongshu skill」。

### 手动 clone 安装的用户（方式三）

```bash
cd <skill目录>
git pull
```

## 查看当前版本

```bash
cat <skill目录>/VERSION

# 或让自检脚本报告本地与远端版本对比
python3 <skill目录>/scripts/check_update.py
```

## 版本说明

- 版本号遵循语义化版本 `主版本.次版本.修订号`
- 全部变更记录见 GitHub [Releases](https://github.com/kulebbb/zovii-xiaohongshu/releases) 页面
