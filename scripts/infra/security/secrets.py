from scripts.utility.log import get_logger

import os


logger = get_logger(__name__)


def get_secret_value(secret_nm: str) -> str:
    secret_vl = os.getenv(secret_nm)
    if not secret_vl:
        logger.error(f"Secret '{secret_nm}' has no value")
        raise ValueError(f"Secret '{secret_nm}' has no value")

    return secret_vl
