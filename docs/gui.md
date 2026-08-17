# Simple desktop GUI package

OmniScript's built-in `gui` package is intentionally small and beginner-friendly. It automatically places controls from top to bottom, so a first app does not need layout classes, widget inheritance, or configuration objects.

```omni
use "gui"

seal window := gui.window("Hello", 420, 240)
window.label("What is your name?")
seal name := window.input()

craft greet() {
    window.message("Welcome", "Hello, " + name.get() + "!")
}

window.button("Say hello", greet)
window.run()
```

Run it with:

```bash
omni examples/gui_hello.omni
```

## Package functions

### `gui.available()`

Returns `true` when the host has Tk GUI support. Official native OmniScript executables bundle the required Python GUI modules.

### `gui.window(title, width := 480, height := 320)`

Creates a window. Width and height are ordinary whole-number pixels and must be at least 100. The returned window provides all other GUI methods.

```omni
seal window := gui.window("Notes", 600, 400)
```

Creating a window requires a desktop session. On a headless server, OmniScript returns a readable runtime error instead of a Python traceback.

## Window methods

Controls are added vertically in the order these methods are called.

| Method | Result |
|---|---|
| `window.heading(text)` | Large heading control |
| `window.label(text)` | Text label control |
| `window.status(text)` | Muted status text control |
| `window.input(value := "")` | One-line text control |
| `window.button(text, action)` | Button that calls a zero-argument craft |
| `window.checkbox(text, checked := false)` | Truth-value control |
| `window.textbox(value := "", height := 8)` | Multiline text control |
| `window.dropdown(options, selected := first)` | Simple option selector |
| `window.listbox(items := [])` | Selectable, editable list |
| `window.slider(min, max, value := min)` | Numeric slider |
| `window.progress(value := 0)` | Progress bar from 0 to 100 |
| `window.separator()` | Horizontal separator |
| `window.space(size := 8)` | Add simple vertical spacing |
| `window.message(title, text)` | Show an information dialog |
| `window.error(title, text)` | Show an error dialog |
| `window.confirm(title, text)` | Ask a yes/no question and return truth |
| `window.open_file(title := "Open file")` | Choose a file path or return `void` |
| `window.save_file(title := "Save file")` | Choose a save path or return `void` |
| `window.choose_folder()` | Choose a folder or return `void` |
| `window.choose_color(initial := "#ffffff")` | Choose a color or return `void` |
| `window.after(milliseconds, action)` | Run a craft later |
| `window.on_close(action)` | Set the close-window craft |
| `window.themes()` / `theme(name)` | List or select a native theme |
| `window.set_title(title)` | Change the title |
| `window.set_size(width, height)` | Change the window size |
| `window.close()` | Close the window |
| `window.run()` | Start the event loop; call this last |

## Control methods

Labels, inputs, checkboxes, and textboxes return a control with:

- `control.get()` — read its current value;
- `control.set(value)` — replace its value;
- `control.enable()` and `control.disable()`;
- `control.focus()` — move keyboard focus to it;
- `control.hide()` and `control.show()`.

Buttons return the enable, disable, focus, hide, and show methods. Dropdowns also provide `set_options(list)`. Listboxes provide `items()`, `set(list)`, `add(value)`, `remove(index)`, and `clear()`.

```omni
seal accepted := window.checkbox("I understand")
seal notes := window.textbox("Write here...", 10)

craft save() {
    when not accepted.get() {
        window.error("Not ready", "Please check the box.")
        return
    }
    write("notes.txt", notes.get())
    window.message("Saved", "Your notes were saved.")
}

window.button("Save", save)
```

## Advanced controls without advanced layout code

```omni
seal app := gui.window("Dashboard", 600, 500)
app.heading("Dashboard")
seal category := app.dropdown(["Work", "Personal"], "Work")
seal tasks := app.listbox([])
seal slider := app.slider(0, 100, 25)
seal progress := app.progress(25)
seal status := app.status("Ready")

craft add_task() {
    tasks.add("[" + category.get() + "] New task")
    progress.set(slider.get())
    status.set("Task added")
}

app.button("Add", add_task)
app.run()
```

The package keeps automatic vertical layout even for advanced controls. See `examples/gui_dashboard.omni` for a complete dashboard with tasks, priority, progress, folders, and dialogs.

## Events and errors

A button action is a normal zero-argument OmniScript craft. It can read controls, change controls, write files, emit output, or close the window. If an event raises an OmniScript error, the GUI loop stops and the CLI prints the normal source-located diagnostic.

The package is backed by the host's Tk toolkit, but Tk/Python objects are never exposed to an OmniScript program. This keeps the API small and consistent on Windows, Linux, and Apple Silicon macOS.
