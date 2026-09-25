"""A competition-side script: the foundation knows nothing about its split or model."""

import argparse
import csv
import json
import random
import statistics
from pathlib import Path


def read_csv(path: str) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.spec.read_text(encoding="utf-8"))
    experiment = request["experiment"]
    dataset = json.loads(Path(experiment["params"]["dataset_config"]).read_text(encoding="utf-8"))
    rows = read_csv(dataset["train"])
    targets = [float(row[dataset["target_column"]]) for row in rows]
    indices = list(range(len(targets)))
    random.Random(experiment["seed"]).shuffle(indices)
    count = experiment["params"]["validation_rows"]
    if not 0 < count < len(indices):
        raise ValueError("validation_rows must leave non-empty train and validation splits")
    validation, train = indices[:count], indices[count:]
    prediction = statistics.mean(targets[i] for i in train)
    mae = statistics.mean(abs(targets[i] - prediction) for i in validation)
    id_column = dataset["id_column"]
    prediction_column = dataset["prediction_column"]
    write_csv(
        args.output.parent / "validation_predictions.csv",
        [id_column, prediction_column],
        [[rows[index][id_column], prediction] for index in validation],
    )
    final_prediction = statistics.mean(targets)
    test_predictions = {row[id_column]: final_prediction for row in read_csv(dataset["test"])}
    sample = read_csv(dataset["sample_submission"])
    header = list(sample[0])
    submission = [
        {id_column: row[id_column], prediction_column: test_predictions[row[id_column]]}
        for row in sample
    ]
    write_csv(
        args.output.parent / "submission.csv",
        header,
        [[row[column] for column in header] for row in submission],
    )
    (args.output.parent / "split.json").write_text(
        json.dumps(
            {"seed": experiment["seed"], "train_indices": train, "validation_indices": validation}
        ),
        encoding="utf-8",
    )
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "0",
                "metrics": {"mae": mae},
                "usage": {"total_tokens": 0, "cost_usd": 0, "cost_source": "not_applicable"},
                "artifacts": ["submission.csv", "validation_predictions.csv", "split.json"],
            }
        ),
        encoding="utf-8",
    )
    print("Completed offline mean-regression baseline")


if __name__ == "__main__":
    main()
