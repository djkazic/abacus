from collections import deque
import json
import requests

from state import _global_all_scored_nodes  # Import global state for recursive analysis


def get_node_availability_data(url: str, limit: int = 5) -> dict:
    """
    Fetches and summarizes node availability data from a given URL (e.g., Lightning Cluster's btc_summary.json).
    Stores the full 'scored' nodes dictionary globally for recursive analysis.
    Returns overall statistics and details for the top N scored nodes to the model.
    """
    global _global_all_scored_nodes  # Declare intent to modify global variable
    try:
        response = requests.get(url)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        return {
            "status": "ERROR",
            "message": f"Failed to fetch data from {url}: {e}",
        }
    except json.JSONDecodeError:
        return {
            "status": "ERROR",
            "message": f"URL returned non-JSON data or empty response: {response.text[:100]}...",
        }

    if "error" in result:
        return {
            "status": "ERROR",
            "message": f"Failed to fetch data from {url}: {result['error']}",
        }

    if "raw_output" in result:
        return {
            "status": "ERROR",
            "message": f"URL returned non-JSON data or empty response: {result['raw_output'][:100]}...",
        }

    full_data = result  # result is already parsed JSON

    _global_all_scored_nodes = full_data.get(
        "scored", {}
    )  # Store the full scored data globally

    summary_data = {
        "last_updated": full_data.get("last_updated"),
        "max_score": full_data.get("max_score"),
        "num_scored": full_data.get("num_scored"),
        "num_stable": full_data.get("num_stable"),
        "num_unstable": full_data.get("num_unstable"),
        "num_non_connectable": full_data.get("num_non_connectable"),
        "heuristics": full_data.get("heuristics"),
        "inbound_thresholds": full_data.get("inbound_thresholds"),
        "top_nodes_summary": [],
    }

    # Convert scored nodes to a list of (pub_key, data) tuples for sorting
    sorted_nodes = []
    for (
        pub_key,
        node_data,
    ) in _global_all_scored_nodes.items():  # Use global data for sorting
        score = node_data.get("score", 0)
        total_peers = node_data.get("total_peers", 0)
        sorted_nodes.append((pub_key, node_data, score, total_peers))

    # Sort by score in descending order
    sorted_nodes.sort(key=lambda x: x[2], reverse=True)

    # Explicitly cast limit to int before slicing
    for i, (pub_key, node_data, score, total_peers) in enumerate(
        sorted_nodes[: int(limit)]
    ):
        summary_data["top_nodes_summary"].append(
            {
                "rank": i + 1,
                "pub_key": pub_key,
                "alias": node_data.get("alias", "N/A"),
                "score": score,
                "total_capacity": node_data.get("total_capacity"),
                "total_peers": node_data.get("total_peers"),
                "centrality_normalized": node_data.get("centrality_normalized"),
                "centrality": node_data.get("centrality"),
                "inbound_efficiency": node_data.get("inbound_efficiency"),
                "max_channel_age": node_data.get("max_channel_age"),
                "addresses": node_data.get("addresses", []),  # Include addresses
            }
        )

    # IMPORTANT: Do NOT return 'all_scored_nodes' here to avoid token limit issues.
    return {"status": "OK", "data_summary": summary_data}


def analyze_peer_network(
    start_pubkey: str, max_depth: int = 3, peers_per_level: int = 3
) -> dict:
    """
    Recursively analyzes a segment of the Lightning Network starting from a given public key,
    fetching details for connected peers up to a specified depth from the globally stored node data.
    Limits the number of peers explored at each level to control token consumption.

    Args:
        start_pubkey (str): The public key of the node to start the analysis from.
        max_depth (int): The maximum recursion depth (e.g., 3 means start_node -> peer1 -> peer2 -> peer3).
        peers_per_level (int): The maximum number of sub-peers to explore at each level.

    Returns:
        dict: A summary of the discovered network segment, including details of each node.
    """
    # Explicitly cast max_depth and peers_per_level to int
    max_depth = int(max_depth)
    peers_per_level = int(peers_per_level)

    if not _global_all_scored_nodes:
        return {
            "status": "ERROR",
            "message": "Global node data is not available. Please call get_node_availability_data first.",
        }

    visited_pubkeys = set()
    queue = deque([(start_pubkey, 0)])  # (pub_key, current_depth)
    discovered_nodes = {}  # Stores full node details for unique pubkeys

    while queue:
        current_pubkey, current_depth = queue.popleft()

        if current_pubkey in visited_pubkeys:
            continue

        visited_pubkeys.add(current_pubkey)

        # Get detailed information for the current node from the global data
        node_data = _global_all_scored_nodes.get(current_pubkey)

        if node_data:
            discovered_nodes[current_pubkey] = {
                "pub_key": current_pubkey,
                "alias": node_data.get("alias", "N/A"),
                "score": node_data.get("score", 0),
                "total_capacity": node_data.get("total_capacity"),
                "total_peers": node_data.get("total_peers"),
                "addresses": node_data.get("addresses", []),
                "depth": current_depth,
            }

            if current_depth < max_depth:
                # Collect all stable peers (inbound and outbound)
                all_stable_peers = set(
                    node_data.get("stable_inbound_peers", [])
                    + node_data.get("stable_outbound_peers", [])
                )

                # Filter out already visited nodes and limit to peers_per_level
                new_peers_to_explore = []
                for peer_pubkey in list(all_stable_peers):
                    if (
                        peer_pubkey not in visited_pubkeys
                        and peer_pubkey in _global_all_scored_nodes
                    ):  # Ensure peer exists in our global data
                        new_peers_to_explore.append(peer_pubkey)
                    if len(new_peers_to_explore) >= peers_per_level:
                        break

                for peer_pubkey in new_peers_to_explore:
                    queue.append((peer_pubkey, current_depth + 1))
        else:
            print(f"Could not find details for {current_pubkey} in global node data.")

    # Convert discovered_nodes dict to a list for the final output, sorted by score
    sorted_discovered_nodes = sorted(
        discovered_nodes.values(), key=lambda x: x.get("score", 0), reverse=True
    )

    return {
        "status": "OK",
        "network_analysis": sorted_discovered_nodes,
        "message": f"Network analysis completed for {len(discovered_nodes)} nodes up to depth {max_depth}.",
    }


def get_node_channels_from_amboss(
    pubkey: str, limit: int = 10, offset: int = 0
) -> dict:
    """
    Fetches detailed channel information for a given Lightning Network node from Amboss.space,
    including fee policies for both sides of each channel. This data is crucial for inferring
    liquidity sink/source characteristics.
    """
    graphql_query = """
    query GetNodeChannels($pubkey: String!, $order: OrderChannelInput, $page: PageInput) {
      getNode(pubkey: $pubkey) {
        graph_info {
          node {
            alias
            __typename
          }
          channels {
            num_channels
            channel_list(order: $order, page: $page) {
              pagination {
                limit
                offset
                __typename
              }
              list {
                block_age
                capacity
                chan_point
                last_update_date
                long_channel_id
                node1_policy {
                  disabled
                  fee_base_msat
                  fee_rate_milli_msat
                  inbound_fee_base_msat
                  inbound_fee_rate_milli_msat
                  last_update
                  max_htlc_msat
                  min_htlc
                  time_lock_delta
                  __typename
                }
                node1_pub
                node2_policy {
                  disabled
                  fee_base_msat
                  fee_rate_milli_msat
                  inbound_fee_base_msat
                  inbound_fee_rate_milli_msat
                  last_update
                  max_htlc_msat
                  min_htlc
                  time_lock_delta
                  __typename
                }
                node2_pub
                opened_by_market_order
                short_channel_id
                node1_report {
                  balance
                  balance_range
                  __typename
                }
                node2_info {
                  node {
                    alias
                    __typename
                  }
                  metrics {
                    capacity
                    channels
                    __typename
                  }
                  __typename
                }
                transactions {
                  open_transaction {
                    batch_amount
                    fee
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
    }
    """

    # Construct the data payload
    data_payload = {
        "operationName": "GetNodeChannels",
        "variables": {"pubkey": pubkey, "page": {"limit": limit, "offset": offset}},
        "query": graphql_query,
    }

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "amboss-client": "amboss-space",
        "apollographql-client-name": "space-prod",
        "apollographql-client-version": "0.1.13",
        "authorization": "",  # Leave empty if no auth token
        "content-type": "application/json",
        "origin": "https://amboss.space",
        "priority": "u=1, i",
        "referer": f"https://amboss.space/node/{pubkey}?section=Channels",
        "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    }

    try:
        response = requests.post(
            "https://amboss.space/graphql", headers=headers, json=data_payload
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        full_data = response.json()

        # Log the size of the raw JSON response
        print(
            f"Tool output size (raw JSON from requests): {len(response.text)} characters."
        )

    except requests.exceptions.RequestException as e:
        return {
            "status": "ERROR",
            "message": f"Failed to fetch channel data from Amboss: {e}",
        }
    except json.JSONDecodeError:
        return {
            "status": "ERROR",
            "message": "Failed to decode JSON response from Amboss.",
        }

    # Extract relevant data
    node_data = full_data.get("data", {}).get("getNode", {})
    if not node_data:
        return {
            "status": "NOT_FOUND",
            "message": f"Node {pubkey} not found or no graph info available on Amboss.",
        }

    alias = node_data.get("graph_info", {}).get("node", {}).get("alias", "N/A")
    channels_info = node_data.get("graph_info", {}).get("channels", {})
    num_channels = channels_info.get("num_channels")
    channel_list = channels_info.get("channel_list", {}).get("list", [])

    # Initialize lists to store fee rates for aggregation
    our_outbound_fees = []
    peer_outbound_fees = []
    our_inbound_fees = []
    peer_inbound_fees = []

    for channel in channel_list:
        node1_pub = channel.get("node1_pub")
        node2_pub = channel.get("node2_pub")

        queried_node_policy = None
        peer_node_policy = None

        if node1_pub == pubkey:
            queried_node_policy = channel.get("node1_policy")
            peer_node_policy = channel.get("node2_policy")
        elif node2_pub == pubkey:
            queried_node_policy = channel.get("node2_policy")
            peer_node_policy = channel.get("node1_policy")

        if queried_node_policy and peer_node_policy:
            # Collect fee rates, converting to int for calculations
            if queried_node_policy.get("fee_rate_milli_msat") is not None:
                our_outbound_fees.append(
                    int(queried_node_policy["fee_rate_milli_msat"])
                )
            if peer_node_policy.get("fee_rate_milli_msat") is not None:
                peer_outbound_fees.append(int(peer_node_policy["fee_rate_milli_msat"]))
            if queried_node_policy.get("inbound_fee_rate_milli_msat") is not None:
                our_inbound_fees.append(
                    int(queried_node_policy["inbound_fee_rate_milli_msat"])
                )
            if peer_node_policy.get("inbound_fee_rate_milli_msat") is not None:
                peer_inbound_fees.append(
                    int(peer_node_policy["inbound_fee_rate_milli_msat"])
                )

    # Calculate aggregated fee statistics
    def calculate_stats(fees_list):
        if not fees_list:
            return {"avg": "N/A", "min": "N/A", "max": "N/A"}
        return {
            "avg": sum(fees_list) / len(fees_list),
            "min": min(fees_list),
            "max": max(fees_list),
        }

    our_outbound_stats = calculate_stats(our_outbound_fees)
    peer_outbound_stats = calculate_stats(peer_outbound_fees)
    our_inbound_stats = calculate_stats(our_inbound_fees)
    peer_inbound_stats = calculate_stats(peer_inbound_fees)

    return {
        "status": "OK",
        "pubkey": pubkey,
        "alias": alias,
        "num_channels": num_channels,
        "fee_policy_summary": {
            "our_outbound_fees_milli_msat": our_outbound_stats,
            "peer_outbound_fees_milli_msat": peer_outbound_stats,
            "our_inbound_fees_milli_msat": our_inbound_stats,
            "peer_inbound_fees_milli_msat": peer_inbound_stats,
        },
        "message": f"Fetched summarized fee policies for {alias} ({pubkey}) across {num_channels} channels.",
    }
