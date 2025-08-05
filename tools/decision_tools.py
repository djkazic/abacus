import grpc
from tools.lnd_tools import LNDClient
from config import LOOP_NODE_PUBKEY
import datetime


def should_open_to_loop(lnd_client: LNDClient) -> dict:
    """
    Checks if the node has enough inbound liquidity and on-chain funds to open a channel to the Loop node.
    The thresholds are 30,000,000 satoshis of inbound liquidity and 31,000,000 satoshis of on-chain funds.
    """
    try:
        # Check on-chain balance
        wallet_balance_response = lnd_client.get_lnd_wallet_balance()
        if wallet_balance_response["status"] != "OK":
            return {
                "status": "ERROR",
                "message": f"Error checking wallet balance: {wallet_balance_response['message']}",
            }

        confirmed_balance = int(
            wallet_balance_response.get("data", {}).get("confirmed_balance", 0)
        )
        if confirmed_balance < 31000000:
            return {
                "status": "OK",
                "message": f"Node has only {confirmed_balance} sats on-chain, which is not enough. "
                f"The threshold is 31,000,000 sats. Cannot open a channel to the Loop node.",
            }

        # Check inbound liquidity
        channel_balance_response = lnd_client.get_lnd_channel_balance()
        if channel_balance_response["status"] != "OK":
            return {
                "status": "ERROR",
                "message": f"Error checking inbound liquidity: {channel_balance_response['message']}",
            }

        remote_balance = int(
            channel_balance_response.get("data", {})
            .get("remote_balance", {})
            .get("sat", 0)
        )

        if remote_balance >= 30000000:
            return {
                "status": "OK",
                "message": f"Node has {remote_balance} sats of inbound liquidity and {confirmed_balance} sats on-chain, "
                f"which is enough to open a channel to the Loop node. "
                f"Consider opening a channel to the Loop node with pubkey {LOOP_NODE_PUBKEY}.",
            }
        else:
            return {
                "status": "OK",
                "message": f"Node has only {remote_balance} sats of inbound liquidity, which is not enough. "
                f"The threshold is 30,000,000 sats. Continue with other channel opening strategies.",
            }
    except grpc.RpcError as e:
        return {
            "status": "ERROR",
            "message": f"Error checking conditions to open to loop: {e.details()}",
        }


def propose_channel_closes(lnd_client: LNDClient) -> dict:
    """
    Identifies and proposes closing channels with low outbound liquidity usage.
    """
    try:
        # 1. Get all channels
        channels_response = lnd_client.list_lnd_channels()
        if channels_response["status"] != "OK":
            return channels_response
        channels = channels_response.get("data", {}).get("channels", [])

        # 2. Get forwarding history for the last 30 days
        fwd_history_response = lnd_client.forwarding_history(days_to_check=30)
        if fwd_history_response["status"] != "OK":
            return fwd_history_response
        fwd_events = fwd_history_response.get("data", {}).get("forwarding_events", [])

        # 3. Calculate routed volume per channel
        routed_volume = {}
        for event in fwd_events:
            chan_id_out = event.get("chan_id_out")
            if chan_id_out:
                routed_volume[chan_id_out] = routed_volume.get(chan_id_out, 0) + int(
                    event.get("amt_out_msat", 0)
                )

        # 4. Filter channels based on age and routed volume
        now = datetime.datetime.now()
        proposals = []
        for channel in channels:
            # Check channel age
            lifetime_seconds = int(channel.get("lifetime", 0))
            age_days = lifetime_seconds / (24 * 60 * 60)
            if age_days > 30:
                chan_id = channel.get("chan_id")
                volume = routed_volume.get(chan_id, 0)
                channel["routed_volume_msat"] = volume
                proposals.append(channel)

        # 5. Identify channels in the bottom 10th percentile for routed volume
        if not proposals:
            return {"status": "OK", "message": "No channels older than 30 days found."}

        proposals.sort(key=lambda x: x["routed_volume_msat"])
        percentile_index = len(proposals) // 10
        idle_channels = proposals[: percentile_index + 1]

        # 6. Format the response
        final_proposals = []
        for channel in idle_channels:
            pubkey = channel.get("remote_pubkey")
            alias_response = lnd_client.get_node_alias(pubkey)
            alias = (
                alias_response.get("data", {}).get("alias", "Unknown")
                if alias_response["status"] == "OK"
                else "Unknown"
            )
            final_proposals.append(
                {
                    "alias": alias,
                    "chan_id": channel.get("chan_id"),
                    "channel_point": channel.get("channel_point"),
                    "capacity_sats": channel.get("capacity"),
                    "routed_volume_msat": channel.get("routed_volume_msat"),
                    "age_days": int(int(channel.get("lifetime", 0)) / (24 * 60 * 60)),
                }
            )

        if not final_proposals:
            return {
                "status": "OK",
                "message": "No channels matching the idle criteria were found.",
            }

        return {
            "status": "PROPOSED",
            "proposals": final_proposals,
            "message": "Found channels that could be closed to reclaim liquidity.",
        }

    except Exception as e:
        return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
