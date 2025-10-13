{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  packages = [
    pkgs.git
    pkgs.gh
  ];

  languages.python = {
    enable = true;
    poetry = {
      enable = true;
      install = {
        enable = true;
        installRootPackage = false;
        onlyInstallRootPackage = false;
        compile = false;
        quiet = false;
        groups = [ ];
        ignoredGroups = [ ];
        onlyGroups = [ ];
        extras = [ ];
        allExtras = false;
        verbosity = "no";
      };
      activate.enable = true;
      package = pkgs.poetry;
    };
  };

  scripts.regenerate-models = {
    description = "Regenerate Pydantic models from Lambda Cloud OpenAPI spec";
    exec = ''
      SPEC_FILE="$DEVENV_ROOT/Lambda Cloud API spec 1.8.3.json"
      OUTPUT_FILE="$DEVENV_ROOT/src/lambdalabs/models.py"

      echo "Regenerating models from OpenAPI spec..."
      echo "Input:  $SPEC_FILE"
      echo "Output: $OUTPUT_FILE"

      datamodel-codegen \
        --input "$SPEC_FILE" \
        --output "$OUTPUT_FILE" \
        --output-model-type pydantic_v2.BaseModel \
        --target-python-version 3.11 \
        --use-standard-collections \
        --use-union-operator \
        --enable-faux-immutability \
        --field-constraints \
        --snake-case-field \
        --use-default-kwarg

      echo "✓ Models regenerated successfully"
      echo ""
      echo "Next steps:"
      echo "  1. Review the generated code"
      echo "  2. Run: black src/lambdalabs/models.py"
      echo "  3. Run: ruff check src/lambdalabs/models.py"
      echo "  4. Run: mypy src/lambdalabs/models.py"
      echo "  5. Commit the changes"
    '';
  };
}
