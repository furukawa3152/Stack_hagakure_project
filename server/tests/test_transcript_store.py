import os

from hagakure.transport.server import _save_transcript


def test_transcript_is_private_and_not_created_for_empty_turn(tmp_path) -> None:
    directory = tmp_path / "conversations"
    _save_transcript(directory, "session", "", "")
    assert not directory.exists()
    _save_transcript(directory, "session", "x", "y")
    path = directory / "session.txt"
    assert path.exists()
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert path.read_text().count("あなた:") == 1
    assert path.read_text().count("はがくれ君:") == 1
