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
              root="''${AI_OPS_ROOT:-$PWD}"
              if [ ! -d "$root/ai_ops" ]; then
                root="${self}"
              fi
              cd "$root"
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
          python-tests = checkDrv pkgs "ai-ops-python-tests" ''
            python -m pytest
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
