{
  description = "salpinx — annotation-style pub/sub and RPC on top of zenoh";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  outputs = { nixpkgs, ... }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    devShells.${system}.default = pkgs.mkShell {
      name = "salpinx-dev";
      packages = with pkgs; [ python312 uv ruff mypy ];
      NIX_LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
      NIX_LD = "${pkgs.stdenv.cc.bintools.dynamicLinker}";
    };
  };
}
