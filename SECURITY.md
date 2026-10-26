# Security policy

CLIPFORGE alpha is for a single trusted user on localhost. It has no login,
tenant isolation or production rate limiter. Do not expose the app or Ollama
to a public interface. See [deployment requirements](docs/DEPLOYMENT.md).

Only the latest alpha is maintained. Keep Python, Node, FFmpeg, Ollama and
dependencies updated. Media decoders and model runtimes process complex input:
do not treat this app as a sandbox for hostile files.

Report vulnerabilities privately using the repository Security tab's **Report
a vulnerability** option when enabled. If unavailable, open a minimal issue
requesting a private reporting channel without exploit details. Never include
tokens, browser cookies, personal media, transcripts or logs with private paths.
Public issue attachments are public. There is no guaranteed response SLA.

Write requests with foreign browser Origins are rejected; trusted hosts and
static-path confinement mitigate browser rebinding/traversal. Upload checks and
container/protocol validation are defense in depth, not internet-service quotas.
No security audit can guarantee absence of vulnerabilities.
