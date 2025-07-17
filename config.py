import os


# --- Configuration Constants ---
MODEL_NAME = "gemini-2.5-flash-lite-preview-06-17"
TICK_INTERVAL_SECONDS = 600  # 10 minutes
MAX_HISTORY_LENGTH = 20  # Max number of turns to keep in chat history before condensing
DOCS_DIR = "docs"  # Directory where your documentation files are stored
MAX_PAYLOAD_SIZE_CHARACTERS = (
    30000  # Max size of the tool response payload to send to the model
)

# --- LND Configuration ---
# The network the agent is operating on. Can be 'mainnet' or 'testnet'.
LND_NETWORK = os.getenv("LND_NETWORK", "mainnet")
LND_ADMIN_MACAROON_PATH = os.getenv(
    "LND_ADMIN_MACAROON_PATH", f"/lnd/data/chain/bitcoin/{LND_NETWORK}/admin.macaroon"
)

# --- Node Blacklist ---
# Nodes that can trigger edge cases for deploying liquidity
NODE_BLACKLIST = [
    "0364913d18a19c671bb36dd04d6ad5be0fe8f2894314c36a9db3f03c2d414907e1",  # 20M minimum chan size
]
