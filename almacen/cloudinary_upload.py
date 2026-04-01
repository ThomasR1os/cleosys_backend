import os

from django.conf import settings


def upload_product_image(file_obj, *, folder: str = "cleosys/products") -> dict:
    """
    Sube un archivo a Cloudinary y devuelve el dict de respuesta (incluye secure_url, public_id).
    """
    cloud_name = getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or ""
    api_key = getattr(settings, "CLOUDINARY_API_KEY", "") or ""
    api_secret = getattr(settings, "CLOUDINARY_API_SECRET", "") or ""
    if not (cloud_name and api_key and api_secret):
        raise RuntimeError("Cloudinary no está configurado (variables de entorno faltantes).")

    api_key = str(api_key).strip()
    api_secret = str(api_secret).strip()
    cloud_name = str(cloud_name).strip()

    # Alinear os.environ con Django (el SDK de Cloudinary también lee env al importar)
    os.environ["CLOUDINARY_CLOUD_NAME"] = cloud_name
    os.environ["CLOUDINARY_API_KEY"] = api_key
    os.environ["CLOUDINARY_API_SECRET"] = api_secret

    import cloudinary
    import cloudinary.uploader
    from cloudinary.utils import SIGNATURE_SHA256

    # Evita estado viejo del SDK si se importó antes con otras credenciales.
    cloudinary.reset_config()
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
        # Cuentas recientes suelen validar con SHA-256; por defecto el SDK usa SHA-1 → "Invalid Signature".
        signature_algorithm=SIGNATURE_SHA256,
    )
    return cloudinary.uploader.upload(
        file_obj,
        folder=folder,
        resource_type="image",
        signature_algorithm=SIGNATURE_SHA256,
    )
