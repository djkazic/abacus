from tools.lnd_tools import LNDClient
from collections import defaultdict


def analyze_channel_liquidity_flow(lnd_client: LNDClient) -> dict:
    """
    Analyzes the liquidity flow of each channel over the last 7 days and
    provides a summary with the current balance and a liquidity trend.
    """
    # 1. Get Forwarding History
    history_response = lnd_client.forwarding_history(days_to_check=7)
    if history_response.get("status") != "OK":
        return history_response

    forwarding_events = history_response.get("data", {}).get("forwarding_events", [])

    # 2. Get Current Channel State
    channels_response = lnd_client.list_lnd_channels()
    if channels_response.get("status") != "OK":
        return channels_response

    channels = channels_response.get("data", {}).get("channels", [])

    # 3. Process Data
    flow_by_channel = defaultdict(lambda: {"inbound_msat": 0, "outbound_msat": 0})

    for event in forwarding_events:
        chan_id_in = event.get("chan_id_in")
        chan_id_out = event.get("chan_id_out")
        amt_in_msat = int(event.get("amt_in_msat", 0))
        amt_out_msat = int(event.get("amt_out_msat", 0))

        if chan_id_in:
            flow_by_channel[chan_id_in]["inbound_msat"] += amt_in_msat
        if chan_id_out:
            flow_by_channel[chan_id_out]["outbound_msat"] += amt_out_msat

    # 4. Generate Analysis
    analysis_results = []
    for channel in channels:
        chan_id = channel.get("chan_id")
        capacity = int(channel.get("capacity", 0))
        local_balance = int(channel.get("local_balance", 0))
        balance_ratio = local_balance / capacity if capacity > 0 else 0

        flow = flow_by_channel.get(chan_id, {"inbound_msat": 0, "outbound_msat": 0})
        inbound_flow = flow["inbound_msat"]
        outbound_flow = flow["outbound_msat"]

        trend = "stagnant"
        if inbound_flow > outbound_flow * 1.1:  # 10% tolerance
            trend = "inbound"
        elif outbound_flow > inbound_flow * 1.1:
            trend = "outbound"
        elif inbound_flow > 0 or outbound_flow > 0:
            trend = "balanced"

        analysis_results.append(
            {
                "channel_id": chan_id,
                "peer_alias": channel.get("peer_alias", "N/A"),
                "balance_ratio": f"{balance_ratio:.2%}",
                "liquidity_trend": trend,
                "inbound_msat_7d": inbound_flow,
                "outbound_msat_7d": outbound_flow,
            }
        )

    return {"status": "OK", "data": {"channel_analysis": analysis_results}}
