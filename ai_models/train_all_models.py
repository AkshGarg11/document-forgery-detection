from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

try:
    from ai_models.scripts.train_test_visual import test_model, train_model
    from ai_models.text.nlp_analysis import train as train_nlp
    from ai_models.image.cnn_pipeline import preprocess_copy_move_image, preprocess_ela_image
except ImportError:
    from scripts.train_test_visual import test_model, train_model
    from text.nlp_analysis import train as train_nlp
    from image.cnn_pipeline import preprocess_copy_move_image, preprocess_ela_image

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train all forgery detection models (ELA, Copy-Move, NLP) in one run"
    )
    parser.add_argument("--data-root", default=None, help="Path to ai_models/data")
    parser.add_argument("--epochs", type=int, default=8, help="Epochs for visual CNN models")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for visual CNN models")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate for visual CNN models")
    parser.add_argument(
        "--backbone",
        choices=["resnet18", "efficientnet_b0"],
        default="resnet18",
        help="Backbone for visual CNN models",
    )
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers")
    parser.add_argument("--pretrained", action="store_true", help="Use ImageNet weights for visual models")
    parser.add_argument("--skip-visual-test", action="store_true", help="Skip visual model test evaluation")
    parser.add_argument("--nlp-samples", type=int, default=400, help="Synthetic samples per class for NLP training")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(__file__).resolve().parent
    data_root = Path(args.data_root) if args.data_root else (root / "data")

    results: dict[str, dict | str | int | float | bool] = {
        "data_root": str(data_root),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "backbone": args.backbone,
        "pretrained": args.pretrained,
        "visual_test_skipped": args.skip_visual_test,
        "nlp_samples_per_class": args.nlp_samples,
    }

    logger.info("Training ELA CNN...")
    ela_ckpt = root / "models" / "ela_cnn.pt"
    results["ela_train"] = train_model(
        model_key="ela",
        data_root=data_root,
        checkpoint_path=ela_ckpt,
        preprocessor=preprocess_ela_image,
        backbone=args.backbone,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        num_workers=args.num_workers,
        pretrained=args.pretrained,
    )

    logger.info("Training Copy-Move CNN...")
    copy_move_ckpt = root / "models" / "copy_move_cnn.pt"
    results["copy_move_train"] = train_model(
        model_key="copy_move",
        data_root=data_root,
        checkpoint_path=copy_move_ckpt,
        preprocessor=preprocess_copy_move_image,
        backbone=args.backbone,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        num_workers=args.num_workers,
        pretrained=args.pretrained,
    )

    if not args.skip_visual_test:
        logger.info("Evaluating ELA CNN on test split...")
        results["ela_test"] = test_model(
            model_key="ela",
            data_root=data_root,
            checkpoint_path=ela_ckpt,
            preprocessor=preprocess_ela_image,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
        )

        logger.info("Evaluating Copy-Move CNN on test split...")
        results["copy_move_test"] = test_model(
            model_key="copy_move",
            data_root=data_root,
            checkpoint_path=copy_move_ckpt,
            preprocessor=preprocess_copy_move_image,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
        )

    logger.info("Training NLP anomaly model...")
    train_nlp(n_per_class=args.nlp_samples)
    results["nlp_train"] = "completed"

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
