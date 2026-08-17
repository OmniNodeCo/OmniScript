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
        except Exception as error:
            raise OmniRuntimeError(
                f"could not open a GUI window: {error}",
                span,
                "desktop windows require a graphical session; GUI code cannot run on a headless server",
            ) from error

    def public_api(self) -> dict[str, Any]:
        return {
            "label": _native("window.label", self.label, 1),
            "input": _native("window.input", self.input, 0, 1),
            "button": _native("window.button", self.button, 2),
            "checkbox": _native("window.checkbox", self.checkbox, 1, 2),
            "textbox": _native("window.textbox", self.textbox, 0, 2),
            "space": _native("window.space", self.space, 0, 1),
            "message": _native("window.message", self.message, 2),
            "error": _native("window.error", self.error, 2),
            "confirm": _native("window.confirm", self.confirm, 2),
            "set_title": _native("window.set_title", self.set_title, 1),
            "set_size": _native("window.set_size", self.set_size, 2),
            "close": _native("window.close", self.close, 0),
            "run": _native("window.run", self.run, 0),
        }

    def label(self, _interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
        variable = self.tk.StringVar(value=stringify(arguments[0]))
        widget = self.ttk.Label(self.body, textvariable=variable)
        widget.pack(anchor="w", pady=4)
        return self._value_control("label", widget, variable)

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

        return {
            "enable": _native(f"{name}.enable", enable, 0),
            "disable": _native(f"{name}.disable", disable, 0),
            "focus": _native(f"{name}.focus", focus, 0),
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
