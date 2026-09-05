"""Delete GitHub branches that have been idle beyond a configurable threshold.

This CLI tool deletes GitHub branches from a repository based on a
maximum age in days (max-days). It has an option to exclude one or
more branches (exclude-branches).

Usage:
    pkg-32828 --repo-url <url> --max-idle-days N [--exclude-branches "comma-separated branches"] [--dry-run]

Environment:
    GH_TOKEN - required GitHub personal access token with content write scope.
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
    """Create and validate a GitHub API client.

    This function reads the ``GH_TOKEN`` environment variable, creates a
    ``Github`` client, and verifies the token by calling ``Github.get_rate_limit``.

    Returns:
        A configured ``Github`` client instance.

    Raises:
        KeyError: If the ``GH_TOKEN`` environment variable is not set.
        PermissionError: If the GitHub token is invalid or has expired.
    """
    try:
        gh_token = os.environ["GH_TOKEN"]
        gh = Github(auth=Auth.Token(gh_token), per_page=100)
        gh.get_rate_limit()
        return gh

    except KeyError:
        raise KeyError("GitHub Token - not found")
    except BadCredentialsException:
        raise PermissionError("GitHub Token - bad credential")


def get_repo(gh: Github, repo_url: str) -> Repository.Repository:
    """Parse a GitHub repository URL and fetch the corresponding Repository object.

    This function validates the URL format, extracts the ``owner/repo`` pair,
    and calls the GitHub API to retrieve the full repository object.

    Parameters:
        gh: A configured ``Github`` client instance.
        repo_url: A GitHub repository URL (e.g. ``https://github.com/{user/org}/repo.git``
            or ``git@github.com:{user/org}/repo.git``).

    Returns:
        A PyGithub ``Repository`` object for the specified repository.

    Raises:
        ValueError: If the URL is invalid or the repository cannot be found on GitHub.
    """
    try:
        list_gh_substrings = ["https://github.com", "git@github.com:"]
        if not any(gh_substring in repo_url for gh_substring in list_gh_substrings):
            raise ValueError(f"repo-url ({repo_url}) is invalid")

        owner_repo = (
            "/".join(repo_url.rsplit("/", 2)[-2:])
            .replace(".git", "")
            .replace("git@github.com:", "")
            .replace("https://github.com/", "")
        )

        repo = gh.get_repo(owner_repo)
        return repo

    except UnknownObjectException as e:
        raise ValueError(f"{repo_url} repository not found ({e.status})")


def get_exempt_branches(repo: Repository.Repository, set_exclude_branches: set) -> set:
    """Build a set of branches exempt from deletion.

    Parameters:
        repo: A PyGithub ``Repository`` object.
        set_exclude_branches: Set of branch names excluded from deletion by user input.

    Returns:
        A set of branch names that should not be deleted.

    Notes:
        * Exemptions include the default branch, protected branches, PR head/base
          branches, and user-specified branches.
    """

    # Use copy() to prevent RuntimeError: Set changed size during iteration
    set_exempt_branches = set_exclude_branches.copy()
    all_branches = repo.get_branches()
    set_all_branches = set()

    # iterate all branches
    for branch in all_branches:
        set_all_branches.add(branch.name)

    # remove branch from set_exempt_branches if the branch is not found
    if len(set_exclude_branches) > 0:
        for user_exclude_branch in set_exclude_branches:
            if user_exclude_branch not in set_all_branches:
                set_exempt_branches.remove(user_exclude_branch)
        print(f"Refined Exclude Branch(es): {set_exempt_branches}") if len(set_exempt_branches) else ""

    # add to set_exempt_branch - default branch
    default_branch = repo.default_branch
    set_exempt_branches.add(default_branch)
    print(f"Default Branch: {default_branch}")

    # add protected branch to set_exempt_branch
    for branch in all_branches:
        if branch.protected:
            set_exempt_branches.add(branch.name)
            print(f"Protected Branch: {branch.name}")

    # add to set_exempt_branch - PR head branch
    pulls = repo.get_pulls()
    for pull in pulls:
        base_branch = pull.base.ref
        set_exempt_branches.add(base_branch)

        head_branch = pull.head.ref
        set_exempt_branches.add(head_branch)
        print(f"Pull Request Head Branch: {head_branch}")

    return set_exempt_branches


def get_branches_to_delete(
    repo: Repository.Repository, set_exempt_branches: set, branch_max_idle: datetime
) -> Tuple[list, int]:
    """Identify branches eligible for deletion from the set of non-exempt branches.

    A branch is eligible if its last commit date precedes ``branch_max_idle``
    and the branch is not in the exempt set.

    Parameters:
        repo: A PyGithub ``Repository`` object.
        set_exempt_branches: Set of branch names exempt from deletion.
        branch_max_idle: Cutoff datetime; branches whose last commit precedes
            this time are candidates for deletion.

    Returns:
        A tuple containing:
            - A list of branch names eligible for deletion.
            - The count of non-exempt branches.
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

    print(f"\nTotal Number of Branches                         : {total_branch_count}")
    print(f"Total Number of Branches (Exempt-From-Delete)    : {len(set_exempt_branches)}")
    print(f"Total Number of Branches (Not-Exempt-From-Delete): {count_not_exempt_branch}")

    return list_branches_to_delete, count_not_exempt_branch


def delete_branches(
    repo: Repository.Repository,
    dry_run: bool,
    max_idle_days: int,
    list_branches_to_delete: list,
    count_not_exempt_branch: int,
) -> bool:
    """Delete branches that are idle beyond the maximum threshold.

    If ``dry_run`` is ``True``, deletions are simulated (logged as "MOCK")
    and no actual branches are removed.

    Parameters:
        repo: A PyGithub ``Repository`` object.
        dry_run: If ``True``, simulate deletions without removing branches.
        max_idle_days: Maximum number of idle days before a branch is considered
            for deletion.
        list_branches_to_delete: List of branch names to delete.
        count_not_exempt_branch: Number of non-exempt branches.

    Returns:
        ``True`` on completion.
    """
    dry_run_msg = "(MOCK) " if dry_run else "✅ "
    print(
        f"\nFrom {count_not_exempt_branch} Not-Exempt-From-Delete branch(es), "
        + f"{len(list_branches_to_delete)} branch is idle more than {max_idle_days} day(s)"
    )
    print("-" * 90)
    if len(list_branches_to_delete) > 0:
        for branch_to_delete in list_branches_to_delete:
            branch = repo.get_branch(branch_to_delete)
            branch_last_commit_time = branch.commit.commit.committer.date.strftime("%Y-%m-%d %H:%M:%S")

            ref = repo.get_git_ref(f"heads/{branch_to_delete}")
            ref.delete() if not dry_run else ""

            print(f"{dry_run_msg}Delete branch - last update UTC {branch_last_commit_time}: {branch_to_delete}")
    else:
        print("There is no branch to delete")

    return True


def build_set_exclude_branches(exclude_branches: str) -> Set[str]:
    """Convert a comma-separated branch string into a set of branch names.

    Each branch name is stripped of surrounding whitespace, and duplicates
    are removed by converting the result to a set.

    Parameters:
        exclude_branches: A comma-separated string of branch names to exclude
            from deletion (e.g. ``"main,develop,feature-x"``).

    Returns:
        A set of unique branch names, or an empty set if the input is not a string.

    Notes:
        * Uses the string method ``.split()`` to convert the comma-separated
          string into a list.
        * Uses ``map()`` with ``str.strip`` to remove leading and trailing
          whitespace from each element.
        * Converts the list to a set to ensure unique branch names.
    """
    if isinstance(exclude_branches, str):
        list_exclude_branches = exclude_branches.split(",")
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
    """Main entry point for the branch deletion CLI.

    Authenticates with GitHub, determines which branches are eligible for
    deletion based on their idle period, and removes them (or simulates
    removal in dry-run mode).
    """
    print(
        f"\n🚀 Starting Delete GitHub Branches (dry-run: {dry_run}, exclude-branches: "
        + f"{exclude_branches}, max-idle-days: {max_idle_days})\n"
    )

    try:
        # validate and process inputs
        gh = get_auth()
        repo = get_repo(gh, repo_url)
        set_exclude_branches = build_set_exclude_branches(exclude_branches)
        with suppress(ValueError):
            max_idle_days = int(max_idle_days)

        # compute idle cutoff datetime
        current_datetime_tzutc = datetime.now(timezone.utc)
        branch_max_idle = current_datetime_tzutc - timedelta(days=max_idle_days)
        print(f'Current Time (UTC): {current_datetime_tzutc.strftime("%Y-%m-%d %H:%M:%S")}\n')

        # build exempt branches
        set_exempt_branches = get_exempt_branches(repo, set_exclude_branches)

        # get list of to-be-deleted branches and number of not-exempt branch
        list_branches_to_delete, count_not_exempt_branch = get_branches_to_delete(repo, set_exempt_branches, branch_max_idle)

        # delete to-be-deleted branches
        delete_branches(repo, dry_run, max_idle_days, list_branches_to_delete, count_not_exempt_branch)

    except Exception as e:
        print(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
