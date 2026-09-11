from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


STORAGE_ACCOUNT_NAME = "stnflanalytics"
CONTAINER_NAME = "nfl-raw"

ACCOUNT_URL = (
    f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
)


def get_blob_service_client() -> BlobServiceClient:
    credential = DefaultAzureCredential()

    return BlobServiceClient(
        account_url=ACCOUNT_URL,
        credential=credential
    )


def upload_file(
    local_file: Path,
    blob_name: str
) -> None:
    blob_service_client = get_blob_service_client()

    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    with open(local_file, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True
        )

    print(
        f"Uploaded {local_file} -> "
        f"{CONTAINER_NAME}/{blob_name}"
    )