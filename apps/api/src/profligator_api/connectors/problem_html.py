"""Read only a provider's statement container, excluding navigation and editors."""

from html.parser import HTMLParser


class StatementContainer(HTMLParser):
    def __init__(self, platform: str):
        super().__init__(convert_charrefs=False)
        self.platform = platform
        self.depth = 0
        self.hidden = 0
        self.parts: list[str] = []
        self.found = 0
        self.complete = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "")
        is_statement = "problem-statement" in classes.split() if self.platform == "codeforces" else (
            attributes.get("id") == "problem-statement" or any(value in classes for value in (
                "problems_problem_content", "problems_problemContent", "problemStatement",
            )) or "problem-statement" in classes.split())
        if not self.depth:
            if not is_statement:
                return
            self.found += 1
            self.depth = 1
            return
        void = tag in {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
        if not void:
            self.depth += 1
        if self.hidden or (tag in {"script", "style", "button", "textarea"}
                           or "title" in classes.split() and self.platform == "codeforces"):
            if not self.hidden:
                self.hidden = self.depth
            return
        self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.depth or tag in {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}:
            return
        if self.hidden:
            if self.depth == self.hidden:
                self.hidden = 0
        elif self.depth > 1:
            self.parts.append(f"</{tag}>")
        self.depth -= 1
        if self.depth == 0:
            self.complete = True

    def handle_data(self, data):
        if self.depth and not self.hidden:
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def problem_html(html: str, platform: str) -> str | None:
    parser = StatementContainer(platform)
    parser.feed(html)
    if parser.found != 1 or not parser.complete or parser.depth:
        return None
    return "".join(parser.parts).strip() or None
