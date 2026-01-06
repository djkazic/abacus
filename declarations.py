from google.genai.types import FunctionDeclaration, Tool

# --- Tool Declarations ---
get_lnd_info_declaration = FunctionDeclaration(
    name="get_lnd_info",
    description="Fetches detailed information about the LND node, including alias, public key, chains, and network status.",
    parameters={"type": "object", "properties": {}},
)

get_lnd_wallet_balance_declaration = FunctionDeclaration(
    name="get_lnd_wallet_balance",
    description="Shows the on-chain wallet balance of the LND node, including confirmed and unconfirmed balances.",
    parameters={"type": "object", "properties": {}},
)

get_lnd_channel_balance_declaration = FunctionDeclaration(
    name="get_lnd_channel_balance",
    description="Shows the node's current channel balance.",
    parameters={"type": "object", "properties": {}},
)

set_fee_policy_declaration = FunctionDeclaration(
    name="set_fee_policy",
    description="Sets the fee policy for a specific Lightning Network channel.",
    parameters={
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "The ID of the channel to update.",
            },
            "fee_rate": {
                "type": "integer",
                "description": "The fee rate in parts per million.",
            },
        },
        "required": ["channel_id", "fee_rate"],
    },
)

propose_channel_opens_declaration = FunctionDeclaration(
    name="propose_channel_opens",
    description="Calculates channel sizes, performs safety checks, and proposes channel openings with a list of peers.",
    parameters={
        "type": "object",
        "properties": {
            "peers": {
                "type": "array",
                "description": "A list of peer objects to open channels with.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pub_key": {"type": "string"},
                    },
                    "required": ["pub_key"],
                },
            },
            "sat_per_vbyte": {
                "type": "integer",
                "description": "The fee rate in satoshis per virtual byte for the funding transaction.",
            },
        },
        "required": ["peers", "sat_per_vbyte"],
    },
)

execute_channel_opens_declaration = FunctionDeclaration(
    name="execute_channel_opens",
    description="Executes a list of proposed channel opening operations.",
    parameters={
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "description": "A list of channel opening operations to execute.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["single", "batch"]},
                        "node_pubkey": {"type": "string"},
                        "local_funding_amount_sat": {"type": "integer"},
                        "sat_per_vbyte": {"type": "integer"},
                        "channels": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "node_pubkey": {"type": "string"},
                                    "local_funding_amount_sat": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
            }
        },
        "required": ["operations"],
    },
)

list_lnd_peers_declaration = FunctionDeclaration(
    name="list_lnd_peers",
    description="Lists information about connected or discoverable Lightning Network peers, including their public keys, aliases, and channel statistics.",
    parameters={"type": "object", "properties": {}},
)

list_lnd_channels_declaration = FunctionDeclaration(
    name="list_lnd_channels",
    description="Lists information about this node's channels.",
    parameters={"type": "object", "properties": {}},
)

search_documents_declaration = FunctionDeclaration(
    name="search_documents",
    description="Searches the internal documentation for relevant documents based on a query. Use this to find 'tome' for factual info or 'runbook' for command-centric guides.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query for documents.",
            },
        },
        "required": ["query"],
    },
)

get_document_content_declaration = FunctionDeclaration(
    name="get_document_content",
    description="Retrieves the full content of a specified internal document by its exact name.",
    parameters={
        "type": "object",
        "properties": {
            "document_name": {
                "type": "string",
                "description": "The exact name of the document to retrieve (e.g., 'tome_liquidity_principles.md').",
            },
        },
        "required": ["document_name"],
    },
)

list_all_documents_declaration = FunctionDeclaration(
    name="list_all_documents",
    description="Lists the names of all available internal documents.",
    parameters={"type": "object", "properties": {}},
)

list_documents_by_type_declaration = FunctionDeclaration(
    name="list_documents_by_type",
    description="Lists the names of internal documents filtered by their type ('tome' or 'runbook').",
    parameters={
        "type": "object",
        "properties": {
            "doc_type": {
                "type": "string",
                "description": "The type of documents to list ('tome' or 'runbook').",
            },
        },
        "required": ["doc_type"],
    },
)

get_top_and_filter_nodes_declaration = FunctionDeclaration(
    name="get_top_and_filter_nodes",
    description="Fetches a list of top nodes from mempool.space, enriches them with details, and filters them based on their average fee rates.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Optional: The maximum number of top nodes to retrieve (default is 10).",
            },
        },
    },
)

connect_peer_declaration = FunctionDeclaration(
    name="connect_peer",
    description="Connects to a Lightning Network peer using their public key and host:port. This is a prerequisite for opening a channel.",
    parameters={
        "type": "object",
        "properties": {
            "node_pubkey": {
                "type": "string",
                "description": "The public key of the peer to connect to.",
            },
            "host_port": {
                "type": "string",
                "description": "The host:port of the peer.",
            },
        },
        "required": ["node_pubkey", "host_port"],
    },
)

analyze_peer_network_declaration = FunctionDeclaration(
    name="analyze_peer_network",
    description="Recursively analyzes a segment of the Lightning Network starting from a given public key, using internally stored comprehensive node data. This helps identify well-connected nodes beyond immediate peers.",
    parameters={
        "type": "object",
        "properties": {
            "start_pubkey": {
                "type": "string",
                "description": "The public key of the node to start the analysis from.",
            },
            "max_depth": {
                "type": "integer",
                "description": "Optional: The maximum recursion depth (default is 3 levels).",
            },
            "peers_per_level": {
                "type": "integer",
                "description": "Optional: The maximum number of sub-peers to explore at each level (default is 3).",
            },
        },
        "required": ["start_pubkey"],
    },
)

get_lnd_state_declaration = FunctionDeclaration(
    name="get_lnd_state",
    description="Fetches the internal state of the LND node.",
    parameters={"type": "object", "properties": {}},
)

get_fee_recommendations_declaration = FunctionDeclaration(
    name="get_fee_recommendations",
    description="Fetches recommended fee rates from mempool.space's API.",
    parameters={"type": "object", "properties": {}},
)

get_node_uri_declaration = FunctionDeclaration(
    name="get_node_uri",
    description="Fetches the connection URI for a given Lightning Network node.",
    parameters={
        "type": "object",
        "properties": {
            "pubkey": {
                "type": "string",
                "description": "The public key of the node to look up.",
            },
        },
        "required": ["pubkey"],
    },
)


batch_connect_peers_declaration = FunctionDeclaration(
    name="batch_connect_peers",
    description="Connects to multiple Lightning Network peers in a batch.",
    parameters={
        "type": "object",
        "properties": {
            "peers": {
                "type": "array",
                "description": "A list of peers to connect to.",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_pubkey": {
                            "type": "string",
                            "description": "The public key of the peer to connect to.",
                        },
                        "host_port": {
                            "type": "string",
                            "description": "The host:port of the peer (e.g., '3.33.236.230:9735').",
                        },
                    },
                    "required": ["node_pubkey", "host_port"],
                },
            },
        },
        "required": ["peers"],
    },
)

analyze_channel_liquidity_flow_declaration = FunctionDeclaration(
    name="analyze_channel_liquidity_flow",
    description="Analyzes the liquidity flow of each channel over the last 7 days and provides a summary with the current balance and a liquidity trend.",
    parameters={"type": "object", "properties": {}},
)

calculate_and_quote_loop_outs_declaration = FunctionDeclaration(
    name="calculate_and_quote_loop_outs",
    description="Calculates the precise amount to Loop Out to rebalance a list of channels to 50% outbound liquidity and fetches a quote for each.",
    parameters={
        "type": "object",
        "properties": {
            "channel_ids": {
                "type": "array",
                "description": "A list of channel IDs to calculate loop out amounts for.",
                "items": {"type": "string"},
            }
        },
        "required": ["channel_ids"],
    },
)

initiate_loop_out_declaration = FunctionDeclaration(
    name="initiate_loop_out",
    description="Initiates a Loop Out swap for a specific channel to rebalance it to 50% outbound liquidity.",
    parameters={
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "The ID of the channel to loop out.",
            },
        },
        "required": ["channel_id"],
    },
)

list_loop_out_swaps_declaration = FunctionDeclaration(
    name="list_loop_out_swaps",
    description="Lists all Loop Out swaps.",
    parameters={"type": "object", "properties": {}},
)

should_open_to_loop_declaration = FunctionDeclaration(
    name="should_open_to_loop",
    description="Checks if the node has enough inbound liquidity to open a new channel to the Loop node.",
    parameters={"type": "object", "properties": {}},
)

propose_fee_adjustments_declaration = FunctionDeclaration(
    name="propose_fee_adjustments",
    description="Analyzes all open channels and proposes fee adjustments based on their recent forwarding activity.",
    parameters={"type": "object", "properties": {}},
)

execute_rebalance_declaration = FunctionDeclaration(
    name="execute_rebalance",
    description="Executes a circular rebalance to move funds from an outbound channel to an inbound channel.",
    parameters={
        "type": "object",
        "properties": {
            "outgoing_channel_id": {
                "type": "string",
                "description": "The ID of the channel to send funds from.",
            },
            "incoming_channel_id": {
                "type": "string",
                "description": "The ID of the channel to send funds to.",
            },
            "amount_sats": {
                "type": "integer",
                "description": "The amount in satoshis to rebalance.",
            },
        },
        "required": ["outgoing_channel_id", "incoming_channel_id", "amount_sats"],
    },
)

find_rebalance_opportunities_declaration = FunctionDeclaration(
    name="find_rebalance_opportunities",
    description="Finds opportunities for rebalancing channels.",
    parameters={"type": "object", "properties": {}},
)

propose_channel_closes_declaration = FunctionDeclaration(
    name="propose_channel_closes",
    description="Identifies and proposes closing channels with low outbound liquidity usage.",
    parameters={"type": "object", "properties": {}},
)

execute_channel_closes_declaration = FunctionDeclaration(
    name="execute_channel_closes",
    description="Closes a list of channels.",
    parameters={
        "type": "object",
        "properties": {
            "channel_points": {
                "type": "array",
                "description": "A list of channel points to close.",
                "items": {"type": "string"},
            }
        },
        "required": ["channel_points"],
    },
)

tools = [
    Tool(function_declarations=[get_lnd_info_declaration]),
    Tool(function_declarations=[get_lnd_wallet_balance_declaration]),
    Tool(function_declarations=[get_lnd_channel_balance_declaration]),
    Tool(function_declarations=[set_fee_policy_declaration]),
    Tool(function_declarations=[propose_channel_opens_declaration]),
    Tool(function_declarations=[execute_channel_opens_declaration]),
    Tool(function_declarations=[list_lnd_peers_declaration]),
    Tool(function_declarations=[list_lnd_channels_declaration]),
    Tool(function_declarations=[search_documents_declaration]),
    Tool(function_declarations=[get_document_content_declaration]),
    Tool(function_declarations=[list_all_documents_declaration]),
    Tool(function_declarations=[list_documents_by_type_declaration]),
    Tool(function_declarations=[get_top_and_filter_nodes_declaration]),
    Tool(function_declarations=[connect_peer_declaration]),
    Tool(function_declarations=[get_lnd_state_declaration]),
    Tool(function_declarations=[get_fee_recommendations_declaration]),
    Tool(function_declarations=[get_node_uri_declaration]),
    Tool(function_declarations=[batch_connect_peers_declaration]),
    Tool(function_declarations=[analyze_channel_liquidity_flow_declaration]),
    Tool(function_declarations=[calculate_and_quote_loop_outs_declaration]),
    Tool(function_declarations=[initiate_loop_out_declaration]),
    Tool(function_declarations=[list_loop_out_swaps_declaration]),
    Tool(function_declarations=[should_open_to_loop_declaration]),
    Tool(function_declarations=[propose_fee_adjustments_declaration]),
    Tool(function_declarations=[execute_rebalance_declaration]),
    Tool(function_declarations=[find_rebalance_opportunities_declaration]),
    Tool(function_declarations=[propose_channel_closes_declaration]),
    Tool(function_declarations=[execute_channel_closes_declaration]),
]
