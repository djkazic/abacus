import grpc
from tools.lnd_tools import LNDClient
from config import LOOP_NODE_PUBKEY


def find_rebalance_opportunities(lnd_client: LNDClient) -> dict:
    """
    Finds opportunities for rebalancing channels.
    An opportunity is defined as a pair of channels where one has low outbound liquidity
    and the other has high outbound liquidity.
    """
    try:
        list_channels_response = lnd_client.list_lnd_channels()
        if list_channels_response.get("status") != "OK":
            return list_channels_response

        channels = list_channels_response.get("data", {}).get("channels", [])
        if not channels:
            return {
                "status": "OK",
                "message": "No channels found.",
                "opportunities": [],
            }

        # Separate channels into two groups: low and high outbound liquidity
        low_outbound = []
        high_outbound = []
        for channel in channels:
            local_balance = int(channel.get("local_balance", 0))
            remote_balance = int(channel.get("remote_balance", 0))
            capacity = local_balance + remote_balance
            outbound_percentage = (
                (local_balance / capacity) * 100 if capacity > 0 else 0
            )

            if outbound_percentage <= 25:  # Low outbound liquidity threshold
                low_outbound.append(channel)
            elif outbound_percentage >= 75:  # High outbound liquidity threshold
                if channel.get("remote_pubkey") != LOOP_NODE_PUBKEY:
                    high_outbound.append(channel)

        if not low_outbound or not high_outbound:
            return {
                "status": "OK",
                "message": "No rebalance opportunities found. Need at least one channel with low outbound liquidity and one with high outbound liquidity.",
                "opportunities": [],
            }

        # Create opportunities by pairing low and high outbound channels
        opportunities = []
        for low_chan in low_outbound:
            for high_chan in high_outbound:
                opportunities.append(
                    {
                        "incoming_channel_id": low_chan.get("chan_id"),
                        "outgoing_channel_id": high_chan.get("chan_id"),
                        "description": f"Rebalance from channel {high_chan.get('chan_id')} (high outbound) to channel {low_chan.get('chan_id')} (low outbound).",
                    }
                )

        return {
            "status": "OK",
            "message": f"Found {len(opportunities)} rebalance opportunities.",
            "opportunities": opportunities,
        }

    except grpc.RpcError as e:
        return {
            "status": "ERROR",
            "message": f"Error finding rebalance opportunities: {e.details()}",
        }
