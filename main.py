import os
import time
import json
import google.generativeai as genai
import sys
import select
from collections import deque

# Import configurations
from config import (
    MODEL_NAME,
    TICK_INTERVAL_SECONDS,
    MAX_HISTORY_LENGTH,
    LND_ADMIN_MACAROON_PATH,
)

# Import global state
from state import total_tokens_used

# Import tool declarations
from declarations import tools

# Import tool implementations
from tools.lnd_tools import LNDClient
from tools.amboss_tools import (
    get_node_availability_data,
    analyze_peer_network,
    get_node_channels_from_amboss,
)
from tools.mempool_space_tools import get_fee_recommendations

# Import the TUI
from tui import TUI

# --- LND gRPC Configuration (assuming environment variables are set) ---
LND_GRPC_HOST = os.getenv("LND_GRPC_HOST", "localhost")
LND_GRPC_PORT = int(os.getenv("LND_GRPC_PORT", 10009))
LND_TLS_CERT_PATH = os.getenv("LND_TLS_CERT_PATH", "/lnd/tls.cert")

# Initialize LND gRPC client
lnd_client = LNDClient(
    LND_GRPC_HOST, LND_GRPC_PORT, LND_TLS_CERT_PATH, LND_ADMIN_MACAROON_PATH
)

# --- Initialize Model and Chat ---
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel(MODEL_NAME, tools=tools)

SYSTEM_PROMPT = """You are an autonomous Lightning Network agent. Your core mission is to optimize liquidity and manage channels, using your tools to gather information and perform actions.

**Decision-Making for Channel Opening:**
- **Initial Peer Identification:** Begin by using `get_node_availability_data` to fetch an initial list of top-performing nodes. This call will also internally store the comprehensive node data for deeper analysis.
- **Deep Network Analysis:**
    1.  Identify at least 2-3 of the highest-scoring potential peers from the `top_nodes_summary` provided by `get_node_availability_data`.
    2.  For **EACH** of these promising candidate peers, you *must* use `analyze_peer_network` on its `pub_key`. This analysis will reveal its broader network connectivity, including its direct and indirect peers.
    3.  A well-connected peer typically has at least 5 existing channels and a high score. When calling `analyze_peer_network`, limit `max_depth` to 3 and `peers_per_level` to 3 to manage token usage.
- **Liquidity Sink/Source Analysis:**
    1.  After performing `analyze_peer_network` on your top candidates, for the most promising 1-2 peers, you **MUST** call `get_node_channels_from_amboss` to retrieve their detailed channel fee policies.
    2.  **Inferring Liquidity Behavior:**
        * **From Outbound Fees (your perspective):** If a peer has a consistently *high* `fee_rate_milli_msat` for its *outbound* channels (meaning it charges a lot to send funds out), it is likely trying to *retain* outbound liquidity and acts as a **liquidity sink**. If it has consistently *low* outbound fees (e.g., < 100 ppm), it is likely trying a **liquidity source**.
        * **From Inbound Fees (peer's perspective, your outbound):** If a peer charges *high* `inbound_fee_rate_milli_msat` for its channels (meaning it's expensive for others to send funds to it), it's trying to *retain* inbound liquidity. If it charges *low* inbound fees, it's trying to *gain* inbound liquidity.
        * **From Peers' Outbound Fees (recursive inference):** If the majority of a candidate peer's *own* channels (as seen in `get_node_channels_from_amboss` output) are connected to nodes that have *high outbound fees* (meaning those nodes are sinks), then the candidate peer itself is likely a **liquidity sink**. Conversely, if its channels are mostly to nodes with *low outbound fees* (sources), then the candidate peer is likely a **liquidity source**.

- **Peer Selection for Channel (Strict Adherence & Combined Analysis):** After performing both `analyze_peer_network` and `get_node_channels_from_amboss` on multiple candidates, you **MUST** carefully compare their `network_analysis` results and their inferred liquidity characteristics. Select the single most suitable peer for a new channel that demonstrates:
    * Highest overall connectivity (e.g., a high number of discovered channels, high average score of its discovered neighbors, or a high score for the node itself from the `analyze_peer_network` output).
    * **And** appears to be a **liquidity source** or has **favorable inbound fee policies** for your node, based on the `get_node_channels_from_amboss` data.
    **The peer chosen for `connect_peer` and `open_channel` must be one of the top candidates identified and validated through this combined analysis process.** Do NOT select a peer that was not part of this recent network analysis or was not deemed most suitable.
    **Special Rule for New Nodes (0 Channels):** If the LND node has `num_active_channels` equal to 0 (zero), the agent **MUST** prioritize opening at least one channel to a highly-connected peer, even if that peer exhibits characteristics of a liquidity sink. The primary goal in this state is to establish initial network connectivity. Once at least one channel is open, the agent can revert to stricter liquidity optimization criteria for subsequent channel openings.

- **Channel Redundancy Check:** Before attempting to open a new channel, you **MUST** call `list_lnd_channels` to ensure a channel with the target peer does not already exist. Do not open a channel if one already exists with the peer.
- **Connection Prerequisite:** **Before opening a channel, you MUST first use `connect_peer` with the chosen peer's public key and a valid `host:port` address.** You can obtain the `host:port` from the `addresses` field within the node data returned by `get_node_availability_data`.
- **Channel Funding:** After successfully connecting, you *must* propose opening a channel with this selected peer. For `local_funding_amount_sat`, you *must* use a value that is at least 5,000,000 satoshis. Aim to fund channels with a portion of the total `walletbalance` or a calculated fraction that leaves room for at least 3-5 more channels) to allow for diversification and future channel openings.
- **Fee Rate:** Before opening a channel, you **MUST** call `get_fee_recommendations` and use the `economyFee` value for the `sat_per_vbyte` parameter in the `open_channel` call.

**Batch Channel Opening:**
- If you identify multiple suitable peers for channel opening, you can use the `batch_open_channel` tool to open them all in a single transaction to save on-chain fees.

**External Data Sources:**
- Use `get_node_availability_data` to fetch and *summarize* external JSON data about node availability and scores from specified URLs. This tool is designed to handle large datasets by providing key statistics and top-node summaries, and it internally stores the full raw data of all scored nodes for subsequent detailed analysis.
- Use `analyze_peer_network` to recursively explore the network around a specific peer, helping to identify highly connected nodes for strategic channel openings. Limit `max_depth` to 3 and `peers_per_level` to 3 to manage token usage.

**Response Style:** Your textual responses should be extremely concise! Focus on direct observations and actionable recommendations when not calling tools.
"""


def main():
    global total_tokens_used
    tui = TUI()
    tui.display_welcome()

    chat = model.start_chat(history=[{"role": "user", "parts": [SYSTEM_PROMPT]}])

    current_user_message = "Perform a comprehensive assessment of the LND node's current state, including its on-chain balance. Identify any immediate actions required for liquidity and channel management. Consider using `get_node_availability_data` to fetch external node scores if relevant for peer selection. After identifying a potential peer, use `analyze_peer_network` to understand its connectivity before opening a channel."

    while True:
        try:
            tui.display_message("system", "--- TICK START ---")

            if "Perform a comprehensive assessment" in current_user_message:
                tui.display_message("system", f"Agent prompt: {current_user_message}")
            else:
                tui.display_message("user", current_user_message)

            tui.start_live_display()

            response = chat.send_message(current_user_message)
            total_tokens_used += response.usage_metadata.total_token_count

            current_response_parts = list(response.parts)

            while current_response_parts:
                function_calls_to_execute = []
                text_output_parts = []

                for part in current_response_parts:
                    if part.function_call:
                        function_calls_to_execute.append(part.function_call)
                    elif part.text:
                        text_output_parts.append(part)

                if text_output_parts:
                    for text_part in text_output_parts:
                        tui.stop_live_display()
                        tui.display_message("model", text_part.text)
                        tui.start_live_display()

                if not function_calls_to_execute:
                    break

                tool_responses_parts = []
                for function_call in function_calls_to_execute:
                    function_name = function_call.name
                    function_args = dict(function_call.args)
                    tui.display_tool_call(function_name, function_args)

                    tool_output = {}
                    sensitive_tools = [
                        "open_channel",
                        "set_fee_policy",
                        "batch_open_channel",
                    ]

                    execute = True
                    if function_name in sensitive_tools:
                        prompt = f"Do you want to execute the tool '{function_name}'?"
                        if not tui.get_confirmation(prompt):
                            tool_output = {
                                "error": f"User denied execution of tool: {function_name}"
                            }
                            execute = False

                    if execute:
                        tool_implementations = {
                            "get_lnd_info": lnd_client.get_lnd_info,
                            "get_lnd_wallet_balance": lnd_client.get_lnd_wallet_balance,
                            "get_lnd_state": lnd_client.get_lnd_state,
                            "set_fee_policy": lnd_client.set_fee_policy,
                            "open_channel": lnd_client.open_channel,
                            "batch_open_channel": lnd_client.batch_open_channel,
                            "list_lnd_peers": lnd_client.list_lnd_peers,
                            "connect_peer": lnd_client.connect_peer,
                            "get_node_availability_data": get_node_availability_data,
                            "analyze_peer_network": analyze_peer_network,
                            "get_node_channels_from_amboss": get_node_channels_from_amboss,
                            "get_fee_recommendations": get_fee_recommendations,
                            "list_lnd_channels": lnd_client.list_lnd_channels,
                        }

                        if function_name in tool_implementations:
                            try:
                                tool_output = tool_implementations[function_name](
                                    **function_args
                                )
                            except Exception as e:
                                tool_output = {"error": str(e)}
                        else:
                            tool_output = {
                                "error": f"Unknown function requested by model: {function_name}"
                            }

                    tui.display_tool_output(function_name, tool_output)

                    tool_responses_parts.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=function_name, response=tool_output
                            )
                        )
                    )

                next_response = chat.send_message(
                    genai.protos.Content(parts=tool_responses_parts)
                )
                total_tokens_used += next_response.usage_metadata.total_token_count
                current_response_parts = list(next_response.parts)

            tui.stop_live_display()
            tui.display_message("system", "--- TICK END ---")
            tui.display_message(
                "system", f"Total tokens used so far: {total_tokens_used}"
            )
            tui.display_message(
                "system",
                f"Waiting for {TICK_INTERVAL_SECONDS} seconds until next tick...",
            )

            ready, _, _ = select.select([sys.stdin], [], [], TICK_INTERVAL_SECONDS)

            if ready:
                current_user_message = sys.stdin.readline().strip()
                if current_user_message.lower() in ["exit", "quit"]:
                    break
            else:
                current_user_message = "Perform a comprehensive assessment of the LND node's current state, including its on-chain balance. Identify any immediate actions required for liquidity and channel management. Consider using `get_node_availability_data` to fetch external node scores if relevant for peer selection. After identifying a potential peer, use `analyze_peer_network` to understand its connectivity before opening a channel."

        except KeyboardInterrupt:
            tui.display_message("system", "\nAgent stopped by user.")
            break
        except Exception as e:
            tui.stop_live_display()
            tui.display_error(str(e))
            time.sleep(TICK_INTERVAL_SECONDS)

    print(f"Final total tokens used: {total_tokens_used}")


if __name__ == "__main__":
    main()
