{
  description = "ai-ops optional Nix operations layer";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
      pythonFor =
        pkgs:
        pkgs.python311.withPackages (
          ps: [
            ps.pytest
          ]
        );
      tools =
        pkgs:
        [
          pkgs.actionlint
          pkgs.bash
          pkgs.coreutils
          pkgs.findutils
          pkgs.git
          pkgs.gnugrep
          pkgs.gnused
          pkgs.jq
          pkgs.nil
          pkgs.nixfmt
          pkgs.ripgrep
          pkgs.rsync
          pkgs.shellcheck
          pkgs.shfmt
          (pythonFor pkgs)
        ]
        ++ nixpkgs.lib.optionals (pkgs ? gh) [ pkgs.gh ]
        ++ nixpkgs.lib.optionals (pkgs ? ghq) [ pkgs.ghq ]
        ++ nixpkgs.lib.optionals (pkgs ? gitleaks) [ pkgs.gitleaks ];
      app = pkgs: name: args: {
        type = "app";
        meta.description = "Run ai-ops ${args}";
        program = "${
          pkgs.writeShellApplication {
            name = name;
            runtimeInputs = tools pkgs;
            text = ''
              # Pass the flake's source tree to paths.py via env var so that
              # AGENTS.md and templates/ are reachable from the bundled build,
              # without altering $PWD. Changing the working directory would
              # hide the user's actual project from cli.py (target_root =
              # Path.cwd()) and confuse downstream agents.
              export AI_OPS_PACKAGE_ROOT="${self}"
              exec python -m ai_ops ${args} "$@"
            '';
          }
        }/bin/${name}";
      };
      checkDrv =
        pkgs: name: command:
        pkgs.runCommand name
          {
            nativeBuildInputs = tools pkgs;
            src = self;
          }
          ''
            cp -R "$src" source
            chmod -R u+w source
            cd source
            ${command}
            touch "$out"
          '';
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages = tools pkgs;
          };
        }
      );

      apps = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          # `nix run github:owner/ai-ops` (no args) prints --help via the
          # argparse dispatcher in cli.py; the empty `args` placeholder is
          # intentional, not a missing default.
          default = app pkgs "ai-ops" "";
          ai-ops = app pkgs "ai-ops" "";
          check = app pkgs "ai-ops-check" "check";
          lifecycle = app pkgs "ai-ops-lifecycle" "audit lifecycle";
          audit-nix = app pkgs "ai-ops-audit-nix" "audit nix";
          audit-security = app pkgs "ai-ops-audit-security" "audit security";
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          # Slow integration tests (e.g. test_packaging.py) shell out to pip,
          # which is not present inside the Nix sandbox. Run them in CI via
          # `python -m pytest -m slow` instead.
          python-tests = checkDrv pkgs "ai-ops-python-tests" ''
            python -m pytest -m "not slow"
          '';
          python-check = checkDrv pkgs "ai-ops-python-check" ''
            python -m ai_ops check
          '';
          lifecycle = checkDrv pkgs "ai-ops-lifecycle" ''
            python -m ai_ops audit lifecycle
          '';
          nix-audit = checkDrv pkgs "ai-ops-nix-audit" ''
            python -m ai_ops audit nix
          '';
          security = checkDrv pkgs "ai-ops-security" ''
            python -m ai_ops audit security
          '';
          ci = checkDrv pkgs "ai-ops-ci" ''
            actionlint .github/workflows/ci.yml
          '';
        }
      );
    };
}
