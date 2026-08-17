const vscode = require('vscode');

function quote(value) {
  if (process.platform === 'win32') {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

async function activeOmniFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== 'omniscript') {
    vscode.window.showErrorMessage('Open an OmniScript .omni file first.');
    return undefined;
  }
  if (!(await editor.document.save())) {
    vscode.window.showErrorMessage('Save the OmniScript file before running it.');
    return undefined;
  }
  return editor.document.uri.fsPath;
}

async function send(subcommand) {
  const file = await activeOmniFile();
  if (!file) return;
  const executable = vscode.workspace.getConfiguration('omniscript').get('executable', 'omni');
  const terminal = vscode.window.createTerminal({ name: 'OmniScript' });
  terminal.show();
  terminal.sendText(`${quote(executable)} ${subcommand} ${quote(file)}`);
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('omniscript.runFile', () => send('run')),
    vscode.commands.registerCommand('omniscript.checkFile', () => send('check'))
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
