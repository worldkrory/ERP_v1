"""Almacenamiento de comprobantes en Cloudinary."""

from __future__ import annotations

from flask import current_app


class CloudStorageError(RuntimeError):
    """Error controlado al guardar un comprobante."""


def upload_receipt(file_storage, public_id: str) -> tuple[str, str]:
    settings = current_app.config
    required = (
        settings.get("CLOUDINARY_CLOUD_NAME"),
        settings.get("CLOUDINARY_API_KEY"),
        settings.get("CLOUDINARY_API_SECRET"),
    )
    if not all(required):
        raise CloudStorageError("El almacenamiento de comprobantes no está configurado.")

    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings["CLOUDINARY_CLOUD_NAME"],
        api_key=settings["CLOUDINARY_API_KEY"],
        api_secret=settings["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    result = cloudinary.uploader.upload(
        file_storage.stream,
        folder=settings.get("CLOUDINARY_FOLDER", "densa-niebla/comprobantes"),
        public_id=public_id,
        resource_type="image",
        overwrite=False,
    )
    return result["secure_url"], result["public_id"]