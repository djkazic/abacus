import requests
from config import LND_NETWORK


def get_fee_recommendations():
    """
    Fetches recommended fee rates from mempool.space's API.

    Returns:
        dict: A dictionary containing the recommended fee rates.
    """
    base_url = "https://mempool.space"
    if LND_NETWORK == "testnet":
        base_url += "/testnet"

    response = requests.get(f"{base_url}/api/v1/fees/recommended")
    response.raise_for_status()
    return response.json()


def get_node_channels_from_mempool(pubkey: str) -> dict:
    """
    Fetches detailed channel information for a given Lightning Network node from mempool.space,
    and returns a summary of their fee policies.
    """
    base_url = "https://mempool.space"
    if LND_NETWORK == "testnet":
        base_url += "/testnet"

    url = f"{base_url}/api/v1/lightning/channels?public_key={pubkey}&status=active&index=-1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        channels = response.json()

        if not channels:
            return {"status": "OK", "data": {"pubkey": pubkey, "num_channels": 0, "average_fee_rate_ppm": "N/A"}}

        total_fee_rate = 0
        for channel in channels:
            # The fee_rate is the outbound fee for the node we are querying
            total_fee_rate += channel.get("fee_rate", 0)

        average_fee_rate = total_fee_rate / len(channels) if channels else 0

        # Get node alias from the first channel (it's the same for all)
        alias = channels[0].get("node", {}).get("alias", "N/A")

        return {
            "status": "OK",
            "data": {
                "pubkey": pubkey,
                "alias": alias,
                "num_channels": len(channels),
                "average_fee_rate_ppm": average_fee_rate,
            }
        }
    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "message": f"Failed to fetch data from {url}: {e}"}
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
