import os
from io import BytesIO
from pathlib import Path

import polars as pl
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


CONTAINER_NAME = "nfl-raw"


def get_blob_service_client() -> BlobServiceClient:
    storage_account_name = os.environ["stnflanalytics"]

    account_url = (
        f"https://{storage_account_name}.blob.core.windows.net"
    )

    credential = DefaultAzureCredential()

    return BlobServiceClient(
        account_url=account_url,
        credential=credential
    )


def upload_dataframe(
    dataframe: pl.DataFrame,
    blob_name: str
) -> None:
    buffer = BytesIO()

    dataframe.write_parquet(buffer)
    buffer.seek(0)

    blob_service_client = get_blob_service_client()

    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    blob_client.upload_blob(
        buffer,
        overwrite=True
    )

    print(
        f"Uploaded {dataframe.height:,} rows -> "
        f"{CONTAINER_NAME}/{blob_name}"
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