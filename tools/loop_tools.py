import codecs
import os
import grpc
from google.protobuf.json_format import MessageToDict
from datetime import datetime, timedelta


try:
    import client_pb2 as looprpc
    import client_pb2_grpc as looprpc_grpc
except ImportError:
    print(
        "Warning: client_pb2 or client_pb2_grpc not found. "
        "Please ensure Loop protobufs are compiled and accessible in your Python path."
    )
    looprpc = None
    looprpc_grpc = None


class LoopClient:
    def __init__(
        self,
        loop_grpc_host: str,
        loop_grpc_port: int,
        tls_cert_path: str,
        macaroon_path: str,
    ):
        self.loop_grpc_host = loop_grpc_host
        self.loop_grpc_port = loop_grpc_port
        self.tls_cert_path = tls_cert_path
        self.macaroon_path = macaroon_path
        self.stub = None
        self._setup_grpc_client()

    def _setup_grpc_client(self):
        """Sets up the gRPC client for the Loop daemon."""
        if None in [looprpc, looprpc_grpc]:
            print("Error: Loop gRPC dependencies not met. Cannot set up gRPC client.")
            return

        try:
            os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"

            with open(self.tls_cert_path, "rb") as f:
                cert = f.read()

            with open(self.macaroon_path, "rb") as f:
                macaroon_bytes = codecs.encode(f.read(), "hex")

            cert_creds = grpc.ssl_channel_credentials(cert)

            def metadata_callback(context, callback):
                callback([("macaroon", macaroon_bytes)], None)

            auth_creds = grpc.metadata_call_credentials(metadata_callback)

            composite_creds = grpc.composite_channel_credentials(cert_creds, auth_creds)

            channel = grpc.secure_channel(
                f"{self.loop_grpc_host}:{self.loop_grpc_port}", composite_creds
            )
            self.stub = looprpc_grpc.SwapClientStub(channel)
            print(
                f"Loop gRPC client initialized for {self.loop_grpc_host}:{self.loop_grpc_port}"
            )

        except Exception as e:
            print(f"An unexpected error occurred during Loop gRPC client setup: {e}")
            self.stub = None

    def list_loop_out_swaps(self) -> dict:
        """
        Lists the 10 most recent Loop Out swaps from the last 24 hours.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "Loop gRPC client not initialized."}

        try:
            # Calculate the timestamp for 24 hours ago in nanoseconds
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            start_timestamp_ns = int(twenty_four_hours_ago.timestamp() * 1e9)

            request = looprpc.ListSwapsRequest(
                list_swap_filter=looprpc.ListSwapsFilter(
                    swap_type=looprpc.ListSwapsFilter.SwapTypeFilter.LOOP_OUT,
                    start_timestamp_ns=start_timestamp_ns,
                ),
            )
            response = self.stub.ListSwaps(request)
            response_data = MessageToDict(
                response,
                preserving_proto_field_name=True,
                always_print_fields_with_no_presence=True,
            )

            # Sort swaps by initiation time (most recent first) and take the top 10
            if "swaps" in response_data:
                swaps = response_data["swaps"]
                # The 'initiation_time' is a string of an int, so we parse it for sorting
                swaps.sort(
                    key=lambda s: int(s["initiation_time"]),
                    reverse=True,
                )
                response_data["swaps"] = swaps[:10]

            return {"status": "OK", "data": response_data}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error listing Loop Out swaps: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def initiate_loop_out(self, lnd_client, channel_id: str) -> dict:
        """
        Initiates a Loop Out swap for a specific channel to rebalance it to 50%
        outbound liquidity.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "Loop gRPC client not initialized."}

        # 0. Check for pending Loop Outs for this specific channel
        pending_swaps_response = self.list_loop_out_swaps()
        if pending_swaps_response.get("status") == "OK":
            for swap in pending_swaps_response.get("data", {}).get("swaps", []):
                if swap.get("state") not in ["SUCCESS", "FAILED"] and str(
                    channel_id
                ) in swap.get("outgoing_chan_set", []):
                    return {
                        "status": "ERROR",
                        "message": f"Channel {channel_id} is already part of a pending Loop Out swap.",
                    }

        # 1. Get channel details to calculate amount
        channels_response = lnd_client.list_lnd_channels()
        if channels_response.get("status") != "OK":
            return channels_response

        all_channels = {
            ch["chan_id"]: ch
            for ch in channels_response.get("data", {}).get("channels", [])
        }

        channel = all_channels.get(str(channel_id))

        if not channel:
            return {
                "status": "ERROR",
                "message": f"Channel {channel_id} not found.",
            }

        local_balance = int(channel.get("local_balance", 0))
        capacity = int(channel.get("capacity", 0))
        target_balance = capacity // 2
        loop_out_amount = int(local_balance - target_balance)
        loop_out_amount = min(loop_out_amount, 10000000)

        if loop_out_amount <= 0:
            return {
                "status": "ERROR",
                "message": "Channel does not need a loop out.",
            }

        max_swap_fee = int(loop_out_amount * 0.0021)
        max_swap_routing_fee = int(loop_out_amount * 0.0035) + 1
        max_prepay_routing_fee = int(30000 * 0.003) + 10

        # 2. Initiate the swap
        try:
            request = looprpc.LoopOutRequest(
                amt=loop_out_amount,
                outgoing_chan_set=[int(channel_id)],
                sweep_conf_target=144,
                max_swap_fee=max_swap_fee,
                max_prepay_amt=30000,
                max_swap_routing_fee=max_swap_routing_fee,
                max_prepay_routing_fee=max_prepay_routing_fee,
            )
            response = self.stub.LoopOut(request)
            response_data = MessageToDict(
                response,
                preserving_proto_field_name=True,
                always_print_fields_with_no_presence=True,
            )
            return {"status": "OK", "data": response_data}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error initiating Loop Out: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
