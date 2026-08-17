"""Small beginner-friendly desktop GUI module backed by Tk.

Tk is loaded lazily so OmniScript keeps working on servers and minimal Python
installations. The public language API uses simple maps of methods rather than
exposing Python or Tkinter objects.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any, Callable

from .errors import OmniError, OmniRuntimeError, Span
from .runtime import NativeFunction, OmniCallable, OmniModule, stringify, truthy


def create_gui_module() -> OmniModule:
    return OmniModule(
        "gui",
        {
            "available": _native("gui.available", _available, 0),
            "window": _native("gui.window", _window, 1, 3),
        },
    )


def _native(
    name: str,
    implementation: Callable[[Any, list[Any], Span], Any],
    minimum: int,
    maximum: int | None = None,
) -> NativeFunction:
    return NativeFunction(name, implementation, minimum, minimum if maximum is None else maximum)


def _available(_interpreter: Any, _arguments: list[Any], _span: Span) -> bool:
    return importlib.util.find_spec("tkinter") is not None


def _window(interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
    title = stringify(arguments[0])
    width = _dimension(arguments[1], "width", span) if len(arguments) >= 2 else 480
    height = _dimension(arguments[2], "height", span) if len(arguments) >= 3 else 320
    return GuiWindow(interpreter, title, width, height, span).public_api()


def _whole_number(value: Any, name: str, minimum: int, span: Span) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise OmniRuntimeError(f"GUI {name} must be a whole number", span)
    result = int(value)
    if result < minimum:
        raise OmniRuntimeError(f"GUI {name} must be at least {minimum}", span)
    return result


def _dimension(value: Any, name: str, span: Span) -> int:
    return _whole_number(value, name, 100, span)


def _number(value: Any, name: str, span: Span) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OmniRuntimeError(f"GUI {name} must be a number", span)
    return float(value)


def _text_list(value: Any, name: str, span: Span) -> list[str]:
    if not isinstance(value, list):
        raise OmniRuntimeError(f"GUI {name} must be a list", span)
    return [stringify(item) for item in value]


def _load_toolkit(span: Span):
    try:
        tk = importlib.import_module("tkinter")
        ttk = importlib.import_module("tkinter.ttk")
        messagebox = importlib.import_module("tkinter.messagebox")
        return tk, ttk, messagebox
    except (ImportError, ModuleNotFoundError) as error:
        raise OmniRuntimeError(
            "the GUI package is unavailable because Tk is not installed",
            span,
            "use an official OmniScript executable or install your system's Tk package",
        ) from error


class GuiWindow:
    def __init__(self, interpreter: Any, title: str, width: int, height: int, span: Span):
        self.interpreter = interpreter
        self.span = span
        self.tk, self.ttk, self.messagebox = _load_toolkit(span)
        self.pending_error: OmniError | None = None
        try:
            self.root = self.tk.Tk()
            self.root.title(title)
            self.root.geometry(f"{width}x{height}")
            self.root.minsize(200, 120)
            self.body = self.ttk.Frame(self.root, padding=14)
            self.body.pack(fill="both", expand=True)
            self.style = self.ttk.Style() if hasattr(self.ttk, "Style") else None
            if self.style is not None:
                self.style.configure("Heading.TLabel", font=("TkDefaultFont", 16, "bold"))
                self.style.configure("Status.TLabel", foreground="#555555")
        except Exception as error:
            raise OmniRuntimeError(
                f"could not open a GUI window: {error}",
                span,
                "desktop windows require a graphical session; GUI code cannot run on a headless server",
            ) from error

    def public_api(self) -> dict[str, Any]:
        return {
            "heading": _native("window.heading", self.heading, 1),
            "label": _native("window.label", self.label, 1),
            "status": _native("window.status", self.status, 1),
            "input": _native("window.input", self.input, 0, 1),
            "button": _native("window.button", self.button, 2),
            "checkbox": _native("window.checkbox", self.checkbox, 1, 2),
            "textbox": _native("window.textbox", self.textbox, 0, 2),
            "dropdown": _native("window.dropdown", self.dropdown, 1, 2),
            "listbox": _native("window.listbox", self.listbox, 0, 1),
            "slider": _native("window.slider", self.slider, 2, 3),
            "progress": _native("window.progress", self.progress, 0, 1),
            "separator": _native("window.separator", self.separator, 0),
            "space": _native("window.space", self.space, 0, 1),
            "message": _native("window.message", self.message, 2),
            "error": _native("window.error", self.error, 2),
            "confirm": _native("window.confirm", self.confirm, 2),
            "open_file": _native("window.open_file", self.open_file, 0, 1),
            "save_file": _native("window.save_file", self.save_file, 0, 1),
            "choose_folder": _native("window.choose_folder", self.choose_folder, 0),
            "choose_color": _native("window.choose_color", self.choose_color, 0, 1),
            "after": _native("window.after", self.after, 2),
            "on_close": _native("window.on_close", self.on_close, 1),
            "themes": _native("window.themes", self.themes, 0),
            "theme": _native("window.theme", self.theme, 1),
            "set_title": _native("window.set_title", self.set_title, 1),
            "set_size": _native("window.set_size", self.set_size, 2),
            "close": _native("window.close", self.close, 0),
            "run": _native("window.run", self.run, 0),
        }

    def heading(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        variable = self.tk.StringVar(value=stringify(arguments[0]))
        widget = self.ttk.Label(self.body, textvariable=variable, style="Heading.TLabel")
        widget.pack(anchor="w", pady=(4, 8))
        return self._value_control("heading", widget, variable)

    def label(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        variable = self.tk.StringVar(value=stringify(arguments[0]))
        widget = self.ttk.Label(self.body, textvariable=variable)
        widget.pack(anchor="w", pady=4)
        return self._value_control("label", widget, variable)

    def status(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        variable = self.tk.StringVar(value=stringify(arguments[0]))
        widget = self.ttk.Label(self.body, textvariable=variable, style="Status.TLabel")
        widget.pack(anchor="w", pady=4)
        return self._value_control("status", widget, variable)

    def input(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        value = stringify(arguments[0]) if arguments else ""
        variable = self.tk.StringVar(value=value)
        widget = self.ttk.Entry(self.body, textvariable=variable)
        widget.pack(fill="x", pady=4)
        return self._value_control("input", widget, variable)

    def button(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        text, action = stringify(arguments[0]), arguments[1]
        if not isinstance(action, OmniCallable):
            raise OmniRuntimeError("window.button action must be a craft", span)
        widget = self.ttk.Button(self.body, text=text, command=lambda: self._invoke(action, span))
        widget.pack(fill="x", pady=6)
        return self._basic_control("button", widget)

    def checkbox(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        checked = truthy(arguments[1]) if len(arguments) == 2 else False
        variable = self.tk.BooleanVar(value=checked)
        widget = self.ttk.Checkbutton(self.body, text=stringify(arguments[0]), variable=variable)
        widget.pack(anchor="w", pady=4)
        return self._value_control("checkbox", widget, variable, boolean=True)

    def textbox(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        value = stringify(arguments[0]) if arguments else ""
        height = _whole_number(arguments[1], "textbox height", 2, span) if len(arguments) == 2 else 8
        widget = self.tk.Text(self.body, height=height, wrap="word")
        widget.insert("1.0", value)
        widget.pack(fill="both", expand=True, pady=4)

        def get(_i: Any, _a: list[Any], _s: Span) -> str:
            return str(widget.get("1.0", "end-1c"))

        def set_value(_i: Any, values: list[Any], _s: Span) -> str:
            text = stringify(values[0])
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            return text

        return {
            **self._basic_control("textbox", widget),
            "get": _native("textbox.get", get, 0),
            "set": _native("textbox.set", set_value, 1),
        }

    def dropdown(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        options = _text_list(arguments[0], "dropdown options", span)
        if not options:
            raise OmniRuntimeError("GUI dropdown options cannot be empty", span)
        selected = stringify(arguments[1]) if len(arguments) == 2 else options[0]
        variable = self.tk.StringVar(value=selected)
        widget = self.ttk.Combobox(self.body, textvariable=variable, values=options, state="readonly")
        widget.pack(fill="x", pady=4)
        control = self._value_control("dropdown", widget, variable)

        def set_options(_i: Any, values: list[Any], call_span: Span) -> None:
            new_options = _text_list(values[0], "dropdown options", call_span)
            if not new_options:
                raise OmniRuntimeError("GUI dropdown options cannot be empty", call_span)
            widget.configure(values=new_options)
            if str(variable.get()) not in new_options:
                variable.set(new_options[0])
            return None

        control["set_options"] = _native("dropdown.set_options", set_options, 1)
        return control

    def listbox(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        initial = _text_list(arguments[0], "listbox items", span) if arguments else []
        widget = self.tk.Listbox(self.body, height=max(4, min(12, len(initial) or 6)))
        for item in initial:
            widget.insert("end", item)
        widget.pack(fill="both", expand=True, pady=4)

        def get(_i: Any, _a: list[Any], _s: Span) -> Any:
            selected = widget.curselection()
            return str(widget.get(selected[0])) if selected else None

        def items(_i: Any, _a: list[Any], _s: Span) -> list[str]:
            return [str(item) for item in widget.get(0, "end")]

        def set_items(_i: Any, values: list[Any], call_span: Span) -> None:
            new_items = _text_list(values[0], "listbox items", call_span)
            widget.delete(0, "end")
            for item in new_items:
                widget.insert("end", item)
            return None

        def add(_i: Any, values: list[Any], _s: Span) -> str:
            value = stringify(values[0])
            widget.insert("end", value)
            return value

        def remove(_i: Any, values: list[Any], call_span: Span) -> None:
            index = _whole_number(values[0], "listbox index", 0, call_span)
            widget.delete(index)
            return None

        def clear(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.delete(0, "end")
            return None

        return {
            **self._basic_control("listbox", widget),
            "get": _native("listbox.get", get, 0),
            "items": _native("listbox.items", items, 0),
            "set": _native("listbox.set", set_items, 1),
            "add": _native("listbox.add", add, 1),
            "remove": _native("listbox.remove", remove, 1),
            "clear": _native("listbox.clear", clear, 0),
        }

    def slider(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        minimum = _number(arguments[0], "slider minimum", span)
        maximum = _number(arguments[1], "slider maximum", span)
        if maximum <= minimum:
            raise OmniRuntimeError("GUI slider maximum must be greater than minimum", span)
        value = _number(arguments[2], "slider value", span) if len(arguments) == 3 else minimum
        variable = self.tk.DoubleVar(value=max(minimum, min(maximum, value)))
        widget = self.ttk.Scale(self.body, from_=minimum, to=maximum, variable=variable)
        widget.pack(fill="x", pady=4)
        return self._numeric_control("slider", widget, variable, minimum, maximum)

    def progress(self, _interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
        value = _number(arguments[0], "progress", span) if arguments else 0.0
        variable = self.tk.DoubleVar(value=max(0.0, min(100.0, value)))
        widget = self.ttk.Progressbar(self.body, maximum=100, variable=variable)
        widget.pack(fill="x", pady=4)
        return self._numeric_control("progress", widget, variable, 0.0, 100.0)

    def separator(self, _interpreter: Any, _arguments: list[Any], _span: Span) -> None:
        widget = self.ttk.Separator(self.body, orient="horizontal")
        widget.pack(fill="x", pady=8)
        return None

    def space(self, _interpreter: Any, arguments: list[Any], span: Span) -> None:
        size = _whole_number(arguments[0], "space", 0, span) if arguments else 8
        spacer = self.ttk.Frame(self.body, height=max(1, size))
        spacer.pack(pady=size // 2)
        return None

    def message(self, _interpreter: Any, arguments: list[Any], _span: Span) -> None:
        self.messagebox.showinfo(stringify(arguments[0]), stringify(arguments[1]), parent=self.root)
        return None

    def error(self, _interpreter: Any, arguments: list[Any], _span: Span) -> None:
        self.messagebox.showerror(stringify(arguments[0]), stringify(arguments[1]), parent=self.root)
        return None

    def confirm(self, _interpreter: Any, arguments: list[Any], _span: Span) -> bool:
        return bool(
            self.messagebox.askyesno(stringify(arguments[0]), stringify(arguments[1]), parent=self.root)
        )

    def open_file(self, _interpreter: Any, arguments: list[Any], _span: Span) -> Any:
        dialog = importlib.import_module("tkinter.filedialog")
        title = stringify(arguments[0]) if arguments else "Open file"
        result = str(dialog.askopenfilename(title=title, parent=self.root))
        return result or None

    def save_file(self, _interpreter: Any, arguments: list[Any], _span: Span) -> Any:
        dialog = importlib.import_module("tkinter.filedialog")
        title = stringify(arguments[0]) if arguments else "Save file"
        result = str(dialog.asksaveasfilename(title=title, parent=self.root))
        return result or None

    def choose_folder(self, _interpreter: Any, _arguments: list[Any], _span: Span) -> Any:
        dialog = importlib.import_module("tkinter.filedialog")
        result = str(dialog.askdirectory(title="Choose folder", parent=self.root))
        return result or None

    def choose_color(self, _interpreter: Any, arguments: list[Any], _span: Span) -> Any:
        chooser = importlib.import_module("tkinter.colorchooser")
        initial = stringify(arguments[0]) if arguments else "#ffffff"
        _rgb, color = chooser.askcolor(color=initial, parent=self.root)
        return str(color) if color else None

    def after(self, _interpreter: Any, arguments: list[Any], span: Span) -> None:
        milliseconds = _whole_number(arguments[0], "timer milliseconds", 0, span)
        action = arguments[1]
        if not isinstance(action, OmniCallable):
            raise OmniRuntimeError("window.after action must be a craft", span)
        self.root.after(milliseconds, lambda: self._invoke(action, span))
        return None

    def on_close(self, _interpreter: Any, arguments: list[Any], span: Span) -> None:
        action = arguments[0]
        if not isinstance(action, OmniCallable):
            raise OmniRuntimeError("window.on_close action must be a craft", span)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self._invoke(action, span))
        return None

    def themes(self, _interpreter: Any, _arguments: list[Any], _span: Span) -> list[str]:
        return [str(name) for name in self.style.theme_names()] if self.style is not None else []

    def theme(self, _interpreter: Any, arguments: list[Any], span: Span) -> str:
        if self.style is None:
            raise OmniRuntimeError("GUI themes are unavailable on this host", span)
        name = stringify(arguments[0])
        available = [str(item) for item in self.style.theme_names()]
        if name not in available:
            raise OmniRuntimeError(f"unknown GUI theme '{name}'; choose from {available}", span)
        self.style.theme_use(name)
        return name

    def set_title(self, _interpreter: Any, arguments: list[Any], _span: Span) -> None:
        self.root.title(stringify(arguments[0]))
        return None

    def set_size(self, _interpreter: Any, arguments: list[Any], span: Span) -> None:
        width = _dimension(arguments[0], "width", span)
        height = _dimension(arguments[1], "height", span)
        self.root.geometry(f"{width}x{height}")
        return None

    def close(self, _interpreter: Any, _arguments: list[Any], _span: Span) -> None:
        self.root.destroy()
        return None

    def run(self, _interpreter: Any, _arguments: list[Any], _span: Span) -> None:
        self.root.mainloop()
        if self.pending_error is not None:
            raise self.pending_error
        return None

    def _invoke(self, action: OmniCallable, span: Span) -> None:
        try:
            self.interpreter.call_value(action, [], span)
        except OmniError as error:
            self.pending_error = error
            self.root.after_idle(self.root.quit)
        except Exception as error:
            self.pending_error = OmniRuntimeError(f"GUI event failed: {error}", span)
            self.root.after_idle(self.root.quit)

    def _basic_control(self, name: str, widget: Any) -> dict[str, Any]:
        def enable(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.configure(state="normal")
            return None

        def disable(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.configure(state="disabled")
            return None

        def focus(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.focus_set()
            return None

        def hide(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.pack_forget()
            return None

        def show(_i: Any, _a: list[Any], _s: Span) -> None:
            widget.pack(fill="x", pady=4)
            return None

        return {
            "enable": _native(f"{name}.enable", enable, 0),
            "disable": _native(f"{name}.disable", disable, 0),
            "focus": _native(f"{name}.focus", focus, 0),
            "hide": _native(f"{name}.hide", hide, 0),
            "show": _native(f"{name}.show", show, 0),
        }

    def _value_control(
        self,
        name: str,
        widget: Any,
        variable: Any,
        *,
        boolean: bool = False,
    ) -> dict[str, Any]:
        def get(_i: Any, _a: list[Any], _s: Span) -> Any:
            return bool(variable.get()) if boolean else str(variable.get())

        def set_value(_i: Any, values: list[Any], _s: Span) -> Any:
            value = truthy(values[0]) if boolean else stringify(values[0])
            variable.set(value)
            return value

        return {
            **self._basic_control(name, widget),
            "get": _native(f"{name}.get", get, 0),
            "set": _native(f"{name}.set", set_value, 1),
        }

    def _numeric_control(
        self,
        name: str,
        widget: Any,
        variable: Any,
        minimum: float,
        maximum: float,
    ) -> dict[str, Any]:
        def get(_i: Any, _a: list[Any], _s: Span) -> float:
            return float(variable.get())

        def set_value(_i: Any, values: list[Any], span: Span) -> float:
            value = _number(values[0], name, span)
            if not minimum <= value <= maximum:
                raise OmniRuntimeError(
                    f"GUI {name} value must be between {minimum:g} and {maximum:g}", span
                )
            variable.set(value)
            return value

        return {
            **self._basic_control(name, widget),
            "get": _native(f"{name}.get", get, 0),
            "set": _native(f"{name}.set", set_value, 1),
        }
