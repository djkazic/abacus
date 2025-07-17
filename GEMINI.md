# Project Context
This repo is for an autonomous LND agent. It has the capability to look for potential channel peers and vet them. If the node needs it, the agent will open channels.

## Architecture
- `declarations.py` contains the tool declarations
- `lightning_pb2_grpc.py` is generated code and can be ignored
- `lightning_pb2.py` is also generated and can be ignored
- `lightning.proto` is downloaded from the LND repo
- `main.py` is the main entry point
- `state.py` holds the global data store and token counter var
- `tools/` is a directory holding the code for the agent's tools
- `tools/network_analysis_tools.py` has tools for fetching node availability and network analysis.
- `tools/mempool_space_tools.py` has mempool.space API tools for fee recommendations and channel lookups.
- `tools/lnd_tools.py` has LND gRPC based tools
