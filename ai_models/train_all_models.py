from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

try:
    from ai_models.scripts.train_forgery_type import train_forgery_type_model
except ImportError:
    from scripts.train_forgery_type import train_forgery_type_model

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train forgery-type model only (always auto-resume from checkpoint)")
    parser.add_argument("--forgery-type-data-root", default=None, help="Path to ai_models/data_forgery_type")
    parser.add_argument("--epochs", type=int, default=12, help="Total target epochs for forgery-type model")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for forgery-type model")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate for forgery-type model")
    parser.add_argument(
        "--forgery-type-backbone",
        choices=["dual_resnet50_srm"],
        default="dual_resnet50_srm",
        help="Backbone for forgery-type CNN",
    )
    parser.add_argument("--num-workers", type=int, default=4, help="DataLoader workers")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(__file__).resolve().parent
    forgery_type_data_root = (
        Path(args.forgery_type_data_root) if args.forgery_type_data_root else (root / "data_forgery_type")
    )

    forgery_type_ckpt = root / "models" / "forgery_type_cnn.pt"

    logger.info("Starting forgery-type training pipeline.")
    logger.info("Checkpoint path: %s", forgery_type_ckpt)
    logger.info("Requested total epochs: %d", args.epochs)
    logger.info("Training resumes from checkpoint when compatible; otherwise starts fresh.")

    results: dict[str, object] = {
        "forgery_type_data_root": str(forgery_type_data_root),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "forgery_type_backbone": args.forgery_type_backbone,
        "pretrained": True,
        "auto_resume": True,
        "mode": "forgery_type_only",
    }

    logger.info("Training Forgery-Type CNN...")
    results["forgery_type_train"] = train_forgery_type_model(
        data_root=forgery_type_data_root,
        checkpoint_path=forgery_type_ckpt,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        backbone=args.forgery_type_backbone,
        num_workers=args.num_workers,
        pretrained=True,
        resume_from_checkpoint=forgery_type_ckpt.exists(),
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
