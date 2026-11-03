"""Affinage optionnel de DeBERTa-v3 pour le choix de la voie (transformers, GPU conseillé).

Usage : python scripts/finetune_deberta.py --epochs 5 --out models/router-deberta
"""
import argparse
from pathlib import Path

import pandas as pd

LABELS = ["HYBRID", "RAG", "SQL"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-base")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--out", default="models/router-deberta")
    args = ap.parse_args()

    from datasets import Dataset
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              Trainer, TrainingArguments)

    base = Path(__file__).resolve().parents[1]
    df = pd.read_csv(base / "data" / "datasets" / "routing_dataset.csv")
    df["label"] = df["label"].map({l: i for i, l in enumerate(LABELS)})
    ds = Dataset.from_pandas(df).train_test_split(test_size=0.2, seed=42,
                                                  stratify_by_column=None)

    tok = AutoTokenizer.from_pretrained(args.model)
    ds = ds.map(lambda b: tok(b["question"], truncation=True, padding="max_length",
                              max_length=64), batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(LABELS),
        id2label=dict(enumerate(LABELS)),
        label2id={l: i for i, l in enumerate(LABELS)})

    trainer = Trainer(
        model=model,
        args=TrainingArguments(output_dir=args.out, num_train_epochs=args.epochs,
                               per_device_train_batch_size=16,
                               evaluation_strategy="epoch", learning_rate=2e-5,
                               seed=42),
        train_dataset=ds["train"], eval_dataset=ds["test"],
    )
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    print(f"Modele sauvegarde : {args.out}")


if __name__ == "__main__":
    main()
