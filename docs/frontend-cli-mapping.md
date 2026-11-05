# Frontend and CLI Integration

For the supported HTTP surface, read [the canonical contract](backend-contract.md).
For command-line execution, read [CLI usage](cli.md). These interfaces serve
different workflows; command groups do not imply matching HTTP endpoints.

Electron starts the backend with loopback binding, an ephemeral port and a token.
The renderer receives the URL/token through preload. Browser development binds
one solution at backend startup. Both use root HTTP routes without a Jobs/SSE layer.

The former endpoint parity matrix has been removed from the active reference.
Describe new integration behavior in the canonical contract and test its consumer.
