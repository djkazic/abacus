![IMAGE 2025-07-11 15:32:27](https://github.com/user-attachments/assets/6764b5d8-f9b3-4eea-9384-c3e6f6c0dc73)

abacus is an autonomous LND agent using Google's Gemini model for tool execution.

Right now it is a work-in-progress, with limited functionality.

Eventually it should be capable of doing everything from opening channels to closing unproductive ones to setting fee policies.

To try out abacus, setup a virtualenv and then install the dependencies in `requirements.txt`

Then, just run `python main.py`!

abacus utilizes `rich` for its TUI and is a hybrid of autonomous agent and human-in-the-loop. It currently won't open a channel without your consent, but this will eventually be removed.

## Reckless
Oh, you're still here?

Set these env vars.

`GOOGLE_API_KEY`
`LND_GRPC_HOST`
`LND_TLS_CERT_PATH`
`LND_ADMIN_MACAROON_PATH`
