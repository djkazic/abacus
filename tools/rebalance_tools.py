import grpc
import json
import base64
from tools.lnd_tools import LNDClient
from config import LOOP_NODE_PUBKEY

try:
    import lightning_pb2 as ln
except ImportError:
    ln = None


def execute_rebalance(
    lnd_client: LNDClient,
    outgoing_channel_id: str,
    incoming_channel_id: str,
    amount_sats: int,
) -> dict:
    """
    Executes a circular rebalance.
    """
    amount_sats = int(amount_sats)
    if amount_sats > 20000:
        amount_sats = 20000

    info_response = lnd_client.get_lnd_info()
    if info_response.get("status") != "OK":
        return info_response
    my_pubkey = info_response.get("data", {}).get("identity_pubkey")

    # Check if the outgoing channel is with the LOOP node
    outgoing_chan_info_response = lnd_client.get_channel_info(outgoing_channel_id)
    if outgoing_chan_info_response.get("status") != "OK":
        return outgoing_chan_info_response

    outgoing_peer_pubkey = outgoing_chan_info_response.get("data", {}).get("node1_pub")
    if outgoing_peer_pubkey == my_pubkey:
        outgoing_peer_pubkey = outgoing_chan_info_response.get("data", {}).get(
            "node2_pub"
        )

    if outgoing_peer_pubkey == LOOP_NODE_PUBKEY:
        return {
            "status": "ERROR",
            "message": "Cannot use a channel with the LOOP node as the outgoing channel for a rebalance.",
        }

    incoming_chan_info_response = lnd_client.get_channel_info(incoming_channel_id)
    if incoming_chan_info_response.get("status") != "OK":
        return incoming_chan_info_response

    last_hop_pubkey = incoming_chan_info_response.get("data", {}).get("node1_pub")
    if last_hop_pubkey == my_pubkey:
        last_hop_pubkey = incoming_chan_info_response.get("data", {}).get("node2_pub")

    amount_msat = amount_sats * 1000
    max_fee_rate = 4000
    fee_limit_msat = int(amount_msat * (max_fee_rate / 1000000))

    query_routes_response = lnd_client._query_routes(
        pub_key=my_pubkey,
        outgoing_chan_id=outgoing_channel_id,
        last_hop_pubkey=last_hop_pubkey,
        amt_msat=amount_msat,
        fee_limit_msat=fee_limit_msat,
    )

    if query_routes_response.get("status") != "OK":
        return query_routes_response

    routes = query_routes_response.get("data").routes
    if not routes:
        return {
            "status": "ERROR",
            "message": "Could not find a route.",
        }

    route = routes[0]

    # Add invoice
    invoice_response = lnd_client._add_invoice(
        value_msat=amount_sats * 1000,
        memo=f"Rebalance of {amount_sats} sats.",
    )
    if invoice_response.get("status") != "OK":
        return invoice_response

    payment_hash = invoice_response.get("data", {}).get("r_hash")
    payment_addr = invoice_response.get("data", {}).get("payment_addr")
    if not payment_hash or not payment_addr:
        return {
            "status": "ERROR",
            "message": "Could not get payment hash or payment address from invoice.",
        }

    # Send payment
    send_response = lnd_client._send_to_route_v2(
        route=route,
        payment_hash=payment_hash,
        payment_addr=payment_addr,
        total_amt_msat=amount_sats * 1000,
    )

    return send_response
