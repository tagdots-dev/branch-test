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

    if max_idle_days is not None and (not isinstance(max_idle_days, int) or max_idle_days <= 0):
        print("❌ Error: max-idle-days must be an integer (0 or more)")
        return False

    if ('github.com' not in repo_url and not isinstance(repo, Repository.Repository)):
        print("❌ Error: repo-url is not a valid github repository url")
        return False

    return True


def get_exempt_branches(repo, exclude_branches):
    """
    build exempt branches (add default, protected, and PR base branches)

    Parameter(s):
    repo             : github repository object
    exclude_branches: exclude_branches from user inputs

    Return: set of exempt branches
    """
    default_branch = repo.default_branch
    exclude_branches.add(default_branch)

    for branch in repo.get_branches():
        if branch.protected:
            exclude_branches.add(branch.name)

    pulls = repo.get_pulls(state='open')
    for pull in pulls:
        base_branch = pull.base.ref
        exclude_branches.add(base_branch)

        head_branch = pull.head.ref
        exclude_branches.add(head_branch)

    return exclude_branches


def get_qualified_branches(repo, exempt_branches, branch_maximum_idle_cutoff):
    """
    get qualified branches

    Parameter(s):
    repo                      : github repository object
    exempt_branches           : exclude_branches from user inputs
    branch_maximum_idle_cutoff: maximum number of days that the branch has been idle

    Return: list of branches that should be deleted and total branch count
    """
    branches = []
    branch_count = 0
    for branch in repo.get_branches():
        branch_count += 1
        if branch.name not in exempt_branches and branch_maximum_idle_cutoff > branch.commit.commit.committer.date:
            branches.append(branch.name)

    print(f'\nTotal Number of Branches              : {branch_count}')
    print(f'Total Number of Branches To Be Deleted: {len(branches)}')

    return branches, branch_count


def delete_branches(repo, dry_run, branch_max_idle_cutoff, qualified_branches):
    """
    get qualified branches

    Parameter(s):
    repo              : github repository object
    qualified_branches: branches exempt from deletion

    Return: boolean
    """
    print(f'\nDeleting Branch(es) older than {branch_max_idle_cutoff.strftime("%Y-%m-%d %H:%M:%S")}')
    print('---------------------------------------------------')
    if len(qualified_branches) > 0:
        for qualified_branch in qualified_branches:
            branch = repo.get_branch(qualified_branch)
            branch_last_commit_time = branch.commit.commit.committer.date.strftime("%Y-%m-%d %H:%M:%S")
            branch.delete() if not dry_run else ""
            print(f'✅ Deleted branch (last update {branch_last_commit_time}): {qualified_branch}')
    else:
        print("There is no qualified branch to delete")

    return True


@click.command()
@click.option("--dry-run", required=False, type=bool, default=True, help="default: true")
@click.option("--repo-url", required=True, type=str, help="e.g. https://github.com/{owner}/{repo}")
@click.option("--exclude-branch", required=False, type=str, multiple=True, help="Branch excluded from deletion")
@click.option("--max-idle-days", required=True, help="Delete branches over max. idle days")
@click.version_option(version=__version__)
def main(dry_run, repo_url, exclude_branch, max_idle_days):
    exclude_branches = set(exclude_branch)
    with suppress(ValueError):
        max_idle_days = int(max_idle_days)

    console = Console()
    console.print(f"\n🚀 Starting to Delete GitHub Branches (dry-run: [red]{dry_run}[/red], repo-url: [red]{repo_url}[/red],"
                  f" exclude-branches: [red]{exclude_branch}[/red], max-idle-days: [red]{max_idle_days}[/red])\n")

    try:
        """setup github repo object"""
        gh = get_auth()
        owner_repo = get_owner_repo(repo_url)
        repo = gh.get_repo(owner_repo)

        if check_user_inputs(repo, repo_url, exclude_branches, max_idle_days):
            """build exempt branches"""
            exempt_branches = get_exempt_branches(repo, exclude_branches)

            """set time"""
            current_datetime_tzutc = datetime.now(timezone.utc)
            branch_max_idle_cutoff = current_datetime_tzutc - timedelta(days=max_idle_days)
            print(f'Current Time (UTC): {current_datetime_tzutc.strftime("%Y-%m-%d %H:%M:%S")}')

            """get qualified branches"""
            qualified_branches, total_branch_count = get_qualified_branches(repo, exempt_branches, branch_max_idle_cutoff)

            """delete qualified branches"""
            delete_branches(repo, dry_run, branch_max_idle_cutoff, qualified_branches)
        else:
            sys.exit(1)

    except Exception as e:
        print(f'❌ Exception Error: {e}')
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main(standalone_mode=False)
    console = Console()
    console.print("\n[bold red]Notes[/ bold red]")
    console.print("* no to delete default branch")
    console.print("* no to delete protected branches")
    console.print("* no to delete branches used in PR\n")
