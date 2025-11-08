#!/usr/bin/env python

"""
Purpose: Delete GitHub Branches
"""
import os
import sys
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Set, Tuple

import click
from github import (
    Auth,
    BadCredentialsException,
    Github,
    Repository,
    UnknownObjectException,
)

from pkg_32828 import __version__


def get_auth() -> Github:
    """
    Creates an instance of Github class to interact with GitHub API
    """
    try:
        gh_token = os.environ['GH_TOKEN']
        gh = Github(auth=Auth.Token(gh_token), per_page=100)
        gh.get_rate_limit()
        return gh

    except KeyError:
        raise KeyError('GH_TOKEN (environment variable) not found')
    except BadCredentialsException:
        raise PermissionError('Invalid GitHub Token (GH_TOKEN)')


def get_repo(gh: Github, repo_url: str) -> Repository.Repository:
    """
    Get owner/repo for pyGitHub to interact with GitHub API

    Parameter(s):
    repo_url: repository url (e.g. https://github.com/{user/org}/repo.git)
    """
    try:
        list_gh_substrings = ['https://github.com', 'git@github.com:']
        if not any(gh_substring in repo_url for gh_substring in list_gh_substrings):
            raise ValueError(f'repo-url ({repo_url}) is invalid')

        owner_repo = '/'.join(repo_url.rsplit('/', 2)[-2:]).\
            replace('.git', '').replace('git@github.com:', '').replace('https://github.com/', '')

        repo = gh.get_repo(owner_repo)
        return repo

    except UnknownObjectException as e:
        raise ValueError(f'{repo_url} repository not found ({e.status})')


def get_exempt_branches(repo: Repository.Repository, set_exclude_branches: set) -> set:
    """
    Add default, protected, and PR base branches to build a set of exempt branches
    Remove user specified branches from exempt branches if the specified branches do not exist

    Parameter(s):
    repo                     : github repository object
    set_exclude_branches: set of branch(es) excluded from delete via user inputs
    """

    """use copy() here to prevent 'Exception Error: Set changed size during iteration'"""
    set_exempt_branches = set_exclude_branches.copy()
    all_branches = repo.get_branches()
    set_all_branches = set()

    """iterate all branches"""
    for branch in all_branches:
        set_all_branches.add(branch.name)

    """remove branch from set_exempt_branches if the branch is not found in existing branches"""
    if len(set_exclude_branches) > 0:
        for user_exclude_branch in set_exclude_branches:
            if user_exclude_branch not in set_all_branches:
                set_exempt_branches.remove(user_exclude_branch)
        print(f'Refined User Exclude Branch(es): {set_exempt_branches}') if len(set_exempt_branches) else ''

    """add to set_exempt_branch - default branch"""
    default_branch = repo.default_branch
    set_exempt_branches.add(default_branch)
    print(f'Default Branch           : {default_branch}')

    """add protected branch to set_exempt_branch"""
    for branch in all_branches:
        if branch.protected:
            set_exempt_branches.add(branch.name)
            print(f'Protected Branch         : {branch.name}')

    """add to set_exempt_branch - PR head branch"""
    pulls = repo.get_pulls()
    for pull in pulls:
        base_branch = pull.base.ref
        set_exempt_branches.add(base_branch)

        head_branch = pull.head.ref
        set_exempt_branches.add(head_branch)
        print(f'Pull Request Head Branch : {head_branch}')

    return set_exempt_branches


def get_branches_to_delete(repo: Repository.Repository, set_exempt_branches: set,
                           branch_max_idle: datetime) -> Tuple[list, int]:
    """
    get to-be-deleted branches from not-exempt branches

    Parameter(s):
    repo               : github repository object
    set_exempt_branches: set of exempt branches excluded from delete
    branch_max_idle    : datetime on maximum number of days that the branch has been idle
    """
    list_branches_to_delete = []
    total_branch_count = 0
    count_not_exempt_branch = 0
    for branch in repo.get_branches():
        total_branch_count += 1
        if branch.name not in set_exempt_branches:
            count_not_exempt_branch += 1
            if branch_max_idle > branch.commit.commit.committer.date:
                list_branches_to_delete.append(branch.name)

    print(f'\nTotal Number of Branches                         : {total_branch_count}')
    print(f'Total Number of Branches (Exempt-From-Delete)    : {len(set_exempt_branches)}')
    print(f'Total Number of Branches (Not-Exempt-From-Delete): {count_not_exempt_branch}')

    return list_branches_to_delete, count_not_exempt_branch


def delete_branches(repo: Repository.Repository, dry_run: bool, max_idle_days: int, list_branches_to_delete: list,
                    count_not_exempt_branch: int) -> bool:
    """
    delete branches

    Parameter(s):
    repo                   : github repository object
    max_idle_days          : maximum number of days that the branch has been idle (without new commits)
    list_branches_to_delete: list of branches to delete
    count_not_exempt_branch: number of branches not exempt from delete
    """
    dry_run_msg = "(MOCK) " if dry_run else "✅ "
    print(f'\nFrom {count_not_exempt_branch} Not-Exempt-From-Delete branch(es), ' +
          f'{len(list_branches_to_delete)} branch is idle more than {max_idle_days} day(s)')
    print("-" * 90)
    if len(list_branches_to_delete) > 0:
        for branch_to_delete in list_branches_to_delete:
            branch = repo.get_branch(branch_to_delete)
            branch_last_commit_time = branch.commit.commit.committer.date.strftime("%Y-%m-%d %H:%M:%S")

            ref = repo.get_git_ref(f"heads/{branch_to_delete}")
            ref.delete() if not dry_run else ""

            print(f'{dry_run_msg}Delete branch - last update UTC {branch_last_commit_time}: {branch_to_delete}')
    else:
        print("There is no branch to delete")

    return True


def build_set_exclude_branches(exclude_branches: str) -> Set[str]:
    """
    turn exclude_branches into a set

    Parameter(s)
    exclude_branches: exclude branches from delete (string)

    * use list method .split to split exclude_branches (str).  This convert str to list
    * use map to strip space before and after each element on the list
    * turn list into set to ensure unqiue branch name
    """
    if isinstance(exclude_branches, str):
        list_exclude_branches = exclude_branches.split(',')
        return set(map(str.strip, list_exclude_branches))
    else:
        return set()


@click.command()
@click.option("--dry-run", required=False, type=bool, default=True, help="default: true")
@click.option("--repo-url", required=True, help="e.g. https://github.com/{owner}/{repo}")
@click.option("--exclude-branches", required=False, type=str, help="e.g. 'exclude-branch-1, exclude-branch-2'")
@click.option("--max-idle-days", required=True, type=int, help="Max. no. of idle days (without commits)")
@click.version_option(version=__version__)
def main(dry_run: bool, repo_url: str, exclude_branches: str, max_idle_days: int):
    print(f"\n🚀 Starting Delete GitHub Branches (dry-run: {dry_run}, exclude-branches: " +
          f"{exclude_branches}, max-idle-days: {max_idle_days})\n")

    try:
        gh = get_auth()
        repo = get_repo(gh, repo_url)
        set_exclude_branches = build_set_exclude_branches(exclude_branches)
        with suppress(ValueError):
            max_idle_days = int(max_idle_days)

        """set time"""
        current_datetime_tzutc = datetime.now(timezone.utc)
        branch_max_idle = current_datetime_tzutc - timedelta(days=max_idle_days)
        print(f'Current Time (UTC): {current_datetime_tzutc.strftime("%Y-%m-%d %H:%M:%S")}\n')

        """build exempt branches"""
        set_exempt_branches = get_exempt_branches(repo, set_exclude_branches)

        """get list of to-be-deleted branches and number of not-exempt branch"""
        list_branches_to_delete, count_not_exempt_branch = \
            get_branches_to_delete(repo, set_exempt_branches, branch_max_idle)

        """delete to-be-deleted branches"""
        delete_branches(repo, dry_run, max_idle_days, list_branches_to_delete, count_not_exempt_branch)

    except Exception as e:
        print(f'Error: {e}\n')
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()
