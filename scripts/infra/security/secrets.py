from scripts.utility.log import get_logger
from typing import Optional
import os


logger = get_logger(__name__)


def get_secret_value(secret_nm: str) -> str:
    secret_vl: Optional[str] = os.getenv(secret_nm)
    if secret_vl:
        return secret_vl
    if not secret_vl:
        logger.error("Secret has no value")
        raise

    return secret_vl
