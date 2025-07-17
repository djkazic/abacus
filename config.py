import os


# --- Configuration Constants ---
MODEL_NAME = "gemini-2.5-flash-lite-preview-06-17"
TICK_INTERVAL_SECONDS = 600  # 10 minutes
MAX_HISTORY_LENGTH = 20  # Max number of turns to keep in chat history before condensing
DOCS_DIR = "docs"  # Directory where your documentation files are stored

# --- LND Configuration ---
# The network the agent is operating on. Can be 'mainnet' or 'testnet'.
LND_NETWORK = os.getenv("LND_NETWORK", "mainnet")
LND_ADMIN_MACAROON_PATH = os.getenv(
    "LND_ADMIN_MACAROON_PATH", f"/lnd/data/chain/bitcoin/{LND_NETWORK}/admin.macaroon"
)
