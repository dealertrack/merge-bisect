#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)
import argparse
import datetime
import subprocess
import sys
from collections import OrderedDict
from contextlib import contextmanager


class Call(object):
    def __init__(self, cmd):
        self._p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.stdout, self.stderr = self._p.communicate()
        self.returncode = self._p.returncode

    def __bool__(self):
        return self.returncode == 0

    __nonzero__ = __bool__


class Commit(object):
    def __init__(self, date, sha1, author, description):
        self.datetime = datetime.datetime.fromtimestamp(int(date))
        self.sha1 = sha1
        self.author = author
        self.description = description

    @classmethod
    def from_log(cls, s, delimiter='\t'):
        return cls(*s.split(delimiter))

    def __repr__(self):
        return (
            '<{} "{datetime}" {sha1} "{author}" "{description}">'
            ''.format(self.__class__.__name__, **vars(self))
        )

    def __eq__(self, other):
        return self.sha1 == other.sha1


def commits_for_n_days(days):
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    cmd = (
        'git log '
        '--first-parent '
        '--pretty="format:%at\t%H\t%an\t%s" '
        '--since={since}'
    ).format(since=since.strftime('%Y-%m-%d'))

    return [
        Commit.from_log(i)
        for i in Call(cmd).stdout.splitlines()
        if i
    ]


def current_branch():
    return Call("git branch | grep '*' | awk '{print $2}'").stdout


def checkout(sha1):
    Call('git checkout {}'.format(sha1))


@contextmanager
def stay_on_branch():
    branch = current_branch()
    try:
        yield
    finally:
        checkout(branch)


def call_on_commit(cmd, commit, verbose=False):
    checkout(commit.sha1)
    c = Call(cmd)

    if verbose:
        print('\n' * 2)

    if c:
        print('PASSED: {!r}'.format(commit))
    else:
        print('FAILED: {!r}'.format(commit))

    if verbose:
        print('=' * 150)
        print(c.stdout)
        print('=' * 150)
        print('\n' * 3)

    return c


parser = argparse.ArgumentParser(
    description='Like git bisect, but on merge commits.'
)

parser.add_argument(
    'cmd',
    help='Command to run in order to find whether the commit is good or bad. ',
)
parser.add_argument(
    '--days',
    type=int,
    default=30,
    help='Check merge commits only going this many days '
         'in the past against the given command.',
)
parser.add_argument(
    '-v', '--verbose',
    dest='verbose',
    action='store_true',
    default=False,
    help='Print stdout while running each command.'
)


def main():
    args = parser.parse_args()

    with stay_on_branch():
        all_commits = OrderedDict((i, None) for i in reversed(commits_for_n_days(args.days)))
        commits = all_commits.keys()

        print('Found {} commits'.format(len(commits)))
        print('')

        if len(commits) < 2:
            print('At least 2 merge commits must be present in order to bisect on merges', file=sys.stderr)
            return 1

        commit = commits[0]
        commits.remove(commit)
        commit_call = call_on_commit(args.cmd, commit, args.verbose)
        all_commits[commit] = bool(commit_call)
        if not commit_call:
            print(
                'Earliest commit {!r} already fails running "{}". '
                'At least one passing commit should be succeeding in the resultset to do bisect.'
                ''.format(commit, args.cmd)
            )
            return 1

        commit = commits[-1]
        commits.remove(commit)
        commit_call = call_on_commit(args.cmd, commit, args.verbose)
        all_commits[commit] = bool(commit_call)
        if commit_call:
            print(
                'Latest commit {!r} already succeeds running "{}". '
                'At least one passing commit should be failing in the resultset to do bisect.'
                ''.format(commit, args.cmd)
            )
            return 1

        while commits:
            middle = len(commits) // 2
            commit = commits[middle]
            commit_call = call_on_commit(args.cmd, commit, args.verbose)
            all_commits[commit] = bool(commit_call)

            if commit_call:
                for c in commits[:middle]:
                    all_commits[c] = bool(commit_call)
                commits = commits[middle + 1:]

            else:
                for c in commits[middle + 1:]:
                    all_commits[c] = bool(commit_call)
                commits = commits[:middle]

        bad_commit = next(commit for commit, is_good in all_commits.items() if not is_good)

        print('')
        print('Done')

        print('')
        print('Commit log (last commit first):')
        for commit, is_good in reversed(all_commits.items()):
            t = 'SUCCESS' if is_good else 'FAILURE'
            print('{}: {!r}'.format(t, commit))

        print()
        print('BAD COMMIT: {!r}'.format(bad_commit))

    return 0


if __name__ == '__main__':
    exit(main())
