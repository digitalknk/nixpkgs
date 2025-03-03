import argparse
import json

from abc import abstractmethod
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any, cast, NamedTuple, Optional, Union
from xml.sax.saxutils import escape, quoteattr
from markdown_it.token import Token
from markdown_it.utils import OptionsDict

from .docbook import DocBookRenderer
from .md import Converter

class RenderedSection:
    id: Optional[str]
    chapters: list[str]

    def __init__(self, id: Optional[str]) -> None:
        self.id = id
        self.chapters = []

class BaseConverter(Converter):
    _sections: list[RenderedSection]

    def __init__(self, manpage_urls: dict[str, str]):
        super().__init__(manpage_urls)
        self._sections = []

    def add_section(self, id: Optional[str], chapters: list[Path]) -> None:
        self._sections.append(RenderedSection(id))
        for chpath in chapters:
            try:
                with open(chpath, 'r') as f:
                    self._md.renderer._title_seen = False # type: ignore[attr-defined]
                    self._sections[-1].chapters.append(self._render(f.read()))
            except Exception as e:
                raise RuntimeError(f"failed to render manual chapter {chpath}") from e

    @abstractmethod
    def finalize(self) -> str: raise NotImplementedError()

class ManualDocBookRenderer(DocBookRenderer):
    # needed to check correctness of chapters.
    # we may want to use front matter instead of this kind of heuristic.
    _title_seen = False

    def _heading_tag(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
                     env: MutableMapping[str, Any]) -> tuple[str, dict[str, str]]:
        (tag, attrs) = super()._heading_tag(token, tokens, i, options, env)
        if self._title_seen:
            if token.tag == 'h1':
                assert token.map is not None
                raise RuntimeError(
                    "only one title heading (# [text...]) allowed per manual chapter "
                    f"but found a second in lines [{token.map[0]}..{token.map[1]}]. "
                    "please remove all such headings except the first, split your "
                    "chapters, or demote the subsequent headings to (##) or lower.",
                    token)
            return (tag, attrs)
        self._title_seen = True
        return ("chapter", attrs | {
            'xmlns': "http://docbook.org/ns/docbook",
            'xmlns:xlink': "http://www.w3.org/1999/xlink",
        })

    # TODO minimize docbook diffs with existing conversions. remove soon.
    def paragraph_open(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
                       env: MutableMapping[str, Any]) -> str:
        return super().paragraph_open(token, tokens, i, options, env) + "\n "
    def paragraph_close(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
                        env: MutableMapping[str, Any]) -> str:
        return "\n" + super().paragraph_close(token, tokens, i, options, env)
    def code_block(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
                   env: MutableMapping[str, Any]) -> str:
        return f"<programlisting>\n{escape(token.content)}</programlisting>"
    def fence(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
              env: MutableMapping[str, Any]) -> str:
        # HACK for temporarily being able to replace md-to-db.sh. pandoc used this syntax to
        # allow md files to inject arbitrary docbook, and manual chapters use it.
        if token.info == '{=docbook}':
            return token.content
        info = f" language={quoteattr(token.info)}" if token.info != "" else ""
        return f"<programlisting{info}>\n{escape(token.content)}</programlisting>"

class DocBookSectionConverter(BaseConverter):
    __renderer__ = ManualDocBookRenderer

    def finalize(self) -> str:
        result = []

        for section in self._sections:
            id = "id=" + quoteattr(section.id) if section.id is not None else ""
            result.append(f'<section {id}>')
            result += section.chapters
            result.append(f'</section>')

        return "\n".join(result)

class ManualFragmentDocBookRenderer(ManualDocBookRenderer):
    _tag: str = "chapter"

    def _heading_tag(self, token: Token, tokens: Sequence[Token], i: int, options: OptionsDict,
                     env: MutableMapping[str, Any]) -> tuple[str, dict[str, str]]:
        (tag, attrs) = super()._heading_tag(token, tokens, i, options, env)
        if token.tag == 'h1':
            return (self._tag, attrs | { 'xmlns:xi': "http://www.w3.org/2001/XInclude" })
        return (tag, attrs)

class DocBookFragmentConverter(Converter):
    __renderer__ = ManualFragmentDocBookRenderer

    def convert(self, file: Path, tag: str) -> str:
        assert isinstance(self._md.renderer, ManualFragmentDocBookRenderer)
        try:
            with open(file, 'r') as f:
                self._md.renderer._title_seen = False
                self._md.renderer._tag = tag
                return self._render(f.read())
        except Exception as e:
            raise RuntimeError(f"failed to render manual {tag} {file}") from e



class Section:
    id: Optional[str] = None
    chapters: list[str]

    def __init__(self) -> None:
        self.chapters = []

class SectionAction(argparse.Action):
    def __call__(self, parser: argparse.ArgumentParser, ns: argparse.Namespace,
                 values: Union[str, Sequence[Any], None], opt_str: Optional[str] = None) -> None:
        sections = getattr(ns, self.dest)
        if sections is None: sections = []
        sections.append(Section())
        setattr(ns, self.dest, sections)

class SectionIDAction(argparse.Action):
    def __call__(self, parser: argparse.ArgumentParser, ns: argparse.Namespace,
                 values: Union[str, Sequence[Any], None], opt_str: Optional[str] = None) -> None:
        sections = getattr(ns, self.dest)
        if sections is None: raise argparse.ArgumentError(self, "no active section")
        sections[-1].id = cast(str, values)

class ChaptersAction(argparse.Action):
    def __call__(self, parser: argparse.ArgumentParser, ns: argparse.Namespace,
                 values: Union[str, Sequence[Any], None], opt_str: Optional[str] = None) -> None:
        sections = getattr(ns, self.dest)
        if sections is None: raise argparse.ArgumentError(self, "no active section")
        sections[-1].chapters.extend(map(Path, cast(Sequence[str], values)))

class SingleFileAction(argparse.Action):
    def __call__(self, parser: argparse.ArgumentParser, ns: argparse.Namespace,
                 values: Union[str, Sequence[Any], None], opt_str: Optional[str] = None) -> None:
        assert isinstance(values, Sequence)
        chapters = getattr(ns, self.dest) or []
        chapters.append((Path(values[0]), Path(values[1])))
        setattr(ns, self.dest, chapters)

def _build_cli_db_section(p: argparse.ArgumentParser) -> None:
    p.add_argument('--manpage-urls', required=True)
    p.add_argument("outfile")
    p.add_argument("--section", dest="contents", action=SectionAction, nargs=0)
    p.add_argument("--section-id", dest="contents", action=SectionIDAction)
    p.add_argument("--chapters", dest="contents", action=ChaptersAction, nargs='+')

def _build_cli_db_fragment(p: argparse.ArgumentParser) -> None:
    p.add_argument('--manpage-urls', required=True)
    p.add_argument("--chapter", action=SingleFileAction, required=True, nargs=2)
    p.add_argument("--section", action=SingleFileAction, required=True, nargs=2)

def _run_cli_db_section(args: argparse.Namespace) -> None:
    with open(args.manpage_urls, 'r') as manpage_urls:
        md = DocBookSectionConverter(json.load(manpage_urls))
        for section in args.contents:
            md.add_section(section.id, section.chapters)
        with open(args.outfile, 'w') as f:
            f.write(md.finalize())

def _run_cli_db_fragment(args: argparse.Namespace) -> None:
    with open(args.manpage_urls, 'r') as manpage_urls:
        md = DocBookFragmentConverter(json.load(manpage_urls))
        for kind in [ 'chapter', 'section' ]:
            for (target, file) in getattr(args, kind):
                converted = md.convert(file, kind)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(converted)

def build_cli(p: argparse.ArgumentParser) -> None:
    formats = p.add_subparsers(dest='format', required=True)
    _build_cli_db_section(formats.add_parser('docbook-section'))
    _build_cli_db_fragment(formats.add_parser('docbook-fragment'))

def run_cli(args: argparse.Namespace) -> None:
    if args.format == 'docbook-section':
        _run_cli_db_section(args)
    elif args.format == 'docbook-fragment':
        _run_cli_db_fragment(args)
    else:
        raise RuntimeError('format not hooked up', args)
