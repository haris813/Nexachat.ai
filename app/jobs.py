from __future__ import annotations

import json
from pathlib import Path

from . import create_app
from .extensions import db
from .models import UploadedFile
from .services.files import extract_file


def extract_upload_job(upload_id: str) -> None:
    app = create_app()
    with app.app_context():
        upload = db.session.get(UploadedFile, upload_id)
        if not upload or upload.status != "processing":
            return
        try:
            text, metadata = extract_file(Path(upload.storage_path), upload.extension)
            upload.extracted_text = text
            upload.metadata_json = json.dumps(metadata, ensure_ascii=False)
            upload.status = "ready"
            db.session.commit()
        except Exception:
            db.session.rollback()
            upload = db.session.get(UploadedFile, upload_id)
            if upload:
                upload.status = "failed"
                db.session.commit()
            raise
