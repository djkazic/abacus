import grpc
from typing import List, Optional

from tools.lnd_tools import LNDClient

LOOP_NODE_PUBKEY = "021c97a90a411ff2b10dc2a8e32de2f29d2fa49d41bfbb52bd416e460db0747d0d"


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
