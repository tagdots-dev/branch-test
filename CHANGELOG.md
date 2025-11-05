# CHANGELOG

## 1.1.40 (2025-11-04)

### Fix

- refactor codes to improve code quality
- upgrade 3.14 in staging and production pipeline
- upgrade to python 3.14
- update cron-tasks - delete-workflow-runs and delete-branches
- add delete-branches-action to cron-tasks
- run header tab on line break
- redo line break

## 1.1.2 (2025-08-19)

### Fix

- fix check_user_inputs zero is ok for max-idle-days
- remove initial assignment of set_user_exclude_branches per codeql
- fix user_exclude_branches

## 1.0.0 (2025-08-17)

### Feat

- setup initial release

### Fix

- add 'head -1' to grep software version to allow adding notes after main

### Refactor

- major overhaul in branches to delete
