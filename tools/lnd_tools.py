import codecs
import os

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
            return {"status": "OK", "data": MessageToDict(response)}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching LND info: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def get_lnd_wallet_balance(self) -> dict:
        """Shows a summary of the on-chain wallet balance of the LND node using gRPC."""
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.WalletBalance(ln.WalletBalanceRequest())
            return {"status": "OK", "data": MessageToDict(response)}
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

    def open_channel(
        self,
        node_pubkey: str,
        local_funding_amount_sat: int,
        sat_per_vbyte: int = 0,
    ) -> dict:
        """
        Opens a new channel with a peer using gRPC after performing a budget check.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        # Programmatic safety check
        balance_response = self.get_lnd_wallet_balance()
        if balance_response["status"] != "OK":
            return balance_response

        confirmed_balance = int(balance_response["data"]["confirmedBalance"])
        available_balance = confirmed_balance - 1000000  # 1M satoshi reserve

        if int(local_funding_amount_sat) > available_balance:
            return {
                "status": "ERROR",
                "message": f"Insufficient funds. Requested: {local_funding_amount_sat}, Available: {available_balance}",
            }

        try:
            request = ln.OpenChannelRequest(
                node_pubkey=bytes.fromhex(node_pubkey),
                local_funding_amount=int(local_funding_amount_sat),
                push_sat=0,
                sat_per_vbyte=int(sat_per_vbyte),
            )
            # Use OpenChannelSync for a synchronous response.
            response = self.stub.OpenChannelSync(request)
            return {"status": "OK", "data": MessageToDict(response)}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error opening channel: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def batch_open_channel(
        self,
        channels: list,
        sat_per_vbyte: int = 0,
    ) -> dict:
        """
        Opens multiple channels in a single transaction after performing a budget check.
        """
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        # Programmatic safety check
        balance_response = self.get_lnd_wallet_balance()
        if balance_response["status"] != "OK":
            return balance_response  # Propagate the error

        confirmed_balance = int(balance_response["data"]["confirmedBalance"])
        available_balance = confirmed_balance - 1000000  # 1M satoshi reserve

        total_funding_amount = sum(
            int(ch["local_funding_amount_sat"]) for ch in channels
        )

        if total_funding_amount > available_balance:
            return {
                "status": "ERROR",
                "message": f"Insufficient funds. Requested: {total_funding_amount}, Available: {available_balance}",
            }

        batch_channels = []
        for ch in channels:
            batch_channels.append(
                ln.BatchOpenChannel(
                    node_pubkey=bytes.fromhex(ch["node_pubkey"]),
                    local_funding_amount=int(ch["local_funding_amount_sat"]),
                    push_sat=0,
                )
            )

        try:
            request = ln.BatchOpenChannelRequest(
                channels=batch_channels,
                sat_per_vbyte=int(sat_per_vbyte),
            )
            response = self.stub.BatchOpenChannel(request)
            return {"status": "OK", "data": MessageToDict(response)}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error batch opening channels: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

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
            return {"status": "OK", "data": MessageToDict(response)}
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

            return {"status": "OK", "data": MessageToDict(response)}
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
            return {"status": "OK", "data": MessageToDict(response)}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching LND state: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def list_lnd_channels(self) -> dict:
        """Fetches a list of all open channels from the LND node using gRPC."""
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.ListChannels(ln.ListChannelsRequest())
            return {"status": "OK", "data": MessageToDict(response)}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error listing channels: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
