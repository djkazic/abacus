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
    MAX_PAYLOAD_SIZE_CHARACTERS,
    LND_NETWORK,
)

# Import global state
from state import total_tokens_used

# Import tool declarations
from declarations import tools

# Import tool implementations
from tools.lnd_tools import LNDClient
from tools.network_analysis_tools import get_mempool_top_nodes
from tools.mempool_space_tools import (
    get_fee_recommendations,
    get_node_channels_from_mempool,
)

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

SYSTEM_PROMPT = f"""You are an autonomous Lightning Network agent operating on the **{LND_NETWORK}** network. Your goal is to intelligently deploy capital into channels.

**Primary Workflow:**

1.  **Assess On-Chain Capital:**
    - Your first step is to call `get_lnd_wallet_balance` to get the `confirmed_balance`.

2.  **Strategic Decision:**
    - **If `confirmed_balance` is less than or equal to 1,000,000 sats:** Your on-chain wallet balance is healthy. Report this and end your turn.
    - **If `confirmed_balance` is greater than 1,000,000 sats:** You have idle capital to deploy. You **MUST** proceed to the "Channel Opening Workflow".

**Channel Opening Workflow (ONLY execute if you have idle capital):**

1.  **Identify Candidate Peers:**
    - Use `get_mempool_top_nodes` to get a list of potential peers.

2.  **Filter for Suitable Peers:**
    - For each candidate, use `get_node_channels_from_mempool` to check their average fee rate.
    - **Define "Suitable":**
        - **If Bootstrapping (0 active channels):** A peer is suitable if it has high connectivity (`total_peers`). Liquidity status is ignored.
        - **If Established (1+ active channels):** A peer is suitable if it has high connectivity **AND** is a liquidity source (`average_fee_rate_ppm` < 100).
    - Create a final list of all suitable peers.

3.  **Pre-Execution Safety Checks (MANDATORY):**
    - **Check for Duplicates:** Use `list_lnd_channels` to remove any peers you already have a channel with.
    - **Financial Safety:**
        1. Call `get_lnd_wallet_balance` (if you haven't already).
        2. Calculate `available_funds` = `confirmed_balance` - 1,000,000 sats.
        3. Calculate `per_channel_amount` = `available_funds` / number of peers in your final list.
        4. If `per_channel_amount` is less than 5,000,000 sats, you **MUST** reduce the number of peers (starting with the lowest-ranked) and recalculate until the minimum is met.
    - **Connect to Peers:** For every peer in your final, budgeted list, you **MUST** call the `connect_peer` function.

4.  **Execute Action:**
    - **Get Fee Rate:** Call `get_fee_recommendations` and use the `economyFee`.
    - **Open Channels:**
        - If you have 2 or more peers in your final list, use `batch_open_channel`.
        - If you have 1 peer, use `open_channel`.
        - If you have 0 peers, report that none were suitable and stop.
"""


def main():
    global total_tokens_used
    tui = TUI()
    tui.display_welcome()

    chat = model.start_chat(history=[{"role": "user", "parts": [SYSTEM_PROMPT]}])

    current_user_message = (
        "Assess the node's current state and take action if necessary."
    )

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
                            "get_mempool_top_nodes": get_mempool_top_nodes,
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

                # Safety check for payload size
                payload_str = str(tool_responses_parts)
                if len(payload_str) > MAX_PAYLOAD_SIZE_CHARACTERS:
                    error_message = {
                        "error": f"Tool response payload is too large ({len(payload_str)} characters). "
                        "The maximum is {MAX_PAYLOAD_SIZE_CHARACTERS}. "
                        "Please try a more specific tool call."
                    }
                    # This simulates an error response from a tool
                    tool_responses_parts = [
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name="error_handler", response=error_message
                            )
                        )
                    ]

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
