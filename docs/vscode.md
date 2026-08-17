# VS Code extension

The custom extension in [`editors/vscode`](../editors/vscode) provides:

- `.omni` language registration
- TextMate syntax highlighting
- bracket/comment/indentation rules
- snippets for crafts, shapes, branches, loops, imports, and assertions
- **OmniScript: Run Current File** command
- **OmniScript: Check Current File** command

## Install from the repository

Copy or link the directory into VS Code's extension folder:

```bash
# Linux/macOS
cp -R editors/vscode ~/.vscode/extensions/omniscript-language-0.1.0
```

On Windows copy it to `%USERPROFILE%\.vscode\extensions\omniscript-language-0.1.0`. Restart VS Code after copying.

For development, open `editors/vscode` in VS Code and press **F5** to launch an Extension Development Host. The extension has no npm dependencies or build step.

The Run and Check commands invoke the `omni` executable in VS Code's integrated terminal, so install the CLI and make sure it is available on `PATH` first.

## Package a VSIX

With `@vscode/vsce` available:

```bash
cd editors/vscode
npx @vscode/vsce package
code --install-extension omniscript-language-0.1.0.vsix
```
