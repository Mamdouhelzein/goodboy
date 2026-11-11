---
name: git-workflow
description: "Everyday git help: branching, rebasing, undoing commits, resolving merge conflicts, and cleaning up history."
---

# Git Workflow

Everyday git help: branching, rebasing, undoing commits, resolving merge conflicts, and cleaning up history.

## Undo

git reset --soft HEAD~1 to undo a commit but keep changes; git revert for shared branches.

## Conflicts

git status, edit the conflict markers, git add, then continue the merge or rebase.

## History

Interactive rebase to squash or reword; never rewrite shared history without telling the team.
