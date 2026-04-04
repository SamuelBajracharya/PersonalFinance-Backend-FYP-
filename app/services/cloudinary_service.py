import cloudinary
import cloudinary.api
import cloudinary.uploader
import random

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
        public_id=f"profile/{user_id}/profile_picture",
        overwrite=True,
        resource_type="image",
        filename_override=filename,
    )

    secure_url = upload_result.get("secure_url")
    if not secure_url:
        raise RuntimeError("Cloudinary upload did not return secure_url")

    return secure_url


def get_random_default_profile_image_url(folder: str = "profile/default") -> str | None:
    """Return a random image URL from a Cloudinary folder, or None if unavailable."""
    try:
        _configure_cloudinary()
    except Exception:
        return None

    resources: list[dict] = []

    try:
        # Preferred API for asset-folder based media.
        resp = cloudinary.api.resources_by_asset_folder(
            folder,
            resource_type="image",
            type="upload",
            max_results=100,
        )
        resources = resp.get("resources", []) if isinstance(resp, dict) else []
    except Exception:
        resources = []

    if not resources:
        try:
            # Fallback for accounts using folder/prefix querying.
            resp = cloudinary.api.resources(
                type="upload",
                prefix=f"{folder}/",
                resource_type="image",
                max_results=100,
            )
            resources = resp.get("resources", []) if isinstance(resp, dict) else []
        except Exception:
            resources = []

    if not resources:
        return None

    selected = random.choice(resources)
    return selected.get("secure_url") or selected.get("url")
