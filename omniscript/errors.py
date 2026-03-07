class OmniError(Exception):
    def __init__(self, message, line=None):
        self.message = message
        self.line = line
        super().__init__(self.format())

    def format(self):
        loc = f" [line {self.line}]" if self.line else ""
        return f"OmniError{loc}: {self.message}"


class OmniSyntaxError(OmniError):
    def format(self):
        loc = f" [line {self.line}]" if self.line else ""
        return f"SyntaxError{loc}: {self.message}"


class OmniRuntimeError(OmniError):
    def format(self):
        loc = f" [line {self.line}]" if self.line else ""
        return f"RuntimeError{loc}: {self.message}"


class OmniReturnSignal(Exception):
    def __init__(self, value):
        self.value = value