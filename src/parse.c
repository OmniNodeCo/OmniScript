/* The parser: tokens to trees. */
#include "omni.h"

#include <stdio.h>
#include <string.h>

typedef struct {
    Token *toks;
    const char *src, *name;
    int idx;
    Arena *a;
    char *err;
    int *eline, *ecol;
} Parser;

static Token *peek(Parser *p) {
    return &p->toks[p->idx];
}

static Token *take(Parser *p) {
    return &p->toks[p->idx++];
}

static int failed(Parser *p) {
    return p->err[0] != '\0';
}

static Node *fail(Parser *p, const char *msg, Token *t) {
    if (!failed(p)) {
        snprintf(p->err, 512, "%s", msg);
        *p->eline = t->line;
        *p->ecol = t->col;
    }
    return NULL;
}

static Token *expect(Parser *p, TokKind kind, const char *what) {
    Token *t = peek(p);
    if (t->kind != kind) {
        char msg[256];
        if (t->kind == T_END)
            snprintf(msg, sizeof(msg), "expected %s, found the end", what);
        else
            snprintf(msg, sizeof(msg), "expected %s, found '%s'", what, t->text);
        fail(p, msg, t);
        return NULL;
    }
    return take(p);
}

static Node *new_node(Parser *p, NodeKind kind) {
    Node *n = arena_alloc(p->a, sizeof(Node));
    memset(n, 0, sizeof(Node));
    n->kind = kind;
    return n;
}

static void node_arg(Parser *p, Node *n, Node *arg) {
    int cap = 0, i;
    Node **na;
    for (i = 0; i < n->nargs; i++)
        ;
    cap = 4;
    while (cap <= n->nargs)
        cap *= 2;
    /* Arena memory cannot grow in place, so reallocate and copy. */
    na = arena_alloc(p->a, sizeof(Node *) * (size_t)cap);
    for (i = 0; i < n->nargs; i++)
        na[i] = n->args[i];
    n->args = na;
    n->args[n->nargs++] = arg;
}

static Node *statement(Parser *p);
static Node *call(Parser *p);
static Node *argument(Parser *p);

static Node *import_statement(Parser *p) {
    Token *kw = take(p);
    Node *n = new_node(p, ND_IMPORT);
    ImportItem *items = NULL;
    int len = 0, cap = 0;
    n->line = kw->line;
    n->col = kw->col;
    for (;;) {
        Token *mod = expect(p, T_NAME, "something to import");
        Token *as;
        ImportItem *ni;
        char *alias;
        int i;
        if (!mod)
            return NULL;
        alias = mod->text;
        {
            const char *dot = strchr(mod->text, '.');
            if (dot) {
                /* `import os.path` binds `os`, like Python. */
                alias = arena_dupn(p->a, mod->text, (size_t)(dot - mod->text));
            }
        }
        if (peek(p)->kind == T_NAME && strcmp(peek(p)->text, "as") == 0) {
            take(p);
            as = expect(p, T_NAME, "a name after 'as'");
            if (!as)
                return NULL;
            alias = as->text;
        }
        if (len == cap) {
            cap = cap ? cap * 2 : 4;
            ni = arena_alloc(p->a, sizeof(ImportItem) * (size_t)cap);
            for (i = 0; i < len; i++)
                ni[i] = items[i];
            items = ni;
        }
        items[len].a = mod->text;
        items[len].b = alias;
        len++;
        if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ",") == 0) {
            take(p);
            continue;
        }
        break;
    }
    n->imports = items;
    n->nimports = len;
    return n;
}

static Node *from_statement(Parser *p) {
    Token *kw = take(p);
    Token *base = expect(p, T_NAME, "a module after 'from'");
    Token *third;
    Node *n;
    ImportItem *items = NULL;
    int len = 0, cap = 0;
    int paren = 0;
    if (!base)
        return NULL;
    third = peek(p);
    if (third->kind != T_NAME || strcmp(third->text, "import") != 0) {
        char msg[256];
        snprintf(msg, sizeof(msg), "expected 'import' after 'from %s'", base->text);
        return fail(p, msg, third);
    }
    take(p);
    n = new_node(p, ND_FROMIMPORT);
    n->line = kw->line;
    n->col = kw->col;
    n->from_base = base->text;
    if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, "(") == 0) {
        take(p);
        paren = 1;
    }
    if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, "*") == 0) {
        take(p);
        items = arena_alloc(p->a, sizeof(ImportItem));
        items[0].a = "*";
        items[0].b = "*";
        len = 1;
    } else {
        for (;;) {
            Token *found = expect(p, T_NAME, "something to import");
            ImportItem *ni;
            int i;
            char *alias;
            if (!found)
                return NULL;
            alias = found->text;
            if (peek(p)->kind == T_NAME && strcmp(peek(p)->text, "as") == 0) {
                Token *as;
                take(p);
                as = expect(p, T_NAME, "a name after 'as'");
                if (!as)
                    return NULL;
                alias = as->text;
            }
            if (len == cap) {
                cap = cap ? cap * 2 : 4;
                ni = arena_alloc(p->a, sizeof(ImportItem) * (size_t)cap);
                for (i = 0; i < len; i++)
                    ni[i] = items[i];
                items = ni;
            }
            items[len].a = found->text;
            items[len].b = alias;
            len++;
            if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ",") == 0) {
                take(p);
                if (paren && peek(p)->kind == T_PUNCT &&
                    strcmp(peek(p)->text, ")") == 0)
                    break;
                continue;
            }
            break;
        }
        if (failed(p))
            return NULL;
    }
    if (paren) {
        Token *closing = peek(p);
        if (closing->kind != T_PUNCT || strcmp(closing->text, ")") != 0)
            return fail(p, "'(' after import is never closed", closing);
        take(p);
    }
    n->imports = items;
    n->nimports = len;
    return n;
}

static Node *call(Parser *p) {
    Token *name = expect(p, T_NAME, "a command");
    Token *opener;
    Node *n;
    if (!name)
        return NULL;
    opener = expect(p, T_PUNCT, "'('");
    if (!opener)
        return NULL;
    if (strcmp(opener->text, "(") != 0) {
        char msg[256];
        snprintf(msg, sizeof(msg), "expected '(' after %s", name->text);
        return fail(p, msg, opener);
    }
    n = new_node(p, ND_CALL);
    n->text = name->text;
    n->line = name->line;
    n->col = name->col;
    if (!(peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ")") == 0)) {
        Node *arg = argument(p);
        if (!arg)
            return NULL;
        node_arg(p, n, arg);
        while (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ",") == 0) {
            take(p);
            if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ")") == 0)
                break;
            arg = argument(p);
            if (!arg)
                return NULL;
            node_arg(p, n, arg);
        }
    }
    {
        Token *closing = peek(p);
        if (closing->kind != T_PUNCT || strcmp(closing->text, ")") != 0) {
            char msg[256];
            snprintf(msg, sizeof(msg), "'(' after %s is never closed", name->text);
            return fail(p, msg, closing);
        }
        take(p);
    }
    return n;
}

/* A bare "(...)" in value position: a pair (or trio, or more) of values. */
static Node *group(Parser *p) {
    Token *opener = take(p);
    Node *n;
    int commas = 0, i;
    if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ")") == 0) {
        take(p);
        n = new_node(p, ND_TUPLE);
        n->line = opener->line;
        n->col = opener->col;
        return n;
    }
    n = new_node(p, ND_TUPLE);
    n->line = opener->line;
    n->col = opener->col;
    for (;;) {
        Node *el = argument(p);
        if (!el)
            return NULL;
        node_arg(p, n, el);
        if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ",") == 0) {
            take(p);
            commas++;
            if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, ")") == 0)
                break;
            continue;
        }
        break;
    }
    {
        Token *closing = peek(p);
        if (closing->kind != T_PUNCT || strcmp(closing->text, ")") != 0)
            return fail(p, "this '(' is never closed", closing);
        take(p);
    }
    for (i = 0; i < n->nargs; i++) {
        if (n->args[i]->kind == ND_KWARG) {
            Node *bad = n->args[i];
            if (!failed(p)) {
                snprintf(p->err, 512, "a keyword cannot go inside (...)");
                *p->eline = bad->line;
                *p->ecol = bad->col;
            }
            return NULL;
        }
    }
    if (n->nargs == 1 && !commas)
        return n->args[0];
    return n;
}

static Node *argument(Parser *p) {
    Token *t = peek(p);
    if (t->kind == T_PUNCT && strcmp(t->text, "(") == 0)
        return group(p);
    if (t->kind == T_NUMBER) {
        Node *n;
        take(p);
        n = new_node(p, ND_NUM);
        n->num = t->num;
        n->is_int = strchr(t->text, '.') == NULL;
        n->line = t->line;
        n->col = t->col;
        return n;
    }
    if (t->kind == T_STRING) {
        Node *n;
        take(p);
        n = new_node(p, ND_STR);
        n->text = t->text;
        n->line = t->line;
        n->col = t->col;
        return n;
    }
    if (t->kind == T_NAME) {
        Token *next = &p->toks[p->idx + 1];
        if (next->kind == T_PUNCT && strcmp(next->text, "=") == 0) {
            Token *key = take(p);
            Node *val;
            Node *n;
            take(p);
            val = argument(p);
            if (!val)
                return NULL;
            if (val->kind == ND_KWARG)
                return fail(p, "a keyword value cannot be another keyword", key);
            n = new_node(p, ND_KWARG);
            n->text = key->text;
            node_arg(p, n, val);
            n->line = key->line;
            n->col = key->col;
            return n;
        }
        take(p);
        if (peek(p)->kind == T_PUNCT && strcmp(peek(p)->text, "(") == 0) {
            p->idx--;
            return call(p);
        } else {
            Node *n = new_node(p, ND_WORD);
            n->text = t->text;
            n->line = t->line;
            n->col = t->col;
            return n;
        }
    }
    return fail(p, "expected a number, a string, a word or a command", t);
}

static Node *statement(Parser *p) {
    Token *t = peek(p);
    if (t->kind == T_NAME && strcmp(t->text, "import") == 0)
        return import_statement(p);
    if (t->kind == T_NAME && strcmp(t->text, "from") == 0)
        return from_statement(p);
    return call(p);
}

Node **parse_program(Arena *a, Token *toks, const char *src, const char *name,
                     int *nstatements, char *err, int *eline, int *ecol) {
    Parser p;
    Node **out = NULL;
    int len = 0, cap = 0;
    p.toks = toks;
    p.src = src;
    p.name = name;
    p.idx = 0;
    p.a = a;
    p.err = err;
    p.eline = eline;
    p.ecol = ecol;
    err[0] = '\0';
    while (peek(&p)->kind != T_END) {
        Node *st = statement(&p);
        Node **no;
        int i;
        if (!st)
            return NULL;
        if (len == cap) {
            cap = cap ? cap * 2 : 16;
            no = arena_alloc(a, sizeof(Node *) * (size_t)cap);
            for (i = 0; i < len; i++)
                no[i] = out[i];
            out = no;
        }
        out[len++] = st;
    }
    *nstatements = len;
    return out;
}
