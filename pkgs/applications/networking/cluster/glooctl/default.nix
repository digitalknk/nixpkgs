{ lib, buildGoModule, fetchFromGitHub, installShellFiles }:

buildGoModule rec {
  pname = "glooctl";
  version = "1.13.6";

  src = fetchFromGitHub {
    owner = "solo-io";
    repo = "gloo";
    rev = "v${version}";
    hash = "sha256-CBWKKW5VIkRgl7wY63OCm/CowWHO389se3kEraqaDCI=";
  };

  subPackages = [ "projects/gloo/cli/cmd" ];
  vendorHash = "sha256-sQv6g0Xgs+6jgxacWJwE3dK3GimfiPHly0Z0rvdKNE4=";

  nativeBuildInputs = [ installShellFiles ];

  postInstall = ''
    mv $out/bin/cmd $out/bin/glooctl

    export HOME=$TMP
    installShellCompletion --cmd glooctl \
      --bash <($out/bin/glooctl completion bash) \
      --zsh <($out/bin/glooctl completion zsh)
  '';

  ldflags = [ "-s" "-w" "-X github.com/solo-io/gloo/pkg/version.Version=${version}" ];

  meta = with lib; {
    description = "glooctl is the unified CLI for Gloo";
    homepage = "https://docs.solo.io/gloo-edge/latest/reference/cli/glooctl/";
    license = licenses.asl20;
    maintainers = with maintainers; [ nelsonjeppesen ];
  };
}
