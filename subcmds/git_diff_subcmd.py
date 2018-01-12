
import os

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

from topics import FormattedFile, GitProject, KrepError, Pattern, \
    RaiseExceptionIfOptionMissed, SubCommand


class RevisionError(KrepError):
    """Indicates the unknown revision."""


class GitDiffSubcmd(SubCommand):
    COMMAND = 'git-diff'

    REPORT_TEXT = 'report.txt'
    REPORT_HTML = 'report.html'

    FILTER_TEXT = 'filter.txt'
    FILTER_HTML = 'filter.html'

    HTML_CSS = (
        '<style type="text/css">\n'
        '  pre,code{font-family:courier;}\n'
        '  h5 {font-family: "Roboto", Sans-Serif;}\n'
        '  .details,\n'
        '  .show,\n'
        '  .hide:focus {display: none;}\n'
        '  .hide:focus + .show {display: inline;}\n'
        '  .hide:focus ~ #details {display: block;}\n\n'
        '  .hoverTable{font-family: verdana,arial,sans-serif;'
        'width:1200px;border-collapse:collapse;font-size:11px;'
        'text-align:left;}\n'
        '  .hoverTable td{padding:3px;}\n'
        '  .hoverTable tr{background: #b8d1f3;}\n'
        '  .hoverTable tr:nth-child(odd){background: #dae5f4;}\n'
        '  .hoverTable tr:nth-child(even){background: #ffffff;}\n'
        '  .hoverTable tr:hover {background-color: #bbbbbb;}\n'
        '  .sha1 {width:350px}\n'
        '  .email {width:200px}\n'
        '  .title {width:450px}\n'
        '</style>\n'
    )

    TABLE_CSS = ('sha1', 'email', 'email', 'title')

    help_summary = 'Generate report of the git commits between two SHA-1s'
    help_usage = """\
%prog [options] SHA-1 [SHA-1] ...

Generates the report of the commits between two SHA-1s in purposed format.

The sub-command provides to list the commits between SHA-1s. If only one SHA-1
provided, the scope would be all the heads to the commit. If specific email or
email pattern provided, the matched commits will be categorized into a
separated report either.

The output format would be set to the plain text or HTML with link to the
gerrit server which can provide a query of the commit if gerrit is enabled."""

    def options(self, optparse):
        SubCommand.options(self, optparse, modules=globals())

        options = optparse.add_option_group('Remote options')
        options.add_option(
            '-r', '--remote',
            dest='remote', action='store',
            help='Set the remote server location')

        options = optparse.add_option_group('Output options')
        options.add_option(
            '-o', '--output',
            dest='output', action='store',
            help='Set the output directory')
        options.add_option(
            '--gitiles',
            dest='gitiles', action='store_true',
            help='Enable gitiles links within the SHA-1')
        options.add_option(
            '--format',
            dest='format', metavar='TEXT, HTML, ALL',
            action='store', default='text',
            help='Set the report format')

    def execute(self, options, *args, **kws):
        SubCommand.execute(self, options, *args, **kws)

        RaiseExceptionIfOptionMissed(options.output, 'output is not set')

        name, remote = None, options.remote
        if options.remote:
            ulp = urlparse.urlparse(options.remote)
            if ulp.path:
                name = ulp.path.strip('/')
                remote = '%s://%s' % (ulp.scheme, ulp.hostname)
                if ulp.port:
                    remote += ':%d' % ulp.port

        format = options.format and options.format.lower()  # pylint: disable=W0622
        GitDiffSubcmd.generate_report(
            args, GitProject(None, worktree=options.working_dir),
            name or '', options.output, format, options.pattern,
            remote, options.gitiles)

    @staticmethod
    def build_pattern(patterns):
        if patterns:
            pats = list()
            for pat in patterns:
                if pat.find(':') > 0:
                    pats.append(pat)
                else:
                    pats.append('email:%s' % pat)

            pattern = Pattern(pats)
        else:
            pattern = Pattern()

        return pattern

    @staticmethod
    def generate_report(  # pylint: disable=R0915
            args, project, name, output, format,  # pylint: disable=W0622
            patterns, remote=None, gitiles=True):
        def _secure_sha(gitp, refs):
            ret, sha1 = gitp.rev_parse(refs)
            if ret == 0:
                return sha1
            else:
                ret, sha1 = gitp.rev_parse('%s/%s' % (project.remote, refs))
                if ret == 0:
                    return sha1

            raise RevisionError('Unknown %s' % refs)

        results = dict()
        pattern = GitDiffSubcmd.build_pattern(patterns)

        brefs = list()
        if len(args) < 2:
            if len(args) == 0:
                print('No SHA-1 provided, use HEAD by default')

            erefs = _secure_sha(project, args[0] if args else 'HEAD')
            ret, head = project.rev_list('--max-parents=0', erefs)
            if ret == 0:
                brefs.extend(head.split('\n'))
        else:
            erefs = _secure_sha(project, args[1])
            brefs.append(_secure_sha(project, args[0]))

        ftext = None
        fhtml = None
        ftextp = None
        fhtmlp = None
        if not os.path.exists(output):
            os.makedirs(output)

        # pylint: disable=W0622
        if format:
            if format in ('all', 'text'):
                ftext = FormattedFile.open(
                    os.path.join(output, GitDiffSubcmd.REPORT_TEXT),
                    name, FormattedFile.TEXT)

                if pattern:
                    ftextp = FormattedFile.open(
                        os.path.join(output, GitDiffSubcmd.FILTER_TEXT),
                        name, FormattedFile.TEXT)

            if format in ('all', 'html'):
                fhtml = FormattedFile.open(
                    os.path.join(output, GitDiffSubcmd.REPORT_HTML),
                    name, FormattedFile.HTML, css=GitDiffSubcmd.HTML_CSS)
                if pattern:
                    fhtmlp = FormattedFile.open(
                        os.path.join(output, GitDiffSubcmd.FILTER_HTML),
                        name, FormattedFile.HTML, css=GitDiffSubcmd.HTML_CSS)
        # pylint: enable=W0622

        logs = list()
        for ref in brefs:
            refs = '%s..%s' % (ref, erefs) \
                if len(brefs) > 0 and len(args) > 1 else '%s' % erefs

            ret, sha1s = project.log('--format="%H', '%s..%s' % (ref, erefs))
            if ret == 0:
                for sha1 in sha1s.split('\n'):
                    sha1 = sha1.strip('"')
                    if not sha1:
                        continue

                    values = list([sha1])
                    for item in ('%ae', '%ce', '%s'):
                        _, val = project.log(
                            '--format=%s' % item, '%s^..%s' % (sha1, sha1))
                        values.append(val.strip('"').strip())
                    logs.append(values)

            if ftext:
                column = [0, 0, 0, 0]
                for item in logs:
                    for k, col in enumerate(item):
                        length = len(col)
                        if length > column[k]:
                            column[k] = length

                ftext.section(refs)
                with ftext.table(column) as table:
                    for sha1, author, committer, subject in logs:
                        table.row(sha1, author, committer, subject)

                if ftextp:
                    ftextp.section(refs)
                    with ftextp.table(column) as table:
                        for sha1, author, committer, subject in logs:
                            if pattern.match('e,email', committer):
                                table.row(sha1, author, committer, subject)

            if fhtml:
                fhtml.section(refs)
                with fhtml.table(css='hoverTable') as table:
                    for sha1, author, committer, subject in logs:
                        hauthor = fhtml.item(author, 'mailto:%s' % author)
                        hcommitter = fhtml.item(
                            committer, 'mailto:%s' % committer)
                        if not remote:
                            table.row(
                                sha1, hauthor, hcommitter, subject,
                                td_csses=GitDiffSubcmd.TABLE_CSS)
                            continue

                        if gitiles and name:
                            sha1a = fhtml.item(
                                sha1[:20], '%s#/q/%s' % (remote, sha1))
                            sha1b = fhtml.item(
                                sha1[20:], '%s/plugins/gitiles/%s/+/%s^!'
                                % (remote, name, sha1))

                            table.row(
                                fhtml.item((sha1a, sha1b), tag='pre'),
                                hauthor, hcommitter, subject,
                                td_csses=GitDiffSubcmd.TABLE_CSS)
                        else:
                            link = fhtml.item(
                                sha1, '%s#/q/%s' % (remote, sha1), tag='pre')
                            table.row(
                                link, hauthor, hcommitter, subject,
                                td_csses=GitDiffSubcmd.TABLE_CSS)

                if fhtmlp:
                    fhtmlp.section(refs)
                    with fhtmlp.table(css='hoverTable') as table:
                        for sha1, author, committer, subject in logs:
                            if not pattern.match('e,email', committer):
                                continue

                            hauthor = fhtml.item(author, 'mailto:%s' % author)
                            hcommitter = fhtml.item(
                                committer, 'mailto:%s' % committer)
                            if not remote:
                                table.row(sha1, hauthor, hcommitter, subject)
                                continue

                            if gitiles and name:
                                sha1a = fhtmlp.item(
                                    sha1[:20], '%s#q,%s' % (remote, sha1))
                                sha1b = fhtmlp.item(
                                    sha1[20:], '%s/plugins/gitiles/%s/+/%s^!'
                                    % (remote, name, sha1))

                                table.row(
                                    fhtmlp.item((sha1a, sha1b), tag='pre'),
                                    hauthor, hcommitter, subject)
                            else:
                                link = fhtmlp.item(
                                    sha1, '%s#q,%s' % (remote, sha1),
                                    tag='pre')
                                table.row(link, hauthor, hcommitter, subject)

        if ftextp:
            ftextp.close()
        if fhtmlp:
            fhtmlp.close()
        if ftext:
            ftext.close()
        if fhtml:
            fhtml.close()

        return logs

    @staticmethod
    def _immediate(path, text, clean=False):
        filename = os.path.join(path, GitDiffSubcmd.IMMEDIATE_FILE)
        if clean and os.path.exists(filename):
            os.unlink(filename)

        if text:
            with open(filename, 'wb') as fp:
                fp.write(text)
