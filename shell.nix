{ pkgs ? import <nixpkgs> {} }:
with pkgs; mkShell {
  nativeBuildInputs = [ (python3.withPackages (p: with p; [ discordpy requests ])) ];
}
