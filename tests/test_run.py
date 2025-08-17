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
    get_exempt_branches,
    get_owner_repo,
    get_qualified_branches,
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


class TestCheckUserInputs:
    def test_user_inputs_success(self):
        repo = Mock()
        assert check_user_inputs(repo, "https://github.com/owner/repo", {'main', 'badges'}, 5)

    def test_user_inputs_max_idle_days_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, '')

    def test_user_inputs_max_idle_days_negative(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, -1)

    def test_user_inputs_max_idle_days_string(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", {'main'}, 'hello')

    def test_user_inputs_exclude_branch_not_set_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", '', 20)

    def test_user_inputs_exclude_branch_not_set_main(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", 'main', 10)

    def test_user_inputs_repo_url_invalid(self):
        repo = Mock()
        assert not check_user_inputs(repo, "invalid_url", {'main'}, 15)

    def test_user_inputs_repo_url_null(self):
        repo = Mock()
        assert not check_user_inputs(repo, '', {'main'}, 50)


class TestGetExemptBranches:
    def test_exempt_branches(self, mock_repo, mock_branch, mock_pull):
        # mock protected branches
        protected_branch_01 = mock_branch("protected_01", protected=True)
        protected_branch_02 = mock_branch("protected_02", protected=True)

        # mock normal branches
        normal_branch_01 = mock_branch("normal_01", protected=False, last_commit_days_ago=10)
        normal_branch_02 = mock_branch("normal_02", protected=False, last_commit_days_ago=15)
        normal_branch_03 = mock_branch("normal_03", protected=False, last_commit_days_ago=5)
        normal_branch_04 = mock_branch("normal_04", protected=False, last_commit_days_ago=2)
        normal_branch_05 = mock_branch("normal_05", protected=False, last_commit_days_ago=20)
        normal_branch_06 = mock_branch("normal_06", protected=False, last_commit_days_ago=8)

        # get all mock branches
        mock_repo.get_branches.return_value = [
            protected_branch_01,
            protected_branch_02,
            normal_branch_01,
            normal_branch_02,
            normal_branch_03,
            normal_branch_04,
            normal_branch_05,
            normal_branch_06,
        ]

        # mock PRs
        pull_01 = mock_pull("main", "feature1")
        pull_02 = mock_pull("dev", "feature2")
        mock_repo.get_pulls.return_value = [pull_01, pull_02]

        # create exempt set
        exempt = get_exempt_branches(mock_repo, exclude_branches=set(["custom-exempt"]))

        # assert branches in or not in exempt
        assert "protected_01" in exempt
        assert "protected_02" in exempt
        assert "normal_01" not in exempt
        assert "normal_02" not in exempt
        assert "normal_03" not in exempt
        assert "normal_04" not in exempt
        assert "normal_05" not in exempt
        assert "normal_06" not in exempt
        assert "main" in exempt
        assert "dev" in exempt
        assert "feature1" in exempt
        assert "feature2" in exempt
        assert "custom-exempt" in exempt


class TestGetQualifiedBranches:
    def test_qualified_branches(self, mock_repo, mock_branch):
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

        exempt_branches = {"main", "normal_01", "normal_02"}
        cutoff_datetime = datetime.now(timezone.utc) - timedelta(days=7)
        qualified, total = get_qualified_branches(mock_repo, exempt_branches, cutoff_datetime)

        # qualified branches will be deleted
        # Total (7) - Exempt branches (3) - Not qualified (1 [normal_03]) = 3 qualified
        assert total == 7
        assert len(qualified) == 3
        assert "normal_03" not in qualified
        assert "normal_04" in qualified
        assert "normal_05" in qualified
        assert "normal_06" in qualified


class TestDeleteBranches:
    def test_delete_with_qualified_branches(self, mock_repo, mock_branch, capsys):
        dry_run = False

        qualified_branches = ["normal_04", "normal_05", "normal_06"]

        mock_repo.get_branch(side_effect=[
            mock_branch("normal_04", last_commit_days_ago=12),
            mock_branch("normal_05", last_commit_days_ago=20),
            mock_branch("normal_06", last_commit_days_ago=10)
        ])

        cutoff_datetime = datetime.now(timezone.utc) - timedelta(days=7)
        delete_branches(mock_repo, dry_run, cutoff_datetime, qualified_branches)

        captured = capsys.readouterr()

        assert "Deleting Branch(es) older than" in captured.out
        assert "✅ Deleted branch" in captured.out
        assert "normal" in captured.out

    def test_delete_without_qualified_branches(self, mock_repo, capsys):
        dry_run = False
        delete_branches(mock_repo, dry_run, datetime.now(timezone.utc), [])
        captured = capsys.readouterr()
        assert "There is no qualified branch to delete" in captured.out


class TestMainCommand:
    def test_main_dry_run_true(self, capsys):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dry-run", "true",
                "--repo-url", "https://github.com/tagdots-dev/branch-test",
                "--exclude-branch", "main",
                "--exclude-branch", "badges",
                "--max-idle-days", 1
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
                "--exclude-branch", "main",
                "--exclude-branch", "badges",
                "--max-idle-days", 5
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
                "--exclude-branch", "main",
                "--exclude-branch", "badges",
                "--max-idle-days", "hello"
            ]
        )

        # assertions
        assert result.exit_code == 1
        captured = capsys.readouterr()
        print(captured)


if __name__ == "__main__":
    pytest.main()
