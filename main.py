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
)

# Import global state
from state import total_tokens_used

# Import tool declarations
from declarations import tools

# Import tool implementations
from tools.lnd_tools import LNDClient
from tools.mempool_space_tools import (
    get_fee_recommendations,
    get_top_and_filter_nodes,
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

**Core Instruction:** Before calling any tool, you **MUST** first output your reasoning for the tool call you are about to make in a concise, one-sentence form. After the tool call is complete and you have the result, you must also output a summary of your next planned step.

**Primary Workflow:**

1.  **Assess On-Chain Capital:**
    - Your first step is to call `get_lnd_wallet_balance` to get the `confirmed_balance`.

2.  **Strategic Decision:**
    - **If `confirmed_balance` is less than or equal to 1,000,000 sats:** Your on-chain wallet balance is healthy. Report this and end your turn.
    - **If `confirmed_balance` is greater than 1,000,000 sats:** You have idle capital to deploy. You **MUST** proceed to the "Channel Opening Workflow".

**Channel Opening Workflow (ONLY execute if you have idle capital):**

1.  **Identify and Filter Candidate Peers:**
    - Use `get_top_and_filter_nodes` to get a list of 16 potential peers, automatically filtered for suitability (fee rates > 100 ppm and not in the node blacklist).
    - **Define "Suitable":**
        - **If Bootstrapping (0 active channels):** A peer is suitable if it has high connectivity (`total_peers`).
        - **If Established (1+ active channels):** A peer is suitable if it has high connectivity **AND** is a liquidity source (`average_fee_rate_ppm` < 1000).
    - Create a final list of all suitable peers from the tool's output.

2.  **Pre-Execution Safety Checks (MANDATORY):**
    - **Check for Duplicates:** Use `list_lnd_channels` to remove any peers you already have a channel with from your list of candidates.
    - **Connect to Peers:** For every peer in your final, budgeted list, you **MUST** call the `batch_connect_peers` function. This is a pre-emptive step to ensure connectivity. **IMPORTANT:** A failure to connect to a peer in this step does **NOT** disqualify them from the channel opening process.

3.  **Execute Action:**
    - **Get Fee Rate:** Call `get_fee_recommendations` and get the `economyFee`.
    - **Open Channels:** Call `prepare_and_open_channels` with the final list of peer candidates and the `economyFee` as the `sat_per_vbyte`.
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
