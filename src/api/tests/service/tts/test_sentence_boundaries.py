"""Keep multilingual sentence boundaries consistent across TTS paths."""

import pytest
from flaskr.service.tts.patterns import SENTENCE_ENDINGS, SENTENCE_PUNCTUATION_FRAGMENT
from flaskr.service.tts.pipeline import _split_by_sentence_and_newline


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ready? Yes!", ["Ready?", "Yes!"]),
        ("第一句。第二句！", ["第一句。", "第二句！"]),
        ("本当？はい。", ["本当？", "はい。"]),
        ("هل أنت جاهز؟ نعم۔", ["هل أنت جاهز؟", "نعم۔"]),
        ("पहला वाक्य। दूसरा वाक्य॥", ["पहला वाक्य।", "दूसरा वाक्य॥"]),
        ("ပထမစာကြောင်း။ ဒုတိယစာကြောင်း။", ["ပထမစာကြောင်း။", "ဒုတိယစာကြောင်း။"]),
        ("ሰላም። ደህና፧", ["ሰላም።", "ደህና፧"]),
        ("Բարև։ Հաջող։", ["Բարև։", "Հաջող։"]),
        ("Ինչպե՞ս ես։ Շատ լավ։", ["Ինչպե՞ս ես։", "Շատ լավ։"]),
        ("Bonjour ! Ça va ?", ["Bonjour !", "Ça va ?"]),
        ("¿Listo? ¡Vamos!", ["¿Listo?", "¡Vamos!"]),
        ("Πώς είσαι; Καλά.", ["Πώς είσαι;", "Καλά."]),
        (
            "First; second\uff1b third؛ tail",
            ["First;", "second\uff1b", "third؛", "tail"],
        ),
        ("“Ready?!” Next... Done.", ["“Ready?!”", "Next...", "Done."]),
        ("«جاهز؟» نعم۔", ["«جاهز؟»", "نعم۔"]),
        ('[Ready!] (Yes.) "Go!"', ["[Ready!]", "(Yes.)", '"Go!"']),
        ("First\r\nSecond\n\nTail", ["First", "Second", "Tail"]),
        ("مرحبا، بالعالم", ["مرحبا، بالعالم"]),
        ("สวัสดีครับ ยินดีต้อนรับ", ["สวัสดีครับ ยินดีต้อนรับ"]),
        ("", []),
        (" \t\n ", []),
    ],
)
def test_sentence_units_use_unicode_terminals(text: str, expected: list[str]) -> None:
    assert _split_by_sentence_and_newline(text) == expected


def test_sentence_matches_retain_source_offsets() -> None:
    text = "  «جاهز؟!»  पहला वाक्य॥  tail"
    matches = list(SENTENCE_ENDINGS.finditer(text))
    assert [match.group() for match in matches] == ["؟!»", "॥"]
    assert [text[: match.end()] for match in matches] == [
        "  «جاهز؟!»",
        "  «جاهز؟!»  पहला वाक्य॥",
    ]


@pytest.mark.parametrize("text", ["!!", "؟!\u201d", "\u201d\u00bb", "!\u00a0\u2003!"])
def test_sentence_punctuation_fragments_are_recognized(text: str) -> None:
    assert SENTENCE_PUNCTUATION_FRAGMENT.fullmatch(text)


@pytest.mark.parametrize("text", ["😀!", "∞!", "---", ",,", "\u0301!"])
def test_other_symbols_and_punctuation_remain_subject_to_provider_policy(
    text: str,
) -> None:
    assert not SENTENCE_PUNCTUATION_FRAGMENT.fullmatch(text)
