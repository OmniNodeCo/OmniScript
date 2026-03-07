TT_INT       = "INT"
TT_FLOAT     = "FLOAT"
TT_STRING    = "STRING"
TT_BOOL      = "BOOL"
TT_IDENTIFIER = "IDENTIFIER"

TT_PLUS      = "PLUS"
TT_MINUS     = "MINUS"
TT_MUL       = "MUL"
TT_DIV       = "DIV"
TT_MOD       = "MOD"
TT_ASSIGN    = "ASSIGN"
TT_EQ        = "EQ"
TT_NEQ       = "NEQ"
TT_LT        = "LT"
TT_GT        = "GT"
TT_LTE       = "LTE"
TT_GTE       = "GTE"
TT_AND       = "AND"
TT_OR        = "OR"
TT_NOT       = "NOT"
TT_DOTDOT    = "DOTDOT"

TT_LPAREN    = "LPAREN"
TT_RPAREN    = "RPAREN"
TT_LBRACE    = "LBRACE"
TT_RBRACE    = "RBRACE"
TT_LBRACKET  = "LBRACKET"
TT_RBRACKET  = "RBRACKET"
TT_COMMA     = "COMMA"
TT_NEWLINE   = "NEWLINE"
TT_EOF       = "EOF"

TT_LET       = "LET"
TT_FUNC      = "FUNC"
TT_IF        = "IF"
TT_ELIF      = "ELIF"
TT_ELSE      = "ELSE"
TT_WHILE     = "WHILE"
TT_LOOP      = "LOOP"
TT_IN        = "IN"
TT_RETURN    = "RETURN"
TT_SHOW      = "SHOW"
TT_INPUT     = "INPUT"

KEYWORDS = {
    "let":    TT_LET,
    "func":   TT_FUNC,
    "if":     TT_IF,
    "elif":   TT_ELIF,
    "else":   TT_ELSE,
    "while":  TT_WHILE,
    "loop":   TT_LOOP,
    "in":     TT_IN,
    "return": TT_RETURN,
    "show":   TT_SHOW,
    "input":  TT_INPUT,
    "true":   TT_BOOL,
    "false":  TT_BOOL,
    "and":    TT_AND,
    "or":     TT_OR,
    "not":    TT_NOT,
}


class Token:
    def __init__(self, type_, value, line=0, col=0):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, ln={self.line})"