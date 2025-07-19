import os
import time
import json
import google.generativeai as genai
import sys
import select
from collections import deque
from google.api_core.retry import Retry
from google.generativeai.types import StopCandidateException

# Import configurations
from config import (
    MODEL_NAME,
    TICK_INTERVAL_SECONDS,
    MAX_HISTORY_LENGTH,
    LND_ADMIN_MACAROON_PATH,
    MAX_PAYLOAD_SIZE_CHARACTERS,
    LND_NETWORK,
    LOOP_GRPC_HOST,
    LOOP_GRPC_PORT,
    LOOP_MACAROON_PATH,
    LOOP_TLS_CERT_PATH,
)

# Import global state
from state import total_tokens_used

# Import tool declarations
from declarations import tools

# Import tool implementations
from tools.lnd_tools import LNDClient
from tools.loop_tools import LoopClient
from tools.mempool_space_tools import (
    get_fee_recommendations,
    get_top_and_filter_nodes,
)
from tools.fee_management_tools import (
    analyze_channel_liquidity_flow,
    calculate_and_quote_loop_outs,
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
loop_client = LoopClient(
    LOOP_GRPC_HOST, LOOP_GRPC_PORT, LOOP_TLS_CERT_PATH, LOOP_MACAROON_PATH
)

# --- Initialize Model and Chat ---
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel(MODEL_NAME, tools=tools)

SYSTEM_PROMPT = f"""You are an autonomous Lightning Network agent operating on the **{LND_NETWORK}** network. Your primary goals are to intelligently deploy capital and actively manage channel fees to maximize routing revenue.

**Core Instruction:** You must decide which workflow to enter based on the node's current state. Before calling any tool, you **MUST** first output a brief justification for the tool call you are about to make. After the tool call is complete and you have the result, you must also output a summary of your next planned step.

---

### Step 1: Initial State Assessment

Your first step is to always get a complete picture of your node's current state.

1.  **Call `get_lnd_wallet_balance`** to get the on-chain `confirmed_balance`.
2.  **Call `list_lnd_channels`** to get a list of all active channels.
3.  **Calculate `total_outbound_liquidity`** by summing the `local_balance` of all your active channels.

---

### Step 2: Strategic Decision

Based on the state assessment, you must now decide which workflow to enter.

-   **If `total_outbound_liquidity` is less than 10,000,000 sats AND `confirmed_balance` is greater than 1,000,000 sats:** You have a need for more outbound liquidity and the funds to acquire it. **Proceed to the Channel Opening Workflow.**
-   **Otherwise:** Your outbound liquidity is sufficient, or you lack the on-chain funds to improve it. **Proceed to the Fee Management Workflow.**

---

### Workflow A: Channel Opening (Deploying Capital)

**Trigger:** Low outbound liquidity and sufficient on-chain funds.

1.  **Identify and Filter Candidate Peers:**
    - Call `get_top_and_filter_nodes` to get a list of 16 potential peers. This list is automatically filtered for high uptime, good fee structures, and excludes blacklisted nodes.
    - From this list, create a final list of suitable peers. A peer is suitable if it has high connectivity (`total_peers`) and, if you are an established node (1+ channels), is a liquidity source (`average_fee_rate_ppm` < 1000).

2.  **Pre-Execution Safety Checks:**
    - From your list of candidates, remove any peers you already have a channel with (this is a redundant check, as `list_lnd_channels` was already called, but it is a good safety measure).
    - Call `batch_connect_peers` for all candidates. A failure to connect does **not** disqualify a peer.

3.  **Execute Action:**
    - Call `get_fee_recommendations` to get the `economyFee`.
    - Call `prepare_and_open_channels` with your final list of peers and the `economyFee` to open the channels.

---

### Workflow B: Fee Management (Maximizing Revenue)

**Trigger:** Sufficient outbound liquidity OR insufficient on-chain funds.

1.  **Analyze Liquidity Flow:**
    - Call `analyze_channel_liquidity_flow` to get a detailed analysis of each channel's performance over the last 7 days.

2.  **Check Channels and Loop Out if Necessary:**
    - From the analysis, create a list of `channel_id`s for channels where `is_economical_loop_out_candidate` is true.
    - If this list is not empty, call `calculate_and_quote_loop_outs` with this list of `channel_id`s.
    - For each channel in the result that has a `loop_out_amount_sat` greater than 0, call `initiate_loop_out` for that `channel_id` to start the swap.

3.  **Perform Per-Channel Fee Adjustments:**
    - For each channel in the analysis:
        - **If `liquidity_trend` is "outbound" and `balance_ratio` is less than 20%:** The channel is depleted. **Raise the fee rate** to discourage further outbound flow. A new `fee_rate_ppm` of 1000 is a good starting point.
        - **If `liquidity_trend` is "inbound" and `balance_ratio` is greater than 80%:** The channel is saturated with local liquidity. **Lower the fee rate** to encourage outbound flow. A new `fee_rate_ppm` of 100 is a good starting point.
        - **If the channel is "balanced" or "stagnant":** Do not adjust the fees.
    - For each channel that needs an adjustment, call the `set_fee_policy` tool with the `channel_id` and the new `fee_rate_ppm`. You can leave `base_fee_msat` at its current value if you are only adjusting the rate.

"""


def _convert_args_to_dict(args):
    """Recursively converts protobuf MapComposite and RepeatedComposite objects to JSON-serializable dicts and lists."""
    if hasattr(args, "items"):  # Dict-like
        return {key: _convert_args_to_dict(value) for key, value in args.items()}
    elif hasattr(args, "__iter__") and not isinstance(args, str):  # List-like
        return [_convert_args_to_dict(item) for item in args]
    else:
        return args


def main():
    global total_tokens_used
    tui = TUI()
    tui.display_welcome()

    chat = model.start_chat(history=[{"role": "user", "parts": [SYSTEM_PROMPT]}])

    current_user_message = (
        "Assess the node's current state and take action if necessary."
    )

    request_options = {"retry": Retry()}

    while True:
        try:
            tui.display_message("system", "--- TICK START ---")

            if "Assess the node" in current_user_message:
                tui.display_message("system", f"Agent prompt: {current_user_message}")
            else:
                tui.display_message("user", current_user_message)

            tui.start_live_display()

            try:
                response = chat.send_message(
                    current_user_message, request_options=request_options
                )
            except StopCandidateException as e:
                tui.stop_live_display()
                tui.display_error(
                    f"Model stopped with reason: {e.args[0].finish_reason.name}"
                )
                tui.display_error(f"Candidate content: {e.args[0].content}")
                continue
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
                    time.sleep(1)
                    function_name = function_call.name
                    function_args = _convert_args_to_dict(function_call.args)

                    tui.display_tool_call(function_name, function_args)

                    tool_output = {}
                    sensitive_tools = [
                        "prepare_and_open_channels",
                        "set_fee_policy",
                        "initiate_loop_out",
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
                            "prepare_and_open_channels": lnd_client.prepare_and_open_channels,
                            "list_lnd_peers": lnd_client.list_lnd_peers,
                            "connect_peer": lnd_client.connect_peer,
                            "batch_connect_peers": lnd_client.batch_connect_peers,
                            "get_top_and_filter_nodes": get_top_and_filter_nodes,
                            "get_fee_recommendations": get_fee_recommendations,
                            "list_lnd_channels": lnd_client.list_lnd_channels,
                            "analyze_channel_liquidity_flow": lambda: analyze_channel_liquidity_flow(
                                lnd_client
                            ),
                            "calculate_and_quote_loop_outs": lambda **kwargs: calculate_and_quote_loop_outs(
                                lnd_client, loop_client, **kwargs
                            ),
                            "initiate_loop_out": lambda **kwargs: loop_client.initiate_loop_out(
                                lnd_client, **kwargs
                            ),
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

                try:
                    next_response = chat.send_message(
                        genai.protos.Content(parts=tool_responses_parts),
                        request_options=request_options,
                    )
                except StopCandidateException as e:
                    tui.stop_live_display()
                    tui.display_error(
                        f"Model stopped with reason: {e.args[0].finish_reason.name}"
                    )
                    tui.display_error(f"Candidate content: {e.args[0].content}")
                    current_response_parts = []
                    continue
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
