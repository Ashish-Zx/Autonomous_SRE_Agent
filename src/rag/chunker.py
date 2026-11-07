"""
Parent-Child Markdown Runbook Chunker (Module 4).
Splits engineering runbooks into:
- Parent Chunks: Comprehensive sections (e.g., full Diagnostic Workflow or Remediation)
- Child Chunks: Granular symptom keywords, exact error codes, and tool commands.

This allows sparse and dense retrieval to match precise error codes while passing
the full parent section context to the LLM.
"""

import re
import uuid
from pathlib import Path
from typing import Dict, List, Any


class MarkdownDocumentChunk:
    """Represents a chunk with parent-child linkage."""
    def __init__(
        self,
        chunk_id: str,
        parent_id: str,
        doc_name: str,
        title: str,
        header_path: str,
        content: str,
        parent_content: str,
        is_parent: bool = False,
        metadata: Dict[str, Any] = None
    ):
        self.chunk_id = chunk_id
        self.parent_id = parent_id
        self.doc_name = doc_name
        self.title = title
        self.header_path = header_path
        self.content = content
        self.parent_content = parent_content
        self.is_parent = is_parent
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "parent_id": self.parent_id,
            "doc_name": self.doc_name,
            "title": self.title,
            "header_path": self.header_path,
            "content": self.content,
            "parent_content": self.parent_content,
            "is_parent": self.is_parent,
            "metadata": self.metadata,
        }


class ParentChildMarkdownChunker:
    """
    Parser that reads Markdown files, discovers H1 (#) and H2 (##) hierarchy,
    and produces paired parent-child chunks.
    """

    def __init__(self, child_sentence_window: int = 3):
        self.child_sentence_window = child_sentence_window

    def chunk_file(self, file_path: Path) -> List[MarkdownDocumentChunk]:
        """Parses a single Markdown runbook into parent and child chunks."""
        text = file_path.read_text(encoding="utf-8")
        doc_name = file_path.name

        # Extract Runbook title from first # header
        h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = h1_match.group(1).strip() if h1_match else file_path.stem

        # Extract metadata like Runbook ID
        rb_id_match = re.search(r"\*\*Runbook ID:\*\*\s*([A-Za-z0-9_-]+)", text)
        runbook_id = rb_id_match.group(1).strip() if rb_id_match else "UNKNOWN_RB"

        # Split by ## (Level 2 headers)
        sections = re.split(r"(?m)^##\s+", text)
        chunks: List[MarkdownDocumentChunk] = []

        # Preamble / Section 0 (Title and Runbook metadata)
        preamble = sections[0].strip()
        if preamble:
            parent_id = f"{runbook_id}_sec_0"
            parent_chunk = MarkdownDocumentChunk(
                chunk_id=parent_id,
                parent_id=parent_id,
                doc_name=doc_name,
                title=doc_title,
                header_path=doc_title,
                content=preamble,
                parent_content=preamble,
                is_parent=True,
                metadata={"runbook_id": runbook_id, "section": "Preamble"}
            )
            chunks.append(parent_chunk)

        # Process each H2 section
        for idx, sec_text in enumerate(sections[1:], start=1):
            lines = sec_text.splitlines()
            if not lines:
                continue
            section_heading = lines[0].strip()
            section_body = "\n".join(lines[1:]).strip()

            parent_id = f"{runbook_id}_sec_{idx}"
            full_parent_content = f"## {section_heading}\n{section_body}"

            # Create Parent Chunk
            parent_chunk = MarkdownDocumentChunk(
                chunk_id=parent_id,
                parent_id=parent_id,
                doc_name=doc_name,
                title=doc_title,
                header_path=f"{doc_title} > {section_heading}",
                content=full_parent_content,
                parent_content=full_parent_content,
                is_parent=True,
                metadata={"runbook_id": runbook_id, "section": section_heading}
            )
            chunks.append(parent_chunk)

            # Generate Child Chunks for fine-grained search
            # Split by bullet points or paragraphs
            child_blocks = re.split(r"(?m)(?:\n\s*\n|^-\s+)", section_body)
            for c_idx, raw_child in enumerate(child_blocks):
                clean_child = raw_child.strip()
                if len(clean_child) < 15:  # Ignore trivial fragments
                    continue

                child_id = f"{parent_id}_child_{c_idx}"
                child_content = f"[{section_heading}] {clean_child}"

                child_chunk = MarkdownDocumentChunk(
                    chunk_id=child_id,
                    parent_id=parent_id,
                    doc_name=doc_name,
                    title=doc_title,
                    header_path=f"{doc_title} > {section_heading}",
                    content=child_content,
                    parent_content=full_parent_content,
                    is_parent=False,
                    metadata={"runbook_id": runbook_id, "section": section_heading}
                )
                chunks.append(child_chunk)

        return chunks

    def chunk_directory(self, dir_path: Path) -> List[MarkdownDocumentChunk]:
        """Walks directory and chunks all markdown files."""
        all_chunks: List[MarkdownDocumentChunk] = []
        for file in sorted(dir_path.glob("*.md")):
            file_chunks = self.chunk_file(file)
            all_chunks.extend(file_chunks)
        return all_chunks
