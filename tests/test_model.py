import subprocess
import sys

from bluekite.model import ReplayModel


def test_replay_folds_repeats():
    model = ReplayModel("T-1005")
    assert len(model.turns) == 40


def test_replay_needs_no_openai():
    code = ("import sys; sys.modules['openai'] = None; "
            "import bluekite.model, bluekite.cli")
    subprocess.run([sys.executable, "-c", code], check=True)
