import cloudinary
import cloudinary.uploader

from app.config.settings import settings


def _configure_cloudinary() -> None:
    if not (
        settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
    ):
        raise RuntimeError(
            "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def upload_user_profile_picture(file_bytes: bytes, filename: str, user_id: str) -> str:
    _configure_cloudinary()

    upload_result = cloudinary.uploader.upload(
        file_bytes,
        public_id=f"users/{user_id}/profile_picture",
        overwrite=True,
        resource_type="image",
        filename_override=filename,
    )

    secure_url = upload_result.get("secure_url")
    if not secure_url:
        raise RuntimeError("Cloudinary upload did not return secure_url")

    return secure_url
