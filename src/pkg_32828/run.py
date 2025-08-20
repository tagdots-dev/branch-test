#!/usr/bin/env python

"""
Purpose: Delete GitHub Branches
"""

import os
import sys
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import click
from github import Auth, Github, Repository
from rich.console import Console

from pkg_32828 import __version__


def get_auth():
    """
    Creates an instance of Github class to interact with GitHub API
    """
    try:
        gh_token = os.environ['GH_TOKEN']
        gh = Github(auth=Auth.Token(gh_token), per_page=100)
        return gh

    except KeyError:
        print("❌ Error: Environment variable (GH_TOKEN) not found.")
    except AssertionError:
        print("❌ Error: Environment variable (GH_TOKEN) is invalid")

    sys.exit(1)


def get_owner_repo(repo_url):
    """
    Get owner/repo for pyGitHub to interact with GitHub API

    Parameter(s):
    repo_url: repository url (e.g. https://github.com/{user/org}/repo.git)

    Return: owner/repo
    """
    owner_repo = '/'.join(repo_url.rsplit('/', 2)[-2:]).\
        replace('.git', '').replace('git@github.com:', '').replace('https://github.com/', '')
    return owner_repo


def check_user_inputs(repo, repo_url, exclude_branch, max_idle_days):
    """
    Check user inputs

    Parameter(s):
    repo           : github repository object
    repo_url       : github repository url
    exclude_branch: branch excluded from delete
    max_idle_days  : maximum number of days that the branch has been idle
                   : e.g. "max_idle_days = 5" means that the branch went idle for over 5 days

    Return: boolean
    """
    if exclude_branch is not None and not isinstance(exclude_branch, set):
        print("❌ Error: excluded-branch must be a set")
        return False

    if max_idle_days is not None and (not isinstance(max_idle_days, int) or max_idle_days < 0):
        print("❌ Error: max-idle-days must be an integer (0 or more)")
        return False

    if ('github.com' not in repo_url and not isinstance(repo, Repository.Repository)):
        print("❌ Error: repo-url is not a valid github repository url")
        return False

    return True


def get_exempt_branches(repo, set_user_exclude_branches):
    """
    Add default, protected, and PR base branches to build a set of exempt branches
    Remove user specified branches from exempt branches if the specified branches do not exist

    Parameter(s):
    repo                     : github repository object
    set_user_exclude_branches: set of branch(es) excluded from delete via user inputs

    Return: set of exempt branches excluded from delete
    """

    """use copy() here to prevent 'Exception Error: Set changed size during iteration'"""
    set_exempt_branches = set_user_exclude_branches.copy()
    all_branches = repo.get_branches()
    set_all_branches = set()

    """iterate all branches"""
    for branch in all_branches:
        set_all_branches.add(branch.name)

    """remove branch from set_exempt_branches if the branch is not found in existing branches"""
    if len(set_user_exclude_branches) > 0:
        for user_exclude_branch in set_user_exclude_branches:
            if user_exclude_branch not in set_all_branches:
                set_exempt_branches.remove(user_exclude_branch)
        print(f'Refined User Exclude Branch(es): {set_exempt_branches}') if len(set_exempt_branches) else ''

    """add to set_exempt_branch - default branch"""
    default_branch = repo.default_branch
    set_exempt_branches.add(default_branch)
    print(f'Default Branch                 : {default_branch}')

    """add protected branch to set_exempt_branch"""
    for branch in all_branches:
        if branch.protected:
            set_exempt_branches.add(branch.name)
            print(f'Protected Branch               : {branch.name}')

    """add to set_exempt_branch - PR head branch"""
    pulls = repo.get_pulls()
    for pull in pulls:
        base_branch = pull.base.ref
        set_exempt_branches.add(base_branch)

        head_branch = pull.head.ref
        set_exempt_branches.add(head_branch)
        print(f'Pull Request Head Branch       : {head_branch}')

    return set_exempt_branches


def get_branches_to_delete(repo, max_idle_days, set_exempt_branches, branch_max_idle):
    """
    get to-be-deleted branches from not-exempt branches

    Parameter(s):
    repo               : github repository object
    set_exempt_branches: set of exempt branches excluded from delete
    branch_max_idle    : datetime on maximum number of days that the branch has been idle

    Return: list of branches to delete, number of branches not exempt from delete
    """
    list_branches_to_delete = []
    total_branch_count = 0
    not_exempt_branch_count = 0
    for branch in repo.get_branches():
        total_branch_count += 1
        if branch.name not in set_exempt_branches:
            not_exempt_branch_count += 1
            if branch_max_idle > branch.commit.commit.committer.date:
                list_branches_to_delete.append(branch.name)

    print(f'\nTotal Number of Branches                         : {total_branch_count}')
    print(f'Total Number of Branches (Exempt-From-Delete)    : {len(set_exempt_branches)}')
    print(f'Total Number of Branches (Not-Exempt-From-Delete): {not_exempt_branch_count}')

    return list_branches_to_delete, not_exempt_branch_count


def delete_branches(repo, dry_run, max_idle_days, list_branches_to_delete, not_exempt_branch_count):
    """
    delete branches

    Parameter(s):
    repo                   : github repository object
    max_idle_days          : maximum number of days that the branch has been idle
    list_branches_to_delete: list of branches to delete
    not_exempt_branch_count: number of branches not exempt from delete

    Return: boolean
    """
    dry_run_msg = "(MOCK) " if dry_run else "✅ "
    console = Console()
    console.print(f'\n[red]From {not_exempt_branch_count} Not-Exempt-From-Delete Branch(es)[/red], '
                  f'[red] {len(list_branches_to_delete)} had no commit in the last {max_idle_days} day(s)[/red]')
    print('-------------------------------------------------------------------------------------------------')
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


def get_set_user_exclude_branches(exclude_branches):
    """
    turn exclude_branches into a set

    Parameter(s)
    exclude_branches: exclude branches from delete (string)

    * use list method .split to split exclude_branches (str).  This convert str to list
    * use map to strip space before and after each element on the list
    * turn list into set to ensure unqiue branch name
    """
    if isinstance(exclude_branches, str):
        list_user_exclude_branches = exclude_branches.split(',')
        set_user_exclude_branches = set(map(str.strip, list_user_exclude_branches))
    else:
        set_user_exclude_branches = set()

    return set_user_exclude_branches


@click.command()
@click.option("--dry-run", required=False, type=bool, default=True, help="default: true")
@click.option("--repo-url", required=True, help="e.g. https://github.com/{owner}/{repo}")
@click.option("--exclude-branches", required=False, help="Branches excluded from deletion")
@click.option("--max-idle-days", required=True, help="Delete branches older than max. idle days")
@click.version_option(version=__version__)
def main(dry_run, repo_url, exclude_branches, max_idle_days):
    with suppress(AttributeError):
        set_user_exclude_branches = get_set_user_exclude_branches(exclude_branches)
    with suppress(ValueError):
        max_idle_days = int(max_idle_days)

    console = Console()
    console.print(f"\n🚀 Starting to Delete GitHub Branches (dry-run: [red]{dry_run}[/red], \
exclude-branches: [red]{set_user_exclude_branches}[/red], max-idle-days: [red]{max_idle_days}[/red])\n")

    try:
        """setup github repo object"""
        gh = get_auth()
        owner_repo = get_owner_repo(repo_url)
        repo = gh.get_repo(owner_repo)

        if check_user_inputs(repo, repo_url, set_user_exclude_branches, max_idle_days):
            """set time"""
            current_datetime_tzutc = datetime.now(timezone.utc)
            branch_max_idle = current_datetime_tzutc - timedelta(days=max_idle_days)
            print(f'Current Time (UTC): {current_datetime_tzutc.strftime("%Y-%m-%d %H:%M:%S")}\n')

            """build exempt branches"""
            set_exempt_branches = get_exempt_branches(repo, set_user_exclude_branches)

            """get list of to-be-deleted branches and number of not-exempt branch"""
            list_branches_to_delete, not_exempt_branch_count = \
                get_branches_to_delete(repo, max_idle_days, set_exempt_branches, branch_max_idle)

            """delete to-be-deleted branches"""
            delete_branches(repo, dry_run, max_idle_days, list_branches_to_delete, not_exempt_branch_count)
        else:
            sys.exit(1)

    except Exception as e:
        print(f'❌ Exception Error: {e}')
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()
