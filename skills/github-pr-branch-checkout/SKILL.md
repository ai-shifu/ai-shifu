# GitHub PR 原始分支拉取与直推校验

## 适用场景

- 用户提供 GitHub PR 链接，希望把 PR 拉到本地修改。
- 用户明确希望后续提交直接推回 PR 的原始分支，而不是推到自己的 fork。

## 目标

- 识别 PR 的 head 仓库、head 分支、base 分支。
- 在本地检出一个跟踪原始分支的工作分支。
- 校验当前机器是否具备直接推送到该原始分支的权限。

## 推荐流程

1. 先在目标仓库中检查 `git remote -v`、`git status --short --branch`，确认当前仓库和工作区状态。
2. 查询 PR 元数据，重点确认 `head.repo.full_name`、`head.ref`、`maintainer_can_modify`。
3. 如果 PR head 在上游仓库内，优先使用现有上游远端抓取对应分支；如果 head 在 fork 中，再补充对应 fork 远端。
4. 使用 `git fetch <remote> <head-branch>` 拉取分支，再用 `git switch --track -C <head-branch> <remote>/<head-branch>` 建立本地跟踪关系。
5. 用 `git status --short --branch` 和 `git branch -vv` 确认当前分支已经跟踪目标远端分支。
6. 需要确认可直推时，执行 `git push --dry-run <remote> HEAD:<head-branch>` 做权限验证。

## 注意事项

- 如果 `maintainer_can_modify` 为 `false`，不要直接假设不能推送，还要结合当前机器的仓库写权限做 dry-run 校验。
- 如果本机没有 `gh`，可以改用 GitHub API 查询 PR 元数据。
- 切分支前确认工作区是否干净，避免覆盖用户当前未提交内容。
- 不要修改或删除用户已有的 `console.log`。
