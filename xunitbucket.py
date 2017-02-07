#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import requests

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


message_header = "# {testname}: {failures} failure(s), {errors} error(s) and {skip} skipped for {tests} tests #"
message_entry = "* **{status}** {class} / {test}\n```node\n{traceback}\n```"
message_join_entries = "\n\n"
message = "{header}\n\n{entries}"


def format_report(xunitfile):
    data = etree.parse(xunitfile)

    testsuite = data.getroot()
    headervars = {
        'testname': args.test,
        'tests': int(testsuite.get('tests'))
    }
    for word in ('errors', 'failures', 'skip'):
        headervars[word] = int(testsuite.get(word, 0))

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
            entries.append(message_entry.format(**entryvars))

    messagevars = {
        'header': message_header.format(**headervars),
        'entries': message_join_entries.join(entries)
    }
    return message.format(**messagevars)

def post_comment(content):
    # Get own username to find own comments
    user_url = 'https://api.bitbucket.org/2.0/user'
    r = requests.get(user_url, auth=auth)
    bitbucket_user = r.json()['username']

    # Check if there is any comment from our user
    comment_url = 'https://api.bitbucket.org/1.0/repositories/{accountname}/{repo_slug}/{type}/{id}/comments'.format(**repository)
    r = requests.get(comment_url, auth=auth)
    for comment in r.json():
        if comment['deleted']: continue
        if comment['username'] == bitbucket_user:
            delete_url = 'https://api.bitbucket.org/1.0/repositories/{accountname}/{repo_slug}/{type}/{id}/comments/{comid}'.format(comid=str(comment['comment_id']), **repository)
            r = requests.delete(delete_url, auth=auth)

    r = requests.post(comment_url, auth=auth, data={'content': str(content)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Submit a well formatted Markdown '
                    'comment to Bitbucket from a xunit.xml file')
    parser.add_argument('xunitfile',
        help='The xunit.xml file to use')

    parser.add_argument('-t', '--test', required=True,
        help='The name of the test to use in the comment')

    parser.add_argument('-p', '--password', required=True,
        help='The bitbucket user password')
    parser.add_argument('-u', '--username', required=True,
        help='The bitbucket user username')

    parser.add_argument('-a', '--accountname', required=True,
        help='The bitbucket repository account name')
    parser.add_argument('-r', '--reposlug', required=True,
        help='The bitbucket repository slug')

    type_group = parser.add_mutually_exclusive_group(required=True)
    type_group.add_argument('--pullrequest', dest='type',
        action='store_const', const='pullrequests',
        help='If the change is a pull request')
    type_group.add_argument('--commit', dest='type',
        action='store_const', const='changesets',
        help='If the change is a commit')

    parser.add_argument('-i', '--changeid', required=True,
        help='The change id')

    args = parser.parse_args()

    repository = {
        'accountname': args.accountname,
        'repo_slug': args.reposlug,
        'type': args.type,
        'id': args.changeid
    }
    auth = (args.username, args.password)

    post_comment(format_report(args.xunitfile))
    print('Comment posted.')
