import json

from sherlock_ml.cli import main


def test_cli_pipeline_preserves_hashes_and_frozen_parameters(tmp_path, capsys):
    dataset = tmp_path / "data"
    features = tmp_path / "features"
    baseline = tmp_path / "baseline"
    assert (
        main(
            [
                "generate",
                "--output",
                str(dataset),
                "--users",
                "15",
                "--days",
                "12",
                "--train-days",
                "6",
                "--validation-days",
                "3",
                "--attack-episodes",
                "18",
            ]
        )
        == 0
    )
    assert main(["features", "--dataset", str(dataset), "--output", str(features)]) == 0
    assert (
        main(
            [
                "baseline",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--output",
                str(baseline),
            ]
        )
        == 0
    )
    saved = json.loads((baseline / "baseline.json").read_text())
    assert saved["provenance"]["fit_population"] == "all training events; labels excluded"
    assert saved["feature_version"] == "login-history-v1"
    second = tmp_path / "reference"
    assert (
        main(
            [
                "baseline",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--reference",
                str(baseline / "baseline.json"),
                "--false-alert-budget",
                "999",
                "--output",
                str(second),
            ]
        )
        == 0
    )
    assert json.loads((second / "baseline.json").read_text()) == saved
    assert main(["generate", "--output", str(dataset)]) == 1  # No accidental overwrites.
    (features / "features.csv").write_text("corrupt")
    assert (
        main(
            [
                "baseline",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--output",
                str(tmp_path / "bad"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "bad").exists()
    assert "synthetic_only" in capsys.readouterr().out


def test_generated_files_are_byte_reproducible(tmp_path):
    arguments = [
        "--users",
        "10",
        "--days",
        "6",
        "--train-days",
        "2",
        "--validation-days",
        "2",
        "--attack-episodes",
        "9",
    ]
    for name in ("first", "second"):
        assert main(["generate", "--output", str(tmp_path / name), *arguments]) == 0
    for name in ("events.jsonl", "labels.jsonl", "manifest.json"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()
