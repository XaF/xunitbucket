#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# xunitbucket - script that allows to read a xunit.xml
# file, format it in markdown and post it as a comment
# on bitbucket. All the options needed can be seen by
# using xunitbucket --help
#
# Raphaël Beamonte <raphael.beamonte@bhvr.com>
#

import argparse
import os
import requests
import sys
import time

from lxml import etree

try:
    # Python 3.4+
    import html
    htmlunescape = html.unescape
except ImportError:
    try:
        # Python 2.6-2.7
        from HTMLParser import HTMLParser
    except ImportError:
        # Python 3.0-3.3
        from html.parser import HTMLParser
    htmlunescape = HTMLParser().unescape


xunit_message_header = "# Failed on {testname}: {failures} failure(s), {errors} error(s) and {skip} skipped for {tests} tests #\n*Build{build} on {timestamp}*"
xunit_message_entry = "* **{status}** {class} / {test}\n```node\n{traceback}\n```"
xunit_message_join_entries = "\n\n"
xunit_message = "{header}\n\n{entries}"

lint_message_header = "# Failed on {testname}: {error_count}#\n*Build{build} on {timestamp}*"
lint_message_entry_file = "* **{filename}**: {file_error_count}\n{error_entries}\n"
lint_message_entry_error = "    * **{severity}** on line {line}, column {column}\n```\n{message}\n```"
lint_message_join_entries_file = "\n\n"
lint_message_join_entries_error = "\n\n"
lint_message = "{header}\n\n{file_entries}"


def format_report_xunit(testsuite):
    headervars = {
        'testname': args.test,
        'tests': int(testsuite.get('tests')),
        'build': '' if args.build < 0 else ' %d' % args.build
    }
    for word in ('errors', 'failures', 'skip'):
        headervars[word] = int(testsuite.get(word, 0))
    headervars['time'] = float(testsuite.get('time', 0))
    headervars['timestamp'] = testsuite.get('timestamp', 'unknown')

    entries = []
    for testcase in testsuite.getchildren():
        report = testcase.getchildren()[0] if testcase.getchildren() else None
        if report is not None and report.tag.lower() != 'skipped':
            entryvars = {
                'status': testcase.get('status', report.tag).capitalize(),
                'class': testcase.get('classname'),
                'test': testcase.get('name'),
                'traceback': htmlunescape(report.text)
            }
            entries.append(xunit_message_entry.format(**entryvars))

    messagevars = {
        'header': xunit_message_header.format(**headervars),
        'entries': xunit_message_join_entries.join(entries)
    }
    return xunit_message.format(**messagevars)


def format_report_lint(checkstyle):
    error_count = {}
    file_entries = []

    for fileelem in checkstyle.findall('file'):

        file_error_count = {}
        error_entries = []

        for errorelem in fileelem.findall('error'):
            severity = errorelem.get('severity')

            file_error_count[severity] = file_error_count.get(severity, 0) + 1
            error_count[severity] = error_count.get(severity, 0) + 1

            error_entryvars = {
                'line': errorelem.get('line'),
                'column': errorelem.get('column'),
                'severity': severity.capitalize(),
                'message': errorelem.get('message'),
            }
            error_entries.append(
                lint_message_entry_error.format(**error_entryvars))

        filename = fileelem.get('name')
        if args.workspace is not None and filename.startswith(args.workspace):
            filename = filename[len(args.workspace):]

        file_entryvars = {
            'filename': filename,
            'error_entries': lint_message_join_entries_error.join(error_entries),
            'file_error_count': ', '.join([
                '{} {}(s)'.format(v, k)
                for k, v in file_error_count.items()]),
        }
        file_entries.append(
            lint_message_entry_file.format(**file_entryvars))

    headervars = {
        'testname': args.test,
        'build': '' if args.build < 0 else ' %d' % args.build,
        'timestamp': time.strftime(
            '%c',
            time.localtime(os.path.getmtime(args.reportfile))),
        'error_count': ', '.join([
            '{} {}(s)'.format(v, k)
            for k, v in error_count.items()]),
    }

    messagevars = {
        'header': lint_message_header.format(**headervars),
        'file_entries': lint_message_join_entries_file.join(file_entries)
    }
    return lint_message.format(**messagevars)


def post_comment(content):
    # Check if there is any comment from our user
    comment_url = 'https://api.bitbucket.org/1.0/repositories/{accountname}/{repo_slug}/{type}/{id}/comments'.format(**repository)
    if args.delete:
        # Get own username
        user_url = 'https://api.bitbucket.org/2.0/user'
        r = requests.get(user_url, auth=auth)
        assert r.status_code == 200
        bitbucket_user = r.json()['username']

        # Get list of comments on the change
        r = requests.get(comment_url, auth=auth)
        assert r.status_code == 200
        for comment in r.json():
            if comment['deleted']: continue
            if comment['username'] == bitbucket_user:
                # For each comment matching the username, send a delete request
                delete_url = 'https://api.bitbucket.org/1.0/repositories/{accountname}/{repo_slug}/{type}/{id}/comments/{comid}'.format(comid=str(comment['comment_id']), **repository)
                r = requests.delete(delete_url, auth=auth)
                assert r.status_code == 200

    r = requests.post(comment_url, auth=auth, data={'content': str(content)})
    assert r.status_code == 200


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Submit a well formatted Markdown '
                    'comment to Bitbucket from a xunit.xml '
                    'or lint.xml file')
    parser.add_argument('reportfile',
        help='The xml file to use')

    parser.add_argument('-t', '--test', required=True,
        help='The name of the test to use in the comment')

    parser.add_argument('-u', '--username', required=True,
        help='The bitbucket user username')
    parser.add_argument('-p', '--password', required=True,
        help='The bitbucket user password')

    parser.add_argument('-a', '--accountname', required=True,
        help='The bitbucket repository account name')
    parser.add_argument('-r', '--reposlug', required=True,
        help='The bitbucket repository slug')
    parser.add_argument('-b', '--build', type=int, default=-1,
        help='The build number')

    type_group = parser.add_mutually_exclusive_group(required=True)
    type_group.add_argument('--pullrequest', dest='type',
        action='store_const', const='pullrequests',
        help='If the change is a pull request')
    type_group.add_argument('--commit', dest='type',
        action='store_const', const='changesets',
        help='If the change is a commit')

    parser.add_argument('-i', '--changeid', required=True,
        help='The change id')

    parser.add_argument('-d', '--delete', action='store_true',
        help='Whether to delete old comments or not')

    parser.add_argument('-w', '--workspace',
        help='The workspace path to remove from the beginning of the '
             'file path when treating a lint report')

    args = parser.parse_args()

    repository = {
        'accountname': args.accountname,
        'repo_slug': args.reposlug,
        'type': args.type,
        'id': args.changeid
    }
    auth = (args.username, args.password)

    data = etree.parse(args.reportfile)
    root = data.getroot()

    if root.tag == 'testsuite':
        report = format_report_xunit(root)
    elif root.tag == 'checkstyle':
        report = format_report_lint(root)
    else:
        parser.print_usage()
        print('{}: error: {}'.format(
            os.path.basename(__file__),
            'Unknown XML type (tag = {})'.format(root.tag)))
        sys.exit(1)

    post_comment(report)
    print('Comment posted.')
