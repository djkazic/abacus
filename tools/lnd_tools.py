import codecs
import os

import grpc

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
            info_dict = {
                "version": response.version,
                "commit_hash": response.commit_hash,
                "identity_pubkey": response.identity_pubkey,
                "alias": response.alias,
                "color": response.color,
                "num_pending_channels": response.num_pending_channels,
                "num_active_channels": response.num_active_channels,
                "num_inactive_channels": response.num_inactive_channels,
                "num_peers": response.num_peers,
                "block_height": response.block_height,
                "block_hash": response.block_hash,
                "best_header_timestamp": response.best_header_timestamp,
                "synced_to_chain": response.synced_to_chain,
                "synced_to_graph": response.synced_to_graph,
                "testnet": response.testnet,
                "chains": [
                    {"chain": c.chain, "network": c.network} for c in response.chains
                ],
                "uris": list(response.uris),
                "features": {
                    str(k): {
                        "name": v.name,
                        "is_required": v.is_required,
                        "is_known": v.is_known,
                    }
                    for k, v in response.features.items()
                },
                "require_htlc_interceptor": response.require_htlc_interceptor,
                "store_final_htlc_resolutions": response.store_final_htlc_resolutions,
            }
            return {"status": "OK", "data": info_dict}
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error fetching LND info: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def get_lnd_wallet_balance(self) -> dict:
        """Shows the on-chain wallet balance of the LND node using gRPC."""
        if self.stub is None:
            return {"status": "ERROR", "message": "LND gRPC client not initialized."}

        try:
            response = self.stub.WalletBalance(ln.WalletBalanceRequest())
            balance_dict = {
                "total_balance": str(response.total_balance),
                "confirmed_balance": str(response.confirmed_balance),
                "unconfirmed_balance": str(response.unconfirmed_balance),
                "locked_balance": str(response.locked_balance),
                "reserved_balance_anchor_chan": str(
                    response.reserved_balance_anchor_chan
                ),
                "account_balance": {
                    account: {
                        "confirmed_balance": str(bal.confirmed_balance),
                        "unconfirmed_balance": str(bal.unconfirmed_balance),
                    }
                    for account, bal in response.account_balance.items()
                },
            }
            return {"status": "OK", "data": balance_dict}
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

        confirmed_balance = int(balance_response["data"]["confirmed_balance"])
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
            # The response for OpenChannelSync is a ChannelPoint
            funding_txid = response.funding_txid_str
            output_index = response.output_index
            return {
                "status": "OK",
                "data": {
                    "funding_txid": funding_txid,
                    "output_index": output_index,
                    "channel_point": f"{funding_txid}:{output_index}",
                },
            }
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

        confirmed_balance = int(balance_response["data"]["confirmed_balance"])
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
            return {
                "status": "OK",
                "data": {
                    "pending_channels": [
                        {
                            "txid": p.txid.hex(),
                            "output_index": int(p.output_index),
                        }
                        for p in response.pending_channels
                    ]
                },
            }
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
            peers_list = []
            for peer in response.peers:
                peers_list.append(
                    {
                        "pub_key": peer.pub_key,
                        "alias": peer.alias or "N/A",
                        "channels": peer.num_channels,
                        "total_capacity_sat": str(peer.total_capacity),
                        "address": peer.address,
                        "bytes_sent": str(peer.bytes_sent),
                        "bytes_recv": str(peer.bytes_recv),
                        "sat_sent": str(peer.sat_sent),
                        "sat_recv": str(peer.sat_recv),
                        "inbound": peer.inbound,
                        "ping_time": str(peer.ping_time),
                        "sync_type": ln.Peer.SyncType.Name(peer.sync_type),
                        "features": {
                            str(k): {
                                "name": v.name,
                                "is_required": v.is_required,
                                "is_known": v.is_known,
                            }
                            for k, v in peer.features.items()
                        },
                    }
                )
            return {
                "status": "OK",
                "peers": peers_list,
                "message": f"Found {len(peers_list)} connected peers.",
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
                "message": f"Successfully connected to peer {node_pubkey} at {host_port}.",
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error connecting to peer: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}

    def get_lnd_state(self) -> dict:
        """Fetches the internal state of the LND node using gRPC."""
        if self.state_stub is None:
            return {
                "status": "ERROR",
                "message": "LND gRPC state client not initialized.",
            }

        try:
            response = self.state_stub.GetState(state_service.GetStateRequest())
            state_str = state_service.WalletState.Name(response.state)
            return {"status": "OK", "data": {"state": state_str}}
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
            channels_list = []
            for channel in response.channels:
                channels_list.append(
                    {
                        "active": channel.active,
                        "remote_pubkey": channel.remote_pubkey,
                        "channel_point": channel.channel_point,
                        "chan_id": channel.chan_id,
                        "capacity": str(channel.capacity),
                        "local_balance": str(channel.local_balance),
                        "remote_balance": str(channel.remote_balance),
                        "commit_fee": str(channel.commit_fee),
                        "commit_weight": str(channel.commit_weight),
                        "fee_per_kw": str(channel.fee_per_kw),
                        "unsettled_balance": str(channel.unsettled_balance),
                        "total_satoshis_sent": str(channel.total_satoshis_sent),
                        "total_satoshis_received": str(channel.total_satoshis_received),
                        "num_updates": str(channel.num_updates),
                        "pending_htlcs": [
                            {
                                "incoming": htlc.incoming,
                                "amount": str(htlc.amount),
                                "hash_lock": htlc.hash_lock.hex(),
                                "expiration_height": htlc.expiration_height,
                            }
                            for htlc in channel.pending_htlcs
                        ],
                        "csv_delay": channel.csv_delay,
                        "private": channel.private,
                        "initiator": channel.initiator,
                        "chan_status_flags": channel.chan_status_flags,
                        "local_chan_reserve_sat": str(channel.local_chan_reserve_sat),
                        "remote_chan_reserve_sat": str(channel.remote_chan_reserve_sat),
                        "static_remote_key": channel.static_remote_key,
                        "commitment_type": ln.CommitmentType.Name(
                            channel.commitment_type
                        ),
                        "lifetime": str(channel.lifetime),
                        "uptime": str(channel.uptime),
                        "close_address": channel.close_address,
                        "push_amount_sat": str(channel.push_amount_sat),
                        "thaw_height": channel.thaw_height,
                    }
                )
            return {
                "status": "OK",
                "channels": channels_list,
                "message": f"Found {len(channels_list)} open channels.",
            }
        except grpc.RpcError as e:
            return {
                "status": "ERROR",
                "message": f"gRPC error listing channels: {e.details()}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"An unexpected error occurred: {e}"}
