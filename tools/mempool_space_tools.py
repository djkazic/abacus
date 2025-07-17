import requests


def get_fee_recommendations():
    """
    Fetches recommended fee rates from mempool.space's API.

    Returns:
        dict: A dictionary containing the recommended fee rates.
    """
    response = requests.get("https://mempool.space/api/v1/fees/recommended")
    response.raise_for_status()
    return response.json()
