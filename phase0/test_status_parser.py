from status_parser import parse_status


def test_no_status_line_returns_none():
    assert parse_status("just some regular text with no status line") is None
    assert parse_status("") is None
    assert parse_status(None) is None


def test_basic_json_status():
    out = parse_status('Some preamble.\nSISYPHX_STATUS: {"outcome": "done", "summary": "wrote the file"}\n')
    assert out == {"outcome": "done", "summary": "wrote the file"}


def test_bare_word_status_not_json():
    out = parse_status("All finished.\nSISYPHX_STATUS: done\n")
    assert out == {"outcome": "done"}


def test_extra_whitespace_tolerated():
    out = parse_status("done.\n   SISYPHX_STATUS:    {\"outcome\": \"blocked\"}   \n")
    assert out == {"outcome": "blocked"}


def test_markdown_backticks_tolerated():
    out = parse_status('Result:\nSISYPHX_STATUS: `{"outcome": "done"}`\n')
    assert out == {"outcome": "done"}


def test_takes_last_match_if_instruction_echoed_earlier():
    stdout = (
        "I was told to end with a line like SISYPHX_STATUS: {\"outcome\": \"done\"} when finished.\n"
        "Working on it now...\n"
        "SISYPHX_STATUS: {\"outcome\": \"partial\", \"summary\": \"blocked on step 2\"}\n"
    )
    out = parse_status(stdout)
    assert out == {"outcome": "partial", "summary": "blocked on step 2"}


def test_malformed_json_falls_back_to_raw_string():
    out = parse_status('SISYPHX_STATUS: {"outcome": "done"  # truncated\n')
    assert out is not None
    assert out["outcome"].startswith("{")  # raw fallback, not a crash


def test_missing_outcome_key_gets_default():
    out = parse_status('SISYPHX_STATUS: {"summary": "no outcome key given"}\n')
    assert out == {"summary": "no outcome key given", "outcome": "unknown"}


def test_case_and_trailing_period_do_not_break_parsing():
    out = parse_status("Done!\nSISYPHX_STATUS: {\"outcome\": \"done\"}")
    assert out == {"outcome": "done"}
