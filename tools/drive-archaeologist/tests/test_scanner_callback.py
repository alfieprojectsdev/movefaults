from unittest.mock import MagicMock

from drive_archaeologist.scanner import DeepScanner


def test_on_classified_fires_for_each_file(tmp_path):
    test_dir = tmp_path / "scan"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("hello")
    (test_dir / "file2.rnx").write_text("rinex")

    callback = MagicMock()
    output_file = tmp_path / "out.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file, on_classified=callback)
    scanner.scan()

    assert callback.call_count == 2
    for call_args in callback.call_args_list:
        metadata = call_args[0][0]
        assert "path" in metadata
        assert "category" in metadata


def test_no_callback_does_not_crash(tmp_path):
    test_dir = tmp_path / "scan"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("hello")

    output_file = tmp_path / "out.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()
    assert scanner.file_count == 1


def test_callback_exception_does_not_abort_scan(tmp_path):
    test_dir = tmp_path / "scan"
    test_dir.mkdir()
    for i in range(5):
        (test_dir / f"file{i}.txt").write_text(f"content {i}")

    def bad_callback(metadata):
        raise RuntimeError("simulated callback failure")

    output_file = tmp_path / "out.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file, on_classified=bad_callback)
    scanner.scan()
    assert scanner.file_count == 5  # all files processed despite callback errors
