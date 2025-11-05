#!/usr/bin/env python

"""
Purpose: tests
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from github import Repository

from pkg_32828.run import (
    check_user_inputs,
    delete_branches,
    get_auth,
    get_branches_to_delete,
    get_exempt_branches,
    get_owner_repo,
    get_set_user_exclude_branches,
    main,
)


@pytest.fixture
def mock_repo():
    repo = Mock(spec=Repository.Repository)
    repo.default_branch = "main"
    return repo


@pytest.fixture
def mock_branch():
    def _create_branch(name, protected=False, last_commit_days_ago=0):
        branch = Mock()
        branch.name = name
        branch.protected = protected
        commit_date = datetime.now(timezone.utc) - timedelta(days=last_commit_days_ago)
        branch.commit.commit.committer.date = commit_date
        return branch
    return _create_branch


@pytest.fixture
def mock_pull():
    def _create_pull(base_ref, head_ref):
        pull = Mock()
        pull.base.ref = base_ref
        pull.head.ref = head_ref
        return pull
    return _create_pull


class TestGetAuth:
    def test_get_auth_success(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "valid_token")
        with patch("pkg_32828.run.Github") as mock_github:
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_gh = mock_github.return_value
            mock_gh.get_user.return_value = mock_user
            gh = get_auth()
            assert gh is not None
            mock_github.assert_called_once()

    def test_get_auth_missing_token(self, monkeypatch):
        if "GH_TOKEN" in os.environ:
            monkeypatch.delenv("GH_TOKEN")
        with pytest.raises(SystemExit) as excinfo:
            get_auth()
        assert excinfo.value.code == 1

    def test_get_auth_invalid_token(self, monkeypatch):
        if "GH_TOKEN" in os.environ:
            monkeypatch.setenv("GH_TOKEN", "")
        with pytest.raises(SystemExit) as excinfo:
            get_auth()
        assert excinfo.value.code == 1


class TestGetOwnerRepo:
    def test_https_url(self):
        repo_url = "https://github.com/owner/repo.git"
        assert get_owner_repo(repo_url) == "owner/repo"

    def test_ssh_url(self):
        repo_url = "git@github.com:owner/repo.git"
        assert get_owner_repo(repo_url) == "owner/repo"

    def test_no_git_suffix(self):
        repo_url = "https://github.com/owner/repo"
        assert get_owner_repo(repo_url) == "owner/repo"


class TestGetSetUserExcludeBranches:
    def test_set_user_exclude_branches_success_01(self):
        exclude_branches = ' test1,test2 , test3 '
        expected_string = 'test3'
        set_user_exclude_branches = get_set_user_exclude_branches(exclude_branches)

        assert isinstance(set_user_exclude_branches, set) is True
        assert expected_string in set_user_exclude_branches

    def test_set_user_exclude_branches_success_02(self):
        exclude_branches = ''
        set_user_exclude_branches = get_set_user_exclude_branches(exclude_branches)

        assert isinstance(set_user_exclude_branches, set) is True

    def test_set_user_exclude_branches_failure_01(self):
        exclude_branches = []  # wrong data type
        set_user_exclude_branches = get_set_user_exclude_branches(exclude_branches)  # type: ignore reportArgumentType

        assert isinstance(set_user_exclude_branches, set) is True


class TestCheckUserInputs:
    def test_user_inputs_success(self):
        repo = Mock()
        assert check_user_inputs(repo, "https://github.com/owner/repo", {'main', 'badges'}, 5)

    def test_user_inputs_max_idle_days_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, '')  # type: ignore reportArgumentType

    def test_user_inputs_max_idle_days_negative(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, -1)

    def test_user_inputs_max_idle_days_string(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, 's')  # type: ignore reportArgumentType

    def test_user_inputs_exclude_branch_not_set_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", '', 20)  # type: ignore reportArgumentType

    def test_user_inputs_exclude_branch_not_set_main(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", 'main', 10)  # type: ignore reportArgumentType

    def test_user_inputs_repo_url_invalid(self):
        repo = Mock()
        assert not check_user_inputs(repo, "invalid_url", {'main'}, 15)

    def test_user_inputs_repo_url_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, '', {'main'}, 50)


class TestGetExemptBranches:
    def test_exempt_branches_01(self, mock_repo, mock_branch, mock_pull):
        # mock protected branches
        protected_branch_01 = mock_branch("protected_01", protected=True)

        # mock normal branches
        normal_branch_01 = mock_branch("normal_01", protected=False, last_commit_days_ago=10)
        normal_branch_02 = mock_branch("normal_02", protected=False, last_commit_days_ago=15)

        # get all mock branches
        mock_repo.get_branches.return_value = [
            protected_branch_01,
            normal_branch_01,
            normal_branch_02,
        ]

        # mock PRs
        pull_01 = mock_pull("main", "feature1")
        pull_02 = mock_pull("dev", "feature2")
        mock_repo.get_pulls.return_value = [pull_01, pull_02]

        # create exempt set
        exempt = get_exempt_branches(mock_repo, set_user_exclude_branches=set(["branch-not-in-all"]))

        # assert branches in or not in exempt
        assert "protected_01" in exempt
        assert "normal_01" not in exempt
        assert "normal_02" not in exempt
        assert "main" in exempt
        assert "dev" in exempt
        assert "feature1" in exempt
        assert "feature2" in exempt
        assert "branch-not-in-all" not in exempt

    def test_exempt_branches_02(self, mock_repo, mock_branch, mock_pull):
        # mock protected branches
        protected_branch_01 = mock_branch("protected_01", protected=True)

        # mock normal branches
        normal_branch_01 = mock_branch("normal_01", protected=False, last_commit_days_ago=10)
        normal_branch_02 = mock_branch("normal_02", protected=False, last_commit_days_ago=15)

        # get all mock branches
        mock_repo.get_branches.return_value = [
            protected_branch_01,
            normal_branch_01,
            normal_branch_02,
        ]

        # mock PRs
        pull_01 = mock_pull("main", "feature1")
        pull_02 = mock_pull("dev", "feature2")
        mock_repo.get_pulls.return_value = [pull_01, pull_02]

        # create exempt set
        exempt = get_exempt_branches(mock_repo, set_user_exclude_branches=set())

        # assert branches in or not in exempt
        assert "protected_01" in exempt
        assert "normal_01" not in exempt
        assert "normal_02" not in exempt
        assert "main" in exempt
        assert "dev" in exempt
        assert "feature1" in exempt
        assert "feature2" in exempt


class TestGetBranchesToDelete:
    def test_branches_to_delete(self, mock_repo, mock_branch):
        normal_branch_01 = mock_branch("normal_01", protected=False, last_commit_days_ago=10)
        normal_branch_02 = mock_branch("normal_02", protected=False, last_commit_days_ago=15)
        normal_branch_03 = mock_branch("normal_03", protected=False, last_commit_days_ago=5)
        normal_branch_04 = mock_branch("normal_04", protected=False, last_commit_days_ago=12)
        normal_branch_05 = mock_branch("normal_05", protected=False, last_commit_days_ago=20)
        normal_branch_06 = mock_branch("normal_06", protected=False, last_commit_days_ago=10)

        # get all mock branches
        mock_repo.get_branches.return_value = [
            main,
            normal_branch_01,
            normal_branch_02,
            normal_branch_03,
            normal_branch_04,
            normal_branch_05,
            normal_branch_06,
        ]

        max_idle_days = 7
        exempt_branches = {"main", "normal_01", "normal_02"}
        cutoff_datetime = datetime.now(timezone.utc) - timedelta(days=max_idle_days)
        list_branches_to_delete, not_exempt_branch_count =\
            get_branches_to_delete(mock_repo, max_idle_days, exempt_branches, cutoff_datetime)

        # Total branches (7) - Exempt branches (3) = not_exempt_branch_count (4)
        # not_exempt_branch_count                  = not in list_branches_to_delete (1) + list_branches_to_delete (3)
        assert not_exempt_branch_count == 4
        assert len(list_branches_to_delete) == 3
        assert "normal_03" not in list_branches_to_delete
        assert "normal_04" in list_branches_to_delete
        assert "normal_05" in list_branches_to_delete
        assert "normal_06" in list_branches_to_delete


class TestDeleteBranches:
    def test_delete_with_branches_to_delete(self, mock_repo, mock_branch, capsys):
        dry_run = False
        max_idle_days = 7
        not_exempt_branch_count = 4

        list_branches_to_delete = ["normal_04", "normal_05", "normal_06"]

        mock_repo.get_branch(side_effect=[
            mock_branch("normal_04", last_commit_days_ago=12),
            mock_branch("normal_05", last_commit_days_ago=20),
            mock_branch("normal_06", last_commit_days_ago=10)
        ])

        delete_branches(mock_repo, dry_run, max_idle_days, list_branches_to_delete, not_exempt_branch_count)
        captured = capsys.readouterr()

        assert "branch is idle more than" in captured.out
        assert "normal" in captured.out

    def test_delete_without_branches_to_delete(self, mock_repo, capsys):
        dry_run = False
        max_idle_days = 7
        not_exempt_branch_count = 4

        delete_branches(mock_repo, dry_run, max_idle_days, [], not_exempt_branch_count)
        captured = capsys.readouterr()
        assert "There is no branch to delete" in captured.out


class TestMainCommand:
    def test_main_dry_run_true(self, capsys):
        """if run locally, export GH_TOKEN"""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dry-run", "true",
                "--repo-url", "https://github.com/tagdots-dev/branch-test",
                "--exclude-branches", "main",
                "--max-idle-days", "1"
            ]
        )

        # capsys to capture result.stdout and stderr
        print(result.stdout)
        print(result.stderr)

        # assertions
        assert result.exit_code == 0
        captured = capsys.readouterr()
        print(captured)

        assert "Starting to Delete GitHub Branches" in captured.out
        assert "dry-run: True" in captured.out
        assert "Total Number of Branches" in captured.out

    def test_main_dry_run_invalid_token(self, monkeypatch, capsys):
        monkeypatch.setenv("GH_TOKEN", "invalid_token")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dry-run", "true",
                "--repo-url", "https://github.com/tagdots-dev/branch-test",
                "--exclude-branches", "main",
                "--max-idle-days", "5"
            ]
        )

        # assertions
        assert result.exit_code == 1
        captured = capsys.readouterr()
        print(captured)

    def test_main_dry_run_invalid_inputs(self, capsys):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dry-run", "true",
                "--repo-url", "https://github.com/tagdots-dev/branch-test",
                "--exclude-branches", "main",
                "--max-idle-days", "hello"
            ]
        )

        # assertions
        assert result.exit_code == 1
        captured = capsys.readouterr()
        print(captured)


if __name__ == "__main__":
    pytest.main()
