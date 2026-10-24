# Homebrew formula — this repository is its own tap:
#   brew tap aviv27-dev/rainbowomma https://github.com/aviv27-dev/RainbowOMMA
#   brew install rainbowomma
# A new release: update url and sha256 (shasum -a 256 of the release's .tar.gz).
class Rainbowomma < Formula
  desc "One Mac, Many Agents: a colored Chrome, ports, processes and a guard per AI agent"
  homepage "https://github.com/aviv27-dev/RainbowOMMA"
  url "https://github.com/aviv27-dev/RainbowOMMA/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0ef8ae6f5743483c52aeefbdc59a9e369293976ffe51a2fb70909017d7ce066b"
  license "Apache-2.0"

  depends_on :macos     # and a python3: Homebrew's, or the developer tools' (xcode-select --install) — install.sh checks

  def install
    libexec.install Dir["*"]
    %w[install uninstall].each do |what|
      (bin/"rainbowomma-#{what}").write <<~SH
        #!/bin/bash
        # the tools live together in one folder of yours (default ~/bin): this puts them there, or takes them out
        exec "#{libexec}/#{what}.sh" "$@"
      SH
    end
  end

  def caveats
    <<~EOS
      RainbowOMMA's tools work from one folder of yours, next to your browsers.json. Put them there (again after
      every `brew upgrade rainbowomma`):
        rainbowomma-install --with-heal --adapter claude-code     # into ~/bin; --bin DIR for another folder
      then fill in ~/bin/browsers.json and run ~/bin/rainbowomma-doctor.
      Taking it out: rainbowomma-uninstall (add --purge for the state and the registry), then brew uninstall.
    EOS
  end

  test do
    assert_match "install.sh", shell_output("#{bin}/rainbowomma-install --help")
  end
end
