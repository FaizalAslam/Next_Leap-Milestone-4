import re

import pytest

from src.chunk import ChunkingError, build_chunks
from src.ingest import ContentSection, FetchResult


class FakeTokenizer:
    model_max_length = 256

    def __init__(self):
        self.word_to_id = {}
        self.id_to_word = {}

    def encode(self, text, add_special_tokens=True):
        ids = []
        for word in re.findall(r"\S+", text):
            if word not in self.word_to_id:
                token_id = len(self.word_to_id) + 1
                self.word_to_id[word] = token_id
                self.id_to_word[token_id] = word
            ids.append(self.word_to_id[word])
        return [101, *ids, 102] if add_special_tokens else ids

    def decode(self, token_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False):
        words = [self.id_to_word[token_id] for token_id in token_ids if token_id in self.id_to_word]
        return " ".join(words)

    def build_inputs_with_special_tokens(self, token_ids):
        return [101, *token_ids, 102]


def _result(source_id, sections, *, scheme="", source_type="help", allowed_uses="factual help"):
    source = {
        "source_id": source_id,
        "title": "Sample source",
        "url": f"https://example.com/{source_id}",
        "source_type": source_type,
        "source": "Groww",
        "amc": "SBI Mutual Fund",
        "scheme": scheme,
        "category": "General",
        "allowed_uses": allowed_uses,
        "approval_status": "approved_listed",
    }
    return FetchResult(
        source=source,
        sections=sections,
        retrieved_at="2026-10-02",
        final_url=source["url"],
        content_type="text/html",
        content_sha256="abc123",
        extraction_method="requests+beautifulsoup",
        raw_files=[],
    )


def test_scheme_filter_retains_public_performance_holdings_and_peer_facts():
    source = _result(
        "source_01",
        [
            ContentSection("Approved scheme facts", "Minimum SIP investment: INR 500"),
            ContentSection("Scheme > Understand terms > Expense ratio", "Expense ratio is a fee."),
            ContentSection("Scheme > Return calculator", "Historic returns 20 percent."),
            ContentSection("Scheme > Holdings (20)", "Portfolio names and weights."),
            ContentSection("Scheme > Understand terms > Compare similar funds", "Peer comparison."),
        ],
        scheme="SBI Large Cap Direct Plan Growth",
        source_type="scheme_page",
        allowed_uses="category; minimum SIP; expense information; exit load; risk; benchmark",
    )

    chunks = build_chunks([source], FakeTokenizer())
    text = "\n".join(chunk.text for chunk in chunks).casefold()

    assert "minimum sip investment" in text
    assert "expense ratio is a fee" in text
    assert "historic returns" in text
    assert "portfolio names" in text
    assert "peer comparison" in text


def test_category_page_public_lists_and_sections_are_retained():
    source = _result(
        "source_07",
        [
            ContentSection("Best Large Cap Mutual Funds", "Large-cap funds invest in large companies."),
            ContentSection("Best Large Cap Mutual Funds > List of Large Cap Mutual Funds in India", "Rank list."),
            ContentSection("Best Large Cap Mutual Funds > Who Should Invest in Large Cap Funds?", "Suitability advice."),
        ],
        source_type="education",
        allowed_uses="large-cap context; exclude rankings and performance content",
    )

    chunks = build_chunks([source], FakeTokenizer())

    text = "\n".join(chunk.text for chunk in chunks).casefold()
    assert "large-cap funds invest" in text
    assert "rank list" in text
    assert "suitability advice" in text


def test_chunks_obey_token_target_metadata_and_stable_ids():
    lines = [f"fact label {index}: value with supporting explanation" for index in range(1, 17)]
    result = _result("source_13", [ContentSection("Exit load procedure", "\n".join(lines))])
    tokenizer = FakeTokenizer()

    first = build_chunks([result], tokenizer, target_tokens=40, overlap_tokens=5)
    second = build_chunks([result], tokenizer, target_tokens=40, overlap_tokens=5)

    assert len(first) > 1
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert all(len(tokenizer.encode(chunk.text, add_special_tokens=True)) <= 40 for chunk in first)
    assert all(chunk.metadata["scheme"] == "" for chunk in first)
    assert all(chunk.metadata["retrieved_at"] == "2026-10-02" for chunk in first)
    assert all(chunk.metadata["chunk_id"] == chunk.id for chunk in first)
    first_body = first[0].text.split("\n", 1)[1].split()
    second_body = first[1].text.split("\n", 1)[1].split()
    assert second_body[:5] == first_body[-5:]


def test_oversized_table_row_fails_instead_of_splitting_label_from_value():
    row = "Label | " + " ".join(f"value{index}" for index in range(50))
    result = _result("source_13", [ContentSection("Table", row)])

    with pytest.raises(ChunkingError, match="table row exceeds"):
        build_chunks([result], FakeTokenizer(), target_tokens=20, overlap_tokens=3)

