"""Small lexical helpers, preserving offsets; this is not a TeX interpreter."""
import re


def masked_text(text: str) -> str:
    """Hide comments and literal regions without changing source offsets."""
    chars = list(text)
    pattern = re.compile(
        r'(?<!\\)\\begin\{(verbatim\*?|Verbatim|lstlisting|minted)\}.*?\\end\{\1\}'
        r'|(?<!\\)\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)'
        r'|(?P<comment>(?<!\\)(?:\\\\)*%[^\n]*)', re.S)
    for match in pattern.finditer(text):
        chars[match.start():match.end()] = ['\n' if c == '\n' else ' ' for c in match.group()]
    return ''.join(chars)


def group_at(text: str, start: int, opening: str = '{', closing: str = '}'):
    """Return (contents, end) for a balanced group after optional whitespace."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start == len(text) or text[start] != opening:
        return None
    stack = [closing]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == '{':
            stack.append('}')
        elif char == opening and (opening != '[' or stack[-1] != '}'):
            stack.append(closing)
        elif char == stack[-1]:
            stack.pop()
            if not stack:
                return text[start + 1:index], index + 1
        index += 1
    return None


def command_option_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Consecutive optional groups after a control word, on a lexical mask.

    Whitespace/comment gaps and nested groups do not end an option sequence.
    A mandatory argument or prose does end it; do not consume a subsequent
    real prose citation after, for example, ``\\emph{Text} [key]``.
    """
    ranges = []
    for command in re.finditer(r'(?<!\\)\\[A-Za-z@]+\*?', text):
        cursor = command.end()
        while True:
            start = cursor
            while start < len(text) and text[start].isspace():
                start += 1
            if start == len(text) or text[start] != '[':
                break
            option = group_at(text, start, '[', ']')
            if option is None:
                ranges.append((start, len(text)))
                break
            ranges.append((start, option[1]))
            cursor = option[1]
    return tuple(ranges)


def environment_blocks(text: str, environment: str):
    scan = masked_text(text)
    begin = re.compile(r'(?<!\\)\\begin\s*\{' + re.escape(environment) + r'\}')
    end = re.compile(r'(?<!\\)\\end\s*\{' + re.escape(environment) + r'\}')
    for match in begin.finditer(scan):
        finish = end.search(scan, match.end())
        if finish is None:
            continue
        optional = group_at(scan, match.end(), '[', ']')
        malformed_title = scan[match.end():finish.start()].lstrip().startswith('[') and optional is None
        body_start = optional[1] if optional else match.end()
        # Read source, not the lexical mask, so every span remains reproducible.
        body = text[body_start:finish.start()]
        left = body_start + len(body) - len(body.lstrip())
        right = left + len(body.strip())
        title = text[scan.find('[', match.end()) + 1:optional[1] - 1] if optional else None
        if malformed_title:
            title = ''  # Unsupported explicit syntax must never use proximity.
        yield match.start(), finish.end(), title, text[left:right], left, right
