"""Render generated CLI examples for the named shell, with explicit options."""

from __future__ import annotations

import shlex


def cli_command(command: str, *, workspace: str = '<WORKSPACE>',
                shell: str = 'powershell', **options: str) -> str:
    """Quote every value; PowerShell literals and POSIX quotes are distinct."""
    def quote(value):
        value = str(value)
        if shell == 'powershell':
            return "'" + value.replace("'", "''") + "'"
        if shell == 'posix':
            return shlex.quote(value)
        raise ValueError(f'Unsupported command shell: {shell}')

    args = ['papergraph-mcp', command, '--workspace', quote(workspace)]
    for name, value in options.items():
        args.extend(['--' + name.replace('_', '-'), quote(value)])
    return ' '.join(args)
