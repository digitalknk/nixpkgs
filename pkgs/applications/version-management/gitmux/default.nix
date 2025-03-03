{ fetchFromGitHub, buildGoModule, lib, testers, gitmux }:

buildGoModule rec {
  pname = "gitmux";
  version = "0.7.12";

  src = fetchFromGitHub {
    owner = "arl";
    repo = pname;
    rev = "v${version}";
    sha256 = "sha256-JPrXq4+53cem0TVnm1/AJz/mYcEKaYzqhptJU4V2U0o=";
  };

  vendorHash = "sha256-V6xe+19NiHYIIN4rgkyzdP4eGnRXo0aW4fVbdlIcvig=";

  # GitHub source does contain a regression test for the module
  # but it requires networking as it git clones a repo from github
  doCheck = false;

  ldflags = [ "-X main.version=${version}" ];

  passthru.tests.version = testers.testVersion {
    package = gitmux;
    command = "gitmux -V";
  };

  subPackages = [ "." ];

  meta = with lib; {
    description = "Git in your tmux status bar";
    homepage = "https://github.com/arl/gitmux";
    license = licenses.mit;
    maintainers = with maintainers; [ nialov ];
  };
}
