from daisywriter.cli import main


def test_validate_and_preview(sample_dir, tmp_path, capsys):
    args = [str(sample_dir / "letter-template.docx"), str(sample_dir / "letter-data.xlsx"),
            "--today", "2026-11-08"]
    assert main(["validate", *args]) == 0
    out = capsys.readouterr().out
    assert "5 letters on the Swintec 1146 CMP: 0 errors, 2 warnings" in out

    assert main(["preview", *args, "--letters", "2", "--format", "plain"]) == 0
    out = capsys.readouterr().out
    assert "Letter 2 of 5" in out and "Dear Thomas," in out and "Letter 1 " not in out

    html = tmp_path / "p.html"
    assert main(["preview", *args, "-o", str(html)]) == 0
    page = html.read_text(encoding="utf-8")
    assert "<u>not</u>" in page and "class='line body'" in page


def test_profiles_and_samples(tmp_path, capsys):
    assert main(["profiles"]) == 0
    assert "olympia-compact-2" in capsys.readouterr().out
    assert main(["make-samples", str(tmp_path / "s")]) == 0
    assert (tmp_path / "s" / "letter-data.xlsx").exists()


def test_status_exit_code(monkeypatch, capsys):
    from daisywriter import transports
    from daisywriter.transports.fake import FakeTransport
    for raw, code in ((0x18, 0), (0x08, 1), (0x38, 1)):
        monkeypatch.setattr(transports, "open_transport", lambda profile, raw=raw: FakeTransport(raw))
        assert main(["status"]) == code
    assert "off-line" in capsys.readouterr().out
