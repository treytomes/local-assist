"""
Tokenizer tool — wraps the Tekken tokenizer (v3, 131k vocab) used by Mistral Large 3.

tekken.json is loaded from ~/.local/share/mistral-tokenizers/tekken.json.
If the file is absent, download it once from HuggingFace:
    python -c "
    from huggingface_hub import hf_hub_download
    hf_hub_download('mistralai/Mistral-Nemo-Instruct-2407', 'tekken.json',
                    local_dir='~/.local/share/mistral-tokenizers')
    "
"""
import os
import pathlib

from mistral_common.tokens.tokenizers.tekken import Tekkenizer

TOKENIZER_MODEL = "Mistral Large 3"
TOKENIZER_VERSION = "Tekken v3 / tiktoken"
TEKKEN_PATH = pathlib.Path(os.path.expanduser("~/.local/share/mistral-tokenizers/tekken.json"))

_tokenizer: Tekkenizer | None = None


def _get() -> Tekkenizer:
    global _tokenizer
    if _tokenizer is None:
        if not TEKKEN_PATH.exists():
            raise FileNotFoundError(
                f"Tekken tokenizer file not found at {TEKKEN_PATH}. "
                "Download it with: python -m huggingface_hub download "
                "mistralai/Mistral-Nemo-Instruct-2407 tekken.json "
                f"--local-dir {TEKKEN_PATH.parent}"
            )
        _tokenizer = Tekkenizer.from_file(TEKKEN_PATH)
    return _tokenizer


def tokenizer_info() -> dict:
    tok = _get()
    return {
        "model": TOKENIZER_MODEL,
        "version": TOKENIZER_VERSION,
        "vocab_size": tok.n_words,
        "num_special_tokens": tok.num_special_tokens,
        "bos_id": tok.bos_id,
        "eos_id": tok.eos_id,
    }


def tokenize(text: str) -> dict:
    tok = _get()
    token_ids: list[int] = tok.encode(text, bos=False, eos=False)
    token_strings: list[str] = [tok.id_to_piece(t) for t in token_ids]
    decoded: str = tok.decode(token_ids)
    special_flags: list[bool] = [tok.is_special(t) for t in token_ids]
    return {
        "token_count": len(token_ids),
        "token_ids": token_ids,
        "token_strings": token_strings,
        "special_flags": special_flags,
        "decoded_text": decoded,
        "round_trip_match": text == decoded,
    }
