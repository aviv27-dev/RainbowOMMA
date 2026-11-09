# Demo video — under 90 seconds, no narration needed (captions)

Setup: two Hermes profiles (agents `alpha` — orange, `bravo` — blue), the human's own Chrome open on example.com.
Language `en`.

| t | on screen | caption |
|---|---|---|
| 0–6 | title card | "RainbowOMMA for Hermes — one Mac, one human, many agents" |
| 6–20 | two terminals side by side: `hermes` as alpha and as bravo. Each is asked "open example.com in your browser". Two Chrome windows appear, orange frame "Alpha · AI Agent", blue frame "Bravo · AI Agent". The human's Chrome stays as it was. | "Every profile gets its own Chrome — colour-framed, never yours" |
| 20–32 | `/rainbow` in alpha's terminal: both agents, browsers up, ports. | "/rainbow — who holds what" |
| 32–48 | alpha is asked to "kill all Chrome processes". The tool call is refused; the agent reads the reason and uses its own browser tools instead. All three Chromes are still there. | "pkill Chrome? Refused — before it runs" |
| 48–60 | bravo is asked to "start a dev server on port 3000". Refused: the port is kept for the human; the agent leases 41xxx and starts there. | "Your ports stay yours" |
| 60–74 | alpha converts a Word document to PDF and is then asked to "quit Word". Conversion works; quitting is refused. | "Documents by lease. Your Word is never quit" |
| 74–84 | `/rainbow pause` → the next tool call of each agent is refused; `/rainbow resume`. | "One stop button for all of them" |
| 84–90 | end card: `hermes plugins install rainbowomma` · github.com/aviv27-dev/RainbowOMMA | |
