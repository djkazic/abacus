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
from tools.network_analysis_tools import (
    get_node_availability_data,
    analyze_peer_network,
)
from tools.mempool_space_tools import get_fee_recommendations, get_node_channels_from_mempool

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
    1.  After performing `analyze_peer_network` on your top candidates, you **MUST** call `get_node_channels_from_mempool` for **each of them** to retrieve their detailed channel fee policies.
    2.  **Inferring Liquidity Behavior:** The `get_node_channels_from_mempool` tool returns a list of channels. For each channel, the `fee_rate` is the outbound fee rate for the peer you are analyzing.
        - A peer is a **liquidity sink** if the average `fee_rate` across all its channels is high (e.g., > 500 ppm).
        - A peer is a **liquidity source** if the average `fee_rate` is low (e.g., < 100 ppm).

- **Peer Selection and Final Action:**
    1. After gathering all data (`analyze_peer_network` and `get_node_channels_from_mempool` for all candidates), you will create a final list of suitable peers based on the node's current state.
    2. **Definition of a "Suitable Peer":**
        - **If the node is bootstrapping (has 0 active channels):** A peer is considered "suitable" if it has high connectivity. The liquidity source/sink status **MUST** be ignored for this initial step. The priority is to get connected.
        - **If the node is established (has 1 or more active channels):** A peer is only "suitable" if it meets **both** of the following criteria: it is a **liquidity source** AND it has high connectivity.
    3. **Your final action is dictated by the number of suitable peers you have identified:**
        - **If your list contains two or more suitable peers, you MUST use the `batch_open_channel` tool.**
        - **If your list contains exactly one suitable peer, you MUST use the `open_channel` tool.**
        - **If your list contains zero suitable peers, you MUST report that you found no suitable peers and end your turn.**
    4. Before calling either channel opening tool, you MUST use `connect_peer` for every peer in your final list.

- **Channel Redundancy Check:** Before attempting to open any new channel(s), you **MUST** call `list_lnd_channels` to ensure a channel with the target peer(s) does not already exist.
- **Connection Prerequisite:** **Before opening a channel, you MUST first use `connect_peer` with the chosen peer's public key and a valid `host:port` address.** You can obtain the `host:port` from the `addresses` field within the node data returned by `get_node_availability_data`. This must be done for every peer, even when using `batch_open_channel`.
- **Channel Funding:** After successfully connecting, you *must* propose opening a channel with the selected peer(s). For `local_funding_amount_sat`, you *must* use a value that is at least 5,000,000 satoshis. Aim to fund channels with a portion of the total `walletbalance` or a calculated fraction that leaves room for at least 3-5 more channels) to allow for diversification and future channel openings.
- **Fee Rate:** Before opening a channel, you **MUST** call `get_fee_recommendations` and use the `economyFee` value for the `sat_per_vbyte` parameter in the `open_channel` or `batch_open_channel` call.

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

                    if (
                        function_name == "batch_open_channel"
                        and "channels" in function_args
                    ):
                        function_args["channels"] = [
                            dict(item) for item in function_args["channels"]
                        ]

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
                            "get_node_channels_from_mempool": get_node_channels_from_mempool,
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
