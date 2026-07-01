"""Tests for RAG document loaders."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.rag import LoaderConfig, load_directory, load_document
from agentx.rag.loaders import _detect_type


class TestDetectType:
    """Verify extension-to-type mapping."""

    def test_pdf(self) -> None:
        assert _detect_type(Path("x.pdf")) == "pdf"

    def test_excel(self) -> None:
        assert _detect_type(Path("x.xlsx")) == "excel"
        assert _detect_type(Path("x.xls")) == "excel"
        assert _detect_type(Path("x.xlsm")) == "excel"

    def test_csv(self) -> None:
        assert _detect_type(Path("x.csv")) == "csv"

    def test_word(self) -> None:
        assert _detect_type(Path("x.docx")) == "word"

    def test_text(self) -> None:
        assert _detect_type(Path("x.txt")) == "txt"

    def test_markdown(self) -> None:
        assert _detect_type(Path("x.md")) == "md"
        assert _detect_type(Path("x.markdown")) == "md"

    def test_unknown_defaults_to_txt(self) -> None:
        assert _detect_type(Path("x.xyz")) == "txt"


class TestLoadDocument:
    """Verify load_document + LoaderConfig."""

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_document("/tmp/agentx-nonexistent-file-12345.txt")

    def test_loads_txt(self, tmp_path: Path) -> None:
        fp = tmp_path / "sample.txt"
        fp.write_text("Line one.\nLine two.\n", encoding="utf-8")
        result = load_document(fp)
        assert result == ["Line one.\nLine two.\n"]

    def test_loads_md(self, tmp_path: Path) -> None:
        fp = tmp_path / "readme.md"
        fp.write_text("# Title\n\nBody.", encoding="utf-8")
        result = load_document(fp)
        assert len(result) == 1
        assert "Title" in result[0]

    def test_loads_csv(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        fp.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        result = load_document(fp)
        assert len(result) == 1
        assert "Alice" in result[0]
        assert "Bob" in result[0]

    def test_empty_text_file(self, tmp_path: Path) -> None:
        fp = tmp_path / "empty.txt"
        fp.write_text("", encoding="utf-8")
        assert load_document(fp) == []


class TestLoadDirectory:
    """Verify load_directory."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert load_directory(tmp_path) == {}

    def test_loads_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("Text A")
        (tmp_path / "b.md").write_text("# Markdown B")
        (tmp_path / "c.csv").write_text("col\nrow1\n")
        result = load_directory(tmp_path)
        assert set(result.keys()) == {"a.txt", "b.md", "c.csv"}

    def test_ignores_unsupported_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "note.txt").write_text("Kept")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        result = load_directory(tmp_path)
        assert "note.txt" in result
        assert "image.png" not in result

    def test_skips_readme_and_dotfiles(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("Skip me")
        (tmp_path / ".hidden.txt").write_text("Skip me too")
        (tmp_path / "real.txt").write_text("Keep me")
        result = load_directory(tmp_path)
        assert "real.txt" in result
        assert "README.md" not in result
        assert ".hidden.txt" not in result


class TestLoaderConfig:
    """Verify LoaderConfig defaults + acceptance of options."""

    def test_defaults(self) -> None:
        cfg = LoaderConfig()
        assert cfg.doc_type == "auto"
        assert cfg.encoding == "utf-8"
        assert cfg.extract_images is False

    def test_max_rows(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        fp.write_text("a\n1\n2\n3\n4\n5\n")
        result = load_document(fp, LoaderConfig(max_rows=3))
        # max_rows caps total rows read (header + data lines).
        assert "1" in result[0]
        assert "5" not in result[0]  # last row must be truncated
