from tools.lnd_tools import LNDClient, LOOP_NODE_PUBKEY
from tools.loop_tools import LoopClient
from collections import defaultdict
import grpc
from google.protobuf.json_format import MessageToDict
from datetime import datetime, timedelta

try:
    import client_pb2 as looprpc
except ImportError:
    looprpc = None


def _is_loop_out_candidate(channel: dict, flow: dict, pending_swaps: list) -> bool:
    """
    Determines if a channel is a candidate for a Loop Out based on liquidity
    balance and pending swap status.
    """
    # Condition 1: High outbound liquidity (over 80%)
    capacity = int(channel.get("capacity", 0))
    if capacity == 0:
        return False
    balance_ratio = int(channel.get("local_balance", 0)) / capacity
    if balance_ratio <= 0.8:
        return False

    # Condition 2: No pending swap for this channel
    chan_id_str = str(channel.get("chan_id"))
    for swap in pending_swaps:
        if chan_id_str in swap.get("outgoing_chan_set", []):
            return False  # This channel is already part of a pending swap

    return True


def analyze_channel_liquidity_flow(
    lnd_client: LNDClient, loop_client: LoopClient
) -> dict:
    """
    Analyzes the liquidity flow of each channel over the last 7 days and
    provides a summary with the current balance and a liquidity trend.
    """
    # 1. Get Pending Swaps
    swaps_response = loop_client.list_loop_out_swaps()
    if swaps_response.get("status") != "OK":
        return swaps_response
    pending_swaps = [
        s
        for s in swaps_response.get("data", {}).get("swaps", [])
        if s.get("state") not in ["SUCCESS", "FAILED"]
    ]

    # 2. Get Forwarding History
    history_response = lnd_client.forwarding_history(days_to_check=7)
    if history_response.get("status") != "OK":
        return history_response
    forwarding_events = history_response.get("data", {}).get("forwarding_events", [])

    # 3. Get Current Channel State
    channels_response = lnd_client.list_lnd_channels()
    if channels_response.get("status") != "OK":
        return channels_response
    channels = channels_response.get("data", {}).get("channels", [])

    # 4. Process Data
    flow_by_channel = defaultdict(
        lambda: {"inbound_msat": 0, "outbound_msat": 0, "last_forward_time": None}
    )
    for event in forwarding_events:
        chan_id_in = event.get("chan_id_in")
        chan_id_out = event.get("chan_id_out")
        amt_in_msat = int(event.get("amt_in_msat", 0))
        amt_out_msat = int(event.get("amt_out_msat", 0))
        timestamp_ns = int(event.get("timestamp_ns", 0))
        event_time = datetime.fromtimestamp(timestamp_ns / 1e9)

        if chan_id_in:
            flow_by_channel[chan_id_in]["inbound_msat"] += amt_in_msat
            if (
                not flow_by_channel[chan_id_in]["last_forward_time"]
                or event_time > flow_by_channel[chan_id_in]["last_forward_time"]
            ):
                flow_by_channel[chan_id_in]["last_forward_time"] = event_time
        if chan_id_out:
            flow_by_channel[chan_id_out]["outbound_msat"] += amt_out_msat
            if (
                not flow_by_channel[chan_id_out]["last_forward_time"]
                or event_time > flow_by_channel[chan_id_out]["last_forward_time"]
            ):
                flow_by_channel[chan_id_out]["last_forward_time"] = event_time

    # 5. Generate Analysis
    analysis_results = []
    for channel in channels:
        if channel.get("remote_pubkey") == LOOP_NODE_PUBKEY:
            continue
        chan_id = channel.get("chan_id")
        capacity = int(channel.get("capacity", 0))
        local_balance = int(channel.get("local_balance", 0))
        balance_ratio = local_balance / capacity if capacity > 0 else 0

        flow = flow_by_channel.get(
            chan_id,
            {"inbound_msat": 0, "outbound_msat": 0, "last_forward_time": None},
        )
        inbound_flow = flow["inbound_msat"]
        outbound_flow = flow["outbound_msat"]
        last_forward_time = flow["last_forward_time"]

        trend = "stagnant"
        if inbound_flow > outbound_flow * 1.1:
            trend = "inbound"
        elif outbound_flow > inbound_flow * 1.1:
            trend = "outbound"
        elif inbound_flow > 0 or outbound_flow > 0:
            trend = "balanced"

        is_candidate = _is_loop_out_candidate(channel, flow, pending_swaps)

        analysis_results.append(
            {
                "channel_id": chan_id,
                "peer_alias": channel.get("peer_alias", "N/A"),
                "local_balance": local_balance,
                "capacity": capacity,
                "balance_ratio": f"{balance_ratio:.2%}",
                "is_loop_out_candidate": is_candidate,
                "liquidity_trend": trend,
                "inbound_msat_7d": inbound_flow,
                "outbound_msat_7d": outbound_flow,
                "last_forward_time": (
                    last_forward_time.isoformat() if last_forward_time else None
                ),
            }
        )

    return {"status": "OK", "data": {"channel_analysis": analysis_results}}


def _get_loop_out_quote(loop_client: LoopClient, amt_sat: int) -> dict:
    """
    Fetches a quote for a Loop Out swap.
    """
    if loop_client.stub is None:
        return {"status": "ERROR", "message": "Loop gRPC client not initialized."}

    try:
        request = looprpc.QuoteRequest(amt=int(amt_sat))
        response = loop_client.stub.LoopOutQuote(request)
        response_data = MessageToDict(response, preserving_proto_field_name=True)
        return {
            "status": "OK",
            "data": {
                "swap_fee_sat": response_data.get("swap_fee_sat"),
                "htlc_sweep_fee_sat": response_data.get("htlc_sweep_fee_sat"),
            },
        }
    except grpc.RpcError as e:
        return {
            "status": "ERROR",
            "message": f"gRPC error fetching Loop Out quote: {e.details()}",
        }
    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}


def calculate_and_quote_loop_outs(
    lnd_client: LNDClient, loop_client: LoopClient, channel_ids: list
) -> dict:
    """
    Calculates the precise amount to Loop Out to rebalance a list of channels to 50%
    outbound liquidity and fetches a quote for each.
    """
    channels_response = lnd_client.list_lnd_channels()
    if channels_response.get("status") != "OK":
        return channels_response

    all_channels = {
        ch["chan_id"]: ch
        for ch in channels_response.get("data", {}).get("channels", [])
    }

    results = []
    for channel_id in channel_ids:
        channel = all_channels.get(str(channel_id))

        if not channel:
            results.append(
                {
                    "channel_id": channel_id,
                    "status": "ERROR",
                    "message": "Channel not found.",
                }
            )
            continue

        local_balance = int(channel.get("local_balance", 0))
        capacity = int(channel.get("capacity", 0))

        if local_balance < 0 or capacity <= 0:
            results.append(
                {
                    "channel_id": channel_id,
                    "status": "ERROR",
                    "message": "Invalid local_balance or capacity found for channel.",
                }
            )
            continue

        target_balance = capacity // 2
        loop_out_amount = int(local_balance - target_balance)
        loop_out_amount = min(loop_out_amount, 10000000)

        if loop_out_amount <= 0:
            results.append(
                {
                    "channel_id": channel_id,
                    "status": "OK",
                    "loop_out_amount_sat": 0,
                    "quote": None,
                    "message": "Channel is already balanced or has inbound liquidity.",
                }
            )
        else:
            quote = _get_loop_out_quote(loop_client, loop_out_amount)
            results.append(
                {
                    "channel_id": channel_id,
                    "status": "OK",
                    "loop_out_amount_sat": loop_out_amount,
                    "quote": quote,
                }
            )

    return {"status": "OK", "data": {"channel_quotes": results}}


def calculate_dynamic_fee(lnd_client: LNDClient, pubkey: str) -> dict:
    """
    Calculates a scaled fee rate for a potential new channel based on the
    historical forwarding activity of existing channels with the same peer.
    The fee is tiered based on total flow over the last 7 days.
    """
    # Get all channels to find existing ones with the specified pubkey.
    channels_response = lnd_client.list_lnd_channels()
    if channels_response.get("status") != "OK":
        return channels_response

    peer_channels = [
        ch
        for ch in channels_response.get("data", {}).get("channels", [])
        if ch.get("remote_pubkey") == pubkey
    ]

    total_flow_sats = 0
    if peer_channels:
        peer_channel_ids = {ch.get("chan_id") for ch in peer_channels}
        history_response = lnd_client.forwarding_history(days_to_check=7)
        if history_response.get("status") != "OK":
            return history_response

        forwarding_events = history_response.get("data", {}).get(
            "forwarding_events", []
        )
        total_flow_msat = sum(
            int(event.get("amt_in_msat", 0)) + int(event.get("amt_out_msat", 0))
            for event in forwarding_events
            if event.get("chan_id_in") in peer_channel_ids
            or event.get("chan_id_out") in peer_channel_ids
        )
        total_flow_sats = total_flow_msat / 1000

    # --- Fee Calculation Logic ---
    if pubkey == LOOP_NODE_PUBKEY:
        # Scaled fees for the LOOP node, with a 4000 ppm floor.
        if total_flow_sats > 50_000_000:
            fee_ppm = 5000
        elif total_flow_sats > 10_000_000:
            fee_ppm = 4800
        else:
            fee_ppm = 4500  # Default for low/no activity
        final_fee_ppm = max(fee_ppm, 4000)
    else:
        # Scaled fees for regular nodes, with an 850 ppm floor.
        if not peer_channels:
            fee_ppm = 1200  # Default for a new peer with no history
        elif total_flow_sats > 10_000_000:
            fee_ppm = 1500
        elif total_flow_sats > 5_000_000:
            fee_ppm = 1300
        elif total_flow_sats > 1_000_000:
            fee_ppm = 1200
        elif total_flow_sats > 500_000:
            fee_ppm = 1100
        else:
            fee_ppm = 900  # For very low activity
        final_fee_ppm = max(fee_ppm, 850)

    return {"status": "OK", "data": {"fee_ppm": final_fee_ppm}}
