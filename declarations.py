from google.generativeai.types import FunctionDeclaration, Tool

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
            "base_fee_msat": {
                "type": "integer",
                "description": "The base fee in millisatoshis.",
            },
            "fee_rate_ppm": {
                "type": "integer",
                "description": "The fee rate in parts per million.",
            },
        },
        "required": ["channel_id", "base_fee_msat", "fee_rate_ppm"],
    },
)

open_channel_declaration = FunctionDeclaration(
    name="open_channel",
    description="Opens a new Lightning Network channel with a specified peer.",
    parameters={
        "type": "object",
        "properties": {
            "node_pubkey": {
                "type": "string",
                "description": "The public key of the peer to open a channel with.",
            },
            "local_funding_amount_sat": {
                "type": "integer",
                "description": "The amount of satoshis to commit to the channel from the local node.",
            },
            "sat_per_vbyte": {
                "type": "integer",
                "description": "Optional: The fee rate in satoshis per virtual byte for the funding transaction.",
            },
        },
        "required": ["node_pubkey", "local_funding_amount_sat"],
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
    parameters={"type": "object", "properties": {}}
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

get_mempool_top_nodes_declaration = FunctionDeclaration(
    name="get_mempool_top_nodes",
    description="Fetches a list of top nodes from mempool.space, enriched with address and capacity details.",
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
                "description": "The host:port of the peer (e.g., '3.33.236.230:9735').",
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

get_node_channels_from_mempool_declaration = FunctionDeclaration(
    name="get_node_channels_from_mempool",
    description="Fetches detailed channel information for a given Lightning Network node from mempool.space.",
    parameters={
        "type": "object",
        "properties": {
            "pubkey": {
                "type": "string",
                "description": "The public key of the node to query channel details for.",
            },
        },
        "required": ["pubkey"],
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

batch_open_channel_declaration = FunctionDeclaration(
    name="batch_open_channel",
    description="Opens multiple channels in a single transaction.",
    parameters={
        "type": "object",
        "properties": {
            "channels": {
                "type": "array",
                "description": "A list of channels to open.",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_pubkey": {
                            "type": "string",
                            "description": "The public key of the peer.",
                        },
                        "local_funding_amount_sat": {
                            "type": "integer",
                            "description": "The amount of satoshis to commit.",
                        },
                    },
                    "required": ["node_pubkey", "local_funding_amount_sat"],
                },
            },
            "sat_per_vbyte": {
                "type": "integer",
                "description": "Optional: The fee rate in satoshis per virtual byte for the funding transaction.",
            },
        },
        "required": ["channels"],
    },
)

tools = [
    Tool(function_declarations=[get_lnd_info_declaration]),
    Tool(function_declarations=[get_lnd_wallet_balance_declaration]),
    Tool(function_declarations=[set_fee_policy_declaration]),
    Tool(function_declarations=[open_channel_declaration]),
    Tool(function_declarations=[list_lnd_peers_declaration]),
    Tool(function_declarations=[list_lnd_channels_declaration]),
    Tool(function_declarations=[search_documents_declaration]),
    Tool(function_declarations=[get_document_content_declaration]),
    Tool(function_declarations=[list_all_documents_declaration]),
    Tool(function_declarations=[list_documents_by_type_declaration]),
    Tool(function_declarations=[get_mempool_top_nodes_declaration]),
    Tool(function_declarations=[connect_peer_declaration]),
    Tool(function_declarations=[get_node_channels_from_mempool_declaration]),
    Tool(function_declarations=[get_lnd_state_declaration]),
    Tool(function_declarations=[get_fee_recommendations_declaration]),
    Tool(function_declarations=[batch_open_channel_declaration]),
]
