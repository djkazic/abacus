import codecs
import os
import time

import grpc
from google.protobuf.json_format import MessageToDict


try:
    import lightning_pb2 as ln
    import lightning_pb2_grpc as lnrpc
    import stateservice_pb2 as state_service
    import stateservice_pb2_grpc as state_service_grpc
except ImportError:
    print(
        "Warning: lightning_pb2, lightning_pb2_grpc, stateservice_pb2, or stateservice_pb2_grpc not found. "
        "Please ensure LND protobufs are compiled and accessible in your Python path, or install 'lnd_grpc'."
    )
    ln = None
    lnrpc = None
    state_service = None
    state_service_grpc = None

LOOP_NODE_PUBKEY = "021c97a90a411ff2b10dc2a8e32de2f29d2fa49d41bfbb52bd416e460db0747d0d"


class LNDClient:
    def __init__(
        self,
        lnd_grpc_host: str,
        lnd_grpc_port: int,
        tls_cert_path: str,
        admin_macaroon_path: str,
    ):
        self.lnd_grpc_host = lnd_grpc_host
        self.lnd_grpc_port = lnd_grpc_port
        self.tls_cert_path = tls_cert_path
        self.admin_macaroon_path = admin_macaroon_path
        self.stub = None
        self.state_stub = None
        self._macaroon_bytes_hex = None
        self._setup_grpc_client()

    def _setup_grpc_client(self):
        """Sets up the gRPC client for LND."""
        if None in [ln, lnrpc, state_service, state_service_grpc]:
            print("Error: LND gRPC dependencies not met. Cannot set up gRPC client.")
            return

        try:
            os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"

            with open(self.tls_cert_path, "rb") as f:
                lnd_cert = f.read()

            with open(self.admin_macaroon_path, "rb") as f:
                self._macaroon_bytes_hex = codecs.encode(f.read(), "hex")

            cert_creds = grpc.ssl_channel_credentials(lnd_cert)

            def metadata_callback(context, callback):
                callback([("macaroon", self._macaroon_bytes_hex)], None)

            auth_creds = grpc.metadata_call_credentials(metadata_callback)

            composite_creds = grpc.composite_channel_credentials(cert_creds, auth_creds)

            channel = grpc.secure_channel(
                f"{self.lnd_grpc_host}:{self.lnd_grpc_port}", composite_creds
            )
            self.stub = lnrpc.LightningStub(channel)
            self.state_stub = state_service_grpc.StateStub(channel)

            print(
                f"LND gRPC client initialized for {self.lnd_grpc_host}:{self.lnd_grpc_port}"
            )

        except FileNotFoundError as e:
            print(f"Error setting up gRPC client: File not found - {e}")
            self.stub = None
        except Exception as e:
            print(f"An unexpected error occurred during gRPC client setup: {e}")
            self.stub = None

    def get_lnd_info(self) -> dict:
        """Fetches detailed information about the LND node using gRPC."""
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.GetInfo(ln.GetInfoRequest())
            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching LND info: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def get_lnd_wallet_balance(self) -> dict:
        """
        Shows the on-chain confirmed wallet balance of the LND node using gRPC.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.WalletBalance(ln.WalletBalanceRequest())
            data = MessageToDict(response, preserving_proto_field_name=True)
            return {
                "status": "OK",
                "data": {"confirmed_balance": data.get("confirmed_balance", 0)},
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching wallet balance: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def get_lnd_channel_balance(self) -> dict:
        """
        Shows the node's current channel balance.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.ChannelBalance(ln.ChannelBalanceRequest())
            data = MessageToDict(response, preserving_proto_field_name=True)
            return {
                "status": "OK",
                "data": data,
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching wallet balance: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def set_fee_policy(
        self, channel_id: str, base_fee_msat: int, fee_rate_ppm: int
    ) -> dict:
        """
        Dummy function to simulate setting a fee policy for a given channel.
        In a real scenario, this would interact with the LND node to update fees.
        """
        print(
            f"Dummy: Setting fee policy for channel {channel_id}: base_fee_msat={base_fee_msat}, fee_rate_ppm={fee_rate_ppm}"
        )
        return {
            "status": "OK",
            "message": f"Fee policy for channel {channel_id} set (dummy).",
        }

    def _internal_open_channel(
        self,
        node_pubkey: str,
        local_funding_amount_sat: int,
        sat_per_vbyte: int = 0,
    ) -> dict:
        """
        Opens a new channel with a peer using gRPC. Intended for internal use.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            request_args = {
                "node_pubkey": bytes.fromhex(node_pubkey),
                "local_funding_amount": int(local_funding_amount_sat),
                "push_sat": 0,
                "sat_per_vbyte": int(sat_per_vbyte),
            }
            if node_pubkey == LOOP_NODE_PUBKEY:
                request_args["use_fee_rate"] = True
                request_args["fee_rate"] = 4500

            request = ln.OpenChannelRequest(**request_args)
            response = self.stub.OpenChannelSync(request)
            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error opening channel: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def _internal_batch_open_channel(
        self,
        channels: list,
        sat_per_vbyte: int = 0,
    ) -> dict:
        """
        Opens multiple channels in a single transaction. Intended for internal use.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        batch_channels = []
        for ch in channels:
            node_pubkey = ch["node_pubkey"]
            batch_channel_args = {
                "node_pubkey": bytes.fromhex(node_pubkey),
                "local_funding_amount": int(ch["local_funding_amount_sat"]),
                "push_sat": 0,
            }
            if node_pubkey == LOOP_NODE_PUBKEY:
                batch_channel_args["use_fee_rate"] = True
                batch_channel_args["fee_rate"] = 4500

            batch_channels.append(ln.BatchOpenChannel(**batch_channel_args))

        try:
            request = ln.BatchOpenChannelRequest(
                channels=batch_channels,
                sat_per_vbyte=int(sat_per_vbyte),
            )
            response = self.stub.BatchOpenChannel(request)
            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error batch opening channels: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def propose_channel_opens(self, peers: list, sat_per_vbyte: int) -> dict:
        """
        Calculates channel sizes, performs safety checks, and proposes channel openings.
        This tool is a higher-level abstraction that simplifies the channel opening process.
        """
        if not peers:
            return {
                "status": "ERROR",
                "message": "No peers provided to open channels with.",
            }

        # Special handling for a single LOOP node peer
        if len(peers) == 1 and peers[0].get("pub_key") == LOOP_NODE_PUBKEY:
            print("A dedicated 30M sat channel to the LOOP node is proposed.")
            return {
                "status": "PROPOSED",
                "operations": [
                    {
                        "type": "single",
                        "node_pubkey": LOOP_NODE_PUBKEY,
                        "local_funding_amount_sat": 30000000,
                        "sat_per_vbyte": sat_per_vbyte,
                    }
                ],
            }

        # 1. Financial Safety Check
        balance_response = self.get_lnd_wallet_balance()
        if balance_response.get("status") != "OK":
            return balance_response

        confirmed_balance = int(
            balance_response.get("data", {}).get("confirmed_balance", 0)
        )
        if not confirmed_balance:
            return {
                "status": "ERROR",
                "message": "Could not retrieve confirmed wallet balance.",
            }

        available_funds = confirmed_balance - 1000000  # 1M satoshi reserve

        if available_funds <= 0:
            return {
                "status": "ERROR",
                "message": "Insufficient funds for channel opening after reserve.",
            }

        # 2. Calculate per-channel amount and adjust peer list if necessary
        num_peers = len(peers)
        per_channel_amount = available_funds // num_peers

        while per_channel_amount < 5000000 and num_peers > 0:
            num_peers -= 1
            if num_peers == 0:
                return {
                    "status": "OK",
                    "message": "Budget too small to open any channels of the minimum size (5M sats).",
                }
            per_channel_amount = available_funds // num_peers

        final_peers = peers[:num_peers]

        # 3. Propose channel opening
        if not final_peers:
            return {
                "status": "OK",
                "message": "No suitable peers left after budget filtering.",
            }

        if len(final_peers) > 1:
            # Propose batch open
            channels_to_open = [
                {
                    "node_pubkey": peer["pub_key"],
                    "local_funding_amount_sat": per_channel_amount,
                }
                for peer in final_peers
            ]
            return {
                "status": "PROPOSED",
                "operations": [
                    {
                        "type": "batch",
                        "channels": channels_to_open,
                        "sat_per_vbyte": sat_per_vbyte,
                    }
                ],
            }
        else:
            # Propose single open
            peer = final_peers[0]
            return {
                "status": "PROPOSED",
                "operations": [
                    {
                        "type": "single",
                        "node_pubkey": peer["pub_key"],
                        "local_funding_amount_sat": per_channel_amount,
                        "sat_per_vbyte": sat_per_vbyte,
                    }
                ],
            }

    def execute_channel_opens(self, operations: list) -> dict:
        """
        Executes a list of proposed channel opening operations.
        """
        if not operations:
            return {"status": "ERROR", "message": "No operations provided to execute."}

        # Validate LOOP node channel amounts
        for op in operations:
            op_type = op.get("type")
            if op_type == "single":
                if (
                    op.get("node_pubkey") == LOOP_NODE_PUBKEY
                    and op.get("local_funding_amount_sat") != 30000000
                ):
                    return {
                        "status": "ERROR",
                        "message": "LOOP node channel open must be exactly 30M satoshis.",
                    }
            elif op_type == "batch":
                for channel in op.get("channels", []):
                    if (
                        channel.get("node_pubkey") == LOOP_NODE_PUBKEY
                        and channel.get("local_funding_amount_sat") != 30000000
                    ):
                        return {
                            "status": "ERROR",
                            "message": "LOOP node channel open must be exactly 30M satoshis.",
                        }

        results = []
        for op in operations:
            op_type = op.get("type")
            if op_type == "single":
                result = self._internal_open_channel(
                    node_pubkey=op["node_pubkey"],
                    local_funding_amount_sat=op["local_funding_amount_sat"],
                    sat_per_vbyte=op["sat_per_vbyte"],
                )
                results.append(result)
            elif op_type == "batch":
                result = self._internal_batch_open_channel(
                    channels=op["channels"],
                    sat_per_vbyte=op["sat_per_vbyte"],
                )
                results.append(result)
            else:
                results.append(
                    {"status": "ERROR", "message": f"Unknown operation type: {op_type}"}
                )

        return {"status": "OK", "results": results}

    def list_lnd_peers(self) -> dict:
        """
        Fetches a list of connected peers from the LND node using gRPC.
        Returns information about each peer, including their public key, alias,
        number of channels, and total capacity.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        print("Fetching LND peers via gRPC...")
        try:
            response = self.stub.ListPeers(ln.ListPeersRequest())
            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error listing peers: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def connect_peer(self, node_pubkey: str, host_port: str) -> dict:
        """
        Connects to a Lightning Network peer using their public key and host:port via gRPC.
        A connection is generally required before opening a channel.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        print(f"Connecting to peer {node_pubkey} at {host_port} via gRPC...")
        try:
            peer_address = ln.LightningAddress(pubkey=node_pubkey, host=host_port)
            request = ln.ConnectPeerRequest(addr=peer_address, perm=True)
            response = self.stub.ConnectPeer(request)

            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error connecting to peer: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def batch_connect_peers(self, peers: list) -> dict:
        """
        Connects to multiple Lightning Network peers in a batch.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        results = []
        for peer in peers:
            node_pubkey = peer.get("node_pubkey")
            host_port = peer.get("host_port")
            if not node_pubkey or not host_port:
                results.append(
                    {
                        "status": "ERROR",
                        "message": "Each peer in the list must have 'node_pubkey' and 'host_port'.",
                    }
                )
                continue

            result = self.connect_peer(node_pubkey, host_port)
            results.append(result)

        return {"status": "OK", "data": results}

    def get_lnd_state(self) -> dict:
        """Fetches the internal state of the LND node using gRPC."""
        if self.state_stub is None:
            return {
                "status": "ERROR",
                "message": "LND gRPC state client not initialized.",
            }

        try:
            response = self.state_stub.GetState(state_service.GetStateRequest())
            return {
                "status": "OK",
                "data": MessageToDict(response, preserving_proto_field_name=True),
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching LND state: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def list_lnd_channels(self) -> dict:
        """
        Fetches a filtered list of all open channels from the LND node using gRPC.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.ListChannels(ln.ListChannelsRequest())
            data = MessageToDict(response, preserving_proto_field_name=True)

            filtered_channels = []
            fields_to_keep = [
                "active",
                "remote_pubkey",
                "channel_point",
                "chan_id",
                "capacity",
                "local_balance",
                "remote_balance",
                "csv_delay",
                "lifetime",
            ]

            for channel in data.get("channels", []):
                filtered_channel = {
                    key: channel.get(key) for key in fields_to_keep if key in channel
                }
                filtered_channels.append(filtered_channel)

            return {"status": "OK", "data": {"channels": filtered_channels}}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error listing channels: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def forwarding_history(self, days_to_check: int = 7) -> dict:
        """
        Fetches the forwarding history of the LND node over a specified period.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            now = time.time()
            start_time = int(now - (days_to_check * 24 * 60 * 60))
            all_events = []
            index_offset = 0
            max_events_per_page = 100  # LND's default is 100

            while True:
                request = ln.ForwardingHistoryRequest(
                    start_time=start_time,
                    index_offset=index_offset,
                    num_max_events=max_events_per_page,
                )
                response = self.stub.ForwardingHistory(request)
                response_data = MessageToDict(
                    response, preserving_proto_field_name=True
                )

                events = response_data.get("forwarding_events", [])
                all_events.extend(events)

                if not events or len(events) < max_events_per_page:
                    break

                index_offset = response_data.get("last_offset_index", 0)
                if index_offset == 0:  # Should not happen if there are more pages
                    break

            return {"status": "OK", "data": {"forwarding_events": all_events}}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching forwarding history: {e.details()}",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"An unexpected error occurred: {e}",
            }
