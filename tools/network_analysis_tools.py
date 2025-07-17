import requests
from config import LND_NETWORK

def get_mempool_top_nodes(limit: int = 10) -> dict:
    """
    Fetches a list of top nodes from mempool.space, then enriches them with
    address and capacity details.
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
            return {"status": "ERROR", "message": "Could not retrieve top nodes by channel count."}

        # Step 2: Enrich with details
        enriched_nodes = []
        for i, node in enumerate(top_by_channels[:int(limit)]):
            pubkey = node.get("publicKey")
            if not pubkey:
                continue

            details_url = f"{base_url}/api/v1/lightning/nodes/{pubkey}"
            details_response = requests.get(details_url)
            if details_response.status_code == 200:
                details = details_response.json()
                # Synthesize a score
                score = details.get("active_channel_count", 0) * int(details.get("capacity", 0))

                enriched_nodes.append({
                    "rank": i + 1,
                    "pub_key": pubkey,
                    "alias": details.get("alias", "N/A"),
                    "score": score,
                    "total_capacity": int(details.get("capacity", 0)),
                    "total_peers": details.get("active_channel_count", 0),
                    "addresses": [details.get("sockets", "")]
                })

        # Sort by our synthesized score
        enriched_nodes.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "status": "OK",
            "data_summary": {"top_nodes_summary": enriched_nodes},
        }

    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "message": f"Failed to fetch data from mempool.space: {e}"}
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
