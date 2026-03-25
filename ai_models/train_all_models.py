from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

try:
    from ai_models.scripts.train_test_visual import test_model, train_model
    from ai_models.scripts.train_forgery_type import train_forgery_type_model
    from ai_models.text.nlp_analysis import train as train_nlp
    from ai_models.image.cnn_pipeline import preprocess_copy_move_image, preprocess_ela_image
except ImportError:
    from scripts.train_test_visual import test_model, train_model
    from scripts.train_forgery_type import train_forgery_type_model
    from text.nlp_analysis import train as train_nlp
    from image.cnn_pipeline import preprocess_copy_move_image, preprocess_ela_image

logger = logging.getLogger(__name__)
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _prepare_binary_dataset_from_type(type_root: Path, binary_root: Path) -> dict[str, int]:
    train_src = type_root / "train"
    test_src = type_root / "test"

    if not train_src.exists() or not test_src.exists():
        raise FileNotFoundError(f"Subtype dataset missing train/test in {type_root}")

    for split in ("train", "test"):
        for cls in ("authentic", "forged"):
            dst = binary_root / split / cls
            if dst.exists():
                shutil.rmtree(dst)
            dst.mkdir(parents=True, exist_ok=True)

    counts = {"train_authentic": 0, "train_forged": 0, "test_authentic": 0, "test_forged": 0}

    for split in ("train", "test"):
        split_src = type_root / split
        for cls_dir in sorted(split_src.iterdir()):
            if not cls_dir.is_dir():
                continue
            cls = cls_dir.name
            target_cls = "authentic" if cls == "authentic" else "forged"
            target_dir = binary_root / split / target_cls

            for p in sorted(cls_dir.rglob("*")):
                if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXT:
                    continue
                name = p.name if cls == "authentic" else f"{cls}__{p.name}"
                dst = target_dir / name
                if dst.exists():
                    dst = target_dir / f"dup__{name}"
                shutil.copy2(p, dst)
                key = f"{split}_{target_cls}"
                counts[key] += 1

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Final one-command trainer for all models (ELA, Copy-Move, Forgery-Type, NLP)"
    )
    parser.add_argument("--data-root", default=None, help="Optional explicit binary data root (train/test/authentic|forged)")
    parser.add_argument("--forgery-type-data-root", default=None, help="Path to ai_models/data_forgery_type")
    parser.add_argument("--epochs", type=int, default=8, help="Epochs for ELA/Copy-Move CNN")
    parser.add_argument("--forgery-type-epochs", type=int, default=12, help="Epochs for forgery-type CNN")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for visual CNN models")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate for visual CNN models")
    parser.add_argument("--forgery-type-lr", type=float, default=1e-4, help="Learning rate for forgery-type model")
    parser.add_argument(
        "--backbone",
        choices=["resnet18", "efficientnet_b0"],
        default="resnet18",
        help="Backbone for visual CNN models",
    )
    parser.add_argument(
        "--forgery-type-backbone",
        choices=["resnet18", "efficientnet_b0"],
        default="resnet18",
        help="Backbone for forgery-type CNN",
    )
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers")
    parser.add_argument("--pretrained", action="store_true", help="Use ImageNet weights for visual models")
    parser.add_argument("--skip-visual-test", action="store_true", help="Skip ELA/Copy-Move test evaluation")
    parser.add_argument("--skip-forgery-type", action="store_true", help="Skip forgery-type training")
    parser.add_argument("--nlp-samples", type=int, default=400, help="Synthetic samples per class for NLP training")
    parser.add_argument("--force-nlp-retrain", action="store_true", help="Retrain NLP even if model files already exist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(__file__).resolve().parent
    forgery_type_data_root = (
        Path(args.forgery_type_data_root) if args.forgery_type_data_root else (root / "data_forgery_type")
    )

    if args.data_root:
        data_root = Path(args.data_root)
        binary_prep_counts = None
    else:
        data_root = root / "data_binary"
        logger.info("Preparing binary dataset from subtype dataset at %s", forgery_type_data_root)
        binary_prep_counts = _prepare_binary_dataset_from_type(forgery_type_data_root, data_root)

    ela_ckpt = root / "models" / "ela_cnn.pt"
    copy_move_ckpt = root / "models" / "copy_move_cnn.pt"
    forgery_type_ckpt = root / "models" / "forgery_type_cnn.pt"

    results: dict[str, object] = {
        "data_root": str(data_root),
        "forgery_type_data_root": str(forgery_type_data_root),
        "epochs": args.epochs,
        "forgery_type_epochs": args.forgery_type_epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "forgery_type_lr": args.forgery_type_lr,
        "backbone": args.backbone,
        "forgery_type_backbone": args.forgery_type_backbone,
        "pretrained": args.pretrained,
        "auto_resume": True,
    }
    if binary_prep_counts is not None:
        results["binary_dataset_prepared"] = binary_prep_counts

    logger.info("Training ELA CNN (auto-resume if checkpoint exists)...")
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
        resume_from_checkpoint=ela_ckpt.exists(),
    )

    logger.info("Training Copy-Move CNN (auto-resume if checkpoint exists)...")
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
        resume_from_checkpoint=copy_move_ckpt.exists(),
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

    if not args.skip_forgery_type:
        logger.info("Training Forgery-Type CNN (auto-resume if checkpoint exists)...")
        results["forgery_type_train"] = train_forgery_type_model(
            data_root=forgery_type_data_root,
            checkpoint_path=forgery_type_ckpt,
            epochs=args.forgery_type_epochs,
            batch_size=args.batch_size,
            learning_rate=args.forgery_type_lr,
            backbone=args.forgery_type_backbone,
            num_workers=args.num_workers,
            pretrained=args.pretrained,
            resume_from_checkpoint=forgery_type_ckpt.exists(),
        )

    nlp_model = root / "text" / "nlp_model.pkl"
    nlp_vec = root / "text" / "nlp_vectorizer.pkl"

    if args.force_nlp_retrain or not (nlp_model.exists() and nlp_vec.exists()):
        logger.info("Training NLP anomaly model...")
        train_nlp(n_per_class=args.nlp_samples)
        results["nlp_train"] = "trained"
    else:
        logger.info("NLP model already exists. Keeping existing model (no overwrite).")
        results["nlp_train"] = "kept_existing"

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
