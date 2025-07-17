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


def get_node_channels_from_mempool(pubkey: str) -> dict:
    """
    Fetches detailed channel information for a given Lightning Network node from mempool.space.
    """
    url = f"https://mempool.space/api/v1/lightning/channels?public_key={pubkey}&status=active&index=-1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return {"status": "OK", "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "message": f"Failed to fetch data from {url}: {e}"}
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
