"""Dry-run-first cleanup for expired private uploads and deleted artifacts."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Artifact, UploadedFile, WhatsAppMessage


def owned_path(value: str, root: Path) -> Path | None:
    path = Path(value).resolve()
    return path if path.is_relative_to(root.resolve()) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete selected files/rows. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()
    app = create_app()
    cutoff = datetime.now(UTC) - timedelta(hours=app.config["FILE_RETENTION_HOURS"])

    with app.app_context():
        upload_root = Path(app.config["UPLOAD_DIR"])
        artifact_root = Path(app.config["ARTIFACT_DIR"])
        expired_uploads = UploadedFile.query.filter(UploadedFile.created_at < cutoff).all()
        deletable_uploads = [
            upload
            for upload in expired_uploads
            if not WhatsAppMessage.query.filter_by(upload_id=upload.id).first()
        ]
        deleted_artifacts = Artifact.query.filter(
            Artifact.deleted_at.is_not(None),
            Artifact.deleted_at < cutoff,
        ).all()
        print(
            f"mode={'apply' if args.apply else 'dry-run'} "
            f"uploads={len(deletable_uploads)} artifacts={len(deleted_artifacts)}"
        )
        if not args.apply:
            return

        records = [
            *((upload, upload_root) for upload in deletable_uploads),
            *((artifact, artifact_root) for artifact in deleted_artifacts),
        ]
        for record, root in records:
            path = owned_path(record.storage_path, root)
            if path and path.is_file():
                path.unlink()
            db.session.delete(record)
        db.session.commit()


if __name__ == "__main__":
    main()
