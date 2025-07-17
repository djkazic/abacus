import requests
from config import LND_NETWORK, NODE_BLACKLIST
import concurrent.futures


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


def _get_node_channels_from_mempool(pubkey: str) -> dict:
    """
    Fetches detailed channel information for a given Lightning Network node from mempool.space,
    and returns a summary of their fee policies.
    """
    base_url = "https://mempool.space"
    if LND_NETWORK == "testnet":
        base_url += "/testnet"

    url = f"{base_url}/api/v1/lightning/channels?public_key={pubkey}&status=active&index=0"
    try:
        response = requests.get(url)
        response.raise_for_status()
        channels = response.json()

        if not channels:
            return {
                "status": "OK",
                "data": {
                    "pubkey": pubkey,
                    "num_channels": 0,
                    "average_fee_rate_ppm": "N/A",
                },
            }

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
            },
        }
    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "message": f"Failed to fetch data from {url}: {e}"}
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}


def get_top_and_filter_nodes(limit: int = 10) -> dict:
    """
    Fetches a list of top nodes, enriches them with details, and filters them
    based on their average fee rates.
    """
    base_url = "https://mempool.space"
    if LND_NETWORK == "testnet":
        base_url += "/testnet"

    try:
        # Step 1: Get top nodes by channel count
        rankings_url = f"{base_url}/api/v1/lightning/nodes/rankings"
        response = requests.get(rankings_url)
        response.raise_for_status()
        rankings = response.json()
        top_by_channels = rankings.get("topByChannels", [])

        if not top_by_channels:
            return {
                "status": "ERROR",
                "message": "Could not retrieve top nodes by channel count.",
            }

        # Step 2: Enrich with details and filter
        pubkeys_to_check = [
            node.get("publicKey")
            for node in top_by_channels[: int(limit)]
            if node.get("publicKey")
        ]

        # Fetch channel info in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            channel_results = list(
                executor.map(_get_node_channels_from_mempool, pubkeys_to_check)
            )

        # Filter out nodes with low fee rates or in blacklist
        final_nodes = []
        for result in channel_results:
            if result.get("status") == "OK":
                data = result.get("data", {})
                pubkey = data.get("pubkey")

                if pubkey in NODE_BLACKLIST:
                    continue

                avg_fee = data.get("average_fee_rate_ppm")
                if isinstance(avg_fee, (int, float)) and avg_fee <= 100:
                    continue  # Skip nodes with low or zero fees

                # If the node is suitable, fetch its full details
                details_url = f"{base_url}/api/v1/lightning/nodes/{pubkey}"
                details_response = requests.get(details_url)
                if details_response.status_code == 200:
                    details = details_response.json()
                    score = details.get("active_channel_count", 0) * int(
                        details.get("capacity", 0)
                    )
                    final_nodes.append(
                        {
                            "pub_key": pubkey,
                            "alias": details.get("alias", "N/A"),
                            "score": score,
                            "total_capacity": int(details.get("capacity", 0)),
                            "total_peers": details.get("active_channel_count", 0),
                            "addresses": [details.get("sockets", "")],
                            "average_fee_rate_ppm": avg_fee,
                        }
                    )

        # Sort by our synthesized score
        final_nodes.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "status": "OK",
            "data_summary": {"top_nodes_summary": final_nodes},
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "ERROR",
            "message": f"Failed to fetch data from mempool.space: {e}",
        }
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
