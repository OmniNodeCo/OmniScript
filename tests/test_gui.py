from __future__ import annotations

import unittest
from unittest.mock import patch

from omniscript.api import OmniEngine


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.state = "normal"
        self.command = kwargs.get("command")

    def pack(self, **_kwargs):
        return None

    def pack_forget(self):
        return None

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def focus_set(self):
        return None


class FakeText(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(*_args, **kwargs)
        self.value = ""

    def insert(self, _start, value):
        self.value = str(value)

    def delete(self, _start, _end):
        self.value = ""

    def get(self, _start, _end):
        return self.value


class FakeListbox(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(*_args, **kwargs)
        self.values = []

    def insert(self, index, value):
        self.values.append(str(value))

    def delete(self, start, end=None):
        if end == "end":
            self.values.clear()
        elif self.values:
            del self.values[int(start)]

    def get(self, start, end=None):
        if end == "end":
            return tuple(self.values[int(start) :])
        return self.values[int(start)]

    def curselection(self):
        return ()


class FakeStyle:
    def __init__(self):
        self.selected = "default"

    def configure(self, *_args, **_kwargs):
        return None

    def theme_names(self):
        return ("default", "friendly")

    def theme_use(self, name):
        self.selected = name


class FakeRoot(FakeWidget):
    def title(self, _value):
        return None

    def geometry(self, _value):
        return None

    def minsize(self, _width, _height):
        return None

    def mainloop(self):
        return None

    def destroy(self):
        return None

    def after_idle(self, action):
        action()

    def after(self, _milliseconds, action):
        action()

    def protocol(self, _name, action):
        self.close_action = action

    def quit(self):
        return None


class FakeTk:
    Tk = FakeRoot
    StringVar = FakeVariable
    BooleanVar = FakeVariable
    DoubleVar = FakeVariable
    Text = FakeText
    Listbox = FakeListbox


class FakeTtk:
    Frame = FakeWidget
    Label = FakeWidget
    Entry = FakeWidget
    Button = FakeWidget
    Checkbutton = FakeWidget
    Combobox = FakeWidget
    Scale = FakeWidget
    Progressbar = FakeWidget
    Separator = FakeWidget
    Style = FakeStyle


class FakeMessageBox:
    @staticmethod
    def showinfo(*_args, **_kwargs):
        return None

    @staticmethod
    def showerror(*_args, **_kwargs):
        return None

    @staticmethod
    def askyesno(*_args, **_kwargs):
        return True


class GuiTests(unittest.TestCase):
    def test_simple_gui_api_without_a_real_display(self) -> None:
        source = """
use "gui"
seal window := gui.window("Test", 400, 240)
seal title := window.heading("Editor")
seal label := window.label("Name")
seal status := window.status("Ready")
seal name := window.input("Ada")
seal accepted := window.checkbox("Ready", true)
seal notes := window.textbox("Hello", 5)
seal choice := window.dropdown(["One", "Two"], "Two")
seal items := window.listbox(["A", "B"])
seal level := window.slider(0, 10, 4)
seal progress := window.progress(25)
craft save() { return notes.get() }
seal save_button := window.button("Save", save)
assert name.get() == "Ada"
name.set("Lin")
assert name.get() == "Lin"
assert accepted.get()
assert notes.get() == "Hello"
assert choice.get() == "Two"
choice.set_options(["New", "Other"])
assert choice.get() == "New"
assert items.items() == ["A", "B"]
items.add("C")
items.remove(1)
assert items.items() == ["A", "C"]
assert level.get() == 4
level.set(8)
progress.set(75)
assert progress.get() == 75
title.hide()
title.show()
label.disable()
label.enable()
name.focus()
window.separator()
window.space(10)
assert "default" in window.themes()
window.theme("friendly")
window.after(0, save)
window.on_close(save)
assert window.confirm("Question", "Continue?")
window.message("Done", "Saved")
status.set("Complete")
window.run()
"""
        with patch("omniscript.gui._load_toolkit", return_value=(FakeTk, FakeTtk, FakeMessageBox)):
            OmniEngine().run(source)


if __name__ == "__main__":
    unittest.main()
